"""Release-evidence sidecar builder. Fail-closed: synthetic input always BLOCKs.

Measured release requires C1 asset manifests + C2/C5 QA; until a resolver is
integrated, measured runs never reach this builder (the worker fails them).
"""
from .contract import digest

QA_GATE_ID = 'c3-integration-gate'
QA_GATE_VERSION = '1.0'


def snapshot(assets):
    """Return (source_snapshot_id, source_snapshot_sha256) for an asset list."""
    pinned = sorted(({'asset_id': a['asset_id'], 'sha256': a['sha256']} for a in assets), key=lambda a: a['asset_id'])
    sha = digest(pinned)
    prefix = 'snap-synthetic-inline-' if not assets else 'snap-'
    return prefix + sha[:16], sha


def rejected_candidates(result):
    rejected = []
    seen = set()
    for site in result.get('sites', []):
        if not site.get('eligible', True) and site['id'] not in seen:
            seen.add(site['id'])
            reasons = [str(r) for r in site.get('failures') or [] if str(r)] or ['NOT_ELIGIBLE']
            rejected.append({'site_id': site['id'], 'reasons': reasons})
    for site_id in result.get('excluded_outside_scope', []):
        if site_id not in seen:
            seen.add(site_id)
            rejected.append({'site_id': site_id, 'reasons': ['OUTSIDE_SELECTED_SCOPE']})
    return rejected


def synthetic_evidence(run_id, input_sha256, result, engine):
    snapshot_id, snapshot_sha = snapshot([])
    return {
        'schema_version': '1.0',
        'run_id': run_id,
        'input_sha256': input_sha256,
        'source_snapshot_id': snapshot_id,
        'source_snapshot_sha256': snapshot_sha,
        'qa_gate_id': QA_GATE_ID,
        'qa_gate_version': QA_GATE_VERSION,
        'data_status': 'synthetic',
        'strict_gate_status': 'NOT_EVALUATED',
        'release_action': 'BLOCK',
        'weights_version': f'{engine.name}-{result.get("algorithm_version") or engine.version}',
        'evidence_coverage': 0,
        'required_evidence_ids': [],
        'assets': [],
        'observations': [],
        'rejected_candidates': rejected_candidates(result),
        'assumptions': ['All input observations, target profiles, costs and durations are SYNTHETIC fixture values.',
                        f'Scores computed by deterministic engine {engine.name} {engine.version}; no AI involved.'],
        'unknowns': ['No validated NASA product pair or source asset was resolved for this run.'],
        'blocking_issues': ['SYNTHETIC_ONLY'],
        'review_ids': [],
    }
