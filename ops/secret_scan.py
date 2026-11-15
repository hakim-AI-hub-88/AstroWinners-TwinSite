"""Scan a tree for committed credentials. Prints findings with redacted values; exit 1 on any.

  python ops/secret_scan.py <tree>
"""
import re
import sys
from pathlib import Path

SKIP_DIRS = {'.git', 'node_modules', '.venv', 'references', '__pycache__', '.runtime', 'dist'}
PATTERNS = [
    ('openai/anthropic-style key', re.compile(r'\bsk-(ant-)?[A-Za-z0-9_-]{20,}')),
    ('groq key', re.compile(r'\bgsk_[A-Za-z0-9]{20,}')),
    ('google api key', re.compile(r'\bAIza[0-9A-Za-z_-]{30,}')),
    ('aws access key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('github token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}')),
    ('huggingface token', re.compile(r'\bhf_[A-Za-z0-9]{30,}')),
    ('private key block', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('jwt (Earthdata token?)', re.compile(r'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}')),
    ('netrc credential', re.compile(r'machine\s+urs\.earthdata\.nasa\.gov\s+login\s+\S+\s+password\s+\S+')),
]
# Env-style assignments with a non-empty value, only in config-like files (not source code).
ENV_ASSIGN = re.compile(r'(?m)^[ \t]*(export[ \t]+)?(EARTHDATA_(USERNAME|PASSWORD|TOKEN)|[A-Z_]*API_KEY|[A-Z_]*SECRET[A-Z_]*|[A-Z_]*TOKEN)[ \t]*=[ \t]*["\']?[^\s"\'#]{6,}')
CONFIG_SUFFIXES = {'.env', '.sh', '.ini', '.toml', '.yml', '.yaml', '.cfg', '.conf', '.service', '.json'}


def config_like(p):
    return p.name.startswith('.env') or p.suffix in CONFIG_SUFFIXES or p.name in ('Dockerfile', 'Procfile')


def main(tree):
    root = Path(tree)
    findings = []
    for p in root.rglob('*'):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        rel = p.relative_to(root)
        if p.name.startswith('.env') and p.name != '.env.example':
            findings.append((str(rel), 'committed .env file'))
        if p.stat().st_size > 5_000_000:
            continue
        try:
            text = p.read_text(errors='ignore')
        except OSError:
            continue
        for label, pat in PATTERNS + ([('assigned credential env', ENV_ASSIGN)] if config_like(p) else []):
            for m in pat.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                findings.append((f'{rel}:{line}', f'{label} ({m.group(0)[:6]}…redacted)'))
    for where, what in findings:
        print(f'SECRET? {where}: {what}')
    print(f'secret scan: {len(findings)} finding(s) in {root}')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
