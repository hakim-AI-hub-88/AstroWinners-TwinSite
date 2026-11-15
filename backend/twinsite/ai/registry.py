"""Optional AI router — DETERMINISTIC STUB. No provider is wired; no network calls.

All 13 agent roles stay registered with their deterministic implementations.
Inference is hard-disabled: no paid fallback exists, quotas are UNKNOWN until a
deployment verifies free entitlement, and AI never produces measurements,
weights, eligibility or portfolios. Default templates/validation never need it.
"""
from dataclasses import asdict, dataclass

POLICY = {
    'pricing_mode': 'free_only_hard_block',
    'allow_billable_fallback': False,
    'default_inference_enabled': False,
    'demo_reserve_fraction': 0.6,
    'max_active_llm_requests': 1,
    'max_optional_llm_calls_per_mission': 4,
    'max_attempts_per_llm_task_including_all_fallbacks': 2,
    'quota_measurement_status': 'UNKNOWN_UNTIL_DEPLOYMENT',
    'fallback': 'deterministic_science_and_report_templates',
}


@dataclass(frozen=True)
class Role:
    agent_id: str
    name: str
    phase: str
    deterministic_implementation: str
    call_policy: str


ROLES = (
    Role('A01', 'Source Curator', 'P10', 'Deterministic NASA/ESA connectors (C1)', 'exception_only'),
    Role('A02', 'Visual Interpreter', 'P20', 'Product-specific sensor decoders (C1)', 'conditional_and_consent_required_for_user_uploads'),
    Role('A03', 'Cleaning Planner', 'P30', 'Allowlisted rule engine', 'exception_only'),
    Role('A04', 'Quality Reviewer', 'P40', 'Hard QA gates and predicates', 'exception_only'),
    Role('A05', 'Scenario Estimator', 'P50', 'User inputs and documented formulas', 'optional_no_fabrication'),
    Role('A06', 'Domain Analyst', 'P60', 'Deterministic comparison engine (C2)', 'exception_only_partitioned'),
    Role('A07', 'Synthesis Analyst', 'P70', 'Deterministic evidence aggregation', 'optional'),
    Role('A08', 'Process Auditor', 'P80', 'Orchestrator event-graph assertions', 'zero_inference'),
    Role('A09', 'Evidence Reviewer', 'P80', 'Claim-to-evidence consistency tests', 'one_call_only_if_needed'),
    Role('A10', 'Portfolio Reviewer', 'P80', 'Deterministic constraint and robustness recheck', 'zero_inference'),
    Role('A11', 'Release Judge', 'P80', 'Deterministic release policy (evidence sidecar)', 'zero_inference'),
    Role('A12', 'Targeted Rechecker', 'P80', 'Focused deterministic replay', 'exception_only_one_recheck'),
    Role('A13', 'Report Writer', 'P90', 'Deterministic evidence-backed HTML template', 'at_most_one_call'),
)


def route(agent_id):
    """Every route resolves to the deterministic implementation while inference is disabled."""
    role = next((r for r in ROLES if r.agent_id == agent_id), None)
    if role is None:
        raise KeyError(agent_id)
    return {'agent_id': role.agent_id, 'execution': 'deterministic', 'provider': None,
            'reason': 'INFERENCE_DISABLED: no verified free entitlement/quota; deterministic implementation used.'}


def ai_enabled():
    return False


def registry():
    return {'ai_enabled': ai_enabled(), 'policy': dict(POLICY), 'roles': [asdict(r) for r in ROLES]}
