"""In-process training/data-collection API, intentionally independent of HTTP.

No model or shaping rewards. Actors get private observations, terminal team rewards,
and uint64-compatible legal candidate codes. A limit truncates; it is not a draw.
"""
from collections import Counter
import copy
from dataclasses import dataclass
from dataclasses import replace
from .engine import (Action, FULL_HEXS, HEXS, FULL_OBJECTIVES, OBJECTIVES, KINDS, board_hexes, clone, legal_actions,
    new_game, team, _apply_legal_action, check_invariants)
from .state import (RULESET_VERSION, action_dict, action_from_dict, snapshot,
    restore, state_digest)

OBSERVATION_VERSION=1
ACTION_ENCODING_VERSION=1
OPS=('pass','initiative','recruit','deploy','bolster','move','attack','control',
    'shot','move_two','charge','bonus_move','finish_bonus','command_move',
    'command_attack','footman_tactic','royal_move','guard_board','guard_supply','draft')
COINS=('',*KINDS,'royal')
COORDS=(None,*sorted(FULL_HEXS))
OP_ID={x:i for i,x in enumerate(OPS)}
COIN_ID={x:i for i,x in enumerate(COINS)}
COORD_ID={x:i for i,x in enumerate(COORDS)}
PHASES=('main','draft','sword_bonus','berserk_bonus','mercenary_bonus',
        'footman_bonus','forced_coin','guard_defense','end_turn','after_attack','priest_draw')
PHASE_ID={x:i for i,x in enumerate(PHASES)}
CELL_OFFSETS={xy:(i-1)*5 for xy,i in COORD_ID.items() if xy is not None}
BOARD_TEMPLATES={n:bytes(v for xy in COORDS[1:] for v in (
    int(xy in cells)|(2 if xy in objectives else 0),0,0,0,0))
    for n,cells,objectives in ((2,HEXS,OBJECTIVES),(4,FULL_HEXS,FULL_OBJECTIVES))}


def encode_action(a):
    return (OP_ID[a.op] | COIN_ID[a.coin]<<5 | COORD_ID[a.src]<<10 |
            COORD_ID[a.dst]<<16 | COORD_ID[a.aux]<<22 | COIN_ID[a.recruit]<<28)


def decode_action(code):
    if not isinstance(code,int) or isinstance(code,bool) or code<0 or code>>33:
        raise ValueError('invalid action code')
    try:
        return Action(OPS[code&31], COINS[(code>>5)&31], COORDS[(code>>10)&63],
            COORDS[(code>>16)&63], COORDS[(code>>22)&63], COINS[(code>>28)&31])
    except IndexError as exc:
        raise ValueError('invalid action code') from exc


def public_action(code):
    """Structured public history entry. Facedown payment identities stay hidden."""
    a=decode_action(code)
    return {'op':a.op,'coin':None if a.op in ('pass','recruit','initiative') else a.coin,
            'src':a.src,'dst':a.dst,'aux':a.aux,'recruit':a.recruit}


def _counts(coins):
    c=Counter(coins)
    return {k:c[k] for k in (*KINDS,'royal') if c[k]}


def observation(game, seat, actions=None):
    if seat not in game.players:
        raise ValueError('unknown seat')
    public={}
    for side,p in game.players.items():
        public[side]={"team":team(game,side),"army":list(p.army),
            "supply":dict(p.supply),"removed":dict(p.removed),
            "bag_count":len(p.bag),"hand_count":len(p.hand),
            "discard_count":len(p.discard),
            "faceup_discard":_counts(k for k,up in p.discard if up)}
    p=game.players[seat]
    own={"hand":_counts(p.hand),"bag":_counts(p.bag),
         "discard":[[k,up] for k,up in p.discard]}
    candidates=(() if game.winner or game.decision!=seat else
                (legal_actions(game) if actions is None else actions))
    forced_coin=(game.tasks[-1].coin if game.phase=='forced_coin' and game.decision==seat else None)
    pending=[]
    for t in game.tasks:
        pending.append({'kind':t.kind,'side':t.side,'src':t.src,'dst':t.dst,
            'remaining':list(t.remaining),
            'coin':t.coin if t.kind!='forced_coin' or t.side==seat else None})
    return {"schema_version":OBSERVATION_VERSION,"ruleset_version":RULESET_VERSION,
        "royal_guard_version":game.royal_guard_version,
        "action_encoding_version":ACTION_ENCODING_VERSION,
        "revision":game.revision,"viewer":seat,"team":team(game,seat),
        "decision_player":None if game.winner else game.decision,
        "initiative":game.initiative,"initiative_moved":game.initiative_moved,
        "phase":game.phase,"round":game.round_no,"winner":game.winner,
        "control_target":game.control_target,"turn_order":list(game.turn_order),
        "board":[[q,r,game.objective_owner.get((q,r)),
            None if (q,r) not in game.units else
            [game.units[q,r].owner,game.units[q,r].kind,game.units[q,r].count]]
            for q,r in sorted(board_hexes(game))],
        "objective_hexes":[list(x) for x in sorted(game.objective_owner)],
        "players":public,"own":own,"forced_coin":forced_coin,"pending":pending,
        "draft_pool":list(game.draft_pool),
        "legal_action_codes":[encode_action(a) for a in candidates]}


