"""Typed provider/account/model catalog. References environment-variable NAMES only.

Accounts are discovered from whatever credential names are present, so keys rotate or
are added without code changes (e.g. GROQ_API_KEY_FOO registers a new Groq account).

Billing basis: every provider here is used ONLY on a free allowance. Evidence is
recorded per provider; where the API itself can confirm it (OpenRouter /key reports
is_free_tier) the router re-checks at runtime and fails closed. Paid inference has no
code path: there is no paid model in this catalog and HTTP 402 opens the breaker.

Egress: E1_PRIVATE providers may receive user uploads WITH provider-specific consent;
E2_PUBLIC providers (free tiers that train on inputs) receive public agency data only.
Corrections vs VESPER provider_supply.toml: google-navigator/briefer, openrouter-auditor
and nvidia-researcher were labelled E1 there although the same file states those
providers are public-only; they are E2 here. GOOGLE_API_KEY_SCHOLAR does not exist and
is not referenced. Groq/Mistral E1 status rests on owner-confirmed account settings
recorded only for the primary keys, so additional keys are E2 until confirmed.
"""
from dataclasses import dataclass, field

E1, E2 = 'E1_PRIVATE', 'E2_PUBLIC'


@dataclass(frozen=True)
class Model:
    model: str
    capabilities: frozenset
    tier: str = 'standard'          # 'strong' | 'standard' | 'fast'


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    wire: str
    endpoint: str
    key_prefix: str
    models: tuple
    daily_request_cap: int          # TwinSite's own ceiling per quota group, kept under the free allowance
    quota_scope: str                # what one quota group is
    egress_primary: str
    egress_additional: str
    billing_basis: str
    data_policy: str
    account_prefix: str = ''
    per_model_quota: bool = False   # Google: unit is (project, model)


TEXT, JSON, VISION, NARRATIVE, IMAGE_GEN, TTS = 'text', 'json', 'vision', 'narrative', 'image_generation', 'speech'

