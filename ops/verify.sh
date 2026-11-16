#!/usr/bin/env bash
# C5 one-shot verification ("make verify" equivalent). Read-only towards the repo:
# builds a composite tree OUTSIDE the repo (main + every lane branch overlaid) and
# tests that. Missing pieces are BLOCKED, never PASS. Exit 0 only if all PASS.
#
#   ops/verify.sh [--from-worktrees] [--out DIR]
#   env: TWINSITE_PYTHON (python with jsonschema; default <main>/.venv/bin/python)
#        TWINSITE_G2_EVIDENCE, TWINSITE_G2_ARTIFACT_ROOT, TWINSITE_G2_RESULT (C1/C3 measured run, optional)
#        TWINSITE_G2_REFETCH=1  (re-download sources to prove NASA origin; network)
set -uo pipefail
QA="$(cd "$(dirname "$0")/.." && pwd)"
MAIN="$(cd "$(git -C "$QA" rev-parse --path-format=absolute --git-common-dir)/.." && pwd)"
FROM_WT=""
OUT="${TMPDIR:-/tmp}/twinsite-verify"
while [ $# -gt 0 ]; do
  case "$1" in
    --from-worktrees) FROM_WT="--from-worktrees" ;;
    --out) OUT="$2"; shift ;;
    *) echo "unknown arg $1"; exit 64 ;;
  esac; shift
done
PY="${TWINSITE_PYTHON:-$MAIN/.venv/bin/python}"
TREE="$OUT/composite"; LOG="$OUT/logs"; SUM="$OUT/summary.tsv"
mkdir -p "$LOG"; : > "$SUM"
rec() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$SUM"; printf '%-9s %-44s %s\n' "$2" "$1" "$3"; }
run() { # name logfile cmd...
  local name="$1" log="$LOG/$2.log"; shift 2
  if "$@" > "$log" 2>&1; then rec "$name" PASS "$(tail -n1 "$log" | cut -c1-110)"
  else local rc=$?; [ $rc -eq 2 ] && st=BLOCKED || st=FAIL; rec "$name" $st "exit $rc: $(tail -n1 "$log" | cut -c1-100) [$log]"; fi
}

echo "TwinSite C5 verify — $(date -u +%FT%TZ) — SYNTHETIC checks never imply scientific validity"
if ! "$PY" -c 'import jsonschema, referencing' 2>/dev/null; then
  rec python_env BLOCKED "$PY lacks jsonschema; run 'make setup' in $MAIN"; PY_OK=0
else rec python_env PASS "$("$PY" --version)"; PY_OK=1; fi

run assemble_composite assemble "$PY" "$QA/ops/assemble.py" --out "$TREE" $FROM_WT
"$PY" - "$TREE/.c5_assembly.json" <<'EOF' >> "$SUM"
import json,sys
r=json.load(open(sys.argv[1]))
for v in r['ownership_violations']: print(f"ownership:{v['lane']}:{v['path']}\tWARN\toutside lane's owned paths — needs C0 ruling before merge")
for c in r['conflicts']: print(f"conflict:{c['path']}\tFAIL\tedited by {c['lanes']}")
for l in r['lanes']: print(f"lane:{l['id']}\tINFO\t{l['branch']} +{l['ahead_of_main']} commits, {l['committed_files']} committed, {l['uncommitted_files']} uncommitted files")
EOF

# Frontend: lockfile required; install so C0's checkpoint can build it.
if [ -f "$TREE/frontend/package.json" ]; then
  if [ -f "$TREE/frontend/package-lock.json" ]; then run frontend_npm_ci npm_ci bash -c "cd '$TREE/frontend' && npm ci --no-audit --no-fund"
  else rec frontend_lockfile FAIL "frontend/package-lock.json absent (reproducible install impossible)"
       run frontend_npm_install npm_install bash -c "cd '$TREE/frontend' && npm install --no-audit --no-fund"; fi
else rec frontend_present BLOCKED "C4 frontend/package.json absent"; fi

# C0's own gate, unmodified, inside the composite (schemas, types, freeze, reference smoke, TwinSite smoke, build).
if [ $PY_OK = 1 ]; then
  (cd "$TREE" && "$PY" scripts/integration/checkpoint.py > "$LOG/checkpoint.log" 2>&1)
  "$PY" - "$TREE/.runtime/checkpoint.json" <<'EOF' >> "$SUM"
import json,sys
for c in json.load(open(sys.argv[1]))['checks']:
    if c['name']=='twinsite_api_smoke':
        # C0's version targets whatever already listens on :8080 (possibly another lane's dev server).
        # The same smoke.py runs below against a stack C5 boots from the composite tree.
        print(f"c0:{c['name']}\tINFO\t{c['status']} against :8080 (not authoritative; see e2e:C0 smoke)"); continue
    print(f"c0:{c['name']}\t{c['status']}\t{c.get('reason','exit '+str(c.get('exit_code','')))}")
EOF
fi

run c5_provenance_selftest prov_selftest "$PY" -m unittest "$QA/tests/acceptance/test_provenance_check.py"
run c5_e2e_stack e2e "$PY" "$QA/tests/e2e/run_stack.py" --tree "$TREE" --python "$PY" --json "$OUT/e2e.json"
[ -f "$OUT/e2e.json" ] && "$PY" -c "
import json,sys
for r in json.load(open('$OUT/e2e.json')): print(f\"e2e:{r['check']}\t{r['status']}\t{r['detail'][:120]}\")" >> "$SUM"

# G2: real NASA provenance. Without a measured run this is BLOCKED, never PASS.
if [ -n "${TWINSITE_G2_EVIDENCE:-}" ]; then
  run g2_provenance g2 "$PY" "$QA/tests/acceptance/provenance_check.py" --evidence "$TWINSITE_G2_EVIDENCE" \
      --artifact-root "${TWINSITE_G2_ARTIFACT_ROOT:-}" ${TWINSITE_G2_RESULT:+--result "$TWINSITE_G2_RESULT"} \
      --repo "$TREE" ${TWINSITE_G2_REFETCH:+--refetch} --json "$OUT/g2.json"
else rec g2_provenance BLOCKED "no measured evidence supplied (TWINSITE_G2_EVIDENCE); no real NASA pair verified"; fi

# Secret scan of every file in the composite (excluding references, node_modules, build output).
run secret_scan secrets "$PY" "$QA/ops/secret_scan.py" "$TREE"

echo; echo "Summary: $SUM"
FAILS=$(awk -F'\t' '$2=="FAIL"' "$SUM" | wc -l | tr -d ' '); BLOCKS=$(awk -F'\t' '$2=="BLOCKED"' "$SUM" | wc -l | tr -d ' ')
PASSES=$(awk -F'\t' '$2=="PASS"' "$SUM" | wc -l | tr -d ' ')
echo "PASS=$PASSES FAIL=$FAILS BLOCKED=$BLOCKS"
awk -F'\t' '$2=="FAIL"||$2=="BLOCKED"||$2=="WARN"||$2=="NOT_EXERCISED"{print "  - "$2" "$1": "$3}' "$SUM"
[ "$FAILS" = 0 ] && [ "$BLOCKS" = 0 ] && { echo "VERIFY: ALL PASS (still requires G2 real-data review)"; exit 0; }
echo "VERIFY: HOLD"; exit 1
