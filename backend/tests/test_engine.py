import copy
import random
from collections import Counter

import pytest

from backend.engine import (Action, COIN_TOTALS, HEXS, NAMES, ROSTERS, GameState, Unit,
                            check_invariants, hexdist, legal_actions, new_game, apply_action)


def put(g, side, kind, where, count=1):
    assert where in HEXS and where not in g.units
    g.players[side].supply[kind] -= count
    assert g.players[side].supply[kind] >= 0
    g.units[where] = Unit(side, kind, count)


def give(g, side, kind):
    p = g.players[side]
    p.bag.remove(kind)
    p.hand.append(kind)


def actions(g,op):
    return [a for a in legal_actions(g) if a.op==op]


def test_setup_first_game_and_coin_conservation():
    g=new_game(42)
    assert g.decision==g.initiative=='south'
    assert len(HEXS)==37
    assert len(g.objective_owner)==10
    assert all(len(p.army)==4 and len(p.hand)==3 for p in g.players.values())
    assert set(ROSTERS['north']).isdisjoint(set(ROSTERS['south']))
    check_invariants(g)


def test_actions_no_mutation_and_illegal_rejected():
    g=new_game(7)
    old=copy.deepcopy(g)
    legal_actions(g)
    assert g.players==old.players and g.units==old.units and g.revision==old.revision
    assert g.rng.getstate()==old.rng.getstate()
    with pytest.raises(ValueError):
        apply_action(g,Action('deploy',coin='royal',dst=(0,0)))
    assert g.revision==0
    check_invariants(g)


def test_royal_only_facedown_actions():
    g=new_game(2)
    if 'royal' not in g.players['south'].hand: give(g,'south','royal')
    acts=[a for a in legal_actions(g) if a.coin=='royal']
    assert acts
    assert {a.op for a in acts} <= {'pass','recruit','initiative'}


def test_scout_adjacency_deploy_and_no_double_deploy():
    g=new_game(11)
    give(g,'north','scout') if 'scout' not in g.players['north'].hand else None
    g.decision='north'
    put(g,'north','archer',(0,-2))
    assert any(a.dst==(0,-1) for a in actions(g,'deploy') if a.coin=='scout')
    a=next(a for a in actions(g,'deploy') if a.coin=='scout' and a.dst==(0,-1))
    apply_action(g,a)
    assert g.units[(0,-1)].kind=='scout'
    if 'scout' not in g.players['north'].hand: give(g,'north','scout')
    g.decision='north'
    assert not [a for a in actions(g,'deploy') if a.coin=='scout']
    check_invariants(g)


def test_archer_and_crossbow_line_of_sight():
    g=new_game(34)
    g.decision='north'
    put(g,'north','archer',(0,0))
    put(g,'south','pikeman',(2,-1))  # distance 2, not collinear
    put(g,'south','crossbowman',(0,-2))
    give(g,'north','archer') if 'archer' not in g.players['north'].hand else None
    assert any(a.dst==(2,-1) for a in actions(g,'shot') if a.coin=='archer')
    assert not [a for a in actions(g,'attack') if a.coin=='archer']

    g2=new_game(8)
    put(g2,'south','crossbowman',(0,0))
    put(g2,'north','archer',(2,0))
    give(g2,'south','crossbowman') if 'crossbowman' not in g2.players['south'].hand else None
    assert any(a.dst==(2,0) for a in actions(g2,'shot') if a.coin=='crossbowman')
    put(g2,'north','scout',(1,0))
    assert not any(a.dst==(2,0) for a in actions(g2,'shot') if a.coin=='crossbowman')


def test_cavalry_charge_requires_attack_after_move():
    g=new_game(4)
    put(g,'north','cavalry',(0,0))
    g.decision='north'
    give(g,'north','cavalry') if 'cavalry' not in g.players['north'].hand else None
    assert not [a for a in actions(g,'charge') if a.coin=='cavalry']
    put(g,'south','pikeman',(2,-1))
    assert any(a.src==(0,0) and a.dst==(1,-1) and a.aux==(2,-1) for a in actions(g,'charge'))


def test_lancer_straight_charge_only():
    g=new_game(5)
    put(g,'north','lancer',(0,0))
    put(g,'south','pikeman',(3,0))
    g.decision='north'
    give(g,'north','lancer') if 'lancer' not in g.players['north'].hand else None
    charges=actions(g,'charge')
    assert Action('charge','lancer',(0,0),(2,0),(3,0)) in charges
    assert not [a for a in actions(g,'attack') if a.coin=='lancer']
    put(g,'south','crossbowman',(1,0))
    assert Action('charge','lancer',(0,0),(2,0),(3,0)) not in legal_actions(g)


