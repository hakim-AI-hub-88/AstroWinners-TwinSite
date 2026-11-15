"""/api/data endpoints: catalogue, metadata, records (pagination, bbox, columns, cleaning), CSV, validation."""
from __future__ import annotations

import csv
import io
import unittest

from tests.flask import _support as S


class DataApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        S.require_zones("atacama")
        cls.c = S.app_client()

    def test_catalog_lists_every_dataset(self):
        j = self.c.get("/api/data/datasets").get_json()
        ids = {d["id"] for d in j["datasets"]}
        for key in ("earth", "merzouga", "mars", "moon"):
            for stage in ("processed", "harmonized", "harmonized_normalized"):
                self.assertIn(f"{key}.{stage}", ids)
        for d in j["datasets"]:
            self.assertIn("available", d)
            if not d["available"]:
                self.assertTrue(d["reason"])               # explicit reason, never a crash
        e = next(d for d in j["datasets"] if d["id"] == "earth.harmonized")
        self.assertTrue(e["available"])
        self.assertEqual(e["rows"], 1200)
        self.assertIn("quality_flags", e["columns"])

    def test_metadata(self):
        j = self.c.get("/api/data/datasets/earth.harmonized_normalized").get_json()
        flags = {f["name"]: f["count"] for f in j["quality_flags"]}
        self.assertEqual(flags["WATER"], 42)
        self.assertEqual(flags["COARSE_SOURCE"], 1200)
        cols = {c["name"]: c for c in j["columns"]}
        self.assertLessEqual(cols["slope"]["max"], 1.0)
        self.assertEqual(cols["thermal_inertia"]["null_pct"], 100.0)
        self.assertIn("params", j["normalization"])
        self.assertTrue(j["provenance"]["processing_steps"])

    def test_pagination_bbox_columns(self):
        base = "/api/data/datasets/earth.harmonized/records"
        p1 = self.c.get(base + "?limit=10&offset=0").get_json()
        p2 = self.c.get(base + "?limit=10&offset=10").get_json()
        self.assertEqual(p1["total"], 1200)
        self.assertEqual(len(p1["rows"]), 10)
        self.assertNotEqual(p1["rows"][0], p2["rows"][0])
        bb = self.c.get(base + "?bbox=-69,-24,-68,-23&columns=slope&limit=5000").get_json()
        self.assertEqual(bb["columns"], ["latitude", "longitude", "slope"])
        self.assertGreater(bb["total"], 0)
        self.assertLess(bb["total"], 1200)
        for r in bb["rows"]:
            self.assertTrue(-69 <= r["longitude"] <= -68 and -24 <= r["latitude"] <= -23)
            self.assertEqual(set(r), {"latitude", "longitude", "slope"})

    def test_cleaning_filter_reduces_rows(self):
        base = "/api/data/datasets/earth.harmonized/records?limit=1"
        totals = {p: self.c.get(f"{base}&cleaning={p}").get_json()["total"] for p in ("raw", "standard", "strict", "robust")}
        self.assertEqual(totals["raw"], totals["standard"])
        self.assertGreaterEqual(totals["standard"], totals["strict"])
        self.assertGreaterEqual(totals["strict"], totals["robust"])
        j = self.c.get(f"{base}&cleaning=strict").get_json()
        self.assertEqual(j["cleaning"]["profile"], "strict")
        self.assertEqual(j["cleaning"]["removed"], 1200 - j["total"])

    def test_csv_download(self):
        r = self.c.get("/api/data/datasets/earth.harmonized/records?format=csv&columns=slope,albedo&cleaning=strict")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        self.assertIn("earth_harmonized_strict.csv", r.headers["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
        self.assertEqual(rows[0], ["latitude", "longitude", "slope", "albedo"])
        self.assertEqual(len(rows) - 1, int(r.headers["X-Total-Count"]))

    def test_clean_report(self):
        r = self.c.post("/api/data/clean", json={"dataset": "earth.harmonized", "profile": "robust",
                                                 "bbox": [-70, -25, -66, -22]})
        self.assertEqual(r.status_code, 200)
        rep = r.get_json()["report"]
        self.assertEqual(rep["profile"], "robust")
        self.assertEqual([s["step"] for s in rep["steps"]],
                         ["invalid_coordinates", "row_flags", "estimated_values", "physical_range", "mad_outliers"])
        self.assertIn("slope", rep["per_feature"])

    def test_cleaning_catalogue_and_sources(self):
        j = self.c.get("/api/data/cleaning").get_json()
        self.assertEqual(j["default"], "standard")
        self.assertEqual([p["id"] for p in j["profiles"]], ["raw", "standard", "strict", "robust"])
        s = self.c.get("/api/data/sources").get_json()
        self.assertIn(s["platform"]["status"], ("ok", "unavailable"))
        if s["platform"]["status"] == "unavailable":
            self.assertTrue(s["platform"]["reason"])
        self.assertTrue(any(x["kind"] == "bundled" for x in s["sources"]))

    def test_invalid_input(self):
        base = "/api/data/datasets/earth.harmonized/records"
        for q in ("?limit=0", "?limit=5001", "?limit=abc", "?offset=-1", "?bbox=1,2,3", "?bbox=10,0,5,1",
                  "?bbox=a,b,c,d", "?columns=nope", "?cleaning=zzz", "?format=xml", "?format=csv&limit=200001"):
            r = self.c.get(base + q)
            self.assertEqual(r.status_code, 400, q)
            self.assertTrue(r.get_json()["message"], q)
        self.assertEqual(self.c.get("/api/data/datasets/nope.harmonized").status_code, 404)
        self.assertEqual(self.c.get("/api/data/datasets/../../etc").status_code, 404)
        for body in (None, {}, {"dataset": "earth.harmonized", "profile": "x"},
                     {"dataset": "earth.harmonized", "bbox": "1,2"}):
            r = self.c.post("/api/data/clean", json=body) if body is not None else self.c.post("/api/data/clean", data="x")
            self.assertEqual(r.status_code, 400, body)


if __name__ == "__main__":
    unittest.main()
