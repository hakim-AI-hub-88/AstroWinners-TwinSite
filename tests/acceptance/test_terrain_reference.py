"""Analytical, NON-NASA controls for the independent terrain decoder."""
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

from terrain_reference import analysis_stats, mola_grid, spacing


class TerrainReferenceTests(unittest.TestCase):
    def test_block_mean_removes_subscale_alternation(self):
        # Each 2x2 block averages to zero: native relief 20 must not survive.
        grid = [[10 if (r+c)%2 else -10 for c in range(12)] for r in range(12)]
        result = analysis_stats(grid, .001, 0, 222.4)
        self.assertEqual((result['block_rows'], result['block_cols']), (2,2))
        for key in ('slope_mean_deg', 'roughness_m', 'relief_m'):
            self.assertEqual(result[key], 0)

    def test_plane_and_support(self):
        grid = [[3*r+2*c for c in range(12)] for r in range(12)]
        support = [[int(r%4==0 and c%4==0) for c in range(12)] for r in range(12)]
        result = analysis_stats(grid, 1/128, -.5/128, 1852.3, 3396000, support)
        dx,dy=spacing(-6/128,4/128,3396000)
        self.assertAlmostEqual(result['slope_mean_deg'], math.degrees(math.atan(math.hypot(8/dx,12/dy))), places=10)
        self.assertAlmostEqual(result['roughness_m'], math.sqrt((8**2+12**2)*2/3), places=10)
        self.assertEqual(result['relief_m'], 40)
        self.assertEqual(result['valid_fraction'], 1)
        support[0][0]=0
        self.assertAlmostEqual(analysis_stats(grid,1/128,-.5/128,1852.3,3396000,support)['valid_fraction'],8/9)

    def test_void_invalidates_whole_block(self):
        grid = [[1.0]*12 for _ in range(12)]
        grid[0][0]=None
        stats=analysis_stats(grid,.001,0,222.4)
        self.assertLess(stats['valid_fraction'],1)
        self.assertEqual(stats['relief_m'],0)

    def test_pds_decode_and_reject_wrong_range_or_datum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); sources=[]
            for kind,bits,name,encoding in [('t',16,'MEDIAN_TOPOGRAPHY','MSB_INTEGER'),('c',8,'COUNTS_PER_BIN','UNSIGNED_INTEGER')]:
                folder=root/kind;folder.mkdir()
                stem='meg'+kind+'00n090hb'
                label=folder/(stem+'.lbl');raw=folder/(stem+'.bin')
                label.write_text(f'''^IMAGE = "{stem.upper()}.IMG"
NAME = {name}
SAMPLE_BITS = {bits}
SAMPLE_TYPE = {encoding}
UNIT = METER
DESCRIPTION = "height above areoid"
MAP_PROJECTION_TYPE = "SIMPLE CYLINDRICAL"
COORDINATE_SYSTEM_NAME = "PLANETOCENTRIC"
POSITIVE_LONGITUDE_DIRECTION = "EAST"
A_AXIS_RADIUS = 3396 <KM>
C_AXIS_RADIUS = 3396 <KM>
MAP_RESOLUTION = 128
LINE_PROJECTION_OFFSET = 0.5
SAMPLE_PROJECTION_OFFSET = 0.5
CENTER_LONGITUDE = 90
LINE_SAMPLES = 12
LINES = 12
RECORD_BYTES = {12*bits//8}
''')
                values=[3*r+2*c if kind=='t' else int(r%4==0 and c%4==0) for r in range(12) for c in range(12)]
                raw.write_bytes(struct.pack('>144'+('h' if kind=='t' else 'B'),*values))
                stride=12*bits//8
                (folder/'asset.json').write_text(json.dumps({'byte_ranges':[[r*stride,(r+1)*stride-1] for r in range(12)]}))
                sources.extend([{'asset_id':kind,'source_url':'https://pds-geosciences.wustl.edu/'+stem+'.img','object_key':str(raw.relative_to(root)),'parent_asset_ids':[kind+'label']},
                                {'asset_id':kind+'label','source_url':'https://pds-geosciences.wustl.edu/'+stem+'.lbl','object_key':str(label.relative_to(root))}])
            bbox=[90,-12/128,90+12/128,0]
            grid,step,north,radius,support=mola_grid(sources,root,bbox)
            self.assertEqual(grid[11][11],55)
            self.assertEqual(analysis_stats(grid,step,north,1852.3,radius,support)['relief_m'],40)
            label=root/'t/megt00n090hb.lbl'
            original=label.read_text();label.write_text(original.replace('MEDIAN_TOPOGRAPHY','PLANETARY_RADIUS'))
            with self.assertRaisesRegex(ValueError,'datum'): mola_grid(sources,root,bbox)
            label.write_text(original)
            (root/'t/asset.json').write_text(json.dumps({'byte_ranges':[[1,2]]}))
            with self.assertRaisesRegex(ValueError,'ranges'): mola_grid(sources,root,bbox)
