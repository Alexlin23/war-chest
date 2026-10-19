"""Rule fixtures preserve every coin; assertions describe card/FAQ semantics."""
from collections import Counter
import random
import pytest
from backend.engine import (Action, COIN_TOTALS, KINDS, Unit, apply_action,
    check_invariants, clone, legal_actions, new_game)


def fixture(south, north, seed=0):
    used = set(south+north)
    rest = [k for k in KINDS if k not in used]
    south = south + tuple(rest[:4-len(south)])
    rest = [k for k in rest if k not in south]
    north = north + tuple(rest[:4-len(north)])
    g = new_game(seed, rosters={"south": south, "north": north}, initiative="south")
    for p in g.players.values():
        p.bag += p.hand
        p.hand.clear()
    return g


def hand(g, side, *coins):
    p = g.players[side]
    for k in coins:
        p.bag.remove(k)
        p.hand.append(k)


def unit(g, side, kind, xy, count=1):
    p = g.players[side]
    for _ in range(count):
        if p.supply[kind]:
            p.supply[kind] -= 1
        else:
            p.bag.remove(kind)
    g.units[xy] = Unit(side, kind, count)


def choose(g, op, **kw):
    return next(a for a in legal_actions(g) if a.op == op and all(getattr(a, k) == v for k,v in kw.items()))


def test_all_16_cards_and_original_totals():
    assert len(KINDS) == 16 and sum(COIN_TOTALS.values()) == 74
    assert COIN_TOTALS['footman'] == 5
    seen = set()
    for seed in range(50):
        g = new_game(seed, setup='random')
        seen.update(k for p in g.players.values() for k in p.army)
        check_invariants(g)
    assert seen == set(KINDS)


def test_bad_rosters_and_editions_rejected():
    with pytest.raises(ValueError): new_game(rosters={'south': ('archer',)*4, 'north': ('scout',)*4})
    with pytest.raises(ValueError): new_game(royal_guard_version='expansion')


@pytest.mark.parametrize('battle',['gaugamela','bannockburn','crecy'])
def test_historical_base_game_rosters(battle):
    from backend.engine import BATTLES
    g=new_game(7,setup=battle)
    assert {s:p.army for s,p in g.players.items()}==BATTLES[battle]
    check_invariants(g)


def test_berserker_discards_stack_coins_and_cannot_spend_last():
    g = fixture(('berserker',), ('scout',))
    unit(g,'south','berserker',(0,0),3)
    hand(g,'south','berserker')
    apply_action(g,choose(g,'move',dst=(1,0)))
    assert g.phase == 'berserk_bonus'
    apply_action(g,choose(g,'move',dst=(1,-1)))
    assert g.units[(1,-1)].count == 2
    assert g.players['south'].removed['berserker'] == 0
    apply_action(g,choose(g,'move',dst=(0,0)))
    assert g.units[(0,0)].count == 1 and g.phase == 'main'
    # Paid coin plus two stack coins all go to public discard (or recycled bag).
    check_invariants(g)


def test_berserker_knight_eligibility_after_paying_stack_cost():
    g = fixture(('berserker',), ('knight',))
    unit(g,'south','berserker',(0,0),2)
    unit(g,'north','knight',(2,0))
    hand(g,'south','berserker')
    apply_action(g,choose(g,'move',dst=(1,0)))
    assert not any(a.op=='attack' for a in legal_actions(g))


def test_ensign_moves_one_step_and_triggers_berserker():
    g = fixture(('ensign','berserker'), ('scout',))
    unit(g,'south','ensign',(0,0))
    unit(g,'south','berserker',(1,0),2)
    hand(g,'south','ensign')
    assert not any(a.op=='command_move' and a.dst==(3,0) for a in legal_actions(g))
    apply_action(g,choose(g,'command_move',dst=(2,0)))
    assert g.phase == 'berserk_bonus' and g.pending_unit == (2,0)


