"""The 13 TwinSite agent roles and the AI-Powered Analysis orchestrator.

Division of labour (never blurred):
  * Deterministic code owns every number: measurements, features, scores, eligibility,
    portfolios and the release gate. AI output can never modify the committed result.
  * AI roles interpret, propose labelled scenarios, synthesise, review and explain. Every
    AI claim must cite evidence IDs that exist in the evidence packet; outputs that cite
    unknown IDs fail schema validation and the router moves to another free provider.
  * A role is reported as executed by AI only when a real provider call returned (or a
    cached response from an earlier real call is reused, which is labelled as such).
"""
import copy
import hashlib
import html
import json
import re
from datetime import datetime, timezone

from .router import Task

METHOD_VERSION = 'twinsite-agents/1.0.0'
DOMAINS = ('spatial_identity', 'topography', 'thermal', 'atmosphere_climate', 'temporal', 'surface_composition',
           'geology_mineralogy', 'mechanics_mobility', 'resources_volatiles', 'planetary_constraints',
           'accessibility_environment', 'operations_economics', 'mission_requirements', 'evidence_quality')
FEATURE_DOMAIN = {'slope_deg': 'topography', 'roughness_m': 'topography', 'local_relief_m': 'topography',
                  'elevation_m': 'topography', 'dry_fraction': 'surface_composition'}

ROLES = (
    ('A01', 'Source Curator', 'P10', 'deterministic', 'Inventories evidence sources, assets and gateway context per domain.'),
    ('A02', 'Visual Interpreter', 'P20', 'ai_vision', 'Qualitative reading of agency imagery (never a measurement).'),
    ('A03', 'Cleaning Planner', 'P30', 'deterministic', 'Allowlisted cleaning transformations recorded by the engine.'),
    ('A04', 'Quality Reviewer', 'P40', 'deterministic', 'Hard QA gates: qa_status, flags, coverage, spatial support.'),
    ('A05', 'Scenario Estimator', 'P50', 'ai_json', 'Proposes labelled alternative weight scenarios; engine re-scores them.'),
    ('A06', 'Domain Analyst', 'P60', 'ai_json', 'Evidence-linked findings per scientific domain, plus data gaps.'),
    ('A07', 'Synthesis Analyst', 'P70', 'ai_json', 'Cross-domain synthesis with claims tied to evidence IDs.'),
    ('A08', 'Process Auditor', 'P80', 'deterministic', 'Asserts the agent trace is well-formed and the result untouched.'),
    ('A09', 'Evidence Reviewer', 'P80', 'ai_json', 'Independent provider reviews each synthesis claim against evidence.'),
    ('A10', 'Portfolio Reviewer', 'P80', 'deterministic', 'Rechecks portfolio constraints and eligibility.'),
    ('A11', 'Release Judge', 'P80', 'deterministic', 'Applies the deterministic release gate; AI cannot release.'),
    ('A12', 'Targeted Rechecker', 'P80', 'ai_json', 'Re-examines only claims the reviewer could not support.'),
    ('A13', 'Report Writer', 'P90', 'ai_narrative', 'Evidence-cited narrative appended to the deterministic report.'),
)
ROLE = {r[0]: r for r in ROLES}

