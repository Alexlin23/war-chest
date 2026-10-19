"""JSON-lines environment bridge for local tools/LLM data collection; no model.

Run: python -m backend.cli. One request and response per line. Only observations
are returned during play; full traces can be exported only after the episode ends.
"""
import json
import sys
from dataclasses import asdict
from .env import WarChestEnv, decode_action
from .state import action_dict


def response(env):
    obs=env.observe()
    obs['candidates']=[{'code':c,**action_dict(decode_action(c))} for c in env.legal_action_codes()]
    return obs


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    env=WarChestEnv(record_trace=True,max_decisions=2000)
    for line in sys.stdin:
        try:
            request=json.loads(line)
            op=request['op']
            if op=='reset':
                # Build a new instance so a failed reset cannot corrupt an episode.
                candidate=WarChestEnv(seed=request.get('seed',0),
                    max_decisions=request.get('max_decisions',2000),record_trace=True,
                    **request.get('options',{}))
                env=candidate
                result=response(env)
            elif op=='observe':
                result=response(env)
            elif op=='step':
                transition=env.step(request['action_code'],expected_revision=request['expected_revision'])
                result={'transition':asdict(transition),'observation':response(env)}
            elif op=='export_trace':
                if not env.done: raise ValueError('full trace is private until the episode ends')
                result=env.export_trace()
            else:
                raise ValueError('unknown operation')
            print(json.dumps({'ok':True,'result':result},ensure_ascii=False),flush=True)
        except (ValueError,KeyError,TypeError) as exc:
            print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
