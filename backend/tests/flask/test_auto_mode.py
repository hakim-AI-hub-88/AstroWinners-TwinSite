"""Agentic Auto Mode + AI bridge tests (Flask test client, no network, no real AI).

Run: python -m unittest discover -s backend/tests/flask -p 'test_auto_*.py'
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
for p in (str(ROOT / "backend"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Hermetic environment BEFORE the app is imported: no real keys, private runtime dir, dead platform API.
_TMP = tempfile.mkdtemp(prefix="twinsite-auto-test-")
for _name in list(os.environ):
    if _name.startswith(("GROQ_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_NIM_API_KEY",
                         "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "OLLAMA_API_KEY", "ELEVENLABS_API_KEY")) \
            or _name == "TWINSITE_AI_SECRET_ENV_FILE":
        os.environ.pop(_name)
os.environ["TWINSITE_DATA_DIR"] = _TMP
os.environ["TWINSITE_API_URL"] = "http://127.0.0.1:9"      # discard port: connection refused
os.environ.pop("TWINSITE_AI_ENABLED", None)
os.environ.pop("TWINSITE_AI_DISABLED", None)

from app import create_app  # noqa: E402
from services import ai_bridge, assistant, auto_mode, report  # noqa: E402
from twinsite.ai import adapters  # noqa: E402
from twinsite.ai.ledger import Ledger  # noqa: E402
from twinsite.ai.router import Router  # noqa: E402

SENTINELS = {"GROQ_API_KEY": "SENTINEL-GROQ-VALUE-123", "MISTRAL_API_KEY_B": "SENTINEL-MISTRAL-456",
             "CLOUDFLARE_API_TOKEN": "SENTINEL-CF-789", "CLOUDFLARE_ACCOUNT_ID": "SENTINEL-ACCT-000"}


def fake_router(text_fn):
    """Router over fake wires: text_fn(model, system, user) -> completion text (or an Exception to raise)."""
    def wire(endpoint, key, model, system, user, **kw):
        out = text_fn(model, system, user)
        if isinstance(out, Exception):
            raise out
        return adapters.Completion(out, model, 200, 10, 5, 3)
    d = Path(tempfile.mkdtemp(dir=_TMP))
    return Router(Ledger(d / "l.sqlite"), dict(SENTINELS), {"openai_chat": wire, "google_generate": wire})


def fake_analysis(planet, location, rover_mode, max_slope, zone, cleaning="standard"):
    return {"zone": {"full_name": f"Zone {zone}"}, "score": 80.5, "confidence": 0.9,
            "method": {"cells_scored": 123, "features_used": ["slope", "albedo"], "features_skipped": []},
            "validation": {"summary": {"evaluated": 2}},
            "ranking": [{"rank": 1, "lat": -23.1, "lon": -68.2, "score": 80.5, "confidence": 0.9, "accessible_pct": 72,
                         "refined": {"lat": -23.11, "lon": -68.21}, "explanation": {"matches": ["slope"], "differs": ["albedo"]}}]}


def _frame(n):
    """Small harmonized-shaped frame (coordinates, every feature, quality flags) for mocked loaders."""
    import pandas as pd
    from utils import config
    cols = {"latitude": [10.0 + i * 0.1 for i in range(n)], "longitude": [20.0 + i * 0.1 for i in range(n)]}
    cols.update({f: [0.2 + 0.05 * (i % 5) for i in range(n)] for f in config.FEATURES})
    cols[config.QUALITY_COLUMN] = [0] * n
    return pd.DataFrame(cols)


def wait_done(mid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        m = auto_mode.get(mid)
        if m and m["state"] != "running":
            return m
        time.sleep(0.1)
    raise AssertionError(f"mission {mid} did not finish")


class AutoModeApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app(preload=False).test_client()

    def tearDown(self):
        ai_bridge.set_router(None)

    # ------------------------------------------------------------ validation
    def test_input_validation(self):
        bad = [
            ("not json", None),
            ({}, "target"),
            ({"target": {"planet": "venus", "location": "x"}}, "planet"),
            ({"target": {"planet": "mars", "location": "Atlantis"}}, "Unknown location"),
            ({"target": {"planet": "mars", "lat": 95, "lon": 10}}, "lat"),
            ({"target": {"planet": "moon", "lat": 10, "lon": "east"}}, "lon"),
            ({"target": {"planet": "moon", "lat": 10, "lon": 20, "radius_km": 70}}, "radius_km"),
            ({"target": {"planet": "mars", "location": "Gale Crater"}, "objective": "party"}, "objective"),
            ({"target": {"planet": "mars", "location": "Gale Crater"}, "slope_limit": 80}, "slope_limit"),
            ({"target": {"planet": "mars", "location": "Gale Crater"}, "zones": ["sahara"]}, "zones"),
            ({"target": {"planet": "mars", "location": "Gale Crater"}, "data_mode": "magic"}, "data_mode"),
            ({"target": {"planet": "mars", "location": "Gale Crater"}, "cleaning": "bleach"}, "cleaning"),
            ({"target": {"planet": "mars", "location": "Gale Crater"}, "ai": "yes"}, "ai"),
        ]
        for body, word in bad:
            with self.subTest(body=body):
                r = self.client.post("/api/auto/missions", data=body) if isinstance(body, str) else \
                    self.client.post("/api/auto/missions", json=body)
                self.assertEqual(r.status_code, 400, r.get_json())
                if word:
                    self.assertIn(word, r.get_json()["message"])

    def test_unknown_mission_404(self):
        self.assertEqual(self.client.get("/api/auto/missions/am-000000000000").status_code, 404)
        self.assertEqual(self.client.get("/api/auto/missions/../../etc").status_code, 404)

    def test_concurrency_cap(self):
        with mock.patch.dict(auto_mode._ACTIVE, {f"am-{i:012x}": mock.Mock(is_alive=lambda: True) for i in range(5)}):
            r = self.client.post("/api/auto/missions", json={"target": {"planet": "mars", "location": "Gale Crater"}})
        self.assertEqual(r.status_code, 429)

    # ------------------------------------------------------------ lifecycle, platform API down
    def test_lifecycle_platform_down(self):
        with mock.patch.object(auto_mode, "run_analysis", side_effect=fake_analysis), \
                mock.patch("services.data_loader.LOADERS", {"mars": lambda: _frame(10), "moon": lambda: _frame(10)}), \
                mock.patch("services.data_loader.load_zone", lambda z, role: _frame(5)), \
                mock.patch.object(auto_mode, "build_report", return_value={
                    "facts": {"recommended_zone": "Zone atacama"}, "maps": {},
                    "narrative": {"executive_summary": "x", "generated_by": "fallback"}}):
            r = self.client.post("/api/auto/missions", json={
                "target": {"planet": "mars", "location": "Jezero Crater"}, "objective": "rover_test",
                "data_mode": "auto", "ai": False})
            self.assertEqual(r.status_code, 202, r.get_json())
            mid = r.get_json()["mission_id"]
            m = wait_done(mid)
        steps = {s["id"]: s for s in m["steps"]}
        self.assertEqual(m["state"], "completed")
        for sid in ("plan", "acquire", "analyze", "report"):
            self.assertEqual(steps[sid]["state"], "completed", steps[sid])
        self.assertIn(steps["clean"]["state"], ("completed", "skipped"))
        self.assertEqual(steps["agents"]["state"], "failed")
        self.assertIn("not reachable", steps["agents"]["detail"])
        self.assertEqual(m["result"]["live_evidence"]["status"], "unavailable")
        self.assertTrue(m["options"]["rover_mode"])
        self.assertEqual(m["result"]["top_regions"][0]["score"], 80.5)
        self.assertEqual(m["result"]["agents"], [])
        for s in m["steps"]:
            self.assertIsNotNone(s["finished"])
        # persisted + listed + served
        self.assertTrue((Path(_TMP) / "auto" / f"{mid}.json").is_file())
        listed = self.client.get("/api/auto/missions").get_json()["missions"]
        self.assertIn(mid, [x["mission_id"] for x in listed])
        body = self.client.get(f"/api/auto/missions/{mid}").get_json()
        self.assertNotIn("pid", body)

    def _platform_mission(self, status, records, pending):
        """Run a mission against a mocked platform API returning `status` and an agent trace."""
        def get_json(path, timeout=20.0):
            if path.endswith("/agents"):
                return 200, {"records": records, "pending": pending, "analysis_mode": "ai"}
            if "/events" in path:
                return 200, [{"sequence": 1, "phase": "P10", "state": "running", "summary": "acquire"}]
            if path.endswith("/result"):
                return 200, {"sites": [{"id": "earth-1", "name": "Site One", "eligible": True,
                                        "observed_similarity": 0.91, "coverage": 1.0}], "limitations": ["l1"]}
            return 200, {"status": status, "error": "WORKER_CRASH: boom" if status == "failed" else None}

        def boom(*a, **k):
            raise FileNotFoundError("dataset missing")
        with mock.patch.object(auto_mode, "_post_json", return_value=(202, {"run_id": "run-x", "prerank": []})), \
                mock.patch.object(auto_mode, "_get_json", side_effect=get_json), \
                mock.patch.object(auto_mode, "POLL_S", 0.01), \
                mock.patch("services.data_loader.LOADERS", {"mars": boom, "moon": boom}), \
                mock.patch("services.data_loader.load_zone", boom):
            r = self.client.post("/api/auto/missions", json={"target": {"planet": "mars", "lat": 18.4, "lon": 77.6}})
            return wait_done(r.get_json()["mission_id"], timeout=10)

    def test_agents_step_reports_platform_failure_fast(self):
        t0 = time.time()
        m = self._platform_mission("failed", [], True)
        agents = next(s for s in m["steps"] if s["id"] == "agents")
        self.assertLess(time.time() - t0, 8)
        self.assertEqual(agents["state"], "failed")
        self.assertIn("WORKER_CRASH", agents["detail"])

    def test_agents_trace_stored_without_account_names(self):
        rec = {"agent_id": "A06", "role": "Domain Analyst", "phase": "P60", "execution": "ai", "summary": "9 findings",
               "agent_result": {"status": "completed"},
               "inference": {"ok": True, "provider": "groq", "model": "m1", "account": "GROQ_API_KEY_X", "latency_ms": 5}}
        m = self._platform_mission("completed_with_limits", [rec], False)
        agents = next(s for s in m["steps"] if s["id"] == "agents")
        self.assertEqual(agents["state"], "completed", agents)
        self.assertEqual(m["state"], "completed")
        a = m["result"]["agents"][0]
        self.assertEqual((a["agent_id"], a["execution"], a["outcome"], a["provider"]), ("A06", "ai", "completed", "groq"))
        self.assertEqual(m["result"]["platform"]["top_sites"][0]["name"], "Site One")
        self.assertEqual(m["result"]["links"]["console"], "/console/analysis/run-x")
        raw = (Path(_TMP) / "auto" / f"{m['mission_id']}.json").read_text()
        self.assertNotIn("GROQ_API_KEY", raw)

    def test_mission_fails_honestly_without_any_data(self):
        def boom(*a, **k):
            raise FileNotFoundError("dataset missing")
        with mock.patch("services.data_loader.LOADERS", {"mars": boom, "moon": boom}), \
                mock.patch("services.data_loader.load_zone", boom):
            r = self.client.post("/api/auto/missions", json={"target": {"planet": "moon", "location": "Apollo 15"}})
            m = wait_done(r.get_json()["mission_id"])
        steps = {s["id"]: s["state"] for s in m["steps"]}
        self.assertEqual(m["state"], "failed")
        self.assertEqual(steps["acquire"], "failed")
        self.assertIn(steps["analyze"], ("skipped", "failed"))
        self.assertEqual(steps["agents"], "failed")
        self.assertEqual(steps["report"], "skipped")
        self.assertTrue(m["error"])

    def test_interrupted_mission_reconciled(self):
        mid = "am-abcdefabcdef"
        m = {"mission_id": mid, "state": "running", "created": "2026-01-01T00:00:00Z", "pid": 999999999,
             "options": auto_mode.validate({"target": {"planet": "mars", "location": "Gale Crater"}}),
             "steps": [{"id": i, "label": l, "state": "running" if i == "plan" else "pending", "started": None,
                        "finished": None, "duration_s": None, "detail": None} for i, l in auto_mode.STEPS],
             "result": {}, "error": None}
        auto_mode._save(m)
        got = self.client.get(f"/api/auto/missions/{mid}").get_json()
        self.assertEqual(got["state"], "failed")
        self.assertIn("restart", got["error"])

    # ------------------------------------------------------------ AI status never leaks values
    def test_ai_status_never_leaks_values(self):
        ai_bridge.set_router(fake_router(lambda *a: "unused"))
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": SENTINELS["GROQ_API_KEY"]}):
            for url in ("/api/ai/status", "/api/assistant/status"):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                raw = r.get_data(as_text=True)
                for value in SENTINELS.values():
                    self.assertNotIn(value, raw)
                self.assertNotIn("GROQ_API_KEY", raw)       # not even account names
        body = self.client.get("/api/ai/status").get_json()
        self.assertTrue(body["enabled"])
        ids = {p["id"]: p["configured"] for p in body["providers"]}
        self.assertTrue(ids["groq"] and ids["mistral"] and ids["cloudflare"])
        self.assertFalse(ids["google"])

    def test_ai_status_unconfigured(self):
        ai_bridge.set_router(Router(Ledger(Path(tempfile.mkdtemp(dir=_TMP)) / "l.sqlite"), {}))
        body = self.client.get("/api/ai/status").get_json()
        self.assertFalse(body["enabled"])
        self.assertIn("No AI provider", body["reason"])
        res = ai_bridge.complete_text("s", "u")
        self.assertEqual(res["status"], "unavailable")
        self.assertTrue(res["reason"])


class AiBridgeConsumersTest(unittest.TestCase):
    def tearDown(self):
        ai_bridge.set_router(None)

    FACTS = {"target": {"site": "Jezero Crater", "body": "mars"},
             "zones": {"atacama": {"name": "Atacama Desert (Chile)", "best_score": 86.8, "confidence_pct": 90,
                                   "cells_scored": 2114, "top_regions": [], "score_range": [12.3, 86.8]}},
             "known_limits": ["Resolution ~11 km for scoring"]}

    def _narr(self, summary, findings):
        return json.dumps({"executive_summary": summary, "key_findings": findings, "recommendations": ["Go."],
                           "risks": ["Heat."], "conclusion": "Done."})

    def test_report_narrative_anchored(self):
        ai_bridge.set_router(fake_router(lambda *a: self._narr(
            "Atacama scores 86.8 / 100 over 2114 cells at ~11 km.", ["Confidence 90 %.", "Invented 42.7 kelvin gap."])))
        out = report.narrative(self.FACTS, use_ai=True)
        self.assertNotEqual(out.get("generated_by"), "fallback")
        self.assertIn("Groq", out["generated_by"])
        self.assertEqual(out["key_findings"], ["Confidence 90 %."])
        self.assertEqual(out["numeric_check"]["removed_items"][0]["numbers"], ["42.7"])

    def test_report_narrative_rejects_invented_summary(self):
        ai_bridge.set_router(fake_router(lambda *a: self._narr("Atacama scores 97.3 / 100.", [])))
        out = report.narrative(self.FACTS, use_ai=True)
        self.assertEqual(out["generated_by"], "fallback")
        self.assertIn("97.3", out["note"])

    def test_report_narrative_unavailable(self):
        ai_bridge.set_router(fake_router(lambda *a: adapters.ProviderError("server", "boom", 503)))
        out = report.narrative(self.FACTS, use_ai=True)
        self.assertEqual(out["generated_by"], "fallback")
        self.assertIn("unavailable", out["note"])

    def test_assistant_falls_back_to_router(self):
        ai_bridge.set_router(fake_router(lambda model, system, user: "Answer from facts."))
        with mock.patch.object(assistant, "_groq_key", return_value=""):
            out = assistant.answer("Why is site 1 best?", [], {})
        self.assertEqual(out["answer"], "Answer from facts.")
        self.assertEqual(out["mode"], "router_no_tools")
        self.assertEqual(out["provider"], "groq")
        self.assertIn("no GROQ_API_KEY", out["fallback_reason"])

    def test_assistant_unavailable_when_everything_down(self):
        ai_bridge.set_router(Router(Ledger(Path(tempfile.mkdtemp(dir=_TMP)) / "l.sqlite"), {}))
        with mock.patch.object(assistant, "_groq_key", return_value=""):
            with self.assertRaises(assistant.AssistantUnavailable):
                assistant.answer("hello", [], {})


if __name__ == "__main__":
    unittest.main()