PROVIDERS = (
    Provider('groq', 'Groq', 'openai_chat', 'https://api.groq.com/openai/v1/chat/completions', 'GROQ_API_KEY',
             (Model('openai/gpt-oss-120b', frozenset({TEXT, JSON, NARRATIVE}), 'strong'),
              Model('qwen/qwen3.8-27b', frozenset({TEXT, JSON, NARRATIVE}), 'standard')),
             60, 'one Groq organization per key (VESPER owner allocation: one account per subsystem)', E1, E2,
             'Free plan, no payment method attached (VESPER provider_supply hard_cap_evidence); free tier refuses at its ceiling.',
             'Primary account: Zero Data Retention confirmed by owner 2026-08-25. Others unconfirmed -> public data only.'),
    Provider('cloudflare', 'Cloudflare Workers AI', 'openai_chat',
             'https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions', 'CLOUDFLARE_API_TOKEN',
             (Model('@cf/openai/gpt-oss-120b', frozenset({TEXT, JSON, NARRATIVE}), 'strong'),
              Model('@cf/meta/llama-4-scout-17b-16e-instruct', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'standard')),
             40, 'one Cloudflare account (10,000 neurons/day shared across all models and modalities)', E1, E1,
             'Workers AI free allocation on accounts with no payment method (VESPER evidence); usage fields unreliable, so TwinSite caps requests far below the neuron pool.',
             'Cloudflare terms: customer content is not used for training.', account_prefix='CLOUDFLARE_ACCOUNT_ID'),
    Provider('google', 'Google Gemini API', 'google_generate',
             'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent', 'GOOGLE_API_KEY',
             (Model('gemini-3.6-flash', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'strong'),
              Model('gemini-3.5-flash-lite', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'fast')),
             15, 'one Google Cloud project; quota unit is (project, model) at ~20 requests/day (measured by VESPER)', E2, E2,
             'Unpaid tier, no billing account (VESPER evidence: 429 GenerateRequestsPerDayPerProjectPerModel-FreeTier).',
             'Unpaid tier may use inputs to improve products: PUBLIC AGENCY DATA ONLY, never user uploads.',
             per_model_quota=True),
    Provider('openrouter', 'OpenRouter (free models only)', 'openai_chat', 'https://openrouter.ai/api/v1/chat/completions',
             'OPENROUTER_API_KEY',
             (Model('nvidia/nemotron-3.5-super-vl:free', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'strong'),
              Model('google/gemma-4-31b-it:free', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'standard'),
              Model('nvidia/nemotron-3-ultra-550b-a55b:free', frozenset({TEXT, JSON, NARRATIVE}), 'strong')),
             40, 'one OpenRouter account (~50 free requests/day without purchased credits)', E2, E2,
             'Only ":free" model IDs are allowed; /api/v1/key must report is_free_tier=true at runtime or the account is closed.',
             'Free endpoints require consent to provider training: PUBLIC AGENCY DATA ONLY.'),
    Provider('mistral', 'Mistral', 'openai_chat', 'https://api.mistral.ai/v1/chat/completions', 'MISTRAL_API_KEY',
             (Model('mistral-medium-latest', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'strong'),
              Model('mistral-small-latest', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'standard')),
             60, 'one Mistral workspace per key (VESPER per-subsystem allocation)', E1, E2,
             'Free (Experiment) plan with no card attached (VESPER evidence); refuses rather than bills.',
             'Primary workspace: training opt-out confirmed by owner 2026-08-25; free tier defaults into training otherwise.'),
    Provider('nvidia', 'NVIDIA NIM', 'openai_chat', 'https://integrate.api.nvidia.com/v1/chat/completions', 'NVIDIA_NIM_API_KEY',
             (Model('nvidia/nemotron-3-ultra-550b-a55b', frozenset({TEXT, JSON, NARRATIVE}), 'strong'),
              Model('nvidia/nemotron-3.5-super-vl-120b-a12b', frozenset({TEXT, JSON, NARRATIVE, VISION}), 'strong')),
             20, 'one NVIDIA developer account (~1,000 trial credits)', E2, E2,
             'Developer trial credits, no card attached (VESPER evidence); refuses at the ceiling.',
             'No-training claim not contractually confirmed: PUBLIC AGENCY DATA ONLY.'),
    Provider('ollama', 'Ollama Cloud', 'openai_chat', 'https://ollama.com/v1/chat/completions', 'OLLAMA_API_KEY',
             (Model('gpt-oss:120b', frozenset({TEXT, JSON, NARRATIVE}), 'strong'),
              Model('gemma4:31b', frozenset({TEXT, JSON, NARRATIVE}), 'standard')),
             30, 'one Ollama account (unpublished "light usage" GPU-time window)', E1, E1,
             'Free plan, no payment method (VESPER evidence); quota unpublished, used opportunistically.',
             'Ollama publishes no logging, no training and zero retention for cloud models.'),
    Provider('elevenlabs', 'ElevenLabs (speech only)', 'elevenlabs_tts', 'https://api.elevenlabs.io/v1/text-to-speech/{voice}',
             'ELEVENLABS_API_KEY', (Model('eleven_multilingual_v2', frozenset({TTS}), 'standard'),),
             10, 'one ElevenLabs account (free character allowance)', E1, E1,
             'Free plan accounts (VESPER evidence). Only invoked by an explicit audio feature; TwinSite has none enabled.',
             'Speech text is egress; only report narration of public results would be sent.'),
)
PROVIDER_BY_ID = {p.id: p for p in PROVIDERS}


@dataclass(frozen=True)
class Account:
    id: str                 # e.g. groq:GROQ_API_KEY_CHOOSER  (env name, never the value)
    provider: str
    key_env: str
    account_env: str | None
    quota_group: str
    egress: str
    private_ok: bool = field(default=False)


def build_accounts(secrets):
    """Accounts for every credential name present. Cloudflare tokens group by account id."""
    accounts = []
    cf_groups = {}
    for provider in PROVIDERS:
        names = sorted(n for n in secrets if n == provider.key_prefix or n.startswith(provider.key_prefix + '_'))
        for name in names:
            suffix = name[len(provider.key_prefix):]
            account_env = None
            if provider.account_prefix:
                account_env = provider.account_prefix + suffix
                if account_env not in secrets:
                    continue
                group = cf_groups.setdefault(secrets[account_env], f'cloudflare#{len(cf_groups) + 1}')
            else:
                group = f'{provider.id}:{name}'
            primary = suffix == ''
            egress = provider.egress_primary if primary else provider.egress_additional
            accounts.append(Account(f'{provider.id}:{name}', provider.id, name, account_env, group, egress, egress == E1))
    return accounts