def test_marshall_only_normal_attack_and_sword_trigger():
    g = fixture(('marshall','swordsman','archer','lancer'), ('scout',))
    unit(g,'south','marshall',(0,0))
    unit(g,'south','swordsman',(1,0))
    unit(g,'south','archer',(0,1))
    unit(g,'south','lancer',(1,-1))
    unit(g,'north','scout',(2,0))
    hand(g,'south','marshall')
    acts = [a for a in legal_actions(g) if a.op=='command_attack']
    assert acts and {a.src for a in acts} == {(1,0)}
    apply_action(g,acts[0])
    assert g.phase == 'sword_bonus'


def test_footman_two_stacks_tactic_different_maneuvers_one_coin():
    g = fixture(('footman',), ('scout',))
    unit(g,'south','footman',(0,0))
    unit(g,'south','footman',(1,-1))
    hand(g,'south','footman')
    hand(g,'north','royal')
    assert not any(a.op=='deploy' and a.coin=='footman' for a in legal_actions(g))
    assert len([a for a in legal_actions(g) if a.op=='footman_tactic']) == 1
    apply_action(g,choose(g,'footman_tactic'))
    apply_action(g,choose(g,'control',src=(1,-1)))
    assert g.decision=='south' and g.phase=='footman_bonus'
    assert {a.src for a in legal_actions(g)} == {(0,0)}
    apply_action(g,choose(g,'move',dst=(1,0)))
    assert g.decision=='north' and g.phase=='main'
    assert len(g.players['south'].discard)==1


def test_mercenary_recruit_bonus_is_optional_maneuver_only():
    g = fixture(('mercenary',), ('scout',))
    unit(g,'south','mercenary',(0,0))
    hand(g,'south','royal')
    apply_action(g,choose(g,'recruit',recruit='mercenary'))
    assert g.phase=='mercenary_bonus'
    assert {a.op for a in legal_actions(g)} <= {'move','attack','control','finish_bonus'}
    apply_action(g,choose(g,'move',dst=(1,0)))
    assert g.phase=='main'


@pytest.mark.parametrize('defense', ['guard_board','guard_supply'])
def test_royal_guard_defender_chooses_loss_and_resumes_attacker(defense):
    g = fixture(('swordsman',), ('royal_guard',))
    unit(g,'south','swordsman',(0,0))
    unit(g,'north','royal_guard',(1,0))
    hand(g,'south','swordsman')
    before=g.players['north'].supply['royal_guard']
    apply_action(g,choose(g,'attack'))
    assert g.decision=='north' and g.phase=='guard_defense'
    assert {a.op for a in legal_actions(g)}=={'guard_board','guard_supply'}
    apply_action(g,choose(g,defense))
    assert g.decision=='south' and g.phase=='sword_bonus'
    assert ((1,0) in g.units) == (defense=='guard_supply')
    assert g.players['north'].supply['royal_guard']==before-(defense=='guard_supply')


def test_royal_guard_original_and_revised_are_distinct():
    g = fixture(('royal_guard',), ('scout',))
    unit(g,'south','royal_guard',(0,0))
    hand(g,'south','royal')
    assert len([a for a in legal_actions(g) if a.op=='royal_move'])==6
    g.royal_guard_version='revised'
    assert not [a for a in legal_actions(g) if a.op=='royal_move']


def test_priest_forces_drawn_coin_and_preserves_old_hand():
    g = fixture(('warrior_priest','scout'), ('pikeman',))
    unit(g,'south','warrior_priest',(1,-1))
    hand(g,'south','warrior_priest','royal')
    # All possible draws have the same type; still preserve conservation.
    p=g.players['south']
    p.discard += [(k,True) for k in p.bag if k!='scout']
    p.bag=[k for k in p.bag if k=='scout']
    apply_action(g,choose(g,'control',src=(1,-1)))
    assert g.phase=='forced_coin'
    assert {a.coin for a in legal_actions(g)}=={'scout'}
    assert 'royal' in p.hand
    apply_action(g,choose(g,'deploy'))
    assert g.phase=='main' and p.hand==['royal']


