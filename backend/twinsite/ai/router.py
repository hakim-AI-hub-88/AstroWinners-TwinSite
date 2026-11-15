"""Free-only AI router: capability + privacy + quota aware selection, bounded attempts,
cooldowns, circuit breakers, response cache and a usage ledger.

Ordering (from VESPER's measured lesson): MODEL is the outer loop and ACCOUNT the inner
loop within a provider, so the strongest model is tried on every quota group before a
weaker one. Providers are ordered per role so independent reviewers land on a different
provider than the claims they review.
"""
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field

from . import adapters
from .catalog import E1, PROVIDER_BY_ID, PROVIDERS, build_accounts
from .ledger import Ledger
from .secrets import SecretFileError, load_ai_secrets

DEFAULT_ORDER = ('groq', 'cloudflare', 'mistral', 'google', 'ollama', 'openrouter', 'nvidia')
VISION_ORDER = ('google', 'mistral', 'openrouter', 'nvidia', 'cloudflare')
MAX_ATTEMPTS = 3
DEMO_RESERVE_FRACTION = 0.5          # 'dev' priority (probes/tests) may only use half of each daily cap
OPENROUTER_RECHECK_S = 6 * 3600
DATA_CLASSES = ('PUBLIC_AGENCY', 'USER_UPLOAD_WITH_PROVIDER_CONSENT', 'PRIVATE_OPERATIONS_NEVER_EGRESS')


@dataclass
class Task:
    agent_id: str
    run_id: str
    capability: str                          # 'json' | 'vision' | 'narrative'
    system: str
    user: str
    images: tuple = ()                       # ((mime, bytes), ...)
    data_class: str = 'PUBLIC_AGENCY'
    consent_providers: frozenset = frozenset()
    max_output_tokens: int = 1200
    priority: str = 'mission'                # 'mission' | 'demo' | 'dev'
    validate: object = None                  # callable(obj) -> list of error strings
    prefer: tuple = ()
    avoid: tuple = ()
    use_cache: bool = True


@dataclass
class Outcome:
    ok: bool
    output: object = None
    provider: str | None = None
    model: str | None = None
    account: str | None = None
    cached: bool = False
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: list = field(default_factory=list)
    error: str | None = None

    def public(self):
        return {k: getattr(self, k) for k in ('ok', 'provider', 'model', 'account', 'cached', 'latency_ms', 'input_tokens',
                                              'output_tokens', 'attempts', 'error')}


_FENCE = re.compile(r'^```(?:json)?\s*|\s*```$', re.M)


def parse_json(text):
    text = _FENCE.sub('', text.strip())
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('no JSON object in completion')
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError('completion JSON is not an object')
    return value


