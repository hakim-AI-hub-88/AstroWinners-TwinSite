"""Single Python worker: lease + heartbeat, real phase events P10–P90,
retries only for transient failures, cancellation at phase boundaries, and an
atomic fenced commit of result + release evidence + report.
"""
import json
import logging
import re
import secrets
import socket
import sqlite3
import threading
import time

from twinsite.storage import BlobStore, LeaseLost, Store, load_settings

from . import evidence as evidence_mod
from . import report as report_mod
from . import science_adapter
from .contract import ContractError, validate

log = logging.getLogger('twinsite.jobs')


class TransientError(RuntimeError):
    """Raise from adapters for failures worth retrying (network, lock, timeout)."""


TRANSIENT = (TransientError, sqlite3.OperationalError, TimeoutError, ConnectionError)
PERMANENT_INPUT = (ValueError, KeyError, TypeError, ContractError)

# Engine stage -> list of (phase, public status, event state, summary). Stage
# names follow the ARES engine callback; C2's engine is expected to reuse them.
# The C2 engine cleans, checks, characterizes, compares and optimizes inside one
# deterministic call, so phases P30-P70 are recorded as running before the call and
# succeeded after it returns. Run status only moves forward.
ENGINE_STAGES = {
    'P30_CLEAN': [('P30', 'cleaning', 'running',
                   'Engine running: cleaning, QA, characterization, comparison and optimization execute in one deterministic call.')],
    'P40_QUALITY': [],
    'P60_ANALYZE': [('P30', 'cleaning', 'succeeded', 'Engine: input observations normalized and cleaned.'),
                    ('P40', 'validating', 'succeeded', 'Engine: unit/coverage quality checks complete.'),
                    ('P50', 'characterizing', 'succeeded', 'Engine: Earth candidate sites characterized and scored.'),
                    ('P60', 'analyzing', 'succeeded', 'Engine: analogue comparison complete.')],
    'P70_PORTFOLIO': [('P70', 'optimizing', 'succeeded', 'Engine: portfolio optimization and weight-sensitivity scenarios complete.')],
    'P80_REVIEW': [('P80', 'reviewing', 'running', 'Engine finished; building release-evidence sidecar.')],
}

_PATH = re.compile(r'(?:[A-Za-z]:)?(?:/[\w.\-~ ]+){2,}')


def public_message(error):
    text = error.__class__.__name__ + ': operation failed; inspect protected diagnostics'
    text = _PATH.sub('<path>', text)
    return text.replace('\n', ' ')[:300]


class _Heartbeat(threading.Thread):
    def __init__(self, store, run, lease_seconds):
        super().__init__(daemon=True)
        self.store, self.run_, self.lease = store, run, lease_seconds
        self.stop_event = threading.Event()
        self.lost = False

    def run(self):
        while not self.stop_event.wait(max(1.0, self.lease / 3)):
            try:
                self.store.heartbeat(self.run_, self.lease)
            except LeaseLost:
                self.lost = True
                return
            except sqlite3.OperationalError:
                continue