@dataclass(frozen=True,slots=True)
class PackedObservation:
    """Immutable numeric buffers, no JSON or framework dependency. Layout v1."""
    schema_version: int
    context: tuple[int,...]
    board: bytes
    players: bytes
    own: bytes
    pending: tuple[tuple[int,...],...]
    legal_action_codes: tuple[int,...]
    truncated: bool = False


def packed_observation(game,seat,codes=None):
    if seat not in game.players: raise ValueError('unknown seat')
    indices={s:i+1 for i,s in enumerate(game.turn_order)}
    faction=lambda s: 1 if team(game,s)=='south' else 2
    board=bytearray(BOARD_TEMPLATES[len(game.players)])
    for xy,owner in game.objective_owner.items():
        if owner is not None: board[CELL_OFFSETS[xy]+1]=1 if owner=='south' else 2
    for xy,u in game.units.items():
        offset=CELL_OFFSETS[xy]
        board[offset+2]=indices[u.owner]
        board[offset+3]=COIN_ID[u.kind]
        board[offset+4]=u.count
    players=bytearray(len(game.players)*69)
    for index,s in enumerate(game.turn_order):
        p=game.players[s]
        offset=index*69
        players[offset:offset+4]=bytes((faction(s),len(p.bag),len(p.hand),len(p.discard)))
        for k in p.army:
            kind=COIN_ID[k]-1
            players[offset+4+kind]=1
            players[offset+20+kind]=p.supply[k]
            players[offset+36+kind]=p.removed[k]
        for k,up in p.discard:
            if up: players[offset+52+COIN_ID[k]-1]+=1
    p=game.players[seat]
    own=bytearray(51)
    for k in p.hand: own[COIN_ID[k]-1]+=1
    for k in p.bag: own[17+COIN_ID[k]-1]+=1
    for k,_ in p.discard: own[34+COIN_ID[k]-1]+=1
    pending=tuple((PHASE_ID[t.kind],indices[t.side],COORD_ID[t.src],COORD_ID[t.dst],
        COIN_ID[t.coin] if t.kind!='forced_coin' or t.side==seat else 0,
        *(COORD_ID[xy] for xy in t.remaining)) for t in game.tasks)
    context=(indices[seat],0 if game.winner else indices[game.decision],
        indices[game.initiative],int(game.initiative_moved),PHASE_ID[game.phase],
        game.round_no,game.control_target,0 if game.winner is None else (1 if game.winner=='south' else 2),
        int(game.royal_guard_version=='revised'),len(game.players),game.revision)
    if codes is None:
        codes=(encode_action(a) for a in legal_actions(game)) if game.decision==seat and not game.winner else ()
    return PackedObservation(1,context,bytes(board),bytes(players),bytes(own),pending,
        tuple(codes) if game.decision==seat and not game.winner else ())


@dataclass(frozen=True,slots=True)
class StepResult:
    actor: str
    decision_player: str | None
    rewards: dict[str,float]
    terminated: bool
    truncated: bool
    revision: int


