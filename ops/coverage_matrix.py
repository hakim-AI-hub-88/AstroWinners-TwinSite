"""Write docs/release/COVERAGE_MATRIX.json from persisted evidence (python ops/coverage_matrix.py)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from twinsite.sources.coverage import matrix  # noqa: E402
from twinsite.storage import load_settings  # noqa: E402

rows = matrix(load_settings().data_dir)
out = {'schema': 'twinsite.coverage_matrix/1', 'generated_at': datetime.now(timezone.utc).isoformat(),
       'generated_from': 'science.sqlite + published G2 pair (actual persisted evidence)',
       'status_legend': {'real_data': 'retrieved, decoded, QA-checked and persisted', 'implemented': 'contract-level capability',
                         'reference_constant': 'bulk body constant only', 'visualization_only': 'imagery, not a measurement',
                         'source_metadata_only': 'catalog discovery only; no data retrieved', 'user_input': 'mission input',
                         'user_input_only': 'only user-provided values, never estimated', 'missing': 'no source implemented'},
       'summary': {s: sum(r['real_data_status'] == s for r in rows) for s in sorted({r['real_data_status'] for r in rows})},
       'rows': rows}
(ROOT / 'docs/release/COVERAGE_MATRIX.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out['summary']))
