"""OpenAPI 3.1 document built from C0's frozen contracts/v1 JSON Schemas."""
import copy
import json

from twinsite.storage.config import WORKSPACE_ROOT

CONTRACT_DIR = WORKSPACE_ROOT / 'contracts' / 'v1'


def _rewrite_refs(node):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == '$schema':
                continue
            if key == '$ref' and isinstance(value, str) and value.endswith('.schema.json'):
                out[key] = '#/components/schemas/' + value[:-len('.schema.json')]
            else:
                out[key] = _rewrite_refs(value)
        return out
    if isinstance(node, list):
        return [_rewrite_refs(v) for v in node]
    return node


def _schemas():
    schemas = {}
    for path in sorted(CONTRACT_DIR.glob('*.schema.json')):
        schemas[path.name[:-len('.schema.json')]] = _rewrite_refs(json.loads(path.read_text(encoding='utf-8')))
    return schemas


def _ref(name):
    return {'$ref': '#/components/schemas/' + name}


def _json(name, description):
    return {'description': description, 'content': {'application/json': {'schema': _ref(name)}}}


def _err(description):
    return _json('error', description)


RUN_PARAM = {'name': 'run_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'},
             'description': 'Opaque server-generated run ID'}


def build_openapi():
    errors_run = {'404': _err('Unknown run_id'), '409': _err('Result not committed, failed or cancelled')}
    paths = {
        '/v1/health': {'get': {'operationId': 'health', 'summary': 'Readiness (AI and uploads disabled by default)',
                               'responses': {'200': _json('health', 'Ready'), '503': _json('health', 'Local storage unavailable')}}},
        '/v1/missions': {'post': {
            'operationId': 'submitMission', 'summary': 'Queue a mission run (explicit user action only)',
            'parameters': [{'name': 'Idempotency-Key', 'in': 'header', 'required': True,
                            'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128}}],
            'requestBody': {'required': True, 'content': {'application/json': {'schema': _ref('mission_request')}}},
            'responses': {'202': _json('mission_accepted', 'Accepted; identical retries replay this payload'),
                          '400': _err('Missing/invalid Idempotency-Key or Content-Length'),
                          '409': _err('Same key, different input'), '413': _err('Body > 1,000,000 bytes'),
                          '415': _err('Content-Type is not application/json'), '422': _err('Validation failed'),
                          '429': _err('Queue full (bounded at 20)')}}},
        '/v1/missions/{run_id}': {'get': {'operationId': 'getMissionStatus', 'parameters': [RUN_PARAM],
                                          'responses': {'200': _json('mission_status', 'Current status'), '404': _err('Unknown run_id')}}},
        '/v1/missions/{run_id}/events': {'get': {
            'operationId': 'getMissionEvents', 'summary': 'Committed progress events, ascending, at most 200',
            'parameters': [RUN_PARAM, {'name': 'after', 'in': 'query', 'required': False,
                                       'schema': {'type': 'integer', 'minimum': 0, 'default': 0}}],
            'responses': {'200': _json('events', 'Events with sequence > after; [] at end'),
                          '400': _err('Invalid cursor'), '404': _err('Unknown run_id')}}},
        '/v1/missions/{run_id}/result': {'get': {'operationId': 'getMissionResult', 'parameters': [RUN_PARAM],
                                                 'responses': {'200': _json('mission_result', 'Unchanged committed result'), **errors_run}}},
        '/v1/missions/{run_id}/evidence': {'get': {'operationId': 'getMissionEvidence', 'parameters': [RUN_PARAM],
                                                   'responses': {'200': _json('release_evidence', 'Release-evidence sidecar'), **errors_run}}},
        '/v1/missions/{run_id}/report': {'get': {'operationId': 'getMissionReport', 'parameters': [RUN_PARAM],
                                                 'responses': {'200': {'description': 'Escaped HTML report',
                                                                       'content': {'text/html': {'schema': {'type': 'string'}}}},
                                                               **errors_run}}},
        '/v1/missions/{run_id}/cancel': {'post': {
            'operationId': 'cancelMission', 'summary': 'PROVISIONAL (pending C0 contract addition): request cancellation',
            'x-twinsite-status': 'provisional', 'parameters': [RUN_PARAM],
            'responses': {'202': _json('mission_status', 'Cancellation recorded or run already terminal'), '404': _err('Unknown run_id')}}},
    }
    reserved = {
        ('/v1/missions/{run_id}/portfolios/alternatives', 'post'): 'Alternative portfolios (G3)',
        ('/v1/data/catalog', 'get'): 'Public curated dataset catalog (G3)',
        ('/v1/data/{dataset_id}/records', 'get'): 'Raw/cleaned/derived record previews (G3)',
        ('/v1/data/{dataset_id}/metadata', 'get'): 'Dataset metadata and lineage (G3)',
        ('/v1/data/compare', 'post'): 'Server-controlled comparison of approved records (G3)',
        ('/v1/uploads', 'post'): 'Private uploads — disabled',
    }
    for (path, method), summary in reserved.items():
        params = [RUN_PARAM] if '{run_id}' in path else []
        if '{dataset_id}' in path:
            params = [{'name': 'dataset_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}]
        paths[path] = {method: {'operationId': 'reserved_' + path.strip('/').replace('/', '_').replace('{', '').replace('}', ''),
                                'summary': 'RESERVED, returns 501: ' + summary, 'x-twinsite-status': 'reserved',
                                'parameters': params, 'responses': {'501': _err('Not implemented / disabled')}}}
    return {
        'openapi': '3.1.0',
        'info': {'title': 'TwinSite API', 'version': '1.0',
                 'description': 'Earth analogue vs Moon/Mars comparison. Deterministic engine; no AI required; '
                                'no login. Synthetic results are always release_action BLOCK.'},
        'jsonSchemaDialect': 'https://json-schema.org/draft/2020-12/schema',
        'paths': paths,
        'components': {'schemas': copy.deepcopy(_schemas())},
    }
