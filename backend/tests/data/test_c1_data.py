"""C1 data-lane tests.  Run from the worktree root:

    PYTHONPATH=backend:. .venv/bin/python -m unittest discover -s backend/tests/data -v

Byte fixtures built here are TEST INPUTS for decoder failure modes only; they
are never exported as observations.  Real-product checks run against the
committed published file and, when present, the SHA-verified raw cache.
"""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from twinsite.sources import fetch, pds3, registry  # noqa: E402
from twinsite.sources.base import (  # noqa: E402
    AOI, AcquisitionError, BodyMismatchError, ChecksumMismatchError, Decoded, InvalidCRSError,
    OutOfFootprintError, ResolutionError, TimeMismatchError, TimeWindow, TruncatedAssetError,
    UnapprovedRuleError, VerticalDatumError, parse_utc,
)
from twinsite.sources.mola import MOLAMEGDRAdapter, _sphere_dx  # noqa: E402
from twinsite.sources.srtm import TILE_POSTS, VOID, SRTMGL1Adapter, earth_dx, earth_dy  # noqa: E402
from twinsite.processing import export, terrain  # noqa: E402

FIXTURES = HERE.parent / "fixtures"
PUBLISHED = ROOT / "backend" / "twinsite" / "processing" / "published" / "g2_feature_pair.json"

EARTH_AOI = AOI("Earth", -5.95, 30.20, -5.65, 30.50, "EPSG:4326")
MARS_AOI = AOI("Mars", 137.25, -4.75, 137.55, -4.45, "IAU_2000:49900")


def _hgt(fn) -> bytes:
    """Synthetic 3601x3601 tile with elevation fn(row, col) (None -> void)."""
    out = bytearray(TILE_POSTS * TILE_POSTS * 2)
    for r in range(TILE_POSTS):
        row = [fn(r, c) for c in range(TILE_POSTS)]
        struct.pack_into(f">{TILE_POSTS}h", out, r * TILE_POSTS * 2, *[VOID if v is None else v for v in row])
    return bytes(out)


_PLANE = None


def plane_tile() -> bytes:
    """Plane rising 1 m per post eastwards (a known slope)."""
    global _PLANE
    if _PLANE is None:
        _PLANE = _hgt(lambda r, c: 500 + c)
    return _PLANE


class TestAOIAndCRS(unittest.TestCase):
    def test_invalid_crs_rejected(self):
        with self.assertRaises(InvalidCRSError):
            AOI("Earth", -6, 30, -5.5, 30.5, "EPSG:3857")
        with self.assertRaises(InvalidCRSError):  # Earth EPSG applied to Mars
            AOI("Mars", 137, -5, 137.5, -4.5, "EPSG:4326")
        with self.assertRaises(InvalidCRSError):
            AOI("Earth", float("nan"), 30, -5.5, 30.5, "EPSG:4326")

    def test_body_mismatch(self):
        with self.assertRaises(BodyMismatchError):
            SRTMGL1Adapter(offline=True).discover(MARS_AOI, None)
        with self.assertRaises(BodyMismatchError):
            MOLAMEGDRAdapter(offline=True).discover(EARTH_AOI, None)

    def test_unbounded_or_inverted_aoi(self):
        with self.assertRaises(OutOfFootprintError):
            AOI("Earth", -5, 30, -6, 31, "EPSG:4326")
        with self.assertRaises(OutOfFootprintError):
            AOI("Earth", -6, 31, -5, 30, "EPSG:4326")