GUARD = ('You are part of TwinSite, a planetary-analog science platform. Use ONLY the evidence provided. '
         'Never invent measurements, sources or numbers. Cite evidence IDs exactly as given. Distinguish measured '
         'values from interpretation. Earth air temperature, Earth land-surface temperature and planetary surface '
         'temperature are different quantities and must not be equated. Reply with one JSON object only.')


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------- evidence packet
def evidence_packet(payload, result, sidecar, observations=None, context=()):
    """Compact, citation-ready evidence list. Synthetic inputs are labelled synthetic."""
    items = []
    if observations:
        for o in observations:
            items.append({'evidence_id': o['evidence_id'], 'site': o['site_id'], 'body': o['body'], 'feature': o['feature_id'],
                          'value': o['value'], 'unit': o['unit'], 'status': o['data_status'], 'qa': o['qa_status'],
                          'flags': o['quality_flags'][:3], 'product': o['source_product'],
                          'interval_p10_p90': [o['uncertainty'].get('low'), o['uncertainty'].get('high')]
                          if o.get('uncertainty') else None, 'scale_m': o.get('analysis_scale_m')})
    else:
        for site in payload.get('sites', []):
            for feature, obs in (site.get('observations') or {}).items():
                items.append({'evidence_id': obs.get('source_id') or f"syn-{site['id']}-{feature}", 'site': site['id'],
                              'body': site.get('body', 'Earth'), 'feature': feature, 'value': obs.get('value'),
                              'unit': obs.get('unit'), 'status': 'synthetic'})
        for profile in payload.get('target_profiles', []):
            for feature, obs in (profile.get('observations') or {}).items():
                items.append({'evidence_id': obs.get('source_id') or f"syn-{profile['body']}-{feature}",
                              'site': profile['location']['id'], 'body': profile['body'], 'feature': feature,
                              'value': obs.get('value'), 'unit': obs.get('unit'), 'status': 'synthetic'})
    for c in context:
        items.append(c)
    # Deterministic outputs are citable too (never as measurements).
    for site in result.get('sites', []):
        items.append({'evidence_id': f"result-{site['id']}", 'site': site['id'], 'body': site.get('body'),
                      'feature': 'deterministic_site_assessment', 'status': 'deterministic_result',
                      'eligible': site.get('eligible'), 'coverage': site.get('coverage'),
                      'similarity': site.get('observed_similarity'), 'failures': site.get('failures', [])[:4],
                      'missing': site.get('missing', [])[:6]})
    items.append({'evidence_id': 'release-gate', 'feature': 'release_gate', 'status': 'deterministic_result',
                  'release_action': sidecar.get('release_action'), 'blocking_issues': sidecar.get('blocking_issues')})
    return items


def _result_digest(result):
    sites = [{'site': s['id'], 'eligible': s['eligible'], 'coverage': s['coverage'],
              'similarity': round(s['observed_similarity'], 4) if s.get('observed_similarity') is not None else None,
              'utility_bounds': [round(s['lower_utility'], 4), round(s['upper_utility'], 4)]
              if s.get('lower_utility') is not None else None, 'failures': s.get('failures', [])[:4],
              'missing': s.get('missing', [])[:6]} for s in result.get('sites', [])]
    return {'status': result.get('status'), 'feasible_portfolios': result.get('feasible_portfolio_count'),
            'weights': result.get('weights'), 'sites': sites, 'limitations': result.get('limitations', [])[:6]}


def _ids(value):
    return set(value) if isinstance(value, list) and all(isinstance(v, str) for v in value) else None


# ---------------------------------------------------------------------- validators
def _v_domain(known):
    def check(o):
        errs = []
        findings = o.get('findings')
        if not isinstance(findings, list) or not findings:
            return ['findings must be a non-empty list']
        kept = [f for f in findings if f.get('domain') in DOMAINS and _ids(f.get('evidence_ids'))
                and _ids(f.get('evidence_ids')) <= known and isinstance(f.get('claim'), str) and len(f['claim']) >= 10]
        o['dropped_uncited_findings'] = len(findings) - len(kept)
        o['findings'] = kept[:10]
        if not kept:
            errs.append('no finding cites evidence present in the packet')
        for g in o.get('data_gaps', []) or []:
            if g.get('domain') not in DOMAINS:
                errs.append('data gap with unknown domain')
        return errs
    return check


def _v_scenarios(features):
    def check(o):
        sc = o.get('scenarios')
        if not isinstance(sc, list) or not 1 <= len(sc) <= 2:
            return ['scenarios must be a list of 1-2 items']
        errs = []
        for i, s in enumerate(sc):
            w = s.get('weights')
            if not isinstance(w, dict) or set(w) != set(features):
                errs.append(f'scenario {i}: weights must cover exactly {sorted(features)}')
            elif any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in w.values()) or sum(w.values()) <= 0:
                errs.append(f'scenario {i}: weights must be in [0,1] with positive sum')
            if not s.get('rationale'):
                errs.append(f'scenario {i}: rationale missing')
        return errs
    return check


