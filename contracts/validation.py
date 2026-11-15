"""Integration validation. Never calculate scores or override scientific QA."""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite JSON number')
    if isinstance(value, dict):
        for item in value.values():
            require_finite(item)
    if isinstance(value, list):
        for item in value:
            require_finite(item)


def validate(name, value):
    """Draft 2020-12 validation, with local-only references and format checks."""
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    require_finite(value)
    resources = []
    for path in sorted((ROOT / 'v1').glob('*.schema.json')):
        resources.append((path.name, Resource.from_contents(json.loads(path.read_text()))))
    schema = json.loads((ROOT / 'v1' / (name + '.schema.json')).read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, registry=Registry().with_resources(resources), format_checker=FormatChecker())
    validator.validate(value)


def measured_release_issues(request, result, manifest, artifact_root):
    """Fail-closed merge/release check; call schema validation first in production.

    A self-declared PASS is insufficient. Source bytes, required observations,
    contribution lineage and independent owner QA must also be present.
    This verifies integration evidence, not the scientific derivation itself.
    """
    issues = []
    try:
        require_finite([request, result, manifest])
    except ValueError:
        return ['NON_FINITE_VALUE']
    if any(x.get('data_status') != 'measured' for x in (request, result, manifest)):
        issues.append('SYNTHETIC_OR_UNVERIFIED_DATA')
    if manifest.get('strict_gate_status') != 'PASS' or manifest.get('release_action') not in ('RELEASE', 'QUALIFIED_RELEASE'):
        issues.append('QA_GATE_NOT_PASSED')
    if manifest.get('blocking_issues') or not manifest.get('review_ids'):
        issues.append('MISSING_OR_BLOCKED_REVIEW')
    if digest(request) != result.get('input_sha256') or result.get('input_sha256') != manifest.get('input_sha256'):
        issues.append('INPUT_SNAPSHOT_MISMATCH')
    assets = manifest.get('assets', [])
    asset_by_id = {a['asset_id']: a for a in assets}
    if len(asset_by_id) != len(assets) or not assets:
        issues.append('EMPTY_OR_DUPLICATE_ASSETS')
    pinned = sorted([{'asset_id':a['asset_id'],'sha256':a['sha256']} for a in assets], key=lambda a:a['asset_id'])
    if digest(pinned) != manifest.get('source_snapshot_sha256'):
        issues.append('SOURCE_SNAPSHOT_MISMATCH')
    artifact_root = Path(artifact_root).resolve()
    for asset in assets:
        path = (artifact_root / asset['object_key']).resolve()
        if not path.is_relative_to(artifact_root) or not path.is_file():
            issues.append('MISSING_SOURCE_BYTES:' + asset['asset_id'])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256'] or path.stat().st_size != asset['byte_size']:
            issues.append('SOURCE_BYTES_MISMATCH:' + asset['asset_id'])
    observations = manifest.get('observations', [])
    obs = {o['evidence_id']: o for o in observations}
    if len(obs) != len(observations):
        issues.append('DUPLICATE_EVIDENCE_ID')
    required = manifest.get('required_evidence_ids', [])
    if not required:
        issues.append('NO_REQUIRED_EVIDENCE')
    for evidence_id in required:
        o = obs.get(evidence_id)
        if not o or o.get('value') is None:
            issues.append('MISSING_REQUIRED_MEASUREMENT:' + evidence_id)
    for o in observations:
        eid = o['evidence_id']
        if o['data_status'] != 'measured' or o['evidence_kind'] not in ('direct_measurement','derived_measurement'):
            issues.append('NON_MEASUREMENT_EVIDENCE:' + eid)
        if o['qa_status'] != 'ACCEPT' or o['valid_coverage_fraction'] <= 0:
            issues.append('UNACCEPTED_EVIDENCE:' + eid)
        if o['spatial_resolution_m'] is None or o['analysis_scale_m'] is None:
            issues.append('MISSING_SPATIAL_SUPPORT:' + eid)
        sources = [asset_by_id.get(aid) for aid in o['source_asset_ids']]
        if not sources or any(a is None for a in sources):
            issues.append('ORPHAN_SOURCE:' + eid)
        elif not any(a['sha256'] == o['source_checksum'] and a['source_url'] == o['source_url'] and a['product_id'] == o['source_product'] and a['body'] == o['body'] for a in sources):
            issues.append('SOURCE_LINEAGE_MISMATCH:' + eid)
    # No published numeric contribution may point to absent or different evidence.
    used = set()
    for site in result.get('sites', []):
        for contribution in site.get('contributions', {}).values():
            for key, value_key, body, site_id in [('source_id','value','Earth',site['id']),('target_source_id','target_value',contribution['target_body'],contribution['target_location_id'])]:
                eid = contribution.get(key)
                used.add(eid)
                o = obs.get(eid)
                if not o or any([o['value'] != contribution[value_key], o['unit'] != contribution['unit'], o['body'] != body, o['site_id'] != site_id, o['feature_id'] != contribution['feature_id']]):
                    issues.append('CONTRIBUTION_EVIDENCE_MISMATCH:' + str(eid))
    if not used:
        issues.append('NO_SCORED_EVIDENCE')
    # Required evidence is derived independently from the request, not only from
    # the manifest supplied by the worker. Missing target data always blocks.
    for feature, spec in request.get('mission',{}).get('features',{}).items():
        if not spec.get('required', False):
            continue
        eligible_ids = {s['id'] for s in result.get('sites',[]) if s.get('eligible')}
        locations = [(s['id'], s.get('observations',{})) for s in request.get('sites',[]) if s['id'] in eligible_ids]
        locations += [(t['location']['id'], t.get('observations',{})) for t in request.get('target_profiles',[])]
        for site_id, values in locations:
            value = values.get(feature)
            if not value or value.get('value') is None or value.get('source_id') not in required or value.get('source_id') not in obs:
                issues.append('REQUIRED_FEATURE_NOT_ATTESTED:' + site_id + '/' + feature)
    return sorted(set(issues))
