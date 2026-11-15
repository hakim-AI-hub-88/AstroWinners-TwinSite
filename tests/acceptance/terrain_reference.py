"""C5 raw-byte reference implementation; no imports from production code.

Reconstructs the declared block-mean analysis grid before Horn slope, population
3x3 SD and AOI relief. PDS subset offsets are checked against label geometry.
"""
import json
import math
from pathlib import Path
import re
import struct


def spacing(latitude, step, radius=None):
    phi = math.radians(latitude)
    if radius is not None:
        meridian = prime = radius
    else:
        ecc = (1 / 298.257223563) * (2 - 1 / 298.257223563)
        q = 1 - ecc * math.sin(phi) ** 2
        prime = 6378137 / math.sqrt(q)
        meridian = 6378137 * (1 - ecc) / q ** 1.5
    return prime * math.cos(phi) * math.radians(step), meridian * math.radians(step)


def analysis_stats(grid, step, north, scale, radius=None, support=None):
    if not grid or not grid[0]:
        raise ValueError('empty AOI')
    mid = north - (len(grid) - 1) * step / 2
    dx, dy = spacing(mid, step, radius)
    if not math.isfinite(scale) or scale < max(dx, dy) * .98:
        raise ValueError('analysis scale finer than native grid')
    by, bx = max(1, round(scale / dy)), max(1, round(scale / dx))
    rows, cols = len(grid) // by, len(grid[0]) // bx
    if min(rows, cols) < 3:
        raise ValueError('insufficient complete analysis blocks')
    blocks, observed = [], 0
    for r in range(rows):
        line = []
        for c in range(cols):
            cells = [grid[y][x] for y in range(r*by, (r+1)*by) for x in range(c*bx, (c+1)*bx)]
            line.append(None if None in cells else math.fsum(cells) / len(cells))
            if support and any(support[y][x] > 0 for y in range(r*by, (r+1)*by) for x in range(c*bx, (c+1)*bx)):
                observed += 1
        blocks.append(line)
    slopes, roughness = [], []
    dy = spacing(mid, step * by, radius)[1]
    for r in range(1, rows - 1):
        latitude = north - (r*by + (by-1)/2) * step
        dx = spacing(latitude, step * bx, radius)[0]
        for c in range(1, cols - 1):
            w = [blocks[r+y][c+x] for y in (-1,0,1) for x in (-1,0,1)]
            neighbours = w[:4] + w[5:]
            if None not in neighbours:
                gx = sum(v*k for v,k in zip(neighbours, [-1,0,1,-2,2,-1,0,1])) / (8*dx)
                gy = sum(v*k for v,k in zip(neighbours, [1,2,1,0,0,-1,-2,-1])) / (8*dy)
                slopes.append(math.degrees(math.atan(math.hypot(gx,gy))))
            if None not in w:
                mean = math.fsum(w)/9
                roughness.append(math.sqrt(math.fsum((v-mean)**2 for v in w)/9))
    elevations = [v for row in blocks for v in row if v is not None]
    native_cov = sum(v is not None for row in grid for v in row)/(len(grid)*len(grid[0]))
    coverage = min(native_cov, len(slopes)/((rows-2)*(cols-2)))
    if support is not None:
        coverage = min(coverage, observed/(rows*cols))
    out = {'valid_fraction': coverage, 'block_rows': by, 'block_cols': bx}
    if elevations:
        out.update(relief_m=max(elevations)-min(elevations), elevation_mean_m=math.fsum(elevations)/len(elevations))
    if slopes: out['slope_mean_deg'] = math.fsum(slopes)/len(slopes)
    if roughness: out['roughness_m'] = math.fsum(roughness)/len(roughness)
    return out


def mola_grid(sources, root, bbox):
    """Decode concatenated row ranges using independent PDS3 label fields."""
    def decode(kind):
        asset = next(s for s in sources if re.search(r'/meg'+kind+r'\w+\.img$', s['source_url'], re.I))
        label = next(s for s in sources if s['asset_id'] in asset['parent_asset_ids'])
        path = (root / asset['object_key']).resolve()
        label_path = (root / label['object_key']).resolve()
        if not path.is_relative_to(root) or not label_path.is_relative_to(root):
            raise ValueError('source path escapes artifact root')
        text = label_path.read_text('ascii')
        def field(key):
            match = re.search(r'^\s*'+re.escape(key)+r'\s*=\s*("[^"]*"|[^\n]+)', text, re.M)
            if not match: raise ValueError('missing PDS field '+key)
            return match[1].strip().strip('"')
        def number(key): return float(field(key).split()[0])
        expected = ('MEDIAN_TOPOGRAPHY',16,'MSB_INTEGER') if kind=='t' else ('COUNTS_PER_BIN',8,'UNSIGNED_INTEGER')
        if (field('NAME'),number('SAMPLE_BITS'),field('SAMPLE_TYPE')) != expected:
            raise ValueError('unexpected image encoding or vertical datum')
        if field('MAP_PROJECTION_TYPE') != 'SIMPLE CYLINDRICAL' or field('COORDINATE_SYSTEM_NAME') != 'PLANETOCENTRIC' or field('POSITIVE_LONGITUDE_DIRECTION') != 'EAST':
            raise ValueError('unsupported PDS projection')
        if kind=='t' and (field('UNIT') != 'METER' or 'areoid' not in text.lower()):
            raise ValueError('topography must be areoid-referenced metres')
        if number('A_AXIS_RADIUS') != number('C_AXIS_RADIUS'): raise ValueError('non-spherical Mars')
        if Path(asset['source_url']).name.lower() != field('^IMAGE').lower(): raise ValueError('label/image mismatch')
        ppd = number('MAP_RESOLUTION')
        north = (number('LINE_PROJECTION_OFFSET')-1)/ppd
        west = number('CENTER_LONGITUDE')+(1-number('SAMPLE_PROJECTION_OFFSET'))/ppd
        w,s,e,n = bbox
        r0,r1 = math.ceil((north-n)*ppd-1e-9),math.floor((north-s)*ppd+1e-9)
        c0,c1 = math.ceil((w%360-west)*ppd-1e-9),math.floor((e%360-west)*ppd+1e-9)
        width = int(number('LINE_SAMPLES')); height = int(number('LINES'))
        if not (0<=r0<=r1<height and 0<=c0<=c1<width): raise ValueError('AOI outside PDS grid')
        size = expected[1]//8; stride=int(number('RECORD_BYTES'))
        if stride != width*size: raise ValueError('PDS record size mismatch')
        ranges = [[r*stride+c0*size,r*stride+(c1+1)*size-1] for r in range(r0,r1+1)]
        meta=json.loads(path.with_name('asset.json').read_text())
        if meta['byte_ranges'] != ranges: raise ValueError('subset ranges disagree with label/AOI')
        raw=path.read_bytes(); nr,nc=r1-r0+1,c1-c0+1
        if len(raw) != nr*nc*size: raise ValueError('subset length mismatch')
        values=struct.unpack('>'+str(nr*nc)+('h' if size==2 else 'B'),raw)
        return [list(values[i*nc:(i+1)*nc]) for i in range(nr)],1/ppd,north-r0/ppd,number('A_AXIS_RADIUS')*1000
    topo,step,north,radius=decode('t')
    counts,cstep,cnorth,cradius=decode('c')
    if (step,north,radius,len(topo),len(topo[0])) != (cstep,cnorth,cradius,len(counts),len(counts[0])):
        raise ValueError('count/topography grids differ')
    return topo,step,north,radius,counts
