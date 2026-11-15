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
ENGINE_STAGES = {
    'P30_CLEAN': [('P30', 'cleaning', 'running', 'Engine: normalizing and cleaning input observations.')],
    'P40_QUALITY': [('P40', 'validating', 'running', 'Engine: unit/coverage quality checks.')],
    'P60_ANALYZE': [('P50', 'characterizing', 'succeeded', 'Engine: Earth candidate sites characterized and scored.'),
                    ('P60', 'analyzing', 'running', 'Engine: portfolio analysis.')],
    'P70_PORTFOLIO': [('P70', 'optimizing', 'running', 'Engine: portfolio optimization and weight-sensitivity scenarios.')],
    'P80_REVIEW': [('P80', 'reviewing', 'running', 'Engine finished; building release-evidence sidecar.')],
}

_PATH = re.compile(r'(?:[A-Za-z]:)?(?:/[\w.\-~ ]+){2,}')


def public_message(error):
    text = str(error) or error.__class__.__name__
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
            delay = self.retry_base_seconds * 2 ** (run['attempt'] - 1)
            self._safe(lambda: self.store.retry_or_fail(run, 'TRANSIENT_' + error.__class__.__name__.upper(),
                                                        public_message(error), delay))
        except science_adapter.ScienceUnavailable as error:
            self._safe(lambda: self.store.fail(run, 'SCIENCE_ENGINE_UNAVAILABLE', public_message(error)))
        except PERMANENT_INPUT as error:
            self._safe(lambda: self.store.fail(run, 'INVALID_MISSION', public_message(error)))
        except Exception as error:  # noqa: BLE001 — permanent: never retried
            log.exception('run %s failed', run['run_id'])
            self._safe(lambda: self.store.fail(run, 'INTERNAL_ERROR', error.__class__.__name__))

    @staticmethod
    def _safe(action):
        try:
            return action()
        except LeaseLost:
            return None

    def _pipeline(self, run):
        payload = run['payload']
        if payload.get('data_status') != 'synthetic':
            # Client-asserted measurements are not science. No C1 resolver is integrated yet.
            self.store.fail(run, 'MEASURED_EVIDENCE_UNAVAILABLE',
                            'Measured runs require observations resolved from approved C1 asset manifests; '
                            'no resolver is integrated, so no measured result is published.', phase='P10')
            return
        snapshot_id, _ = evidence_mod.snapshot([])
        self._advance(run, 'acquiring', 'P10', 'succeeded',
                      'No remote acquisition: request carries inline SYNTHETIC observations; 0 source assets fetched.',
                      'acquire', 0, 0, source_snapshot_id=snapshot_id)
        self._advance(run, 'decoding', 'P20', 'succeeded', 'No source products to decode (0 assets).', 'decode', 0, 0)
        engine = self.engine_loader()

        def progress(stage, completed):
            for phase, status, state, summary in ENGINE_STAGES.get(stage, []):
                self._advance(run, status, phase, state, summary, 'engine-' + phase.lower(), completed, None)

        result = engine.analyze(payload, progress=progress)
        if result.get('input_sha256') != run['input_sha256']:
            raise ValueError('Engine input hash does not match the canonical original input')
        validate('mission_result', result)
        sidecar = evidence_mod.synthetic_evidence(run['run_id'], run['input_sha256'], result, engine)
        validate('release_evidence', sidecar)
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
