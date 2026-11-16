"""Persistent scientific store: sources, raw assets (bytes in managed storage, referenced by
sha256), sites, and normalized observations with lineage, units, support and QA.

Observation `kind` keeps measurement semantics explicit:
  measurement | derived_measurement | reanalysis_model | visualization | reference_constant | discovery_only
"""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

KINDS = ('measurement', 'derived_measurement', 'reanalysis_model', 'visualization', 'reference_constant', 'discovery_only')
_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class ScienceDB:
    def __init__(self, path):
        self.path = str(path)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY, name TEXT, provider TEXT, bodies TEXT, domains TEXT, access TEXT,
                    auth TEXT, documentation_url TEXT, status TEXT, notes TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY, source_id TEXT, product_id TEXT, granule_id TEXT, source_url TEXT,
                    sha256 TEXT, byte_size INTEGER, media_type TEXT, object_key TEXT, retrieved_at TEXT);
                CREATE TABLE IF NOT EXISTS sites (
                    site_id TEXT PRIMARY KEY, name TEXT, body TEXT, crs TEXT, lon REAL, lat REAL, bbox TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS observations (
                    evidence_id TEXT PRIMARY KEY, site_id TEXT, body TEXT, domain TEXT, quantity TEXT, value REAL,
                    unit TEXT, kind TEXT, statistic TEXT, temporal_support TEXT, spatial_support TEXT, crs TEXT,
                    vertical_datum TEXT, qa_status TEXT, quality_flags TEXT, uncertainty TEXT, missing_reason TEXT,
                    source_id TEXT, product_id TEXT, asset_id TEXT, processing TEXT, comparability TEXT, created_at TEXT);
                CREATE INDEX IF NOT EXISTS obs_site ON observations(site_id);
                CREATE INDEX IF NOT EXISTS obs_domain ON observations(domain, body);
            """)

    @contextmanager
    def _db(self):
        with _LOCK:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            finally:
                db.close()

    def upsert_source(self, **row):
        row.setdefault('updated_at', _now())
        for k in ('bodies', 'domains'):
            if isinstance(row.get(k), (list, tuple)):
                row[k] = json.dumps(list(row[k]))
        self._upsert('sources', row)

    def upsert_asset(self, **row):
        row.setdefault('retrieved_at', _now())
        self._upsert('assets', row)

    def upsert_site(self, keep_name=False, **row):
        row.setdefault('created_at', _now())
        if keep_name:
            with self._db() as db:
                old = db.execute('SELECT name FROM sites WHERE site_id=?', (row['site_id'],)).fetchone()
            if old and old[0] and old[0] != row['site_id']:
                row['name'] = old[0]
        if isinstance(row.get('bbox'), (list, tuple)):
            row['bbox'] = json.dumps(list(row['bbox']))
        self._upsert('sites', row)

    def upsert_observation(self, **row):
        assert row['kind'] in KINDS, row['kind']
        row.setdefault('created_at', _now())
        for k in ('quality_flags', 'uncertainty', 'comparability'):
            if not isinstance(row.get(k), (str, type(None))):
                row[k] = json.dumps(row[k])
        self._upsert('observations', row)

    def _upsert(self, table, row):
        cols = ','.join(row)
        with self._db() as db:
            db.execute(f'INSERT OR REPLACE INTO {table}({cols}) VALUES({",".join("?" * len(row))})', tuple(row.values()))

    @staticmethod
    def _decode(row):
        out = dict(row)
        for k in ('quality_flags', 'uncertainty', 'comparability', 'bodies', 'domains', 'bbox'):
            if isinstance(out.get(k), str) and out[k][:1] in '[{':
                out[k] = json.loads(out[k])
        return out

    def sources(self):
        with self._db() as db:
            return [self._decode(r) for r in db.execute('SELECT * FROM sources ORDER BY source_id')]

    def sites(self):
        with self._db() as db:
            rows = db.execute("""SELECT s.*, count(o.evidence_id) AS observation_count FROM sites s
                                 LEFT JOIN observations o ON o.site_id=s.site_id GROUP BY s.site_id ORDER BY s.created_at""")
            return [self._decode(r) for r in rows]

    def observations(self, site_ids=None, domain=None, body=None, kind=None, limit=100, offset=0):
        sql, args = 'SELECT * FROM observations WHERE 1=1', []
        if site_ids:
            sql += f' AND site_id IN ({",".join("?" * len(site_ids))})'
            args += list(site_ids)
        for col, val in (('domain', domain), ('body', body), ('kind', kind)):
            if val:
                sql += f' AND {col}=?'
                args.append(val)
        with self._db() as db:
            total = db.execute(sql.replace('SELECT *', 'SELECT count(*)'), args).fetchone()[0]
            rows = db.execute(sql + ' ORDER BY site_id, domain, quantity LIMIT ? OFFSET ?', args + [limit, offset]).fetchall()
        return total, [self._decode(r) for r in rows]

    def asset(self, asset_id):
        with self._db() as db:
            row = db.execute('SELECT * FROM assets WHERE asset_id=?', (asset_id,)).fetchone()
        return dict(row) if row else None

    def coverage(self):
        with self._db() as db:
            return [dict(r) for r in db.execute("""SELECT body, domain, kind, source_id, count(*) AS n,
                     count(DISTINCT site_id) AS sites FROM observations GROUP BY body, domain, kind, source_id""")]


def science_db(data_dir):
    return ScienceDB(data_dir / 'science.sqlite')


def wait(seconds):
    time.sleep(seconds)
