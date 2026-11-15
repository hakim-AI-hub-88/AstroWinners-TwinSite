"""Cleaning profiles: standard reproduces the historical engine result; profiles are monotonic."""
from __future__ import annotations

import hashlib
import json
import unittest

from tests.flask import test_data_support as S

# Digest of analysis.run("mars", CUSTOM, rover, 15, zone) captured BEFORE the cleaning code existed
# (Merzouga frames standing in for Mars). cleaning="standard" must reproduce it exactly.
GOLDEN = {
    "atacama": {"score": 93.0, "cells_scored": 1099, "map_sha": "4f1f96e6a803c076",
                "top": [[326, 93.0], [1120, 92.9], [124, 92.9], [243, 92.9], [681, 92.8], [362, 92.8], [560, 92.8],
                        [842, 92.8], [4, 92.7], [962, 92.7]]},
    "merzouga": {"score": 98.6, "cells_scored": 400, "map_sha": "438ba0555ee88698",
                 "top": [[302, 98.6], [19, 98.6], [139, 98.6], [308, 98.6], [209, 98.6], [381, 98.6], [131, 98.6],
                         [305, 98.6], [15, 98.5], [220, 98.5]]},
}


def digest(r):
    return {"score": r["score"], "cells_scored": r["method"]["cells_scored"],
            "map_sha": hashlib.sha256(json.dumps(r["map"], sort_keys=True).encode()).hexdigest()[:16],
            "top": [[x["cell_id"], x["score"]] for x in r["ranking"]]}


class StandardReproducesDefault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        S.require_zones("atacama", "merzouga")

    def test_golden_digest(self):
        from services import analysis
        with S.merzouga_as_mars():
            for zone, gold in GOLDEN.items():
                for rover in (False, True):
                    r = analysis.run("mars", S.CUSTOM, rover, 15.0, zone, "standard")
                    self.assertEqual(digest(r), gold, f"{zone} rover={rover}")
                    self.assertEqual(r["options"], {"cleaning": "standard"})
                    self.assertEqual(r["cleaning_report"]["earth"]["rows_removed"], 0)

    def test_default_equals_standard(self):
        from services import analysis
        with S.merzouga_as_mars():
            a = analysis.run("mars", S.CUSTOM, True, 15.0, "atacama")
            b = analysis.run("mars", S.CUSTOM, True, 15.0, "atacama", "standard")
        self.assertEqual(json.dumps(a, sort_keys=True, default=str), json.dumps(b, sort_keys=True, default=str))

    def test_moon_standard_equals_engine_direct(self):
        """With real Moon files: cleaning='standard' == engine called on the uncleaned frames."""
        if not S.body_files_present("moon"):
            self.skipTest("Moon harmonized files not downloaded")
        from services import analysis, data_loader, similarity_engine
        from utils import config
        loc = "Mare Tranquillitatis"
        t = config.TARGETS["moon"][loc]
        rad = config.BODY_RADIUS_M["moon"]
        w = data_loader.extract_target_window(data_loader.load_moon_data(), t["lat"], t["lon"], t["window_km"], rad)
        wp = data_loader.extract_target_window(data_loader.load_physical("moon"), t["lat"], t["lon"], t["window_km"], rad)
        direct = similarity_engine.compute(similarity_engine.SimilarityRequest(
            body="moon", location=loc, target_window=w, earth=data_loader.load_zone("atacama", "normalized"),
            target_window_physical=wp, earth_physical=data_loader.load_zone("atacama", "physical"),
            earth_processed=data_loader.load_zone("atacama", "processed"), rover_mode=False, max_slope=15.0))
        r = analysis.run("moon", loc, False, 15.0, "atacama", "standard")
        for k in ("score", "ranking", "map", "method"):
            self.assertEqual(json.dumps(r[k], sort_keys=True, default=str),
                             json.dumps(direct[k], sort_keys=True, default=str), k)


class ProfileMonotonicity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        S.require_zones("atacama")

    def _reports(self, df, scale):
        from services import cleaning
        return {p: cleaning.apply(df, p, None, scale)[1] for p in cleaning.PROFILE_IDS}

    def check(self, df, scale):
        rep = self._reports(df, scale)
        for key in ("rows_out", "rows_complete"):
            self.assertGreaterEqual(rep["raw"][key], rep["standard"][key], key)
            self.assertGreaterEqual(rep["standard"][key], rep["strict"][key], key)
            self.assertGreaterEqual(rep["strict"][key], rep["robust"][key], key)
        for f, pf in rep["robust"]["per_feature"].items():
            self.assertGreaterEqual(rep["strict"]["per_feature"][f]["valid"], pf["valid"], f)
        return rep

    def test_atacama_frames(self):
        from services import data_loader
        rep = self.check(data_loader.load_zone("atacama", "normalized"), "normalized")
        self.check(data_loader.load_zone("atacama", "physical"), "physical")
        # strict removes the documented cell flags (WATER 42 + GAP_FILLED cells)
        self.assertEqual(rep["strict"]["rows_in"] - rep["strict"]["rows_out"],
                         sum(rep["strict"]["steps"][1]["detail"]["rows_by_flag"].values()))
        self.assertEqual(rep["strict"]["steps"][1]["detail"]["rows_by_flag"]["WATER"], 42)

    def test_standard_and_raw_do_not_copy_or_modify(self):
        from services import cleaning, data_loader
        df = data_loader.load_zone("atacama", "normalized")
        before = df.copy()
        for p in ("raw", "standard"):
            out, rep = cleaning.apply(df, p)
            self.assertIs(out, df)
            self.assertEqual(rep["rows_removed"], 0)
        cleaning.apply(df, "robust")
        self.assertTrue(df.equals(before), "input frame must never be modified")

    def test_flag_masking_is_per_feature(self):
        import pandas as pd
        from services import cleaning
        from utils import config
        df = pd.DataFrame({"latitude": [0.0, 1.0, 2.0, 3.0], "longitude": [0.0, 0.0, 0.0, 200.0],
                           **{f: [0.5, 0.5, 0.5, 0.5] for f in config.FEATURES},
                           "quality_flags": [0, config.FLAG_BITS["ALBEDO_PROXY"], config.FLAG_BITS["WATER"], 0]})
        out, rep = cleaning.apply(df, "strict")
        self.assertEqual(list(out.index), [0, 1])                 # water row + invalid longitude dropped
        self.assertTrue(pd.isna(out.loc[1, "albedo"]))            # proxy albedo masked ...
        self.assertEqual(out.loc[1, "slope"], 0.5)                # ... other features of that row kept
        self.assertEqual(rep["steps"][0]["removed"], 1)

    def test_mad_skips_constant_feature(self):
        import numpy as np
        import pandas as pd
        from services import cleaning
        n = 40
        df = pd.DataFrame({"latitude": np.linspace(0, 1, n), "longitude": np.zeros(n),
                           "slope": np.r_[np.linspace(1, 2, n - 1), 50.0], "albedo": np.full(n, 0.2),
                           "quality_flags": np.zeros(n, int)})
        out, rep = cleaning.apply(df, "robust", ["slope", "albedo"], "physical")
        mad = rep["steps"][-1]["detail"]
        self.assertEqual(mad["values_by_feature"]["slope"], 1)
        self.assertIn("albedo", mad["skipped"])
        self.assertTrue(np.isnan(out["slope"].iloc[-1]))

    def test_unknown_profile(self):
        from services import cleaning
        with self.assertRaises(cleaning.CleaningError):
            cleaning.validate_profile("aggressive")


if __name__ == "__main__":
    unittest.main()
