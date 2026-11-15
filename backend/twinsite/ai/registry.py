"""AI registry facade: the 13 roles, the free-only policy and live provider state."""
from .agents import ROLES as _ROLES

POLICY = {
    'pricing_mode': 'free_only_hard_block',
    'allow_billable_fallback': False,
    'default_analysis_mode': 'ai',
    'fallback': 'simple_analysis_deterministic_engine',
    'max_ai_calls_per_mission': 7,
    'max_attempts_per_llm_task_including_all_fallbacks': 3,
    'ai_may_modify_measurements_scores_or_release': False,
}
ROLES = tuple({'agent_id': a, 'name': n, 'phase': p, 'kind': k, 'purpose': d} for a, n, p, k, d in _ROLES)


def router(settings=None):
    from twinsite.storage import load_settings
    from .router import default_router
    return default_router((settings or load_settings()).data_dir)


def ai_enabled(settings=None):
    return router(settings).enabled()


def registry(settings=None):
    r = router(settings)
    return {'ai_enabled': r.enabled(), 'policy': dict(POLICY), 'roles': list(ROLES), 'providers': r.status()}
