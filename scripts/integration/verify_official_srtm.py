"""Authenticated NASA-only acquisition, full raster comparison, then provenance rebuild.
Run after protected credential provisioning. Never accepts a token argument.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
from twinsite.sources.credentials import earthdata_token
from twinsite.sources.srtm import SRTMGL1Adapter
from twinsite.sources.base import AOI
from twinsite.processing import g2_pair


def main():
    report = {'authentication': 'NOT_ATTEMPTED', 'official_verified': False}
    out = ROOT / '.runtime/c0'
    out.mkdir(parents=True, exist_ok=True)
    try:
        if not earthdata_token():
            report['blocker'] = 'EARTHDATA_CREDENTIAL_NOT_PROVISIONED'
            return 2
        old = json.loads(g2_pair.PUBLISHED.read_text())
        mirror = next(a for a in old['assets'] if a['body'] == 'Earth')
        source = Path(os.environ.get('TWINSITE_SOURCE_DATA_DIR', ROOT / '.runtime/data'))
        official_root = ROOT / '.runtime/official-data'
        if (source / 'raw/MOLA_MEGDR').exists() and not (official_root / 'raw/MOLA_MEGDR').exists():
            shutil.copytree(source / 'raw/MOLA_MEGDR', official_root / 'raw/MOLA_MEGDR', dirs_exist_ok=True)
        adapter = SRTMGL1Adapter(root=official_root, request_timeout=15, request_retries=0)
        aoi = AOI('Earth', -5.95, 30.2, -5.65, 30.5, 'EPSG:4326')
        try:
            granules = adapter.discover(aoi, None)
            report['catalog_metadata'] = 'fresh CMR discovery'
        except Exception:
            granules = SRTMGL1Adapter(root=source, offline=True).discover(aoi, None)
            report['catalog_metadata'] = 'previous CMR metadata retained; live CMR unavailable'
        report['authentication'] = 'ATTEMPTED_NO_VERIFIED_RESPONSE' 
        assets = adapter.acquire(granules, 30_000_000, aoi)
        official = assets[0]
        if not official.source_url.startswith('https://data.lpdaac.earthdatacloud.nasa.gov/'):
            raise ValueError('Official source required')
        decoded = adapter.decode(assets, aoi, granules[0])
        def raster(path):
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist() if n.lower().endswith('.hgt')]
                if len(names) != 1: raise ValueError('Ambiguous raster')
                return z.read(names[0])
        new_bytes = raster(official.path)
        old_bytes = raster(source / mirror['object_key'])
        report.update(authentication='AUTHENTICATED_PRODUCT_DOWNLOAD', official_verified=True,
                      official_size=official.byte_size, official_sha256=official.sha256,
                      official_source=official.source_url, mirror_sha256=mirror['sha256'],
                      official_hgt_sha256=hashlib.sha256(new_bytes).hexdigest(),
                      mirror_hgt_sha256=hashlib.sha256(old_bytes).hexdigest(),
                      raster_bytes_identical=new_bytes == old_bytes,
                      differing_samples=sum(new_bytes[i:i+2] != old_bytes[i:i+2] for i in range(0,len(new_bytes),2)),
                      decoded_size=len(new_bytes), catalog=granules[0].catalog_evidence)
        # Preserve the previous published provenance before replacing it.
        (out / 'previous-mirror-feature-pair.json').write_text(json.dumps(old, indent=2)+'\n')
        # Publish the verified raw product into the worker's configured source
        # cache before switching the published snapshot. Never replace old bytes.
        destination = source / official.object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != official.sha256:
                raise ValueError('Existing content-addressed source differs')
        else:
            shutil.copy2(official.path, destination)
        metadata = destination.parent / 'asset.json'
        if not metadata.exists():
            shutil.copy2(Path(official.path).parent / 'asset.json', metadata)
        previous = os.environ.get('TWINSITE_DATA_DIR')
        os.environ['TWINSITE_DATA_DIR'] = str(official_root)
        try:
            updated = g2_pair.run(offline=True)
        finally:
            if previous is None: os.environ.pop('TWINSITE_DATA_DIR', None)
            else: os.environ['TWINSITE_DATA_DIR'] = previous
        report['new_source_snapshot_sha256'] = updated['source_snapshot_sha256']
        report['next_step'] = 'Verified official bytes installed in the configured source cache; rerun C0/C5 checks and independent review. Release remains BLOCK.'
        return 0
    except Exception as error:
        report['blocker'] = type(error).__name__
        report['note'] = 'Acquisition failed; credentials and exception text withheld. No authentication success claimed.'
        return 2
    finally:
        (out / 'official-srtm-verification.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({k: report[k] for k in ('authentication','official_verified','blocker') if k in report}))

if __name__ == '__main__': sys.exit(main())