def test_priest_dying_to_pikeman_still_draws():
    g=fixture(('warrior_priest',),('pikeman',))
    unit(g,'south','warrior_priest',(0,0))
    unit(g,'north','pikeman',(1,0))
    hand(g,'south','warrior_priest')
    apply_action(g,choose(g,'attack'))
    assert not g.units and g.phase=='forced_coin'


def test_knight_restriction_and_pikeman_effect_bypass():
    g=fixture(('knight',),('pikeman',))
    unit(g,'south','knight',(0,0))
    unit(g,'north','pikeman',(1,0))
    hand(g,'south','knight')
    apply_action(g,choose(g,'attack'))
    assert not g.units
    assert g.players['south'].removed['knight']==1


def test_seeded_random_rosters_full_rules_stress():
    picker=random.Random(47)
    exercised=set()
    for seed in range(80):
        g=new_game(seed,setup='random',record_events=False)
        for step in range(500):
            acts=legal_actions(g)
            assert acts and len(acts)==len(set(acts))
            proactive=[a for a in acts if a.op not in ('pass','initiative','recruit','finish_bonus')]
            a=picker.choice(proactive if proactive and picker.random()<.8 else acts)
            exercised.add(a.op)
            apply_action(g,a)
            if g.winner: break
        check_invariants(g)
    assert {'footman_tactic','command_move','command_attack','guard_supply','royal_move'} <= exercised


def test_clone_preserves_rng_and_does_not_share_mutable_state():
    g=new_game(42,setup='random')
    h=clone(g)
    assert g.rng.getstate()==h.rng.getstate()
    apply_action(h,legal_actions(h)[0])
    assert g.revision==0 and h.revision==1
    assert g.players!=h.players


def test_two_step_move_can_return_to_vacated_origin():
    g=fixture(('light_cavalry',),('scout',))
    unit(g,'south','light_cavalry',(0,0))
    hand(g,'south','light_cavalry')
    hand(g,'north','royal')
    a=choose(g,'move_two',dst=(0,0))
    assert a.aux not in g.units
    apply_action(g,a)
    assert g.units[(0,0)].kind=='light_cavalry'
    assert g.players['south'].discard==[('light_cavalry',True)]


def test_priest_winning_control_ends_before_bonus_draw():
    g=fixture(('warrior_priest',),('scout',))
    target=(2,0)
    unit(g,'south','warrior_priest',target)
    for xy in [(-2,0),(-1,1),(1,-1)]: g.objective_owner[xy]='south'
    hand(g,'south','warrior_priest')
    before=g.rng.getstate()
    apply_action(g,choose(g,'control',src=target))
    assert g.winner=='south' and g.phase=='main' and not g.tasks
    assert g.rng.getstate()==before


def test_blocked_remaining_footman_is_skipped_under_declared_rule_interpretation():
    rosters={'south':('footman','archer','knight'),'north':('pikeman','ensign','royal_guard'),
        'south2':('swordsman','scout','lancer'),'north2':('mercenary','cavalry','crossbowman')}
    g=new_game(1,player_count=4,rosters=rosters,initiative='south')
    for p in g.players.values():
        p.bag+=p.hand
        p.hand.clear()
    unit(g,'south','footman',(2,0))
    unit(g,'south','footman',(0,0))
    for side,kind,xy in [('south','archer',(1,-1)),('south','knight',(0,-1)),
        ('south2','swordsman',(-1,0)),('south2','scout',(-1,1)),('south2','lancer',(0,1))]:
        unit(g,side,kind,xy)
    hand(g,'south','footman')
    hand(g,'north','royal')
    apply_action(g,choose(g,'footman_tactic'))
    apply_action(g,choose(g,'move',src=(2,0),dst=(1,0)))
    assert g.phase=='main' and g.decision=='north'
    check_invariants(g)