class Worker:
    def __init__(self, settings=None, worker_id=None, engine_loader=None, poll_seconds=0.25, retry_base_seconds=2.0):
        self.settings = settings or load_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.settings.db_path, self.settings.queue_limit, self.settings.max_attempts)
        self.blobs = BlobStore(self.settings.artifact_root)
        self.worker_id = worker_id or f'{socket.gethostname()}-{secrets.token_hex(4)}'
        self.engine_loader = engine_loader or science_adapter.load_engine
        self.poll_seconds = poll_seconds
        self.retry_base_seconds = retry_base_seconds
        self.stop_event = threading.Event()

    # ------------------------------------------------------------ loop
    def run_once(self):
        run = self.store.claim(self.worker_id, self.settings.lease_seconds)
        if run is None:
            return False
        heartbeat = _Heartbeat(self.store, run, self.settings.lease_seconds)
        heartbeat.start()
        try:
            self._execute(run)
        finally:
            heartbeat.stop_event.set()
            heartbeat.join(timeout=5)
        return True

    def run_forever(self):
        log.info('worker %s started; db=%s', self.worker_id, self.settings.db_path.name)
        while not self.stop_event.is_set():
            try:
                worked = self.run_once()
            except sqlite3.OperationalError as error:
                log.warning('store busy: %s', error)
                worked = False
            if not worked:
                self.stop_event.wait(self.poll_seconds)

    # ------------------------------------------------------------ one run
    def _advance(self, run, status, phase, state, summary, task, completed=0, total=None, **kw):
        return self.store.advance(run, status, phase, state, summary, task, completed, total,
                                  lease_seconds=self.settings.lease_seconds, **kw)

    def _execute(self, run):
        try:
            self._pipeline(run)
        except LeaseLost as error:
            if str(error) == 'cancel_requested' and self.store.acknowledge_cancel(run):
                log.info('run %s cancelled', run['run_id'])
            else:
                log.warning('run %s: lease lost (%s); another attempt owns it', run['run_id'], error)
        except TRANSIENT as error:
            log.warning('run %s transient failure', run['run_id'], exc_info=True)
            delay = self.retry_base_seconds * 2 ** (run['attempt'] - 1)
            self._safe(lambda: self.store.retry_or_fail(run, 'TRANSIENT_' + error.__class__.__name__.upper(),
                                                        public_message(error), delay))
        except science_adapter.ScienceUnavailable as error:
            log.error('run %s: science engine unavailable', run['run_id'], exc_info=True)
            self._safe(lambda: self.store.fail(run, 'SCIENCE_ENGINE_UNAVAILABLE', public_message(error)))
        except PERMANENT_INPUT as error:
            # Public status stays redacted; full diagnostics go to the protected service log only.
            log.warning('run %s rejected as invalid mission', run['run_id'], exc_info=True)
            self._safe(lambda: self.store.fail(run, 'INVALID_MISSION', public_message(error)))
        except Exception as error:  # noqa: BLE001 — permanent: never retried
            log.error('run %s failed (%s)', run['run_id'], error.__class__.__name__, exc_info=True)
            self._safe(lambda: self.store.fail(run, 'INTERNAL_ERROR', error.__class__.__name__))

    @staticmethod
    def _safe(action):
        try:
            return action()
        except LeaseLost:
            return None

    def _pipeline(self, run):
        payload = run['payload']
        pair = None
        if payload.get('data_status') == 'measured':
            from .measured import evidence_for
            pair = evidence_for(payload)
        snapshot_id = pair['source_snapshot_id'] if pair else evidence_mod.snapshot([])[0]
        count = len(pair['assets']) if pair else 0
        self._advance(run, 'acquiring', 'P10', 'succeeded',
                      'Resolved published measured evidence; no new network acquisition.' if pair else
                      'Inline SYNTHETIC observations; no source assets fetched.',
                      'acquire', count, count, source_snapshot_id=snapshot_id)
        self._advance(run, 'decoding', 'P20', 'succeeded',
                      'Loaded published features with product lineage.' if pair else 'No source products to decode.',
                      'decode', count, count)
        engine = self.engine_loader()

        def progress(stage, completed):
            for phase, status, state, summary in ENGINE_STAGES.get(stage, []):
                self._advance(run, status, phase, state, summary, 'engine-' + phase.lower(), completed, None)

        if pair:
            from twinsite.science import analyze_mission
            from .measured import sidecar as measured_sidecar
            progress('P30_CLEAN', 0)
            progress('P40_QUALITY', 0)
            output = analyze_mission(payload, evidence=pair['observations'], mode='strict')
            result = output['result']
            for stage in ('P60_ANALYZE', 'P70_PORTFOLIO', 'P80_REVIEW'):
                progress(stage, 1)
        else:
            result = engine.analyze(payload, progress=progress)
        if result.get('input_sha256') != run['input_sha256']:
            raise ValueError('Engine input hash does not match the canonical original input')
        validate('mission_result', result)
        sidecar = measured_sidecar(run, output, pair) if pair else evidence_mod.synthetic_evidence(run['run_id'], run['input_sha256'], result, engine)
        validate('release_evidence', sidecar)
        self._advance(run, 'reviewing', 'P80', 'succeeded', 'Release-evidence sidecar built and validated against the contract.',
                      'engine-p80', 1, None)
        final_status = 'completed' if sidecar['release_action'] == 'RELEASE' else 'completed_with_limits'
        self._advance(run, 'publishing', 'P90', 'running',
                      f'Release gate: {sidecar["release_action"]} ({", ".join(sidecar["blocking_issues"]) or "no issues"}). '
                      'Rendering deterministic report.', 'publish', 0, 1)
        html = report_mod.render(run['run_id'], result, sidecar)
        artifacts = [self.blobs.put(json.dumps(result, allow_nan=False, sort_keys=True).encode('utf-8')),
                     self.blobs.put(json.dumps(sidecar, allow_nan=False, sort_keys=True).encode('utf-8')),
                     self.blobs.put(html.encode('utf-8'))]
        self.store.commit(run, result, sidecar, html, final_status, sidecar['source_snapshot_id'],
                          ['sha256:' + a for a in artifacts])
