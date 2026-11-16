"""Seed real, characterized analog sites (Earth) and targets (Moon, Mars) for exploration and matching.

    python ops/seed_sites.py [--workers 6] [--body Earth]

Every value comes from real public data (AWS Terrain Tiles skadi + NASA POWER for Earth, LRO LOLA + Diviner for the
Moon, MGS MOLA for Mars). Failures are reported per site and never replaced with guesses. Idempotent (cached).
"""
import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from twinsite.sources.sites import characterize  # noqa: E402
from twinsite.storage import load_settings  # noqa: E402

SITES = [
    # Earth analog sites (lon, lat)
    ('Earth', -70.03, -24.08, 'Atacama Desert (Yungay)'), ('Earth', -89.68, 75.38, 'Devon Island (Haughton crater)'),
    ('Earth', -155.47, 19.82, 'Mauna Kea summit'), ('Earth', -6.58, 37.72, 'Rio Tinto, Spain'),
    ('Earth', -116.87, 36.46, 'Death Valley'), ('Earth', -111.02, 35.03, 'Meteor Crater, Arizona'),
    ('Earth', 76.51, 19.98, 'Lonar crater, India'), ('Earth', 13.9, 79.4, 'Bockfjorden, Svalbard'),
    ('Earth', -16.75, 65.05, 'Askja / Holuhraun, Iceland'), ('Earth', 10.6, 48.88, 'Nordlinger Ries crater'),
    ('Earth', -13.78, 29.0, 'Timanfaya, Lanzarote'), ('Earth', -115.7, 34.9, 'Kelso Dunes, Mojave'),
    ('Earth', -110.79, 38.41, 'Hanksville, Utah (MDRS)'), ('Earth', 18.53, 19.79, 'Emi Koussi, Tibesti'),
    ('Earth', 15.3, -24.73, 'Sossusvlei, Namib'), ('Earth', 119.4, -21.2, 'Pilbara, Australia'),
    ('Earth', 127.8, -19.17, 'Wolfe Creek crater'), ('Earth', -155.28, 19.41, 'Kilauea'),
    ('Earth', -113.52, 43.42, 'Craters of the Moon, Idaho'), ('Earth', -111.63, 35.58, 'SP Crater, San Francisco field'),
    ('Earth', -156.25, 20.71, 'Haleakala crater'), ('Earth', 40.3, 14.24, 'Dallol, Danakil'),
    ('Earth', 93.0, 38.0, 'Qaidam Basin'), ('Earth', 77.95, 33.3, 'Tso Kar, Ladakh'),
    ('Earth', -16.64, 28.27, 'Teide, Tenerife'), ('Earth', 15.0, 37.75, 'Mount Etna'),
    ('Earth', 160.33, 55.83, 'Tolbachik, Kamchatka'), ('Earth', -102.3, 43.75, 'Badlands, South Dakota'),
    ('Earth', -67.5, -20.25, 'Salar de Uyuni'), ('Earth', -67.88, -22.83, 'Licancabur, Altiplano'),
    ('Earth', 103.7, 44.1, 'Flaming Cliffs, Gobi'), ('Earth', 35.42, 29.58, 'Wadi Rum'),
    ('Earth', -119.0, 38.0, 'Mono Lake'), ('Earth', -115.79, 34.54, 'Amboy crater'),
    ('Earth', -113.85, 40.77, 'Bonneville Salt Flats'), ('Earth', -5.8, 30.35, 'Zagora, Draa valley (seeded 1900 m site)'),
    # Moon targets
    ('Moon', 23.47, 0.67, 'Apollo 11, Mare Tranquillitatis'), ('Moon', -23.42, -3.01, 'Apollo 12, Oceanus Procellarum'),
    ('Moon', -17.47, -3.65, 'Apollo 14, Fra Mauro'), ('Moon', 3.63, 26.13, 'Apollo 15, Hadley Rille'),
    ('Moon', 15.5, -8.97, 'Apollo 16, Descartes'), ('Moon', 30.77, 20.19, 'Apollo 17, Taurus-Littrow'),
    ('Moon', 0.0, -85.9, 'Malapert massif region'), ('Moon', -47.5, 24.0, 'Aristarchus plateau'),
    ('Moon', -11.36, -43.31, 'Tycho crater'), ('Moon', -20.0, 9.62, 'Copernicus crater'),
    ('Moon', -56.5, 13.4, 'Marius Hills'), ('Moon', -15.0, 33.0, 'Mare Imbrium'),
    ('Moon', -19.51, 44.12, "Chang'e 3, Mare Imbrium"), ('Moon', 177.6, -45.46, "Chang'e 4, Von Karman"),
    ('Moon', -59.0, 7.5, 'Reiner Gamma'),
    # Mars targets
    ('Mars', 137.44, -4.59, 'Gale crater (Curiosity)'), ('Mars', 77.45, 18.44, 'Jezero crater (Perseverance)'),
    ('Mars', -5.53, -1.95, 'Meridiani Planum (Opportunity)'), ('Mars', 175.47, -14.57, 'Gusev crater (Spirit)'),
    ('Mars', 135.62, 4.5, 'Elysium Planitia (InSight)'), ('Mars', 109.93, 25.07, 'Utopia Planitia (Zhurong)'),
    ('Mars', -125.75, 68.22, 'Phoenix landing site'), ('Mars', -133.8, 18.4, 'Olympus Mons caldera'),
    ('Mars', -73.0, -6.0, 'Candor Chasma, Valles Marineris'), ('Mars', -19.0, 24.0, 'Mawrth Vallis'),
    ('Mars', 70.0, -42.5, 'Hellas Planitia floor'), ('Mars', -160.0, 46.0, 'Arcadia Planitia'),
    ('Mars', -49.97, 22.48, 'Chryse Planitia (Viking 1)'), ('Mars', 134.29, 47.64, 'Utopia Planitia (Viking 2)'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--body')
    ap.add_argument('--backfill-osm', action='store_true', help='add OSM accessibility to stored Earth sites (sequential, polite)')
    args = ap.parse_args()
    if args.backfill_osm:
        from twinsite.sources import gateway, sites
        from twinsite.storage.science_db import science_db
        data_dir = load_settings().data_dir
        db = science_db(data_dir)
        for d in sites.load_sites(data_dir, 'Earth'):
            if db.observations([d['site_id']], domain='accessibility_environment')[0]:
                continue
            try:
                rows = gateway.acquire_osm_access(data_dir, d['site_id'], d['aoi'], timeout=60)
                print(json.dumps({'site': d['name'], 'osm': [(r['quantity'], r['value']) for r in rows]}), flush=True)
            except Exception as error:  # noqa: BLE001
                print(json.dumps({'site': d['name'], 'error': type(error).__name__}), flush=True)
            time.sleep(6)
        return
    data_dir = load_settings().data_dir
    todo = [s for s in SITES if not args.body or s[0] == args.body]

    def one(s):
        body, lon, lat, name = s
        t = time.time()
        try:
            d = characterize(data_dir, body, lon, lat, name)
            ok = [o['feature_id'] for o in d['observations'] if o['value'] is not None]
            return {'site': name, 'body': body, 'site_id': d['site_id'], 'features': ok, 'errors': d['acquisition_errors'],
                    'seconds': round(time.time() - t, 1)}
        except Exception as error:  # noqa: BLE001
            return {'site': name, 'body': body, 'error': f'{type(error).__name__}: {str(error)[:200]}'}

    results = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        for r in ex.map(one, todo):
            results.append(r)
            print(json.dumps(r), flush=True)
    ok = sum('error' not in r for r in results)
    print(json.dumps({'seeded': ok, 'failed': len(results) - ok}))
    (data_dir / 'seed-report.json').write_text(json.dumps(results, indent=1))


if __name__ == '__main__':
    main()
