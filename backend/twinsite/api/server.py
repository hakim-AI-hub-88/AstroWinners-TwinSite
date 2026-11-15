"""TwinSite v1 HTTP API (stdlib ThreadingHTTPServer; zero third-party deps).

Implements the frozen G1 routes from contracts/SHARED_CONTRACT.md. Reserved G3
routes return explicit 501 until C0 approves their response schemas. No login,
no settings, no SQL surface, no AI requirement.
"""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import re
from urllib.parse import parse_qs, urlsplit

from twinsite.jobs import science_adapter
from twinsite.jobs.contract import ContractError, validate
from twinsite.storage import COMMITTED, CapacityError, Conflict, Store, load_settings

from .openapi import build_openapi

log = logging.getLogger('twinsite.api')
SCHEMA_VERSION = '1.0'
RUN = r'(?P<run_id>[A-Za-z0-9_\-]{1,128})'

ROUTES = [
    ('GET', re.compile(r'^/v1/health$'), 'health'),
    ('GET', re.compile(r'^/v1/openapi\.json$'), 'openapi'),
    ('POST', re.compile(r'^/v1/missions$'), 'submit'),
    ('POST', re.compile(r'^/v1/missions/measured$'), 'submit_measured'),
    ('GET', re.compile(rf'^/v1/missions/{RUN}$'), 'status'),
    ('GET', re.compile(rf'^/v1/missions/{RUN}/events$'), 'events'),
    ('GET', re.compile(rf'^/v1/missions/{RUN}/result$'), 'result'),
    ('GET', re.compile(rf'^/v1/missions/{RUN}/evidence$'), 'evidence'),
    ('GET', re.compile(rf'^/v1/missions/{RUN}/report$'), 'report'),
    ('POST', re.compile(rf'^/v1/missions/{RUN}/cancel$'), 'cancel'),
    ('GET', re.compile(rf'^/v1/missions/{RUN}/agents$'), 'agents'),
    ('GET', re.compile(r'^/v1/ai/status$'), 'ai_status'),
    # Reserved G3 routes: explicit 501 (contract: response schemas need C0 review first).
    ('POST', re.compile(rf'^/v1/missions/{RUN}/portfolios/alternatives$'), 'not_implemented'),
    ('GET', re.compile(r'^/v1/data/catalog$'), 'data_catalog'),
    ('GET', re.compile(r'^/v1/data/(?P<dataset_id>[A-Za-z0-9_.\-]{1,128})/records$'), 'data_records'),
    ('GET', re.compile(r'^/v1/data/(?P<dataset_id>[A-Za-z0-9_.\-]{1,128})/metadata$'), 'data_metadata'),
    ('GET', re.compile(r'^/v1/data/(?P<dataset_id>[A-Za-z0-9_.\-]{1,128})/grid$'), 'data_grid'),
    ('POST', re.compile(r'^/v1/data/compare$'), 'data_compare'),
    ('POST', re.compile(r'^/v1/uploads$'), 'uploads_disabled'),
]


class ApiError(Exception):
    def __init__(self, status, code, message, field=None, headers=None):
        super().__init__(message)
        self.status, self.code, self.message, self.field = status, code, message, field
        self.headers = headers or {}


def error_body(code, message, field=None):
    return {'schema_version': SCHEMA_VERSION, 'error': {'code': code, 'message': message, 'field': field}}


def _ai_enabled(settings):
    try:
        from twinsite.ai import ai_enabled
        return ai_enabled(settings)
    except Exception:  # noqa: BLE001 - health must not fail because of AI configuration
        return False


def _reject_constant(name):
    raise ValueError(f'Non-finite JSON number {name} is not allowed')


class App:
    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.settings.db_path, self.settings.queue_limit, self.settings.max_attempts)
        self.openapi = build_openapi()

    def status_body(self, run):
        return {'schema_version': SCHEMA_VERSION, 'run_id': run['run_id'], 'id': run['run_id'],
                'status': run['status'], 'attempt': run['attempt'], 'input_sha256': run['input_sha256'],
                'source_snapshot_id': run['source_snapshot_id'], 'error': run['error']}

    def accepted_body(self, run_id):
        return {'schema_version': SCHEMA_VERSION, 'run_id': run_id, 'id': run_id, 'status': 'queued',
                'status_url': f'/v1/missions/{run_id}'}

    def require_run(self, run_id):
        run = self.store.get(run_id)
        if run is None:
            raise ApiError(404, 'RUN_NOT_FOUND', 'Unknown run_id')
        return run

    def require_committed(self, run_id):
        run = self.require_run(run_id)
        committed = self.store.committed(run_id) if run['status'] in COMMITTED else None
        if committed is None:
            code = {'failed': 'RUN_FAILED', 'cancelled': 'RUN_CANCELLED'}.get(run['status'], 'RESULT_NOT_COMMITTED')
            raise ApiError(409, code, f'No committed result; run status is {run["status"]}')
        return committed


