import json
from pathlib import Path
import subprocess
import sys
from backend.env import replay,public_action,encode_action
from backend.engine import Action


def test_json_lines_bridge_and_private_trace_boundary():
    proc=subprocess.Popen([sys.executable,'-m','backend.cli'],
        cwd=Path(__file__).resolve().parents[2],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,encoding='utf-8')
    def ask(request):
        proc.stdin.write(json.dumps(request)+'\n')
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())
    try:
        assert not ask({'op':'export_trace'})['ok']
        start=ask({'op':'reset','seed':7,'max_decisions':1})
        obs=start['result']
        assert start['ok'] and obs['candidates']
        end=ask({'op':'step','action_code':obs['candidates'][0]['code'],'expected_revision':obs['revision']})
        assert end['ok'] and end['result']['transition']['truncated']
        trace=ask({'op':'export_trace'})
        assert trace['ok'] and replay(trace['result']).revision==1
        assert not ask({'op':'unknown'})['ok']
        assert ask({'op':'observe'})['ok']
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode==0,proc.stderr.read()


def test_public_history_redacts_facedown_payment():
    a=public_action(encode_action(Action('recruit','royal',recruit='archer')))
    b=public_action(encode_action(Action('recruit','scout',recruit='archer')))
    assert a==b and a['coin'] is None and a['recruit']=='archer'
