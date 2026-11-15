"""Bounded API contract smoke. Reference mode is explicitly synthetic-only."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from contracts.validation import validate
REFERENCE=ROOT/'references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation'


def fetch(base,path,body=None,key=None,content_type='application/json'):
    headers={}
    if body is not None:
        headers['Content-Type']=content_type
    if key:
        headers['Idempotency-Key']=key
    request=Request(base+path,data=json.dumps(body,allow_nan=False).encode() if body is not None else None,headers=headers)
    try:
        response=urlopen(request,timeout=5)
    except HTTPError as error:
        response=error
    with response:
        data=response.read()
        media=response.headers.get('Content-Type','')
        return response.status,json.loads(data) if 'application/json' in media else data.decode()


def expect(code, expected):
    if code!=expected:
        raise AssertionError(f'Expected HTTP {expected}, received {code}')


def run(base,reference=False,worker=None):
    code,health=fetch(base,'/v1/health');expect(code,200)
    if not reference:
        validate('health',health)
    payload=json.loads((ROOT/'contracts/examples/mission.synthetic.json').read_text())
    if not reference:
        validate('mission_request',payload)
    key='smoke-'+uuid.uuid4().hex
    code,accepted=fetch(base,'/v1/missions',payload,key);expect(code,202)
    if not reference:
        validate('mission_accepted',accepted)
    run_id=accepted['id'] if reference else accepted['run_id']
    path='/v1/missions/'+run_id
    code,replay=fetch(base,'/v1/missions',payload,key);expect(code,202)
    assert replay['id']==run_id
    changed=json.loads(json.dumps(payload));changed['mission']['id']='conflicting-payload'
    code,_=fetch(base,'/v1/missions',changed,key);expect(code,409)
    if worker:
        code,_=fetch(base,path+'/result');expect(code,409)
        worker()
    deadline=time.monotonic()+20
    while True:
        code,result=fetch(base,path+'/result')
        if code==200:
            break
        expect(code,409)
        if time.monotonic()>deadline:
            raise AssertionError('Worker did not commit a result within 20 seconds')
        time.sleep(.1)
    assert result['data_status']=='synthetic'
    baseline=json.loads((ROOT/'contracts/examples/mission.result.synthetic.json').read_text())
    if reference:
        assert result==baseline, 'Reference fixture result changed from the frozen deterministic baseline'
    else:
        # C2 may ship a different versioned algorithm; compare two fresh jobs
        # under the same current implementation instead of imposing ARES scores.
        code,second=fetch(base,'/v1/missions',payload,key+'-replay');expect(code,202)
        validate('mission_accepted',second)
        replay_deadline=time.monotonic()+20
        while True:
            code,recomputed=fetch(base,'/v1/missions/'+second['run_id']+'/result')
            if code==200: break
            expect(code,409)
            if time.monotonic()>replay_deadline: raise AssertionError('Deterministic replay timed out')
            time.sleep(.1)
        assert recomputed==result, 'Identical inputs must produce identical scientific results'
    if not reference:
        validate('mission_result',result)
    code,status=fetch(base,path);expect(code,200)
    if not reference:
        validate('mission_status',status)
    code,events=fetch(base,path+'/events?after=0');expect(code,200)
    seq=[e['sequence'] for e in events];assert seq==sorted(set(seq)) and seq
    code,tail=fetch(base,path+'/events?after='+str(seq[-1]));expect(code,200);assert not tail
    if not reference:
        validate('events',events)
        code,evidence=fetch(base,path+'/evidence');expect(code,200);validate('release_evidence',evidence)
        assert evidence['data_status']=='synthetic' and evidence['release_action']=='BLOCK'
    code,report=fetch(base,path+'/report');expect(code,200);assert 'synthetic' in report.lower()
    code,_=fetch(base,'/v1/missions/not-a-run/result');expect(code,404)
    code,_=fetch(base,'/v1/missions',{},'bad-payload');expect(code,422)
    code,_=fetch(base,'/v1/missions',payload,'wrong-media','text/plain');expect(code,415)
    code,_=fetch(base,path+'/events?after=oops');expect(code,400)
    # Historical UI assets exist and consume the mission endpoints; visual QA is separate.
    if reference:
        code,page=fetch(base,'/');expect(code,200);assert '<html' in page.lower()
        code,script=fetch(base,'/app.js');expect(code,200);assert '/v1/missions' in script
    print('PASS: '+('historical reference' if reference else 'TwinSite')+' submit, idempotency, worker, deterministic result, events, report, failure responses. SYNTHETIC ONLY.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reference',action='store_true');parser.add_argument('--base-url',default='http://127.0.0.1:8080');args=parser.parse_args()
    if not args.reference:
        run(args.base_url)
        return
    with tempfile.TemporaryDirectory(prefix='twinsite-smoke-') as folder:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        db=str(Path(folder)/'jobs.sqlite')
        process=subprocess.Popen([sys.executable,'-m','ares','serve','--db',db,'--port',str(port)],cwd=REFERENCE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        base=f'http://127.0.0.1:{port}'
        try:
            deadline=time.monotonic()+5
            while True:
                try:
                    fetch(base,'/v1/health');break
                except (URLError,ConnectionError):
                    if process.poll() is not None or time.monotonic()>deadline:
                        raise RuntimeError('Reference API failed to start')
                    time.sleep(.05)
            def worker():
                subprocess.run([sys.executable,'-m','ares','worker','--db',db,'--once'],cwd=REFERENCE,check=True,timeout=20)
            run(base,reference=True,worker=worker)
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()


if __name__=='__main__':
    try:
        main()
    except PermissionError:
        print('BLOCKED: sandbox prohibits local socket binding; HTTP smoke did not execute.',file=sys.stderr)
        raise SystemExit(2)