class WarChestEnv:
    """One owned mutable environment. Use clone() for branches and worker processes.

    step(code, expected_revision=...) checks the current legal set before mutation.
    observe() is deliberately separate: rollouts need not serialize every step.
    """
    def __init__(self, seed=0, *, max_decisions=None, record_trace=False,
                 verify=False, **options):
        if max_decisions is not None and (not isinstance(max_decisions,int) or max_decisions<=0):
            raise ValueError('max_decisions must be a positive integer or None')
        self.max_decisions=max_decisions
        self.record_trace=record_trace
        self.verify=verify
        self.reset(seed,**options)

    def reset(self, seed=0, **options):
        options.setdefault('record_events',False)
        self._game=new_game(seed,**options)
        self.seed=seed
        self.options=options
        self.steps=0
        self.truncated=False
        self.trace=[]
        self._cached_revision=-1
        self._initial=snapshot(self._game) if self.record_trace else None
        return self.observe()

    @property
    def revision(self): return self._game.revision

    @property
    def decision_player(self): return None if self._game.winner else self._game.decision

    @property
    def done(self): return bool(self._game.winner) or self.truncated

    def _actions(self):
        if self._cached_revision!=self.revision:
            acts=legal_actions(self._game)
            self._codes={encode_action(a):a for a in acts}
            self._cached_revision=self.revision
        return self._codes

    def legal_action_codes(self):
        return () if self.done else tuple(self._actions())

    def observe(self, seat=None):
        seat=seat or self._game.decision
        actions=() if self.done else self._actions().values()
        obs=observation(self._game,seat,actions)
        obs['truncated']=self.truncated
        return obs

    def observe_packed(self,seat=None):
        obs=packed_observation(self._game,seat or self._game.decision,self.legal_action_codes())
        return replace(obs,truncated=True) if self.truncated else obs

    def step(self, code, *, expected_revision):
        if self.done:
            raise ValueError('episode already ended')
        if expected_revision!=self.revision:
            raise ValueError('stale revision')
        # bool and non-integral floats must not alias an integer action code.
        if not isinstance(code,int) or isinstance(code,bool):
            raise ValueError('action code must be an integer')
        chosen=self._actions().get(code)
        if chosen is None:
            raise ValueError('illegal action code')
        actor=self._game.decision
        _apply_legal_action(self._game,chosen)
        if self.verify: check_invariants(self._game)
        self.steps+=1
        terminated=bool(self._game.winner)
        self.truncated=bool(not terminated and self.max_decisions is not None and self.steps>=self.max_decisions)
        if self.record_trace:
            self.trace.append({"actor":actor,"action":action_dict(chosen),
                "revision":self.revision,"state_digest":state_digest(self._game)})
        rewards={s: (1.0 if team(self._game,s)==self._game.winner else -1.0)
            if terminated else 0.0 for s in self._game.players}
        return StepResult(actor,self.decision_player,rewards,terminated,self.truncated,self.revision)

    def clone(self):
        branch=object.__new__(WarChestEnv)
        branch.__dict__=self.__dict__.copy()
        branch._game=clone(self._game)
        branch.trace=self.trace.copy()
        branch._cached_revision=-1
        return branch

    def export_trace(self):
        if not self.record_trace:
            raise ValueError('enable record_trace at episode creation')
        return {"schema_version":1,"ruleset_version":RULESET_VERSION,
            "initial_state":copy.deepcopy(self._initial),"decisions":copy.deepcopy(self.trace),
            "terminated":bool(self._game.winner),"truncated":self.truncated,
            "max_decisions":self.max_decisions,"winner":self._game.winner}

    def trusted_snapshot(self):
        return snapshot(self._game)


def replay(trace):
    if trace.get('schema_version')!=1 or trace.get('ruleset_version')!=RULESET_VERSION:
        raise ValueError('incompatible trace')
    game=restore(trace['initial_state'])
    for entry in trace['decisions']:
        a=action_from_dict(entry['action'])
        if entry['actor']!=game.decision or a not in legal_actions(game):
            raise ValueError('illegal replay decision')
        _apply_legal_action(game,a)
        if entry['revision']!=game.revision or entry['state_digest']!=state_digest(game):
            raise ValueError('replay diverged')
    if trace.get('winner')!=game.winner or trace.get('terminated') is not bool(game.winner):
        raise ValueError('incorrect replay outcome')
    if trace.get('truncated'):
        limit=trace.get('max_decisions')
        if game.winner or not isinstance(limit,int) or limit<=0 or len(trace['decisions'])<limit:
            raise ValueError('incorrect truncation outcome')
    check_invariants(game)
    return game