class Router:
    def __init__(self, ledger, secrets=None, wires=None):
        self.ledger = ledger
        self.load_error = None
        if secrets is None:
            try:
                secrets = load_ai_secrets()
            except SecretFileError as error:
                self.load_error, secrets = str(error), {}
        self._secrets = secrets
        self.accounts = build_accounts(secrets)
        self.wires = wires or adapters.WIRES

    # ------------------------------------------------------------ state
    def disabled_reason(self):
        if os.environ.get('TWINSITE_AI_DISABLED', '').lower() in ('1', 'true', 'yes') or \
                os.environ.get('TWINSITE_AI_ENABLED', '').lower() in ('0', 'false', 'no'):
            return 'AI disabled by operator (TWINSITE_AI_DISABLED)'
        if self.load_error:
            return 'AI secret file rejected: ' + self.load_error
        if not any(a.provider != 'elevenlabs' for a in self.accounts):
            return 'No AI provider credentials are provisioned on this server'
        return None

    def enabled(self):
        return self.disabled_reason() is None

    def _key(self, account):
        return self._secrets[account.key_env]

    def _endpoint(self, provider, account):
        if provider.account_prefix:
            return provider.endpoint.replace('{account}', self._secrets[account.account_env])
        return provider.endpoint

    # ------------------------------------------------------------ selection
    def _free_tier_ok(self, provider, account):
        if provider.id != 'openrouter':
            return True, None
        fact, updated = self.ledger.fact('openrouter_free:' + account.key_env)
        if fact is None or time.time() - updated > OPENROUTER_RECHECK_S:
            try:
                _, data = adapters.get_json('https://openrouter.ai/api/v1/key', {'Authorization': 'Bearer ' + self._key(account)})
                info = data.get('data') or {}
                fact = {'is_free_tier': info.get('is_free_tier') is True, 'usage': info.get('usage')}
            except adapters.ProviderError as error:
                return False, 'free-tier check failed: ' + error.kind
            self.ledger.fact('openrouter_free:' + account.key_env, fact)
        if not fact.get('is_free_tier'):
            return False, 'account is not on the free tier (credits purchased) - closed to prevent billing'
        return True, None

    def candidates(self, task):
        capability = {'json': 'json', 'vision': 'vision', 'narrative': 'narrative'}[task.capability]
        if task.data_class not in DATA_CLASSES or task.data_class == 'PRIVATE_OPERATIONS_NEVER_EGRESS':
            return [], ['data class forbids egress']
        order = list(task.prefer) + [p for p in (VISION_ORDER if capability == 'vision' else DEFAULT_ORDER)
                                     if p not in task.prefer]
        order = [p for p in order if p not in task.avoid] + [p for p in order if p in task.avoid]
        out, skipped = [], []
        for pid in order:
            provider = PROVIDER_BY_ID[pid]
            accounts = [a for a in self.accounts if a.provider == pid]
            if task.data_class == 'USER_UPLOAD_WITH_PROVIDER_CONSENT':
                accounts = [a for a in accounts if a.egress == E1 and pid in task.consent_providers]
            random.shuffle(accounts)  # spread load across independent quota groups
            for model in sorted((m for m in provider.models if capability in m.capabilities),
                                key=lambda m: {'strong': 0, 'standard': 1, 'fast': 2}[m.tier]):
                for account in accounts:
                    cap = provider.daily_request_cap * ((1 - DEMO_RESERVE_FRACTION) if task.priority == 'dev' else 1)
                    used = self.ledger.used_today(account.quota_group, model.model if provider.per_model_quota else None)
                    if used >= cap:
                        skipped.append(f'{account.id}/{model.model}: daily cap {int(cap)} reached')
                        continue
                    for key in (account.quota_group, f'{account.quota_group}|{model.model}'):
                        ok, reason = self.ledger.available(key)
                        if not ok:
                            skipped.append(f'{account.id}/{model.model}: cooling down ({reason})')
                            break
                    else:
                        out.append((provider, model, account, used))
        # least-used quota group first within the same (provider, model) rank is already randomised
        return out, skipped

    # ------------------------------------------------------------ execution
    def _cache_key(self, task):
        h = hashlib.sha256()
        for part in (task.agent_id, task.capability, task.system, task.user):
            h.update(part.encode('utf-8'))
            h.update(b'\0')
        for _, data in task.images:
            h.update(hashlib.sha256(data).digest())
        return 'v1:' + h.hexdigest()

    def complete(self, task):
        reason = self.disabled_reason()
        if reason:
            return Outcome(False, error=reason)
        cache_key = self._cache_key(task)
        if task.use_cache:
            hit = self.ledger.cache_get(cache_key)
            if hit:
                return Outcome(True, hit['output'], hit['provider'], hit['model'], hit['account'], cached=True,
                               attempts=[{'cached_from': hit.get('at')}])
        candidates, skipped = self.candidates(task)
        outcome = Outcome(False, attempts=[{'skipped': s} for s in skipped[:6]])
        tried_groups, bad_models = set(), set()
        for provider, model, account, _used in candidates:
            if (provider.id, model.model) in bad_models:
                continue  # same model on a sibling account behaves the same: move to the next provider/model
            if len([a for a in outcome.attempts if 'provider' in a]) >= MAX_ATTEMPTS:
                break
            if account.quota_group in tried_groups:
                continue
            ok, why = self._free_tier_ok(provider, account)
            if not ok:
                self.ledger.fail(account.quota_group, why, 6 * 3600)
                outcome.attempts.append({'provider': provider.id, 'model': model.model, 'account': account.key_env,
                                         'result': 'blocked', 'reason': why})
                continue
            tried_groups.add(account.quota_group)
            attempt = {'provider': provider.id, 'model': model.model, 'account': account.key_env}
            started = time.time()
            try:
                wire = self.wires[provider.wire]
                extra = {'reasoning_effort': 'low'} if provider.id == 'groq' and 'gpt-oss' in model.model else {}
                completion = wire(self._endpoint(provider, account), self._key(account), model.model, task.system, task.user,
                                  images=task.images,
                                  # reasoning models spend output budget on thinking; give them headroom
                                  max_tokens=max(task.max_output_tokens, 3000 if provider.id == 'google' or 'gpt-oss' in model.model
                                                 or 'nemotron' in model.model else 0),
                                  json_mode=task.capability in ('json', 'vision'), timeout=60, **extra)
            except adapters.ProviderError as error:
                cooldown = {'rate_limited': error.retry_after or 120, 'auth': 6 * 3600, 'payment_required': 24 * 3600,
                            'not_found': 24 * 3600}.get(error.kind, 0)
                key = account.quota_group if error.kind in ('rate_limited', 'auth', 'payment_required') else \
                    f'{account.quota_group}|{model.model}'
                self.ledger.fail(key, str(error), cooldown)
                self.ledger.record(provider=provider.id, account=account.key_env, quota_group=account.quota_group,
                                   model=model.model, agent_id=task.agent_id, run_id=task.run_id, capability=task.capability,
                                   priority=task.priority, outcome='error', error_kind=error.kind, http_status=error.status,
                                   latency_ms=int((time.time() - started) * 1000), detail=str(error)[:200])
                if error.kind in ('timeout', 'not_found', 'bad_request', 'empty', 'policy'):
                    bad_models.add((provider.id, model.model))
                attempt.update(result='error', error=error.kind, http_status=error.status)
                outcome.attempts.append(attempt)
                continue
            try:
                value = completion.text if task.capability == 'narrative' else parse_json(completion.text)
                problems = task.validate(value) if task.validate else []
            except (ValueError, json.JSONDecodeError) as error:
                value, problems = None, [f'unparseable JSON: {str(error)[:80]}']
            row = dict(provider=provider.id, account=account.key_env, quota_group=account.quota_group, model=model.model,
                       agent_id=task.agent_id, run_id=task.run_id, capability=task.capability, priority=task.priority,
                       http_status=completion.http_status, latency_ms=completion.latency_ms,
                       input_tokens=completion.input_tokens, output_tokens=completion.output_tokens)
            if problems:
                self.ledger.record(**row, outcome='invalid_output', error_kind='schema', detail='; '.join(problems)[:200])
                self.ledger.fail(f'{account.quota_group}|{model.model}', 'invalid structured output', 0)
                bad_models.add((provider.id, model.model))
                attempt.update(result='invalid_output', problems=problems[:4])
                outcome.attempts.append(attempt)
                continue
            self.ledger.record(**row, outcome='success')
            self.ledger.ok(account.quota_group)
            self.ledger.ok(f'{account.quota_group}|{model.model}')
            attempt.update(result='success', latency_ms=completion.latency_ms)
            outcome.attempts.append(attempt)
            if task.use_cache:
                self.ledger.cache_put(cache_key, {'output': value, 'provider': provider.id, 'model': model.model,
                                                  'account': account.key_env, 'at': time.time()})
            return Outcome(True, value, provider.id, model.model, account.key_env, False, completion.latency_ms,
                           completion.input_tokens, completion.output_tokens, outcome.attempts)
        if not candidates:
            outcome.error = 'No eligible free provider: ' + ('; '.join(skipped[:3]) or 'no account supports this capability/privacy class')
        else:
            outcome.error = 'All attempted free providers failed: ' + ', '.join(
                f"{a['provider']}={a.get('error') or a.get('result')}" for a in outcome.attempts if 'provider' in a)
        return outcome

    # ------------------------------------------------------------ status
    def status(self):
        usage = self.ledger.summary()
        probes = self.ledger.facts('probe:')
        providers = []
        for provider in PROVIDERS:
            accounts = [a for a in self.accounts if a.provider == provider.id]
            groups = sorted({a.quota_group for a in accounts})
            verified = usage.get(provider.id, {}).get('verified', [])
            probe = {k.split(':', 1)[1]: v['value'] | {'at': v['updated']} for k, v in probes.items()
                     if v['value'].get('provider') == provider.id}
            if not accounts:
                state = 'not_provisioned'
            elif verified:
                state = 'inference_verified'
            elif any(p.get('result') == 'error' for p in probe.values()):
                state = 'temporarily_unavailable'
            else:
                state = 'migrated'
            providers.append({
                'id': provider.id, 'name': provider.name, 'state': state, 'free_eligible': bool(accounts),
                'accounts': len(accounts), 'quota_groups': len(groups), 'quota_scope': provider.quota_scope,
                'daily_request_cap_per_group': provider.daily_request_cap,
                'models': [{'model': m.model, 'capabilities': sorted(m.capabilities), 'tier': m.tier} for m in provider.models],
                'private_data_eligible_accounts': sum(1 for a in accounts if a.egress == E1),
                'billing_basis': provider.billing_basis, 'data_policy': provider.data_policy,
                'verified_models': sorted({v['model'] for v in verified}),
                'calls_today': usage.get(provider.id, {}).get('calls_today', 0),
                'outcomes': usage.get(provider.id, {}).get('outcomes', {}),
                'probes': list(probe.values()),
            })
        return {'enabled': self.enabled(), 'disabled_reason': self.disabled_reason(), 'paid_inference': 'forbidden',
                'max_attempts_per_task': MAX_ATTEMPTS, 'dev_reserve_fraction': DEMO_RESERVE_FRACTION,
                'providers': providers, 'open_breakers': self.ledger.breakers()}


_ROUTER = None


def default_router(data_dir):
    global _ROUTER
    if _ROUTER is None or _ROUTER.ledger.path != str(data_dir / 'ai_ledger.sqlite'):
        _ROUTER = Router(Ledger(data_dir / 'ai_ledger.sqlite'))
    return _ROUTER