def _v_synthesis(known):
    def check(o):
        claims = o.get('key_claims')
        if not isinstance(o.get('summary'), str) or not isinstance(claims, list) or not 1 <= len(claims) <= 8:
            return ['summary and 1-8 key_claims required']
        kept = []
        for c in claims:
            ids = _ids(c.get('evidence_ids'))
            if ids and ids <= known and isinstance(c.get('claim'), str):
                if c.get('basis') not in ('measured', 'derived', 'assumption', 'ai_hypothesis', 'synthetic'):
                    c['basis'] = 'ai_hypothesis'
                kept.append(c)
        o['dropped_uncited_claims'] = len(claims) - len(kept)
        o['key_claims'] = kept
        return [] if kept else ['no claim cites evidence present in the packet']
    return check


def _v_review(n):
    def check(o):
        rv = o.get('reviews')
        if not isinstance(rv, list) or len(rv) != n:
            return [f'reviews must contain exactly {n} items']
        return [f'review {i}: bad verdict/index' for i, r in enumerate(rv)
                if r.get('verdict') not in ('supported', 'unsupported', 'uncertain') or r.get('claim_index') not in range(n)]
    return check


def _v_recheck(known, indexes):
    def check(o):
        rc = o.get('rechecks')
        if not isinstance(rc, list) or not rc:
            return ['rechecks required']
        errs = []
        for r in rc:
            if r.get('claim_index') not in indexes or r.get('verdict') not in ('supported', 'unsupported', 'withdrawn'):
                errs.append('bad claim_index/verdict')
            ids = _ids(r.get('evidence_ids'))
            if ids is None or not ids <= known:
                errs.append('evidence_ids not in packet')
        return errs
    return check


_CITE = re.compile(r'\[([A-Za-z0-9_.:\-]{3,120})\]')


def _v_narrative(known):
    def check(text):
        cited = set(_CITE.findall(text))
        if not cited & known:
            return ['narrative must cite at least one evidence ID in [brackets]']
        unknown = {c for c in cited if c not in known and c.startswith(('ev-', 'syn', 'synthetic-', 'power-', 'gibs-', 'ctx-',
                                                                         'result-', 'cmr-'))}
        return [f'cites unknown evidence IDs: {sorted(unknown)[:3]}'] if unknown else []
    return check


def _v_visual(o):
    obs = o.get('observations')
    if not isinstance(obs, list) or not obs:
        return ['observations list required']
    return [] if all(isinstance(x.get('description'), str) for x in obs) else ['each observation needs a description']


# ---------------------------------------------------------------------- numeric cross-check (A09 deterministic half)
_NUM = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)')   # unsigned; hyphens in ranges are not minus signs


