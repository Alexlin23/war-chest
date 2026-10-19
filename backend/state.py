"""Versioned trusted snapshots. Private information: never serve as player views.

JSON only; no pickle, executable payloads or interpreter objects in saved files.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import random
from .engine import Action, GameState, Player, Task, Unit, check_invariants

RULESET_VERSION = "base-1"
SNAPSHOT_VERSION = 1


def action_dict(action):
    return asdict(action)


def action_from_dict(data):
    fields = dict(data)
    for key in ('src','dst','aux'):
        if fields.get(key) is not None:
            fields[key] = tuple(fields[key])
    return Action(**fields)


def snapshot(game):
    return {"schema_version": SNAPSHOT_VERSION, "ruleset_version": RULESET_VERSION,
        "players": {s: {**asdict(p),"removed":dict(p.removed)} for s,p in game.players.items()},
        "units": [[*xy,asdict(u)] for xy,u in sorted(game.units.items())],
        "objectives": [[*xy,v] for xy,v in sorted(game.objective_owner.items())],
        "rng": game.rng.getstate(),
        **{k:getattr(game,k) for k in ('initiative','decision','round_no',
            'initiative_moved','phase','pending_unit','winner','revision',
            'royal_guard_version','record_events','turn_order','control_target',
            'draft_pool','draft_order','draft_index')},
        "events":list(game.events),"teams":dict(game.teams),
        "tasks": [asdict(t) for t in game.tasks]}


def _tuples(value):
    return tuple(_tuples(x) for x in value) if isinstance(value,list) else value


def restore(data):
    if data.get('schema_version') != SNAPSHOT_VERSION or data.get('ruleset_version') != RULESET_VERSION:
        raise ValueError('incompatible snapshot or ruleset')
    players = {}
    for side, raw in data['players'].items():
        p=dict(raw)
        p['army']=tuple(p['army'])
        p['bag'],p['hand']=list(p['bag']),list(p['hand'])
        p['supply']=dict(p['supply'])
        p['discard']=[tuple(x) for x in p['discard']]
        p['removed']=Counter(p['removed'])
        players[side]=Player(**p)
    rng=random.Random(0)
    rng.setstate(_tuples(data['rng']))
    tasks=[]
    for raw in data['tasks']:
        t=dict(raw)
        for k in ('src','dst'):
            t[k]=tuple(t[k]) if t[k] is not None else None
        t['remaining']=tuple(tuple(x) for x in t['remaining'])
        tasks.append(Task(**t))
    game=GameState(players=players,
        units={(q,r):Unit(**u) for q,r,u in data['units']},
        objective_owner={(q,r):v for q,r,v in data['objectives']},rng=rng,
        **{k:data[k] for k in ('initiative','decision','round_no','initiative_moved',
            'phase','winner','revision','royal_guard_version','record_events',
            'control_target','draft_index')},
        teams=dict(data['teams']), turn_order=tuple(data['turn_order']),
        draft_pool=tuple(data['draft_pool']), draft_order=tuple(data['draft_order']),
        pending_unit=tuple(data['pending_unit']) if data['pending_unit'] is not None else None,
        events=[tuple(e) for e in data['events']],tasks=tasks)
    check_invariants(game)
    return game


def dumps(game):
    return json.dumps(snapshot(game),ensure_ascii=False,separators=(',',':'))


def loads(payload):
    return restore(json.loads(payload))


def state_digest(game):
    data=snapshot(game)
    # Presentation logging has no effect on rules, randomness or replay identity.
    data.pop('events')
    data.pop('record_events')
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
