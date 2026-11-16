#############################################################################
# AI BRIDGE (Flask side -> TwinSite free-only multi-provider router)
#
# Why this file exists:
#   One place where the web app asks a language model for text. It reuses the
#   platform's router (backend/twinsite/ai): free tiers only (Groq, Cloudflare,
#   Google, Mistral, OpenRouter, NVIDIA, Ollama), bounded attempts, cooldowns,
#   circuit breakers, response cache and a usage ledger shared with the worker.
#
# Keys: process environment or the owner-only file named by
#   TWINSITE_AI_SECRET_ENV_FILE (read by twinsite.ai.secrets). Values never
#   leave the router: nothing here returns, logs or serialises a key or even
#   the name of the account that answered.
#
# Contract (docs/INTEGRATION_SPEC.md):
#   complete_text(system, user, json_mode=False, purpose="narrative")
#       -> {"status": "ok"|"unavailable", "text", "provider", "model", "reason"}
#          (+ "data" with the parsed object when json_mode, "cached", "latency_ms")
#   status() -> {"enabled", "reason", "providers": [{id, name, configured, ...}]}
#   Neither function raises.
#############################################################################
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()
_ROUTER = None
_ROUTER_ERROR = None


def data_dir() -> Path:
    """Runtime folder shared with the platform (ledger, cache). Same default as twinsite.storage."""
    return Path(os.environ.get("TWINSITE_DATA_DIR") or APP_ROOT / ".runtime")


def set_router(router) -> None:
    """Inject a router (tests) or reset with None (next call rebuilds from env / secret file)."""
    global _ROUTER, _ROUTER_ERROR
    with _LOCK:
        _ROUTER, _ROUTER_ERROR = router, None


def _router():
    global _ROUTER, _ROUTER_ERROR
    with _LOCK:
        if _ROUTER is None and _ROUTER_ERROR is None:
            try:
                from twinsite.ai.ledger import Ledger
                from twinsite.ai.router import Router
                folder = data_dir()
                folder.mkdir(parents=True, exist_ok=True)
                _ROUTER = Router(Ledger(folder / "ai_ledger.sqlite"))
            except Exception as exc:  # noqa: BLE001 - AI is optional; the app must keep working
                _ROUTER_ERROR = f"AI router could not start ({exc.__class__.__name__})"
                log.warning("ai_bridge: %s", _ROUTER_ERROR)
        return _ROUTER


def _unavailable(reason: str) -> dict:
    return {"status": "unavailable", "text": "", "provider": None, "model": None, "reason": reason}


def complete_text(system: str, user: str, json_mode: bool = False, purpose: str = "narrative",
                  max_tokens: int = 1200, validate=None, use_cache: bool = True) -> dict:
    """Ask the first healthy free provider. `validate(obj) -> [problems]` (JSON mode) lets the router
    move to another provider when an answer is structurally unusable."""
    router = _router()
    if router is None:
        return _unavailable(_ROUTER_ERROR or "AI router unavailable")
    try:
        reason = router.disabled_reason()
        if reason:
            return _unavailable(reason)
        from twinsite.ai.router import Task
        task = Task(agent_id=f"flask-{purpose}"[:40], run_id="flask", capability="json" if json_mode else "narrative",
                    system=system, user=user, max_output_tokens=max_tokens, priority="demo",
                    validate=validate if json_mode else None, use_cache=use_cache)
        outcome = router.complete(task)
    except Exception as exc:  # noqa: BLE001 - never raise to callers
        log.warning("ai_bridge: completion error %s", exc.__class__.__name__)
        return _unavailable(f"AI call failed ({exc.__class__.__name__})")
    if not outcome.ok:
        return _unavailable(outcome.error or "No free provider answered")
    out = {"status": "ok", "provider": outcome.provider, "model": outcome.model, "reason": None,
           "cached": bool(outcome.cached), "latency_ms": outcome.latency_ms}
    if json_mode:
        out["data"] = outcome.output
        out["text"] = json.dumps(outcome.output, ensure_ascii=False)
    else:
        out["text"] = str(outcome.output or "").strip()
    return out


def provider_label(result: dict) -> str:
    """Human label of who answered, e.g. 'Groq · openai/gpt-oss-120b'."""
    from twinsite.ai.catalog import PROVIDER_BY_ID
    p = PROVIDER_BY_ID.get(result.get("provider") or "")
    return f"{p.name if p else result.get('provider')} · {result.get('model')}"


def status() -> dict:
    """Configured providers (names and counts only, never key values or account names)."""
    router = _router()
    if router is None:
        return {"enabled": False, "reason": _ROUTER_ERROR or "AI router unavailable", "providers": [],
                "paid_inference": "forbidden"}
    try:
        st = router.status()
    except Exception as exc:  # noqa: BLE001
        return {"enabled": False, "reason": f"AI status unavailable ({exc.__class__.__name__})", "providers": [],
                "paid_inference": "forbidden"}
    providers = []
    for p in st.get("providers", []):
        if p.get("id") == "elevenlabs":
            continue                              # speech only, not used for text
        providers.append({
            "id": p["id"], "name": p["name"], "configured": bool(p.get("accounts")),
            "quota_groups": p.get("quota_groups", 0), "state": p.get("state"),
            "models": [m["model"] for m in p.get("models", [])],
            "calls_today": p.get("calls_today", 0), "daily_request_cap_per_group": p.get("daily_request_cap_per_group"),
        })
    return {"enabled": bool(st.get("enabled")), "reason": st.get("disabled_reason"),
            "paid_inference": "forbidden", "configured_count": sum(1 for p in providers if p["configured"]),
            "providers": providers, "open_breakers": len(st.get("open_breakers") or [])}