class Handler(BaseHTTPRequestHandler):
    server_version = 'TwinSite/1.0'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    app: App = None  # injected by make_server

    # ------------------------------------------------------------ plumbing
    def log_message(self, fmt, *args):
        log.info('HTTP %s', self.command)

    def _cors(self):
        origin = self.headers.get('Origin')
        if origin and origin in self.app.settings.cors_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Expose-Headers', 'Location, Retry-After')

    def _send(self, status, body: bytes, content_type, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if content_type.startswith('text/html'):
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self._cors()
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_json(self, status, value, headers=None):
        self._send(status, json.dumps(value, allow_nan=False, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8', headers)

    def send_raw_json(self, status, text):
        self._send(status, text.encode('utf-8'), 'application/json; charset=utf-8')

    def _dispatch(self, method):
        parts = urlsplit(self.path)
        allowed = []
        try:
            for route_method, pattern, name in ROUTES:
                match = pattern.match(parts.path)
                if not match:
                    continue
                if route_method != method:
                    allowed.append(route_method)
                    continue
                getattr(self, 'route_' + name)(parse_qs(parts.query, keep_blank_values=True), **match.groupdict())
                return
            if allowed:
                raise ApiError(405, 'METHOD_NOT_ALLOWED', 'Method not allowed', headers={'Allow': ', '.join(sorted(set(allowed)))})
            raise ApiError(404, 'NOT_FOUND', 'Unknown route')
        except ApiError as error:
            self.send_json(error.status, error_body(error.code, error.message, error.field), error.headers)
        except Exception:  # noqa: BLE001 — never leak internals
            log.error('unhandled HTTP error (%s)', method, exc_info=True)
            self.close_connection = True
            self.send_json(500, error_body('INTERNAL_ERROR', 'Internal server error'))

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def do_PUT(self):
        self._dispatch('PUT')

    def do_DELETE(self):
        self._dispatch('DELETE')

    def do_PATCH(self):
        self._dispatch('PATCH')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        if self.headers.get('Origin') in self.app.settings.cors_origins:
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Idempotency-Key')
            self.send_header('Access-Control-Max-Age', '600')
        self.send_header('Content-Length', '0')
        self.end_headers()

    # ------------------------------------------------------------ routes
    def route_health(self, query):
        ready = True
        try:
            self.app.store.ping()
            probe = self.app.settings.data_dir / '.health-probe'
            probe.write_bytes(b'ok')
            probe.unlink()
        except Exception:  # noqa: BLE001
            ready = False
        body = {'schema_version': SCHEMA_VERSION, 'status': 'ready' if ready else 'unavailable',
                'ai_enabled': _ai_enabled(self.app.settings), 'uploads_enabled': self.app.settings.uploads_enabled}
        self.send_json(200 if ready else 503, body)

    def route_openapi(self, query):
        self.send_json(200, self.app.openapi)

    DRAIN_LIMIT = 8_000_000

    def _discard_body(self, length):
        """Read and drop an unwanted body (bounded) so the client sees our error, not a reset."""
        self.close_connection = True
        remaining = min(length, self.DRAIN_LIMIT)
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _read_json_body(self):
        raw_length = self.headers.get('Content-Length')
        length = int(raw_length) if raw_length is not None and raw_length.isdigit() else None
        media = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if media != 'application/json':
            self._discard_body(length or 0)
            raise ApiError(415, 'UNSUPPORTED_MEDIA_TYPE', 'Content-Type must be application/json')
        if length is None:
            self.close_connection = True
            raise ApiError(400, 'LENGTH_REQUIRED', 'A valid Content-Length header is required')
        if length > self.app.settings.max_body_bytes:
            self._discard_body(length)
            raise ApiError(413, 'PAYLOAD_TOO_LARGE', f'Request body exceeds {self.app.settings.max_body_bytes} bytes')
        return self.rfile.read(length)

    def route_submit_measured(self, query):
        self.route_submit(query, measured=True)

    def route_submit(self, query, measured=False):
        raw = self._read_json_body()
        key = self.headers.get('Idempotency-Key')
        if key is None or not 1 <= len(key) <= 128 or not key.isprintable():
            raise ApiError(400, 'IDEMPOTENCY_KEY_REQUIRED', 'Idempotency-Key header of 1-128 printable characters is required',
                           'Idempotency-Key')
        try:
            payload = json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)
        except (UnicodeDecodeError, ValueError) as error:
            raise ApiError(422, 'INVALID_JSON', 'Body is not valid UTF-8 JSON: ' + str(error)[:200]) from None
        if measured:
            from twinsite.jobs.measured import resolve_request
            try:
                payload = resolve_request(payload)
            except ValueError as error:
                raise ApiError(422, 'MEASURED_RESOLUTION_FAILED', str(error)) from None
        elif isinstance(payload, dict) and payload.get('data_status') == 'measured':
            raise ApiError(422, 'SERVER_RESOLUTION_REQUIRED', 'Use /v1/missions/measured with a published dataset_id')
        try:
            validate('mission_request', payload)
        except ContractError as error:
            raise ApiError(422, 'SCHEMA_VALIDATION_FAILED', str(error), error.field) from None
        try:
            science_adapter.validate(copy.deepcopy(payload))  # never let validation mutate the hashed original
        except science_adapter.ScienceUnavailable:
            pass  # worker records SCIENCE_ENGINE_UNAVAILABLE; schema validation already ran
        except (ValueError, KeyError, TypeError) as error:
            raise ApiError(422, 'SEMANTIC_VALIDATION_FAILED', str(error)[:500] or error.__class__.__name__) from None
        try:
            mode = (query.get('analysis_mode') or ['ai'])[0]
            if mode not in ('ai', 'simple'):
                raise ApiError(422, 'INVALID_ANALYSIS_MODE', 'analysis_mode must be ai or simple', 'analysis_mode')
            run_id, _replay = self.app.store.submit(payload, key, mode)
        except Conflict as error:
            raise ApiError(409, 'IDEMPOTENCY_CONFLICT', str(error), 'Idempotency-Key') from None
        except CapacityError as error:
            raise ApiError(429, 'QUEUE_FULL', str(error), headers={'Retry-After': '30'}) from None
        self.send_json(202, self.app.accepted_body(run_id), {'Location': f'/v1/missions/{run_id}'})

    def route_status(self, query, run_id):
        self.send_json(200, self.app.status_body(self.app.require_run(run_id)))

    def route_events(self, query, run_id):
        values = query.get('after', ['0'])
        after = values[-1]
        if not after.isdigit() or len(after) > 18:
            raise ApiError(400, 'INVALID_CURSOR', 'after must be a non-negative integer', 'after')
        self.app.require_run(run_id)
        self.send_json(200, self.app.store.events(run_id, int(after), 200))

    def route_result(self, query, run_id):
        self.send_raw_json(200, self.app.require_committed(run_id)['result'])

    def route_evidence(self, query, run_id):
        self.send_raw_json(200, self.app.require_committed(run_id)['evidence'])

    def route_report(self, query, run_id):
        self._send(200, self.app.require_committed(run_id)['report'].encode('utf-8'), 'text/html; charset=utf-8')

    def route_agents(self, query, run_id):
        self.app.require_run(run_id)
        trace = self.app.store.agent_trace(run_id)
        mode = self.app.store.analysis_mode(run_id)
        self.send_json(200, trace or {'schema': 'twinsite.agent_trace/1', 'run_id': run_id, 'analysis_mode': mode,
                                      'records': [], 'pending': mode == 'ai'})

    def route_ai_status(self, query):
        from twinsite.ai import registry
        self.send_json(200, registry(self.app.settings))

    def route_cancel(self, query, run_id):
        # Provisional (pending C0 contract addition): request cancellation; worker stops at next phase boundary.
        if self.app.store.request_cancel(run_id) is None:
            raise ApiError(404, 'RUN_NOT_FOUND', 'Unknown run_id')
        self.send_json(202, self.app.status_body(self.app.store.get(run_id)))

    def _data_response(self, action):
        try:
            self.send_json(200, action())
        except KeyError:
            raise ApiError(404, 'DATASET_NOT_FOUND', 'Unknown dataset or required field') from None
        except ValueError:
            raise ApiError(422, 'INVALID_DATA_QUERY', 'Invalid stage, column, record selection or comparison request') from None

    def route_data_catalog(self, query):
        from .data import catalog
        def read():
            limit = int(query.get('limit', ['100'])[-1])
            if not 1 <= limit <= 100:
                raise ValueError('limit')
            return {'items': catalog()['items'][:limit]}
        self._data_response(read)

    def route_data_records(self, query, dataset_id):
        from .data import records
        def read():
            limit = int(query.get('limit', ['100'])[-1])
            if not 1 <= limit <= 100:
                raise ValueError('limit')
            return records(dataset_id, query.get('stage', ['cleaned'])[-1], limit)
        self._data_response(read)

    def route_data_metadata(self, query, dataset_id):
        from .data import metadata
        self._data_response(lambda: metadata(dataset_id))

    def route_data_grid(self, query, dataset_id):
        from .data import grid, SourceIntegrityError
        try:
            self._data_response(lambda: grid(dataset_id))
        except SourceIntegrityError:
            raise ApiError(409, 'SOURCE_INTEGRITY_FAILED', 'Cleaned grid does not match its pinned checksum') from None

    def route_data_compare(self, query):
        from .data import compare
        raw = self._read_json_body()
        self._data_response(lambda: compare(json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)))

    def route_not_implemented(self, query, **_):
        raise ApiError(501, 'NOT_IMPLEMENTED', 'Reserved G3 endpoint: response schema awaiting C0 review; no simulated data is served.')

    def route_uploads_disabled(self, query, **_):
        raise ApiError(501, 'UPLOADS_DISABLED', 'Private uploads are disabled until capability isolation, consent and retention are verified by QA.')


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(settings=None, host=None, port=None):
    app = App(settings)
    handler = type('BoundHandler', (Handler,), {'app': app})
    server = Server((host or app.settings.host, app.settings.port if port is None else port), handler)
    server.app = app
    return server
