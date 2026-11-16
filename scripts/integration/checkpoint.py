"""One-shot gate, or a 75-minute local watcher. Missing checks never count as PASS."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]


def checkpoint():
    runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
    checks=[('integration_unittest',[sys.executable,'-m','unittest','discover','-s','scripts/integration/tests','-v'],ROOT),
            ('schema_validation',[sys.executable,'scripts/integration/validate_contracts.py'],ROOT),
            ('typescript_contract_drift',[sys.executable,'scripts/integration/generate_types.py','--check'],ROOT),
            ('reference_unittest',[sys.executable,'-m','unittest','discover','-s','tests','-v'],ROOT/'references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation'),
            ('handoff_unittest',[sys.executable,'-m','unittest','discover','-s','validation','-v'],ROOT/'references/extracted/TwinSite_Engineering_Handoff/TwinSite_Engineering_Handoff'),
            ('contract_freeze',[sys.executable,'scripts/integration/freeze.py','--check'],ROOT),
            ('reference_api_smoke',[sys.executable,'scripts/integration/smoke.py','--reference'],ROOT)]
    report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'checks':[],'scientific_gate':'BLOCKED_NO_VALIDATED_SOURCE_PAIR'}
    if (ROOT/'frontend/package.json').exists():
        checks.append(('frontend_build',['npm','run','build'],ROOT/'frontend'))
    else:
        report['checks'].append({'name':'frontend_build','status':'BLOCKED','reason':'C4 package.json absent'})
    if (ROOT/'backend/twinsite/api/__main__.py').exists():
        checks.append(('twinsite_api_smoke',[sys.executable,'scripts/integration/smoke.py'],ROOT))
    else:
        report['checks'].append({'name':'twinsite_api_smoke','status':'BLOCKED','reason':'C3 entry point absent'})
    for name,command,cwd in checks:
        try:
            completed=subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=120)
            entry={'name':name,'status':'PASS' if completed.returncode==0 else 'BLOCKED' if completed.returncode==2 else 'FAIL','exit_code':completed.returncode}
            if name=='integration_unittest' and 'skipped=' in completed.stderr:
                entry['status']='PARTIAL'
                entry['reason']='Some tests skipped; see schema_validation check'
            # Never save arbitrary service output or environment values to reports.
            print(f"{name}: {entry['status']}",flush=True)
            if completed.returncode!=0 and name in ('schema_validation','reference_api_smoke'):
                print('Check unavailable or failed; run its Make target directly for diagnostics.',flush=True)
        except (OSError,subprocess.TimeoutExpired) as error:
            entry={'name':name,'status':'BLOCKED','reason':type(error).__name__}
        report['checks'].append(entry)
    report['passed']=all(c['status']=='PASS' for c in report['checks'])
    (runtime/'checkpoint.json').write_text(json.dumps(report,indent=2)+'\n')
    print('G1 '+('CHECKS PASS (owner review still required)' if report['passed'] else 'BLOCKED; see .runtime/checkpoint.json'),flush=True)
    return report['passed']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    while True:
        passed=checkpoint()
        if not args.watch:
            raise SystemExit(0 if passed else 1)
        # Short intervals keep SIGINT responsive; rerun every 75 minutes.
        deadline=time.monotonic()+75*60
        while time.monotonic()<deadline:
            time.sleep(min(1,deadline-time.monotonic()))


if __name__=='__main__':
    main()
