from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from contracts.validation import validate


def main():
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print('BLOCKED: jsonschema is unavailable. Run make setup; schema checks did not pass.',file=sys.stderr)
        raise SystemExit(2)
    for schema in (ROOT / 'contracts/v1').glob('*.schema.json'):
        Draft202012Validator.check_schema(json.loads(schema.read_text()))
    index = json.loads((ROOT / 'contracts/examples/index.json').read_text())
    for entry in index['examples']:
        value = json.loads((ROOT / 'contracts' / entry['file']).read_text())
        name = Path(entry['schema']).name.removesuffix('.schema.json')
        validate(name, value)
    print(f"PASS: Draft 2020-12 schemas and {len(index['examples'])} shared examples")


if __name__ == '__main__':
    main()
