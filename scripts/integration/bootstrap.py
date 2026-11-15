"""Restore pinned, reference-only archives without overwriting authored files."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    manifest = json.loads((ROOT / 'references/SNAPSHOT.json').read_text())
    for item in manifest['packages']:
        source = ROOT / item['path']
        if hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
            raise SystemExit(f'Reference snapshot mismatch: {source.name}')
        out = ROOT / 'references/extracted' / source.stem
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                target = (out / member.filename).resolve()
                if not target.is_relative_to(out.resolve()):
                    raise SystemExit('Unsafe archive path')
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                data = archive.read(member)
                if target.exists() and target.read_bytes() != data:
                    raise SystemExit(f'Refusing to overwrite modified reference: {target}')
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_bytes(data)
    print('Pinned reference archives verified and extracted; synthetic science only.')


if __name__ == '__main__':
    main()
