"""Durable job queue, event log and fenced result commit on SQLite (WAL).

SQLite is the accepted demo fallback: one API process, exactly one worker
process, durable file on local disk. All writes use BEGIN IMMEDIATE so the
API threads and the worker serialize safely. A result, its release-evidence
sidecar, its HTML report and the terminal status are committed in ONE
transaction guarded by the worker's fence token (lease owner + attempt).
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import secrets
import sqlite3
import time

SCHEMA_VERSION = '1.0'
ACTIVE = ('acquiring', 'decoding', 'cleaning', 'validating', 'characterizing',
          'analyzing', 'optimizing', 'reviewing', 'publishing')
TERMINAL = ('completed', 'completed_with_limits', 'failed', 'cancelled')
COMMITTED = ('completed', 'completed_with_limits')


class Conflict(ValueError):
    """Same idempotency key, different canonical input."""


class CapacityError(RuntimeError):
    """Bounded queue is full."""


class LeaseLost(RuntimeError):
    """Worker no longer owns the run (expired, superseded or cancelled)."""


def canonical_sha256(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def dumps(value):
    return json.dumps(value, allow_nan=False, separators=(',', ':'), ensure_ascii=False)


class Store:
    def __init__(self, path, queue_limit=20, max_attempts=3):
        self.path = str(path)
        self.queue_limit = queue_limit
        self.max_attempts = max_attempts
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    idem_key TEXT UNIQUE NOT NULL,
                    input_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    data_status TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    fence TEXT,
                    lease_owner TEXT,
                    lease_expires REAL,
                    next_attempt_at REAL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    source_snapshot_id TEXT,
                    error TEXT,
                    trace_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_order INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_status ON runs(status, created_order);
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    sequence INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS run_options (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                    analysis_mode TEXT NOT NULL DEFAULT 'ai'
                );
                CREATE TABLE IF NOT EXISTS agent_traces (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS results (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
                    result TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    report TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    attempt INTEGER NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def write(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
            except BaseException:
                db.execute('ROLLBACK')
                raise
            db.execute('COMMIT')

    def ping(self):
        with self.write() as db:
            db.execute('SELECT count(*) FROM runs').fetchone()
        return True

    # ---------------------------------------------------------------- events
    @staticmethod
    def _event(db, run, phase, state, summary, task_id, completed=0, total=None, artifact_ids=(), attempt=None):
        row = db.execute('SELECT coalesce(max(sequence),0)+1 FROM events WHERE run_id=?', (run['run_id'],)).fetchone()
        sequence = row[0]
        attempt_no = run['attempt'] if attempt is None else attempt
        body = {
            'schema_version': SCHEMA_VERSION, 'mission_id': run['run_id'], 'task_id': task_id,
            'attempt_id': f'attempt-{attempt_no}', 'sequence': sequence, 'timestamp': utc_now(),
            'phase': phase, 'state': state, 'completed_units': completed, 'total_units': total,
            'summary': summary, 'trace_id': run['trace_id'], 'artifact_ids': list(artifact_ids),
        }
        db.execute('INSERT INTO events(run_id,sequence,body) VALUES(?,?,?)', (run['run_id'], sequence, dumps(body)))
        return body

    def events(self, run_id, after=0, limit=200):
        with self.connection() as db:
            rows = db.execute('SELECT body FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?',
                              (run_id, after, min(limit, 200))).fetchall()
        return [json.loads(r['body']) for r in rows]

    # ---------------------------------------------------------------- submit
    def submit(self, payload, idempotency_key, analysis_mode='ai'):
        """Return (run_id, replay). Raises Conflict or CapacityError."""
        digest = canonical_sha256(payload)
        with self.write() as db:
            old = db.execute('SELECT run_id,input_sha256 FROM runs WHERE idem_key=?', (idempotency_key,)).fetchone()
            if old:
                if old['input_sha256'] != digest:
                    raise Conflict('Idempotency-Key already belongs to a different request body')
                return old['run_id'], True
            queued = db.execute("SELECT count(*) FROM runs WHERE status='queued'").fetchone()[0]
            if queued >= self.queue_limit:
                raise CapacityError('Mission queue is full; retry later')
            now = utc_now()
            run = {'run_id': 'run-' + secrets.token_hex(12), 'trace_id': 'trace-' + secrets.token_hex(8), 'attempt': 0}
            order = db.execute('SELECT coalesce(max(created_order),0)+1 FROM runs').fetchone()[0]
            db.execute("""INSERT INTO runs(run_id,idem_key,input_sha256,payload,data_status,status,trace_id,
                          created_at,updated_at,created_order) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (run['run_id'], idempotency_key, digest, dumps(payload), str(payload.get('data_status')),
                        'queued', run['trace_id'], now, now, order))
            db.execute('INSERT INTO run_options(run_id, analysis_mode) VALUES(?,?)', (run['run_id'], analysis_mode))
            label = 'SYNTHETIC input; not NASA measurements.' if payload.get('data_status') == 'synthetic' \
                else 'Input declares measured data; evidence must be resolved from approved assets.'
            self._event(db, run, 'P00', 'queued', 'Mission accepted and queued. ' + label, 'register')
            return run['run_id'], False

    # ---------------------------------------------------------------- reads
    def get(self, run_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        return dict(row) if row else None

    def analysis_mode(self, run_id):
        with self.connection() as db:
            row = db.execute('SELECT analysis_mode FROM run_options WHERE run_id=?', (run_id,)).fetchone()
        return row[0] if row else 'simple'

    def agent_trace(self, run_id):
        with self.connection() as db:
            row = db.execute('SELECT body FROM agent_traces WHERE run_id=?', (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_agent_trace(self, run, trace):
        with self.write() as db:
            self._owned(db, run)
            db.execute('INSERT OR REPLACE INTO agent_traces(run_id, body, created_at) VALUES(?,?,?)',
                       (run['run_id'], dumps(trace), utc_now()))

    def note(self, run, phase, state, summary, task_id, lease_seconds=30):
        """Fenced event without a status change (agent activity)."""
        with self.write() as db:
            self._owned(db, run)
            db.execute('UPDATE runs SET lease_expires=? WHERE run_id=?', (time.time() + lease_seconds, run['run_id']))
            return self._event(db, run, phase, state, summary, task_id)

    def committed(self, run_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM results WHERE run_id=?', (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, limit=50):
        with self.connection() as db:
            rows = db.execute('SELECT run_id,status,attempt,created_at FROM runs ORDER BY created_order DESC LIMIT ?',
                              (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- worker side
    def claim(self, worker_id, lease_seconds=30):
        """Claim the oldest runnable run. One active mission at a time."""
        now = time.time()
        with self.write() as db:
            # Recover expired leases: retry while attempts remain, else fail.
            placeholders = ','.join('?' * len(ACTIVE))
            expired = db.execute(f'SELECT * FROM runs WHERE status IN ({placeholders}) AND lease_expires<?',
                                 (*ACTIVE, now)).fetchall()
            for row in expired:
                run = dict(row)
                if run['cancel_requested']:
                    self._terminal(db, run, 'cancelled', None, 'P90', 'cancelled', 'Cancelled after worker lease expired.')
                elif run['attempt'] >= self.max_attempts:
                    self._terminal(db, run, 'failed', 'WORKER_LEASE_EXPIRED: attempt budget exhausted',
                                   'P90', 'failed', 'Worker lease expired and attempt budget is exhausted.')
                else:
                    db.execute("UPDATE runs SET status='queued',fence=NULL,lease_owner=NULL,lease_expires=NULL,"
                               "next_attempt_at=?,updated_at=? WHERE run_id=?", (now, utc_now(), run['run_id']))
                    self._event(db, run, 'P00', 'retry_wait', 'Worker lease expired; run re-queued for another attempt.', 'lease')
            active = db.execute(f'SELECT count(*) FROM runs WHERE status IN ({placeholders})', ACTIVE).fetchone()[0]
            if active:
                return None
            row = db.execute("""SELECT * FROM runs WHERE status='queued' AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                                ORDER BY created_order LIMIT 1""", (now,)).fetchone()
            if row is None:
                return None
            run = dict(row)
            run['attempt'] += 1
            run['fence'] = secrets.token_hex(16)
            db.execute("""UPDATE runs SET status='acquiring',attempt=?,fence=?,lease_owner=?,lease_expires=?,
                          next_attempt_at=NULL,updated_at=? WHERE run_id=?""",
                       (run['attempt'], run['fence'], worker_id, now + lease_seconds, utc_now(), run['run_id']))
            self._event(db, run, 'P10', 'running', f'Attempt {run["attempt"]} of {self.max_attempts} claimed by worker.', 'acquire')
            run['status'] = 'acquiring'
            run['payload'] = json.loads(run['payload'])
            return run

    def _owned(self, db, run, allow_cancel=False):
        row = db.execute('SELECT * FROM runs WHERE run_id=?', (run['run_id'],)).fetchone()
        if row is None or row['fence'] != run['fence'] or row['status'] not in ACTIVE or row['lease_expires'] < time.time():
            raise LeaseLost('Run lease expired or superseded')
        if row['cancel_requested'] and not allow_cancel:
            raise LeaseLost('cancel_requested')
        return dict(row)

    def heartbeat(self, run, lease_seconds=30):
        with self.write() as db:
            current = self._owned(db, run, allow_cancel=True)
            db.execute('UPDATE runs SET lease_expires=? WHERE run_id=?', (time.time() + lease_seconds, run['run_id']))
            return bool(current['cancel_requested'])

    def cancel_requested(self, run_id):
        with self.connection() as db:
            row = db.execute('SELECT cancel_requested FROM runs WHERE run_id=?', (run_id,)).fetchone()
        return bool(row and row[0])

    def advance(self, run, status, phase, state, summary, task_id, completed=0, total=None,
                source_snapshot_id=None, lease_seconds=30, artifact_ids=()):
        """Fenced phase transition + event. Raises LeaseLost (incl. pending cancel)."""
        with self.write() as db:
            self._owned(db, run)
            db.execute("""UPDATE runs SET status=?,lease_expires=?,updated_at=?,
                          source_snapshot_id=coalesce(?,source_snapshot_id) WHERE run_id=?""",
                       (status, time.time() + lease_seconds, utc_now(), source_snapshot_id, run['run_id']))
            run['status'] = status
            return self._event(db, run, phase, state, summary, task_id, completed, total, artifact_ids)

    def _terminal(self, db, run, status, error, phase, state, summary, completed=0, total=None, artifact_ids=()):
        db.execute("""UPDATE runs SET status=?,error=?,fence=NULL,lease_owner=NULL,lease_expires=NULL,
                      next_attempt_at=NULL,updated_at=? WHERE run_id=?""", (status, error, utc_now(), run['run_id']))
        return self._event(db, run, phase, state, summary, 'finalize', completed, total, artifact_ids)

    def retry_or_fail(self, run, error_code, public_message, delay_seconds):
        """Transient failure: re-queue with backoff while attempts remain."""
        with self.write() as db:
            current = self._owned(db, run, allow_cancel=True)
            if current['cancel_requested']:
                self._terminal(db, run, 'cancelled', None, 'P90', 'cancelled', 'Cancelled at user request.')
                return 'cancelled'
            if current['attempt'] >= self.max_attempts:
                self._terminal(db, run, 'failed', f'{error_code}: {public_message}', 'P90', 'failed',
                               f'Transient failure; attempt budget exhausted ({error_code}).')
                return 'failed'
            db.execute("""UPDATE runs SET status='queued',fence=NULL,lease_owner=NULL,lease_expires=NULL,
                          next_attempt_at=?,error=NULL,updated_at=? WHERE run_id=?""",
                       (time.time() + delay_seconds, utc_now(), run['run_id']))
            self._event(db, run, 'P00', 'retry_wait',
                        f'Transient failure ({error_code}); retry scheduled in {delay_seconds:g}s.', 'retry')
            return 'queued'

    def fail(self, run, error_code, public_message, phase='P90'):
        with self.write() as db:
            current = self._owned(db, run, allow_cancel=True)
            if current['cancel_requested']:
                self._terminal(db, run, 'cancelled', None, phase, 'cancelled', 'Cancelled at user request.')
                return 'cancelled'
            self._terminal(db, run, 'failed', f'{error_code}: {public_message}', phase, 'failed',
                           f'Run failed permanently ({error_code}).')
            return 'failed'

    def acknowledge_cancel(self, run):
        with self.write() as db:
            row = db.execute('SELECT * FROM runs WHERE run_id=?', (run['run_id'],)).fetchone()
            if row and row['status'] in ACTIVE and row['fence'] == run['fence']:
                self._terminal(db, run, 'cancelled', None, 'P90', 'cancelled', 'Cancelled at user request between phases.')
                return True
        return False

    def commit(self, run, result, evidence, report, final_status, source_snapshot_id, artifact_ids=()):
        """Atomic, fenced commit of result + evidence sidecar + report + terminal status."""
        if final_status not in COMMITTED:
            raise ValueError('final_status must be completed or completed_with_limits')
        result_text = dumps(result)
        with self.write() as db:
            self._owned(db, run)
            if db.execute('SELECT 1 FROM results WHERE run_id=?', (run['run_id'],)).fetchone():
                raise LeaseLost('Result already committed')
            db.execute("""INSERT INTO results(run_id,result,evidence,report,result_sha256,committed_at,attempt)
                          VALUES(?,?,?,?,?,?,?)""",
                       (run['run_id'], result_text, dumps(evidence), report,
                        hashlib.sha256(result_text.encode('utf-8')).hexdigest(), utc_now(), run['attempt']))
            db.execute('UPDATE runs SET source_snapshot_id=? WHERE run_id=?', (source_snapshot_id, run['run_id']))
            summary = (f'Result, release evidence and report committed atomically; release_action '
                       f'{evidence["release_action"]}; status {final_status}.')
            self._terminal(db, run, final_status, None, 'P90', 'succeeded', summary, 1, 1, artifact_ids)

    # ---------------------------------------------------------------- cancellation (API side)
    def request_cancel(self, run_id):
        """Return resulting status, or None if unknown."""
        with self.write() as db:
            row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if row is None:
                return None
            run = dict(row)
            if run['status'] in TERMINAL:
                return run['status']
            if run['status'] == 'queued':
                self._terminal(db, run, 'cancelled', None, 'P00', 'cancelled', 'Cancelled at user request before start.')
                return 'cancelled'
            # No event here: the worker records the actual `cancelled` event when it stops.
            db.execute('UPDATE runs SET cancel_requested=1,updated_at=? WHERE run_id=?', (utc_now(), run_id))
            return run['status']