def test_pikeman_simultaneous_strike():
    h=new_game(13)
    put(h,'north','cavalry',(0,0))
    put(h,'south','pikeman',(1,0))
    h.decision='north'
    give(h,'north','cavalry') if 'cavalry' not in h.players['north'].hand else None
    move=next(a for a in actions(h,'attack') if a.coin=='cavalry' and a.dst==(1,0))
    apply_action(h,move)
    assert (0,0) not in h.units and (1,0) not in h.units
    assert h.players['north'].removed['cavalry']==1
    assert h.players['south'].removed['pikeman']==1
    check_invariants(h)


def test_swordsman_post_attack_optional_move():
    g=new_game(22)
    put(g,'south','swordsman',(0,0))
    put(g,'north','archer',(1,0))
    give(g,'south','swordsman') if 'swordsman' not in g.players['south'].hand else None
    a=next(a for a in actions(g,'attack') if a.coin=='swordsman' and a.dst==(1,0))
    apply_action(g,a)
    assert g.phase=='sword_bonus' and g.decision=='south'
    assert any(a.op=='finish_bonus' for a in legal_actions(g))
    a=next(a for a in legal_actions(g) if a.op=='bonus_move' and a.dst==(1,0))
    apply_action(g,a)
    assert g.phase=='main' and g.units[(1,0)].kind=='swordsman'
    check_invariants(g)


def test_winning_six_control_markers_ends_immediately():
    g=new_game(23)
    for k in [(-2,0),(-1,1),(1,-1)]:
        if k in g.objective_owner: g.objective_owner[k]='south'
    assert sum(v=='south' for v in g.objective_owner.values())==5
    target=(2,0)
    put(g,'south','swordsman',target)
    give(g,'south','swordsman') if 'swordsman' not in g.players['south'].hand else None
    a=next(a for a in actions(g,'control') if a.coin=='swordsman' and a.src==target)
    apply_action(g,a)
    assert g.winner=='south'
    assert legal_actions(g)==[]


def test_5000_random_state_transitions_never_break_conservation():
    g=new_game(543)
    picker=random.Random(17)
    for _ in range(5000):
        acts=legal_actions(g)
        assert acts
        # Prefer forward-moving actions over passes for exercise diversity.
        proactive=[a for a in acts if a.op not in ('pass','initiative','recruit')]
        a=picker.choice(proactive if proactive and picker.random()<.85 else acts)
        apply_action(g,a)
        if g.winner:
            break
    check_invariants(g)


def test_round_respects_one_coin_per_action_and_recycles_discards():
    g=new_game(19)
    first={s:len(p.hand) for s,p in g.players.items()}
    assert first=={'north':3,'south':3}
    for _ in range(6):
        actor=g.decision
        a=next(a for a in legal_actions(g) if a.op=='pass')
        apply_action(g,a)
    assert g.round_no==2
    assert sum(len(p.hand) for p in g.players.values())==6
    assert g.initiative=='south' and g.decision=='south'
    check_invariants(g)


def test_initiative_transfer_once_only_then_next_round_turn_order():
    g=new_game(19)
    a=next(a for a in legal_actions(g) if a.op=='pass')
    apply_action(g,a)
    assert g.decision=='north'
    a=next(a for a in legal_actions(g) if a.op=='initiative')
    apply_action(g,a)
    assert g.initiative=='north' and g.initiative_moved
    assert not any(a.op=='initiative' for a in legal_actions(g))
    for _ in range(4):
        a=next(a for a in legal_actions(g) if a.op=='pass')
        apply_action(g,a)
    assert g.round_no==2 and g.decision=='north'
    assert not g.initiative_moved
    check_invariants(g)


def test_legal_action_ids_are_stable_for_identical_state():
    from backend.api import Room, _sign
    g=new_game(77)
    room=Room(g,{'south':'','north':''})
    a=legal_actions(g)
    assert len(a)==len(set(a))
    s=[_sign(room,'g-test',g,act) for act in a]
    assert len(s)==len(set(s))
    assert s==[_sign(room,'g-test',g,act) for act in legal_actions(g)]
