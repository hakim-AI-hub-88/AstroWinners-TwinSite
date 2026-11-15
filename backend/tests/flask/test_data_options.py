"""Mission options (cleaning, data_mode) on POST /api/similarity and POST /api/report."""
from __future__ import annotations

import unittest

from tests.flask import test_data_support as S


class MissionOptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        S.require_zones("atacama", "merzouga")
        cls.c = S.app_client()

    def test_similarity_default_echoes_options(self):
        with S.merzouga_as_mars():
            j = self.c.post("/api/similarity", json={"planet": "mars", "location": S.CUSTOM}).get_json()
        self.assertEqual(j["options"], {"data_mode": "bundled", "cleaning": "standard"})
        self.assertEqual(j["cleaning_report"]["profile"], "standard")
        self.assertNotIn("live_evidence", j)
        self.assertEqual(j["score"], 93.0)

    def test_similarity_profiles_and_auto(self):
        with S.merzouga_as_mars():
            scored = {}
            for p in ("raw", "standard", "strict", "robust"):
                r = self.c.post("/api/similarity", json={"planet": "mars", "location": S.CUSTOM, "cleaning": p,
                                                         "data_mode": "auto"})
                self.assertEqual(r.status_code, 200, p)
                j = r.get_json()
                self.assertEqual(j["options"], {"data_mode": "auto", "cleaning": p})
                live = j["live_evidence"]
                self.assertIn(live["status"], ("ok", "unavailable"))
                if live["status"] == "unavailable":
                    self.assertTrue(live["reason"])
                    self.assertEqual(live["observations"], [])          # never fabricated
                scored[p] = j["method"]["cells_scored"]
            self.assertEqual(j["method"]["uncertainty_penalty"], 0.3)
        self.assertEqual(scored["raw"], scored["standard"])
        self.assertGreaterEqual(scored["standard"], scored["strict"])
        self.assertGreaterEqual(scored["strict"], scored["robust"])

    def test_live_evidence_does_not_leak_into_cache(self):
        with S.merzouga_as_mars():
            self.c.post("/api/similarity", json={"planet": "mars", "location": S.CUSTOM, "data_mode": "auto"})
            j = self.c.post("/api/similarity", json={"planet": "mars", "location": S.CUSTOM}).get_json()
        self.assertNotIn("live_evidence", j)
        self.assertEqual(j["options"]["data_mode"], "bundled")

    def test_invalid_options(self):
        for body in ({"cleaning": "aggressive"}, {"data_mode": "live"}):
            r = self.c.post("/api/similarity", json={"planet": "mars", "location": "Jezero Crater", **body})
            self.assertEqual(r.status_code, 400)
            r = self.c.post("/api/report", json={"planet": "mars", "location": "Jezero Crater", **body})
            self.assertEqual(r.status_code, 400)

    def test_report_options(self):
        with S.merzouga_as_mars():
            j = self.c.post("/api/report", json={"planet": "mars", "location": S.CUSTOM, "use_ai": False,
                                                 "cleaning": "strict", "data_mode": "auto"}).get_json()
            d = self.c.post("/api/report", json={"planet": "mars", "location": S.CUSTOM, "use_ai": False}).get_json()
        self.assertEqual(j["options"], {"data_mode": "auto", "cleaning": "strict"})
        self.assertEqual(j["cleaning_report"]["atacama"]["earth"]["profile"], "strict")
        self.assertIn(j["live_evidence"]["status"], ("ok", "unavailable"))
        self.assertIn("data_cleaning", j["facts"])
        self.assertEqual(d["options"], {"data_mode": "bundled", "cleaning": "standard"})
        self.assertNotIn("data_cleaning", d["facts"])                 # default facts unchanged
        self.assertNotIn("live_evidence", d["facts"])

    def test_live_data_unreachable_is_explicit(self):
        from services import live_data
        r = live_data.characterize("mars", 77.58, 18.38, "Jezero")
        self.assertIn(r["status"], ("ok", "unavailable"))
        bad = live_data.characterize("mars", 0, 89.5, "pole")
        self.assertEqual(bad["status"], "unavailable")
        self.assertEqual(live_data.for_target("mars", "Nowhere")["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()


class LiveDataStub(unittest.TestCase):
    """Success path of live_data against a stub platform API answering like /v1/science/characterize."""

    @classmethod
    def setUpClass(cls):
        import http.server
        import json
        import pathlib
        import threading
        doc = json.loads((pathlib.Path(__file__).with_name("test_data_characterize_fixture.json")).read_text())
        cls.calls = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.calls.append(body)
                if self.path != "/v1/science/characterize":
                    self.send_response(404); self.end_headers(); return
                out = json.dumps(doc).encode()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        import os
        from services import live_data
        self.old = os.environ.get("TWINSITE_API_URL")
        os.environ["TWINSITE_API_URL"] = f"http://127.0.0.1:{self.srv.server_address[1]}"
        live_data._cache.clear()
        live_data._failures.clear()

    def tearDown(self):
        import os
        from services import live_data
        os.environ["TWINSITE_API_URL"] = self.old or "http://127.0.0.1:9"
        live_data._cache.clear()
        live_data._failures.clear()

    def test_characterize_ok_and_cached(self):
        from services import live_data
        r = live_data.characterize("mars", 137.44, -4.59, "Gale")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(self.calls[-1]["body"], "Mars")
        self.assertIn("MGS-M-MOLA-5-MEGDR-L3-V1.0", r["source_products"])
        self.assertEqual({o["feature_id"] for o in r["observations"]}, {"slope_deg", "roughness_m", "local_relief_m"})
        self.assertNotIn("geometry", r["observations"][0])            # compacted
        n = len(self.calls)
        self.assertTrue(live_data.characterize("mars", 137.44, -4.59, "Gale").get("cached"))
        self.assertEqual(len(self.calls), n)

    def test_report_auto_facts(self):
        S.require_zones("atacama", "merzouga")
        c = S.app_client()
        with S.merzouga_as_mars():
            j = c.post("/api/report", json={"planet": "mars", "location": S.CUSTOM, "use_ai": False,
                                            "data_mode": "auto"}).get_json()
        self.assertEqual(j["live_evidence"]["status"], "ok")
        self.assertEqual(j["facts"]["live_evidence"]["status"], "ok")
        self.assertTrue(j["facts"]["live_evidence"]["measured"])
