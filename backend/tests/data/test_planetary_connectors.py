"""Offline tests: LOLA label handling, Diviner GCP decoding/QA, PDS3 multi-line sets, site AOIs, pre-ranking."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))

from twinsite.sources import diviner, pds3, sites  # noqa: E402
from twinsite.sources.base import AOI, AcquisitionError, DecodeError  # noqa: E402
from twinsite.sources.lola import LOLAGDRAdapter  # noqa: E402

LDEM_LABEL = '''PDS_VERSION_ID = "PDS3"
MISSION_PHASE_NAME = {"COMMISSIONING","NOMINAL MISSION","SCIENCE
                      MISSION"}
PRODUCT_ID = "LDEM_64"
OBJECT = UNCOMPRESSED_FILE
 RECORD_BYTES = 46080
 OBJECT = IMAGE
  NAME = HEIGHT
  LINES = 11520
  LINE_SAMPLES = 23040
  SAMPLE_TYPE = LSB_INTEGER
  SAMPLE_BITS = 16
  UNIT = METER
  SCALING_FACTOR = 0.5
  OFFSET = 1737400.
  MINIMUM = -18251
  MAXIMUM = 21546
 END_OBJECT = IMAGE
END_OBJECT = UNCOMPRESSED_FILE
OBJECT = IMAGE_MAP_PROJECTION
 MAP_PROJECTION_TYPE = "SIMPLE CYLINDRICAL"
 A_AXIS_RADIUS = 1737.4 <km>
 C_AXIS_RADIUS = 1737.4 <km>
 POSITIVE_LONGITUDE_DIRECTION = "EAST"
 CENTER_LONGITUDE = 180 <deg>
 MAP_RESOLUTION = 64 <pix/deg>
 MAXIMUM_LATITUDE = 90 <deg>
 WESTERNMOST_LONGITUDE = 0 <deg>
 LINE_PROJECTION_OFFSET = 5759.5 <pix>
 SAMPLE_PROJECTION_OFFSET = 11519.5 <pix>
 COORDINATE_SYSTEM_NAME = "MEAN EARTH/POLAR AXIS OF DE421"
END_OBJECT = IMAGE_MAP_PROJECTION
END
'''


class LolaTests(unittest.TestCase):
    def test_multiline_set_and_layout(self):
        lab = pds3.parse_label(LDEM_LABEL)
        self.assertIn('SCIENCE MISSION', str(lab['MISSION_PHASE_NAME']).replace('  ', ' '))
        L = LOLAGDRAdapter().layout(lab)
        self.assertEqual(L['fmt'], '<h')
        self.assertAlmostEqual(L['lat_first'], 90 - 0.5 / 64)
        self.assertAlmostEqual(L['lon_first'], 0.5 / 64)
        self.assertEqual(L['scale'], 0.5)
        win = LOLAGDRAdapter().window(L, AOI('Moon', 30.25, 20.0, 31.35, 21.1, 'IAU_2000:30100'))
        self.assertEqual(win[3] - win[2] + 1, 70)

    def test_rejects_unknown_frame(self):
        bad = LDEM_LABEL.replace('MEAN EARTH/POLAR AXIS OF DE421', 'PRINCIPAL AXIS')
        with self.assertRaises(DecodeError):
            LOLAGDRAdapter().layout(pds3.parse_label(bad))


def _rows(b, lat_lo, tbol_fn):
    out = []
    ilon0, ilon1, ilat0, ilat1 = b
    for ilon in range(ilon0, ilon1 + 1):
        for ilat in range(ilat0, ilat1 + 1):
            for it in range(diviner.NT):
                clon, clat, lt = -180 + (ilon + .5) * .5, lat_lo + (ilat + .5) * .5, (it + .5) * .25
                t = tbol_fn(lt)
                row = f'{clon:7.2f},{clat:7.2f},{lt:7.2f},' + ','.join(f'{t:10.4f}' for _ in range(8))
                out.append(row.ljust(diviner.REC - 2) + '\r\n')
    return ''.join(out).encode('ascii')


class DivinerTests(unittest.TestCase):
    def setUp(self):
        self.aoi = AOI('Moon', 30.25, 20.0, 31.35, 21.1, 'IAU_2000:30100')
        self.fname, self.lo = diviner.files_for(self.aoi)
        self.b = diviner.bins(self.aoi, self.lo)

    def asset(self, data):
        tmp = Path(tempfile.mkdtemp()) / 'sub.bin'
        tmp.write_bytes(data)
        import hashlib
        return SimpleNamespace(path=str(tmp), sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data),
                               object_key='x', byte_ranges=None)

    def test_file_band_and_byte_ranges(self):
        self.assertEqual(self.fname, 'global_cumul_avg_cyl_20n30n_002.tab')
        self.assertEqual(diviner.files_for(AOI('Moon', -10, -15, -8, -13, 'IAU_2000:30100'))[0],
                         'global_cumul_avg_cyl_20s10s_002.tab')
        r = diviner.byte_ranges(self.b)
        self.assertEqual(len(r), self.b[1] - self.b[0] + 1)
        self.assertEqual((r[0][1] - r[0][0] + 1) % diviner.REC, 0)
        with self.assertRaises(AcquisitionError):
            diviner.files_for(AOI('Moon', 0, 19, 1, 21, 'IAU_2000:30100'))

    def test_decode_features_fill_and_negative_masked(self):
        def tbol(lt):
            if lt < 1:
                return -9999
            if lt < 2:
                return -50
            return 380.0 if 11 < lt < 13 else (95.0 if lt < 6 or lt > 18 else 250.0)
        from unittest import mock
        with mock.patch.object(diviner.fetch, 'verify_raw'):
            cells = diviner.decode(self.asset(_rows(self.b, self.lo, tbol)), self.b, self.lo)
        f = diviner.features(cells)
        self.assertEqual(f['surface_temperature_day_K']['value'], 380.0)
        self.assertEqual(f['surface_temperature_night_K']['value'], 95.0)
        self.assertEqual(f['surface_temperature_diurnal_range_K']['value'], 285.0)

    def test_misaligned_rows_rejected(self):
        data = _rows(self.b, self.lo, lambda lt: 200.0)
        from unittest import mock
        with mock.patch.object(diviner.fetch, 'verify_raw'), self.assertRaises(DecodeError):
            diviner.decode(self.asset(data[diviner.REC:] + data[:diviner.REC]), self.b, self.lo)


class SiteTests(unittest.TestCase):
    def test_aoi_is_metric_and_inside_one_tile(self):
        for body, lon, lat in (('Earth', -70.03, -24.08), ('Earth', 10.99, 48.99), ('Moon', 30.77, 20.19),
                               ('Mars', 77.45, 18.44), ('Mars', -179.9, 43.9)):
            a = sites.aoi_for(body, lon, lat)
            km = (a.north - a.south) * 3.14159 / 180 * sites.RADIUS_KM[body]
            self.assertAlmostEqual(km, sites.SIDE_KM, delta=0.5)

    def test_prerank_orders_by_similarity(self):
        def doc(sid, slope, rough, relief):
            return {'site_id': sid, 'observations': [{'feature_id': 'slope_deg', 'value': slope},
                                                     {'feature_id': 'roughness_m', 'value': rough},
                                                     {'feature_id': 'local_relief_m', 'value': relief}]}
        target = doc('t', 2.0, 60, 1000)
        ranked = sites.prerank(target, [doc('far', 15, 400, 4000), doc('near', 2.2, 65, 1100)])
        self.assertEqual([c['site_id'] for _, c in ranked], ['near', 'far'])


if __name__ == '__main__':
    unittest.main()