class TestSRTMDecoder(unittest.TestCase):
    def setUp(self):
        self.a = SRTMGL1Adapter(offline=True)
        self.g = self.a.discover(EARTH_AOI, None)[0]

    def test_out_of_footprint(self):
        with self.assertRaises(OutOfFootprintError):
            self.a.discover(AOI("Earth", 10, 70, 10.5, 70.5, "EPSG:4326"), None)  # north of 60N
        with self.assertRaises(OutOfFootprintError):  # AOI straddles two tiles
            self.a.decode_hgt(plane_tile(), AOI("Earth", -6.2, 30.2, -5.8, 30.5, "EPSG:4326"), self.g)
        with self.assertRaises(OutOfFootprintError):  # AOI entirely elsewhere
            self.a.decode_hgt(plane_tile(), AOI("Earth", 10.1, 30.2, 10.3, 30.4, "EPSG:4326"), self.g)

    def test_time_mismatch(self):
        tw = TimeWindow(parse_utc("2015-01-01"), parse_utc("2015-12-31"))
        with self.assertRaises(TimeMismatchError):
            self.a.discover(EARTH_AOI, tw)
        ok = TimeWindow(parse_utc("2000-02-15"), parse_utc("2000-02-16"))
        self.assertEqual(len(self.a.discover(EARTH_AOI, ok)), 1)

    def test_truncated_hgt(self):
        with self.assertRaises(TruncatedAssetError):
            self.a.decode_hgt(plane_tile()[:-2], EARTH_AOI, self.g)
        with self.assertRaises(TruncatedAssetError):  # 3 arc-second size is not 1 arc-second
            self.a.decode_hgt(b"\0" * (1201 * 1201 * 2), EARTH_AOI, self.g)

    def test_truncated_zip_and_mutated_raw(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("N30W006.hgt", plane_tile())
        data = buf.getvalue()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            meta = {"asset_id": "t", "source_id": "SRTMGL1", "product_id": "SRTMGL1", "product_version": "003",
                    "granule_id": self.g.granule_id, "body": "Earth", "role": "data",
                    "source_url": "https://example.invalid/x.zip", "byte_size": len(data) // 2,
                    "retrieved_at": "2026-11-15T00:00:00Z", "format": "zip", "crs": "EPSG:4326",
                    "coordinate_conventions": "", "license_url": "https://example.invalid/", "byte_ranges": None}
            path, key, digest = fetch.store_raw(data[: len(data) // 2], filename="x.zip", meta=meta, root=root)
            asset = fetch.asset_from_meta({**meta, "path": str(path), "object_key": key, "sha256": digest},
                                          self.g.observation, False)
            with self.assertRaises(TruncatedAssetError):
                self.a.decode([asset], EARTH_AOI, self.g)
            # mutate stored bytes -> checksum gate
            os.chmod(path, 0o644)
            b = bytearray(path.read_bytes())
            b[100] ^= 0xFF
            path.write_bytes(bytes(b))
            with self.assertRaises(ChecksumMismatchError):
                fetch.verify_raw(asset)

    def test_missing_fill_kept_null_and_blocks_aggregation(self):
        # voids on a band of columns inside the AOI
        void_cols = range(500, 520)
        tile = _hgt(lambda r, c: None if c in void_cols else 500 + c)
        dec = self.a.decode_hgt(tile, EARTH_AOI, self.g)
        self.assertGreater(dec.fill_count, 0)
        self.assertEqual(dec.fill_count, sum(1 for v in dec.grid.values if v is None))
        self.assertTrue(all(v is None or v >= 500 for v in dec.grid.values))  # no fabricated values
        val = self.a.validate(dec)
        self.assertEqual(val.verdict, "REPAIR_ALLOWED")
        cln = self.a.clean(dec, ["srtm_void_mask"])
        fs = self.a.features(cln, 463.2)
        self.assertLess(fs.valid_coverage_fraction, 1.0)
        # any block touching a void is invalid (never averaged over a gap)
        by, bx = terrain.choose_block(earth_dx(30.35, 1 / 3600), earth_dy(30.35, 1 / 3600), 463.2)
        agg = terrain.aggregate(dec.grid, by, bx)
        self.assertIn(None, agg.values)
        self.assertEqual(export.evidence_qa(val, fs, ["srtm_void_mask"]), "ACCEPT")
        self.assertEqual(export.evidence_qa(val, fs, []), "REPAIR_ALLOWED")

    def test_mostly_void_is_insufficient_and_withheld(self):
        tile = _hgt(lambda r, c: 600 if (r + c) % 3 == 0 else None)
        dec = self.a.decode_hgt(tile, EARTH_AOI, self.g)
        self.assertEqual(self.a.validate(dec).verdict, "INSUFFICIENT")
        fs = self.a.features(self.a.clean(dec, ["srtm_void_mask"]), 463.2)
        for f in fs.features:
            self.assertIsNone(f.value)
            self.assertEqual(f.evidence_kind, "unavailable")
            self.assertTrue(f.missing_reason)

    def test_known_slope_and_coarser_target_resolution(self):
        dec = self.a.decode_hgt(plane_tile(), EARTH_AOI, self.g)
        self.assertEqual(dec.fill_count, 0)
        cln = self.a.clean(dec, ["srtm_void_mask"])
        for scale in (31.0, 90.0, 463.2, 1000.0):  # all >= native: aggregation allowed
            fs = self.a.features(cln, scale)
            slope = next(f for f in fs.features if f.feature_id == "slope_deg")
            # 1 m per post east; per-row dx varies with latitude
            # dx shrinks poleward, so the steepest rows are the northernmost
            lo = math.degrees(math.atan(1 / earth_dx(30.20, 1 / 3600)))
            hi = math.degrees(math.atan(1 / earth_dx(30.50, 1 / 3600)))
            self.assertGreaterEqual(slope.value, lo - 1e-6, scale)
            self.assertLessEqual(slope.value, hi + 1e-6, scale)
            self.assertGreaterEqual(fs.cell_size_m[1], scale * 0.5)

    def test_finer_than_native_rejected(self):
        dec = self.a.decode_hgt(plane_tile(), EARTH_AOI, self.g)
        with self.assertRaises(ResolutionError):
            self.a.features(self.a.clean(dec, ["srtm_void_mask"]), 10.0)

    def test_wrong_vertical_datum(self):
        dec = self.a.decode_hgt(plane_tile(), EARTH_AOI, self.g)
        bad = Decoded(**{**dec.__dict__, "vertical_datum": "WGS84 ellipsoid"})
        with self.assertRaises(VerticalDatumError):
            self.a.validate(bad)

    def test_unapproved_rule_and_uncleaned_features(self):
        dec = self.a.decode_hgt(plane_tile(), EARTH_AOI, self.g)
        with self.assertRaises(UnapprovedRuleError):
            self.a.clean(dec, ["fill_voids_by_interpolation"])
        with self.assertRaises(UnapprovedRuleError):
            self.a.features(dec, 463.2)


class TestMOLA(unittest.TestCase):
    """Uses the real MEGDR PDS3 labels (committed fixtures) with synthetic data bytes."""

    @classmethod
    def setUpClass(cls):
        cls.topo_lbl = (FIXTURES / "megt00n090hb.lbl").read_text()
        cls.cnt_lbl = (FIXTURES / "megc00n090hb.lbl").read_text()

    def setUp(self):
        self.a = MOLAMEGDRAdapter(offline=True)
        self.g = self.a.discover(MARS_AOI, None)[0]
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _asset(self, role, data, ranges=None, fname=None):
        meta = {"asset_id": f"t-{role}", "source_id": "MOLA_MEGDR", "product_id": self.a.product_id,
                "product_version": "2.0", "granule_id": self.g.granule_id, "body": "Mars", "role": role,
                "source_url": f"https://example.invalid/{role}", "byte_size": len(data),
                "retrieved_at": "2026-11-15T00:00:00Z", "format": "test", "crs": self.a.crs,
                "coordinate_conventions": "", "license_url": "https://example.invalid/",
                "byte_ranges": [list(r) for r in ranges] if ranges else None}
        path, key, digest = fetch.store_raw(data, filename=fname or role, meta=meta, root=self.tmp)
        return fetch.asset_from_meta({**meta, "path": str(path), "object_key": key, "sha256": digest},
                                     self.g.observation, False)

    def _assets(self, topo_label=None, truncate=False, aoi=MARS_AOI):
        tl = pds3.parse_label(topo_label or self.topo_lbl)
        cl = pds3.parse_label(self.cnt_lbl)
        tr, cr = self.a.byte_ranges(tl, aoi), self.a.byte_ranges(cl, aoi)
        n = len(tr)
        ncols = (tr[0][1] - tr[0][0] + 1) // 2
        topo = b"".join(struct.pack(f">{ncols}h", *[-4500 + 3 * c + 2 * r for c in range(ncols)]) for r in range(n))
        cnt = bytes((r + c) % 3 for r in range(n) for c in range(ncols))
        if truncate:
            topo = topo[:-1]
        return [self._asset("label", (topo_label or self.topo_lbl).encode()),
                self._asset("count_label", self.cnt_lbl.encode()),
                self._asset("data", topo, tr, "t.bin"), self._asset("count", cnt, cr, "c.bin")]

    def test_label_layout_matches_tile_edges(self):
        L = self.a.layout(pds3.parse_label(self.topo_lbl))
        self.assertEqual((L["lines"], L["samples"], L["res"], L["fmt"]), (5632, 11520, 128.0, ">h"))
        self.assertAlmostEqual(L["lat_first"], -1 / 256)
        self.assertAlmostEqual(L["lon_first"], 90 + 1 / 256)
        self.assertEqual(L["radius_m"], 3396000.0)
        self.assertEqual(L["name"], "MEDIAN_TOPOGRAPHY")

    def test_decode_and_geodesy_is_mars_sphere(self):
        dec = self.a.decode(self._assets(), MARS_AOI, self.g)
        self.assertEqual(dec.body_radius_m, 3396000.0)
        self.assertIn("Mars sphere", dec.radius_model)
        self.assertAlmostEqual(dec.native_resolution_m, 3396000.0 * math.radians(1 / 128), places=3)
        # first cell centre must be inside the AOI and on the 1/256-offset lattice
        self.assertLessEqual(dec.grid.lat0, MARS_AOI.north)
        self.assertAlmostEqual((dec.grid.lat0 * 256) % 2, 1.0, places=6)
        self.assertGreaterEqual(dec.grid.lon0, MARS_AOI.west)
        self.assertNotEqual(dec.native_resolution_m, earth_dy(-4.6, 1 / 128))  # not Earth geodesy

    def test_planetary_radius_layer_is_wrong_vertical_datum(self):
        radius_label = self.topo_lbl.replace("MEDIAN_TOPOGRAPHY", "PLANETARY_RADIUS")
        with self.assertRaises(VerticalDatumError):
            self.a.decode(self._assets(topo_label=radius_label), MARS_AOI, self.g)

    def test_truncated_subset(self):
        with self.assertRaises(TruncatedAssetError):
            self.a.decode(self._assets(truncate=True), MARS_AOI, self.g)

    def test_out_of_footprint_and_time(self):
        with self.assertRaises(OutOfFootprintError):
            self.a.discover(AOI("Mars", 10, 88.5, 11, 89.5, "IAU_2000:49900"), None)
        with self.assertRaises(OutOfFootprintError):  # spans the 180E tile boundary
            self.a.discover(AOI("Mars", 179.5, -4.7, 180.5, -4.4, "IAU_2000:49900"), None)
        other = AOI("Mars", 137.6, -4.75, 137.8, -4.45, "IAU_2000:49900")
        with self.assertRaises(OutOfFootprintError):  # cached subset does not cover a different AOI
            self.a.decode(self._assets(), other, self.g)
        with self.assertRaises(TimeMismatchError):
            self.a.discover(MARS_AOI, TimeWindow(parse_utc("2012-08-06"), parse_utc("2012-08-07")))

    def test_longitude_convention_normalised(self):
        signed = AOI("Mars", -10.5, -4.75, -10.2, -4.45, "IAU_2000:49900")  # -180..180 east-positive
        east360 = AOI("Mars", 349.5, -4.75, 349.8, -4.45, "IAU_2000:49900")  # 0..360 east-positive
        self.assertEqual(self.a.tile_for(signed), self.a.tile_for(east360))
        self.assertEqual(self.a.tile_for(east360), ("00n", 0, 270))

    def test_interpolated_cells_flagged_not_dropped(self):
        dec = self.a.decode(self._assets(), MARS_AOI, self.g)
        v = self.a.validate(dec)
        self.assertLess(v.metrics["shot_supported_fraction"], 1.0)
        cln = self.a.clean(dec, ["mola_flag_interpolated"])
        self.assertEqual(cln.grid.values, dec.grid.values)
        self.assertTrue(any(f.startswith("MOLA_SHOT_SUPPORTED_FRACTION=") for f in cln.quality_flags))
        with self.assertRaises(ResolutionError):
            self.a.features(cln, 100.0)
        fs = self.a.features(cln, 470.0)
        self.assertIsNotNone(next(f for f in fs.features if f.feature_id == "slope_deg").value)


class TestObservationSupport(unittest.TestCase):
    def test_reported_coverage_is_observation_supported(self):
        from twinsite.processing.dem_features import block_support_fraction
        from twinsite.sources.base import Grid
        # 6x6 support grid with shots only in the top-left 2x2 block
        vals = [1.0 if (r < 2 and c < 2) else 0.0 for r in range(6) for c in range(6)]
        g = Grid(6, 6, 0, 0, 1, 1, vals, "area")
        self.assertAlmostEqual(block_support_fraction(g, 1, 1), 4 / 36)
        self.assertAlmostEqual(block_support_fraction(g, 2, 2), 1 / 9)
        self.assertAlmostEqual(block_support_fraction(g, 3, 3), 1 / 4)
        self.assertEqual(block_support_fraction(Grid(6, 6, 0, 0, 1, 1, [0.0] * 36, "area"), 2, 2), 0.0)


class TestFetchSafety(unittest.TestCase):
    def test_credential_urls_refused(self):
        for url in ("https://user:pw@example.org/x", "https://example.org/x?token=abc",
                    "https://example.org/x?X-Amz-Signature=1"):
            with self.assertRaises(AcquisitionError):
                fetch.assert_credential_free(url)

    def test_registry_refuses_unintegrated(self):
        with self.assertRaises(AcquisitionError):
            registry.get("MOD11A2")
        self.assertEqual(set(registry.ADAPTERS), {"SRTMGL1", "MOLA_MEGDR"})


@unittest.skipUnless(PUBLISHED.exists(), "published G2 pair not generated yet")
class TestPublishedPair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(PUBLISHED.read_text())

    def test_observations_match_contract_schema(self):
        try:
            from contracts.validation import validate
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("jsonschema unavailable")
        for o in self.doc["observations"]:
            validate("evidence_observation", o)
        for a in self.doc["assets"]:
            validate("asset_manifest", a)
        for s in self.doc["sites"]:
            validate("quality_verdict", s["quality_verdict"])

    def test_pair_is_real_measured_and_lineage_consistent(self):
        obs = self.doc["observations"]
        self.assertEqual({o["body"] for o in obs}, {"Earth", "Mars"})
        assets = {a["asset_id"]: a for a in self.doc["assets"]}
        for o in obs:
            self.assertEqual(o["data_status"], "measured")
            self.assertNotIn("synthetic", json.dumps(o).lower())
            src = [assets[i] for i in o["source_asset_ids"]]
            self.assertTrue(any(a["sha256"] == o["source_checksum"] and a["source_url"] == o["source_url"]
                                and a["product_id"] == o["source_product"] and a["body"] == o["body"] for a in src))
        self.assertEqual(export.snapshot_sha256(self.doc["assets"]), self.doc["source_snapshot_sha256"])
        scales = {o["analysis_scale_m"] for o in obs}
        self.assertEqual(len(scales), 1, "pair must share one analysis scale")
        for p in self.doc["comparison_pairs"]:
            ids = {o["evidence_id"]: o for o in obs}
            self.assertEqual(ids[p["earth_evidence_id"]]["body"], "Earth")
            self.assertEqual(ids[p["mars_evidence_id"]]["body"], "Mars")

    def test_raw_cache_bytes_verified(self):
        root = fetch.artifact_root()
        missing = [a for a in self.doc["assets"] if not (root / a["object_key"]).is_file()]
        if missing:
            self.skipTest("raw cache not present on this machine")
        for a in self.doc["assets"]:
            p = root / a["object_key"]
            self.assertEqual(fetch.sha256_file(p), a["sha256"])
            self.assertEqual(p.stat().st_size, a["byte_size"])


if __name__ == "__main__":
    unittest.main()
