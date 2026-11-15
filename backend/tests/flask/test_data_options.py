"""Mission options (cleaning, data_mode) on POST /api/similarity and POST /api/report."""
from __future__ import annotations

import unittest

from tests.flask import _support as S


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