def _numbers(value, out):
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        out.extend(float(x) for x in _NUM.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            _numbers(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _numbers(v, out)
    return out


def numeric_mismatches(claim, packet_by_id, mission_numbers=()):
    """Every number quoted in a claim must appear (2% / rounding tolerance) in the cited evidence items or the
    mission parameters; small integers are exempt. Unit misuse is left to the independent AI reviewer."""
    allowed = list(mission_numbers)
    for i in claim.get('evidence_ids', []):
        if i in packet_by_id:
            _numbers({k: v for k, v in packet_by_id[i].items() if k != 'evidence_id'}, allowed)
    bad = []
    for token in _NUM.findall(claim.get('claim', '')):
        x = float(token)
        if abs(x) <= 10 and float(x).is_integer():
            continue
        if not any(abs(x - abs(a)) <= max(0.02 * abs(a), 0.051 if '.' in token else 0.51) for a in allowed):
            bad.append(token)
    return bad


# ---------------------------------------------------------------------- orchestrator
class Orchestrator:
    def __init__(self, router, emit=None, rescore=None, max_ai_calls=7):
        self.router, self.emit, self.rescore = router, emit or (lambda *a: None), rescore
        self.max_ai_calls = max_ai_calls
        self.ai_calls = 0
        self.records = []

    def _record(self, agent_id, execution, summary, output=None, outcome=None, evidence_ids=(), issues=(),
                actions=('continue',), run_id=''):
        aid, name, phase, kind, purpose = ROLE[agent_id]
        status = {'ai': 'completed', 'ai_cached': 'completed', 'deterministic': 'completed', 'skipped': 'skipped',
                  'failed': 'failed', 'fallback': 'skipped'}[execution]
        if any(i.get('severity') == 'critical' for i in issues):
            status = 'needs_review'
        agent_result = {'run_id': run_id, 'agent_id': aid, 'phase_id': phase, 'task_id': f'agent-{aid.lower()}',
                        'status': status, 'summary': summary[:600], 'input_artifact_ids': [], 'output_artifact_ids': [],
                        'evidence_ids': sorted(set(evidence_ids))[:60], 'issues': list(issues)[:20],
                        'proposed_actions': list(actions), 'ai_used': execution in ('ai', 'ai_cached'),
                        'method_version': METHOD_VERSION, 'created_at': _now()}
        rec = {'agent_id': aid, 'role': name, 'phase': phase, 'execution': execution, 'purpose': purpose,
               'summary': summary, 'output': output, 'agent_result': agent_result}
        if outcome is not None:
            rec['inference'] = outcome.public()
        self.records.append(rec)
        via = ''
        if outcome is not None and outcome.ok:
            via = f' via {outcome.provider}/{outcome.model}' + (' (cached response from an earlier real call)' if outcome.cached else
                                                                f' in {outcome.latency_ms} ms')
        self.emit(phase, aid, f'{aid} {name}: {execution.replace("_", " ")}{via}. {summary}'[:480])
        return rec

    def _ai(self, task):
        if self.ai_calls >= self.max_ai_calls:
            return None
        self.ai_calls += 1
        return self.router.complete(task)

    def run(self, run_id, payload, result, sidecar, observations=None, context=(), image=None, priority='mission'):
        before = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        packet = evidence_packet(payload, result, sidecar, observations, context)
        by_id = {e['evidence_id']: e for e in packet}
        known = set(by_id)
        digest = _result_digest(result)
        features = sorted(payload['mission']['features'])
        ctx = json.dumps({'mission_features': payload['mission']['features'], 'deterministic_result': digest,
                          'release_action': sidecar.get('release_action'), 'blocking_issues': sidecar.get('blocking_issues'),
                          'evidence': packet[:60]}, separators=(',', ':'), default=str)
        ai_available = self.router.enabled()

        # A01 Source Curator (deterministic)
        products = sorted({e.get('product') or e.get('status') for e in packet
                           if (e.get('product') or e.get('status')) and e.get('status') != 'deterministic_result'})
        covered = sorted({FEATURE_DOMAIN.get(e['feature'], e.get('domain', 'evidence_quality')) for e in packet})
        missing = [d for d in DOMAINS if d not in covered and d not in ('mission_requirements', 'evidence_quality', 'spatial_identity')]
        self._record('A01', 'deterministic', f'{len(packet)} evidence items from {", ".join(products) or "no products"}; '
                     f'domains with evidence: {", ".join(covered)}. No evidence yet for: {", ".join(missing)}.',
                     {'products': products, 'domains_with_evidence': covered, 'domains_without_evidence': missing},
                     evidence_ids=known, issues=[{'code': 'DOMAIN_WITHOUT_EVIDENCE:' + d, 'severity': 'info', 'evidence_id': None}
                                                 for d in missing], run_id=run_id)

        # A02 Visual Interpreter (vision AI, only with real agency imagery)
        if image and ai_available:
            o = self._ai(Task('A02', run_id, 'vision', GUARD + ' Describe what is visible qualitatively; colours in a '
                              'visualization are NOT calibrated measurements.',
                              f'Image: {image["label"]} (evidence {image["evidence_id"]}). Return {{"observations":'
                              '[{"aspect":"terrain|surface|clouds|vegetation|infrastructure|other","description":str,'
                              '"confidence":"low|medium|high"}],"caveats":[str]}', images=((image['mime'], image['bytes']),),
                              priority=priority, validate=_v_visual, max_output_tokens=700))
            if o and o.ok:
                self._record('A02', 'ai_cached' if o.cached else 'ai', f'{len(o.output["observations"])} qualitative visual '
                             'observations (not measurements).', o.output, o, [image['evidence_id']], run_id=run_id)
            else:
                self._record('A02', 'failed', 'Vision interpretation unavailable: ' + (o.error if o else 'AI call budget spent'),
                             outcome=o, run_id=run_id)
        else:
            self._record('A02', 'skipped', 'No agency image available for this mission or AI disabled; no visual claims made.',
                         run_id=run_id)

        # A03 Cleaning Planner, A04 Quality Reviewer (deterministic)
        transforms = result.get('transformations', [])
        self._record('A03', 'deterministic', f'{len(transforms)} allowlisted transformations recorded; cleaned input hash '
                     f'{"unchanged" if result.get("cleaned_sha256") == result.get("input_sha256") else "changed"}.',
                     {'transformations': transforms[:20]}, run_id=run_id)
        qa_issues = [{'code': 'QA_' + str(e.get('qa')), 'severity': 'warning', 'evidence_id': e['evidence_id']}
                     for e in packet if e.get('qa') not in (None, 'ACCEPT')]
        flags = sorted({f for e in packet for f in e.get('flags') or []})
        self._record('A04', 'deterministic', f'{len(packet) - len(qa_issues)}/{len(packet)} evidence items pass QA; '
                     f'{len(flags)} distinct quality flags carried forward.', {'quality_flags': flags}, issues=qa_issues,
                     evidence_ids=known, run_id=run_id)

        if not ai_available:
            reason = self.router.disabled_reason()
            for aid in ('A05', 'A06', 'A07', 'A09', 'A12', 'A13'):
                self._record(aid, 'fallback', f'AI unavailable ({reason}); Simple Analysis covers this step deterministically.',
                             run_id=run_id)
        else:
            self._ai_roles(run_id, payload, result, sidecar, packet, by_id, known, features, ctx, priority, observations)

        # A08 Process Auditor (deterministic)
        after = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        problems = [] if before == after else ['RESULT_MUTATED_DURING_AI_STAGE']
        for r in self.records:
            if r['execution'] in ('ai', 'ai_cached') and not (r.get('inference') or {}).get('provider'):
                problems.append(f'{r["agent_id"]}_CLAIMS_AI_WITHOUT_PROVIDER')
        self._record('A08', 'deterministic', 'Process audit ' + ('passed: deterministic result unchanged by AI stages; every '
                     'AI record carries provider provenance.' if not problems else 'FAILED: ' + ', '.join(problems)),
                     {'result_sha256': after, 'problems': problems},
                     issues=[{'code': p, 'severity': 'critical', 'evidence_id': None} for p in problems],
                     actions=('block',) if problems else ('continue',), run_id=run_id)

        # A10 Portfolio Reviewer (deterministic)
        eligible = {s['id'] for s in result.get('sites', []) if s.get('eligible')}
        bad = [p for p in result.get('portfolios', []) for sid in (p.get('site_ids') or p.get('sites') or [])
               if isinstance(sid, str) and sid not in eligible]
        self._record('A10', 'deterministic', f'{result.get("feasible_portfolio_count", 0)} feasible portfolios; '
                     f'{len(eligible)} eligible sites; {"no" if not bad else len(bad)} constraint violations.',
                     {'eligible_sites': sorted(eligible), 'violations': bad[:10]},
                     issues=[{'code': 'PORTFOLIO_INELIGIBLE_SITE', 'severity': 'critical', 'evidence_id': None}] if bad else [],
                     run_id=run_id)

        # A11 Release Judge (deterministic; AI cannot release)
        action = sidecar.get('release_action')
        self._record('A11', 'deterministic', f'Release gate: {action}. Blocking issues: '
                     f'{", ".join(sidecar.get("blocking_issues") or []) or "none"}. AI review is advisory and cannot override it.',
                     {'release_action': action, 'blocking_issues': sidecar.get('blocking_issues')},
                     actions=('release_qualified',) if action == 'RELEASE' else ('block',), run_id=run_id)
        order = {r[0]: i for i, r in enumerate(ROLES)}
        self.records.sort(key=lambda r: order[r['agent_id']])
        return self.trace(run_id, ai_available)

    def _ai_roles(self, run_id, payload, result, sidecar, packet, by_id, known, features, ctx, priority, observations):
        # A05 Scenario Estimator -> deterministic re-scoring of labelled AI-proposed weights
        if len(features) >= 2 and self.rescore:
            o = self._ai(Task('A05', run_id, 'json', GUARD, 'Propose 1-2 alternative feature-weight scenarios a mission '
                              'planner might reasonably consider, each with a rationale grounded in the evidence. Weights in '
                              f'[0,1] for exactly these features: {features}. Return {{"scenarios":[{{"name":str,"weights":'
                              '{feature:number},"rationale":str}]}.\nCONTEXT:' + ctx, priority=priority,
                              validate=_v_scenarios(features)))
            if o and o.ok:
                rescored = []
                for s in o.output['scenarios']:
                    try:
                        rescored.append({'name': s['name'], 'weights': s['weights'], 'rationale': s['rationale'],
                                         'label': 'AI-PROPOSED SCENARIO (assumption, not measured)',
                                         'deterministic_outcome': self.rescore(s['weights'])})
                    except Exception as error:  # noqa: BLE001 - scenario failure never affects the main result
                        rescored.append({'name': s['name'], 'weights': s['weights'], 'error': type(error).__name__})
                self._record('A05', 'ai_cached' if o.cached else 'ai', f'{len(rescored)} AI-proposed weight scenarios '
                             're-scored by the deterministic engine (labelled assumptions).', {'scenarios': rescored}, o,
                             run_id=run_id)
            else:
                self._record('A05', 'failed', 'Scenario estimation unavailable: ' + (o.error if o else 'budget'), outcome=o,
                             run_id=run_id)
        else:
            self._record('A05', 'skipped', 'Single-feature mission or no rescoring engine; no scenarios proposed.', run_id=run_id)

        # A06 Domain Analyst
        o = self._ai(Task('A06', run_id, 'json', GUARD, 'Analyse the evidence by scientific domain. Allowed domains: '
                          f'{list(DOMAINS)}. For each finding give the domain, a precise claim, the evidence_ids it rests on, '
                          'kind (interpretation|hypothesis) and confidence. Also list data_gaps (domain, missing, '
                          'why_it_matters) for domains with no evidence. Return {"findings":[...],"data_gaps":[...]}.\n'
                          'CONTEXT:' + ctx, priority=priority, validate=_v_domain(known), prefer=('groq', 'cloudflare')))
        domain = None
        if o and o.ok:
            domain = o.output
            ids = {i for f in o.output['findings'] for i in f['evidence_ids']}
            self._record('A06', 'ai_cached' if o.cached else 'ai', f'{len(o.output["findings"])} evidence-linked domain '
                         f'findings; {len(o.output.get("data_gaps") or [])} data gaps identified.', o.output, o, ids, run_id=run_id)
        else:
            self._record('A06', 'failed', 'Domain analysis unavailable: ' + (o.error if o else 'budget'), outcome=o, run_id=run_id)

        # A07 Synthesis Analyst
        extra = ('\nDOMAIN_FINDINGS:' + json.dumps(domain['findings'][:8], separators=(',', ':'))) if domain else ''
        o = self._ai(Task('A07', run_id, 'json', GUARD, 'Synthesise what the evidence and the deterministic result say '
                          'about this analog site. The deterministic result is authoritative for scores and eligibility. '
                          'Return {"summary":str,"key_claims":[{"claim":str,"evidence_ids":[...],"basis":"measured|derived|'
                          'assumption|ai_hypothesis|synthetic"}],"recommendation":str,"uncertainties":[str]}. Quote numbers '
                          'exactly as in the evidence.\nCONTEXT:' + ctx + extra, priority=priority,
                          validate=_v_synthesis(known), prefer=('cloudflare', 'groq')))
        synthesis, synth_provider = None, None
        if o and o.ok:
            synthesis, synth_provider = o.output, o.provider
            ids = {i for c in o.output['key_claims'] for i in c['evidence_ids']}
            self._record('A07', 'ai_cached' if o.cached else 'ai', o.output['summary'][:300], o.output, o, ids, run_id=run_id)
        else:
            self._record('A07', 'failed', 'Synthesis unavailable: ' + (o.error if o else 'budget'), outcome=o, run_id=run_id)

        # A09 Evidence Reviewer: independent provider + deterministic numeric cross-check
        flagged = []
        mission_numbers = _numbers(payload['mission']['features'], []) + _numbers(
            {k: payload['mission'].get(k) for k in ('min_coverage', 'max_sites', 'budget', 'max_days')}, [])
        if synthesis:
            claims = synthesis['key_claims']
            numeric = {i: numeric_mismatches(c, by_id, mission_numbers) for i, c in enumerate(claims)}
            cited = {i: [by_id[e] for e in c['evidence_ids']] for i, c in enumerate(claims)}
            o = self._ai(Task('A09', run_id, 'json', GUARD + ' You are an independent reviewer. Be strict.',
                              'For each claim decide whether the cited evidence supports it. Return {"reviews":[{"claim_index":'
                              'int,"verdict":"supported|unsupported|uncertain","reason":str}]} with one review per claim.\n'
                              'CLAIMS_WITH_CITED_EVIDENCE:' + json.dumps([{'claim_index': i, 'claim': c['claim'],
                                                                           'basis': c['basis'], 'cited': cited[i]}
                                                                          for i, c in enumerate(claims)],
                                                                         separators=(',', ':'), default=str),
                              priority=priority, validate=_v_review(len(claims)),
                              avoid=(synth_provider,) if synth_provider else (), prefer=('google', 'openrouter', 'nvidia')))
            reviews = o.output['reviews'] if o and o.ok else []
            verdict = {r['claim_index']: r for r in reviews}
            for i, c in enumerate(claims):
                if numeric[i] or verdict.get(i, {}).get('verdict') in ('unsupported', 'uncertain') or i not in verdict:
                    flagged.append(i)
            issues = [{'code': 'NUMERIC_MISMATCH', 'severity': 'warning', 'evidence_id': None, 'claim_index': i,
                       'numbers': n} for i, n in numeric.items() if n]
            issues += [{'code': 'CLAIM_' + r['verdict'].upper(), 'severity': 'warning', 'evidence_id': None,
                        'claim_index': r['claim_index']} for r in reviews if r['verdict'] != 'supported']
            if o and o.ok:
                independent = o.provider != synth_provider
                self._record('A09', 'ai_cached' if o.cached else 'ai', f'{sum(r["verdict"] == "supported" for r in reviews)}/'
                             f'{len(claims)} claims supported by an {"independent" if independent else "SAME-PROVIDER"} '
                             f'reviewer; {sum(bool(n) for n in numeric.values())} numeric mismatches found deterministically.',
                             {'reviews': reviews, 'numeric_mismatches': numeric, 'independent_provider': independent}, o,
                             issues=issues, actions=('targeted_recheck',) if flagged else ('continue',), run_id=run_id)
            else:
                self._record('A09', 'failed', 'AI review unavailable (' + (o.error if o else 'budget') + '); deterministic '
                             f'numeric check flagged {sum(bool(n) for n in numeric.values())} claims.',
                             {'numeric_mismatches': numeric}, o, issues=issues, run_id=run_id)
        else:
            self._record('A09', 'skipped', 'No synthesis claims to review.', run_id=run_id)

        # A12 Targeted Rechecker
        if synthesis and flagged:
            claims = synthesis['key_claims']
            o = self._ai(Task('A12', run_id, 'json', GUARD, 'These claims were flagged by review. For each, either restate '
                              'it so it is strictly supported by the cited evidence (quote numbers exactly), or withdraw it. '
                              'Return {"rechecks":[{"claim_index":int,"revised_claim":str,"evidence_ids":[...],'
                              '"verdict":"supported|unsupported|withdrawn"}]}.\nFLAGGED:' +
                              json.dumps([{'claim_index': i, 'claim': claims[i]['claim'],
                                           'cited': [by_id[e] for e in claims[i]['evidence_ids']]} for i in flagged],
                                         separators=(',', ':'), default=str),
                              priority=priority, validate=_v_recheck(known, set(flagged)), avoid=(synth_provider,)))
            if o and o.ok:
                for r in o.output['rechecks']:
                    if r['verdict'] == 'supported' and numeric_mismatches({'claim': r['revised_claim'],
                                                                           'evidence_ids': r['evidence_ids']}, by_id,
                                                                          mission_numbers):
                        r['verdict'], r['note'] = 'unsupported', 'deterministic numeric check still fails'
                self._record('A12', 'ai_cached' if o.cached else 'ai', f'{len(o.output["rechecks"])} flagged claims rechecked: '
                             f'{sum(r["verdict"] == "supported" for r in o.output["rechecks"])} now supported.',
                             o.output, o, {i for r in o.output['rechecks'] for i in r['evidence_ids']}, run_id=run_id)
            else:
                self._record('A12', 'failed', 'Recheck unavailable: ' + (o.error if o else 'budget') +
                             '; flagged claims remain marked unverified.', outcome=o, run_id=run_id)
        else:
            self._record('A12', 'skipped', 'No claims required a targeted recheck.', run_id=run_id)

        # A13 Report Writer (narrative, evidence-cited)
        accepted = []
        if synthesis:
            for i, c in enumerate(synthesis['key_claims']):
                accepted.append({'claim': c['claim'], 'evidence_ids': c['evidence_ids'],
                                 'review': 'flagged' if i in flagged else 'supported'})
        o = self._ai(Task('A13', run_id, 'narrative', GUARD.replace('Reply with one JSON object only.', '') +
                          ' Write plain prose, no markdown headings, 120-220 words.',
                          'Write the mission narrative for a scientific reader. Cite evidence IDs in square brackets, e.g. '
                          '[ev-...]. State the deterministic release action and that AI review is advisory. Mention flagged '
                          'claims only as unverified.\nCLAIMS:' + json.dumps(accepted, separators=(',', ':')) + '\nCONTEXT:' + ctx,
                          priority=priority, validate=_v_narrative(known), max_output_tokens=900))
        if o and o.ok:
            self._record('A13', 'ai_cached' if o.cached else 'ai', 'Evidence-cited narrative written.', {'narrative': o.output},
                         o, set(_CITE.findall(o.output)) & known, run_id=run_id)
        else:
            self._record('A13', 'failed', 'Narrative unavailable: ' + (o.error if o else 'budget') +
                         '; deterministic report template used alone.', outcome=o, run_id=run_id)

    def trace(self, run_id, ai_available):
        executed = [r['agent_id'] for r in self.records if r['execution'] in ('ai', 'ai_cached')]
        return {'schema': 'twinsite.agent_trace/1', 'run_id': run_id, 'method_version': METHOD_VERSION,
                'analysis_mode': 'ai', 'ai_available': ai_available, 'ai_calls_attempted': self.ai_calls,
                'ai_roles_executed': executed, 'fallback_reason': None if ai_available else self.router.disabled_reason(),
                'records': self.records, 'created_at': _now()}


def report_section(trace):
    """HTML appended to the deterministic report; everything escaped."""
    rows = ''.join(f'<tr><td>{html.escape(r["agent_id"])}</td><td>{html.escape(r["role"])}</td><td>{html.escape(r["execution"])}'
                   f'</td><td>{html.escape(((r.get("inference") or {}).get("provider") or "") + "/" + ((r.get("inference") or {}).get("model") or "")).strip("/")}'
                   f'</td><td>{html.escape(r["summary"][:300])}</td></tr>' for r in trace['records'])
    narrative = next((r['output']['narrative'] for r in trace['records'] if r['agent_id'] == 'A13' and r.get('output')), None)
    body = ('<section id="ai-analysis"><h2>AI-Powered Analysis (advisory)</h2>'
            '<p><strong>AI interpretation is advisory.</strong> Every number above comes from the deterministic engine; '
            'the release decision is the deterministic gate. AI claims cite evidence IDs and were reviewed independently '
            'where possible. This is not a scientific certification.</p>')
    if not trace['ai_available']:
        body += f'<p>AI unavailable: {html.escape(trace.get("fallback_reason") or "")}. Simple Analysis result delivered.</p>'
    if narrative:
        body += '<h3>Narrative (A13 Report Writer)</h3><p>' + html.escape(narrative).replace('\n\n', '</p><p>') + '</p>'
    body += ('<h3>Agent activity</h3><table><thead><tr><th>ID</th><th>Role</th><th>Execution</th><th>Provider/model</th>'
             '<th>Summary</th></tr></thead><tbody>' + rows + '</tbody></table></section>')
    return body


def rescore_function(payload, observations, analyze_measured, analyze_synthetic):
    """Return weights -> compact deterministic outcome, re-running the real engine on a copy."""
    def rescore(weights):
        alt = copy.deepcopy(payload)
        for feature, w in weights.items():
            alt['mission']['features'][feature]['weight'] = float(w)
        result = analyze_measured(alt, observations) if observations else analyze_synthetic(alt)
        return {'status': result.get('status'), 'feasible_portfolios': result.get('feasible_portfolio_count'),
                'sites': [{'site': s['id'], 'eligible': s['eligible'],
                           'similarity': round(s['observed_similarity'], 4) if s.get('observed_similarity') is not None else None}
                          for s in result.get('sites', [])]}
    return rescore
