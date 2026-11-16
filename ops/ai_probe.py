"""One minimal real inference probe per independent quota group (free models only).

Prints provider / env-name / model / outcome / latency / tokens. Never prints values.
Usage: python ops/ai_probe.py [--provider groq] [--vision] [--max-per-provider N]
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from twinsite.ai import adapters  # noqa: E402
from twinsite.ai.catalog import PROVIDER_BY_ID  # noqa: E402
from twinsite.ai.router import Router, parse_json  # noqa: E402
from twinsite.ai.ledger import Ledger  # noqa: E402
from twinsite.storage import load_settings  # noqa: E402

SYSTEM = 'You are a health-check endpoint. Reply with a single JSON object and nothing else.'
USER = 'Return exactly {"status":"ok","body":"Mars"}.'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--provider', action='append')
    ap.add_argument('--max-per-provider', type=int, default=99)
    ap.add_argument('--model', help='override model for this probe')
    args = ap.parse_args()
    settings = load_settings()
    router = Router(Ledger(settings.data_dir / 'ai_ledger.sqlite'))
    if not router.enabled():
        print(json.dumps({'error': router.disabled_reason()}))
        return 2
    seen, results = {}, []
    for account in router.accounts:
        provider = PROVIDER_BY_ID[account.provider]
        if provider.wire not in router.wires or (args.provider and provider.id not in args.provider):
            continue
        if account.quota_group in seen or sum(1 for r in results if r['provider'] == provider.id) >= args.max_per_provider:
            continue
        seen[account.quota_group] = True
        ok, why = router._free_tier_ok(provider, account)
        model = args.model or next(m.model for m in provider.models if 'json' in m.capabilities)
        row = {'provider': provider.id, 'account': account.key_env, 'quota_group': account.quota_group.split(':')[0]
               if provider.id == 'cloudflare' else account.key_env, 'model': model}
        if not ok:
            row.update(result='blocked', reason=why)
        else:
            started = time.time()
            try:
                extra = {'reasoning_effort': 'low'} if provider.id == 'groq' and 'gpt-oss' in model else {}
                c = router.wires[provider.wire](router._endpoint(provider, account), router._key(account), model, SYSTEM, USER,
                                                max_tokens=400, json_mode=True, timeout=60, **extra)
                value = parse_json(c.text)
                row.update(result='success' if value.get('status') == 'ok' else 'invalid_output', http_status=c.http_status,
                           latency_ms=c.latency_ms, input_tokens=c.input_tokens, output_tokens=c.output_tokens,
                           returned_model=c.model)
            except adapters.ProviderError as error:
                row.update(result='error', error=error.kind, http_status=error.status, detail=str(error)[:160])
            except ValueError as error:
                row.update(result='invalid_output', detail=str(error)[:120])
            router.ledger.record(provider=provider.id, account=account.key_env, quota_group=account.quota_group, model=model,
                                 agent_id='probe', run_id='probe', capability='json', priority='dev',
                                 outcome=row['result'], error_kind=row.get('error'), http_status=row.get('http_status'),
                                 latency_ms=row.get('latency_ms') or int((time.time() - started) * 1000),
                                 input_tokens=row.get('input_tokens'), output_tokens=row.get('output_tokens'))
        router.ledger.fact('probe:' + account.key_env, row)
        results.append(row)
        print(json.dumps(row), flush=True)
    summary = {}
    for r in results:
        s = summary.setdefault(r['provider'], {'groups': 0, 'success': 0})
        s['groups'] += 1
        s['success'] += r['result'] == 'success'
    print(json.dumps({'summary': summary}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
