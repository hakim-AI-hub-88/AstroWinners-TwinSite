"""Persistent AI usage ledger, cooldowns, circuit breakers and response cache (SQLite).

Survives restarts (lives in the data dir). Stores env-variable NAMES and outcomes only.
Note: VESPER shares several of these accounts and its spend is invisible here, so a
provider 429 is treated as authoritative regardless of what this ledger counts.
"""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

DAY = 86_400


def _utc_day_start(now):
    return now - (now % DAY)


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY, ts REAL NOT NULL, provider TEXT, account TEXT, quota_group TEXT,
                    model TEXT, agent_id TEXT, run_id TEXT, capability TEXT, priority TEXT, outcome TEXT,
                    error_kind TEXT, http_status INTEGER, latency_ms INTEGER, input_tokens INTEGER, output_tokens INTEGER,
                    detail TEXT);
                CREATE INDEX IF NOT EXISTS usage_group_ts ON usage(quota_group, ts);
                CREATE TABLE IF NOT EXISTS breaker (
                    key TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, open_until REAL NOT NULL DEFAULT 0,
                    reason TEXT, updated REAL);
                CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, created REAL, value TEXT);
                CREATE TABLE IF NOT EXISTS facts (key TEXT PRIMARY KEY, value TEXT, updated REAL);
            """)

    @contextmanager
    def _db(self):
        with self._lock:
            db = sqlite3.connect(self.path, timeout=10)
            try:
                db.execute('PRAGMA journal_mode=WAL')
                yield db
                db.commit()
            finally:
                db.close()

    # ---------------------------------------------------------------- usage
    def record(self, **row):
        row.setdefault('ts', time.time())
        cols = ','.join(row)
        with self._db() as db:
            db.execute(f'INSERT INTO usage({cols}) VALUES({",".join("?" * len(row))})', tuple(row.values()))

    def used_today(self, quota_group, model=None, now=None):
        start = _utc_day_start(now or time.time())
        sql = "SELECT count(*) FROM usage WHERE quota_group=? AND ts>=? AND outcome IN ('success','invalid_output')"
        args = [quota_group, start]
        if model:
            sql += ' AND model=?'
            args.append(model)
        with self._db() as db:
            return db.execute(sql, args).fetchone()[0]

    def recent(self, limit=50):
        with self._db() as db:
            rows = db.execute('SELECT ts,provider,account,model,agent_id,run_id,capability,outcome,error_kind,http_status,'
                              'latency_ms,input_tokens,output_tokens FROM usage ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        keys = ('ts', 'provider', 'account', 'model', 'agent_id', 'run_id', 'capability', 'outcome', 'error_kind',
                'http_status', 'latency_ms', 'input_tokens', 'output_tokens')
        return [dict(zip(keys, r)) | {'ts': datetime.fromtimestamp(r[0], timezone.utc).isoformat()} for r in rows]

    def summary(self):
        start = _utc_day_start(time.time())
        with self._db() as db:
            rows = db.execute("""SELECT provider, outcome, count(*), max(ts) FROM usage GROUP BY provider, outcome""").fetchall()
            today = db.execute("""SELECT provider, count(*) FROM usage WHERE ts>=? AND outcome IN ('success','invalid_output')
                                  GROUP BY provider""", (start,)).fetchall()
            ok_models = db.execute("""SELECT provider, model, account, max(ts) FROM usage WHERE outcome='success'
                                      GROUP BY provider, model, account""").fetchall()
        out = {}
        for provider, outcome, count, last in rows:
            p = out.setdefault(provider, {'outcomes': {}, 'calls_today': 0, 'verified': []})
            p['outcomes'][outcome] = count
            p.setdefault('last_ts', 0)
            p['last_ts'] = max(p['last_ts'], last)
        for provider, count in today:
            out.setdefault(provider, {'outcomes': {}, 'verified': []})['calls_today'] = count
        for provider, model, account, last in ok_models:
            out.setdefault(provider, {'outcomes': {}, 'verified': [], 'calls_today': 0})['verified'].append(
                {'model': model, 'account': account, 'last_success': datetime.fromtimestamp(last, timezone.utc).isoformat()})
        return out

    # -------------------------------------------------------------- breaker
    def available(self, key, now=None):
        with self._db() as db:
            row = db.execute('SELECT open_until, reason FROM breaker WHERE key=?', (key,)).fetchone()
        if row and row[0] > (now or time.time()):
            return False, row[1]
        return True, None

    def fail(self, key, reason, cooldown):
        now = time.time()
        with self._db() as db:
            row = db.execute('SELECT failures FROM breaker WHERE key=?', (key,)).fetchone()
            failures = (row[0] if row else 0) + 1
            # Breaker opens on an explicit cooldown, or after 3 consecutive failures (exponential, max 1h).
            until = now + cooldown if cooldown else (now + min(3600, 60 * 2 ** (failures - 3)) if failures >= 3 else 0)
            db.execute('INSERT INTO breaker(key,failures,open_until,reason,updated) VALUES(?,?,?,?,?) '
                       'ON CONFLICT(key) DO UPDATE SET failures=excluded.failures, open_until=excluded.open_until, '
                       'reason=excluded.reason, updated=excluded.updated', (key, failures, until, reason[:200], now))

    def ok(self, key):
        with self._db() as db:
            db.execute('DELETE FROM breaker WHERE key=?', (key,))

    def breakers(self):
        now = time.time()
        with self._db() as db:
            rows = db.execute('SELECT key, failures, open_until, reason FROM breaker WHERE open_until>?', (now,)).fetchall()
        return [{'key': k, 'failures': f, 'open_for_s': int(u - now), 'reason': r} for k, f, u, r in rows]

    # ---------------------------------------------------------------- cache
    def cache_get(self, key, max_age=7 * DAY):
        with self._db() as db:
            row = db.execute('SELECT created, value FROM cache WHERE key=?', (key,)).fetchone()
        if row and time.time() - row[0] < max_age:
            return json.loads(row[1])
        return None

    def cache_put(self, key, value):
        with self._db() as db:
            db.execute('INSERT OR REPLACE INTO cache(key, created, value) VALUES(?,?,?)', (key, time.time(), json.dumps(value)))

    # ---------------------------------------------------------------- facts (probe results, free-tier checks)
    def fact(self, key, value=None):
        with self._db() as db:
            if value is None:
                row = db.execute('SELECT value, updated FROM facts WHERE key=?', (key,)).fetchone()
                return (json.loads(row[0]), row[1]) if row else (None, None)
            db.execute('INSERT OR REPLACE INTO facts(key,value,updated) VALUES(?,?,?)', (key, json.dumps(value), time.time()))
            return value, time.time()

    def facts(self, prefix):
        with self._db() as db:
            rows = db.execute('SELECT key, value, updated FROM facts WHERE key LIKE ?', (prefix + '%',)).fetchall()
        return {k: {'value': json.loads(v), 'updated': datetime.fromtimestamp(u, timezone.utc).isoformat()} for k, v, u in rows}
