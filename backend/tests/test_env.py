import json
import random
import pytest
from backend.engine import (Action, FULL_HEXS, FULL_OBJECTIVES, Unit, apply_action,
    check_invariants, legal_actions, new_game)
from backend.env import (WarChestEnv, encode_action, decode_action, observation, replay)
from backend.state import dumps, loads, state_digest
from backend.storage import GameStore
from .test_base_units import fixture, unit, hand, choose


@pytest.mark.parametrize('players',[2,4])
def test_draft_order_armies_and_first_draw(players):
    g=new_game(3,setup='draft',player_count=players,draft_first='south')
    assert g.phase=='draft' and all(not p.hand for p in g.players.values())
    order=[]
    while g.phase=='draft':
        order.append(g.decision)
        apply_action(g,legal_actions(g)[0])
    expected=(['south','north','north','south','south','north','north','south'] if players==2 else
        ['south','north','south2','north2','north2','south2','north','south','north','south2','north2','south'])
    assert order==expected
    assert all(len(p.army)==(4 if players==2 else 3) and len(p.hand)==3 for p in g.players.values())
    if players==2: assert g.initiative==g.decision=='north'
    check_invariants(g)


def test_four_player_map_resources_and_clockwise_turns():
    g=new_game(3,player_count=4,initiative='south')
    assert len(FULL_HEXS)==47 and len(FULL_OBJECTIVES)==14
    assert len(g.objective_owner)==14 and g.control_target==8
    assert {s:len(p.bag)+len(p.hand) for s,p in g.players.items()} == {s:7 for s in g.players}
    order=[]
    for _ in range(12):
        order.append(g.decision)
        apply_action(g,choose(g,'pass'))
    assert order==list(g.turn_order)*3 and g.round_no==2
    assert sum(v=='south' for v in g.objective_owner.values())==3


def test_four_player_shared_deployment_and_no_ally_initiative_claim():
    g=new_game(4,player_count=4,initiative='south')
    g.decision='south2'
    assert not any(a.op=='initiative' for a in legal_actions(g))
    for a in legal_actions(g):
        if a.op=='deploy': assert g.objective_owner[a.dst]=='south'


def test_four_player_marshall_commands_teammate_sword():
    rosters={'south':('marshall','archer','scout'),'north':('pikeman','knight','lancer'),
        'south2':('swordsman','ensign','footman'),'north2':('mercenary','cavalry','crossbowman')}
    g=new_game(4,player_count=4,rosters=rosters,initiative='south')
    for p in g.players.values():
        p.bag+=p.hand
        p.hand.clear()
    unit(g,'south','marshall',(0,0))
    unit(g,'south2','swordsman',(1,0))
    unit(g,'north','lancer',(2,0))
    hand(g,'south','marshall')
    hand(g,'north','royal')
    apply_action(g,choose(g,'command_attack'))
    assert g.decision=='south2' and g.phase=='sword_bonus'
    apply_action(g,choose(g,'finish_bonus'))
    # Resume after the original actor, rather than the teammate doing the bonus.
    assert g.decision=='north'


@pytest.mark.parametrize('players',[2,4])
def test_random_full_games_codes_snapshot_and_replay(players):
    picker=random.Random(12)
    e=WarChestEnv(4,setup='random',player_count=players,record_trace=True,verify=True,max_decisions=800)
    for i in range(800):
        codes=e.legal_action_codes()
        assert codes and len(codes)==len(set(codes))
        assert all(encode_action(decode_action(c))==c for c in codes)
        result=e.step(picker.choice(codes),expected_revision=e.revision)
        assert result.actor in e._game.players
        if result.terminated or result.truncated: break
    payload=json.loads(json.dumps(e.export_trace()))
    assert state_digest(replay(payload))==state_digest(e._game)
    assert state_digest(loads(dumps(e._game)))==state_digest(e._game)


def test_snapshot_suspended_guard_reaction_and_removed_counter(tmp_path):
    g=fixture(('swordsman',),('royal_guard',))
    unit(g,'south','swordsman',(0,0))
    unit(g,'north','royal_guard',(1,0))
    hand(g,'south','swordsman')
    apply_action(g,choose(g,'attack'))
    h=loads(dumps(g))
    apply_action(h,choose(h,'guard_supply'))
    store=GameStore(str(tmp_path/'save.sqlite3'))
    store.save_game('g',h,{'north':'secret'},b'secret')
    restored,_,_=store.load_game('g')
    assert restored.players['north'].removed['royal_guard']==1
    assert legal_actions(restored)==legal_actions(h)
    assert state_digest(restored)==state_digest(h)


def test_observation_does_not_leak_hidden_opponent_coins_or_rng():
    g=new_game(10)
    g.players['north'].discard.extend((k,False) for k in g.players['north'].hand)
    g.players['north'].hand.clear()
    before=observation(g,'south')
    # Redistribute unseen enemy coins while keeping every public count identical.
    p=g.players['north']
    p.bag[0],p.discard[0]=(p.discard[0][0]),(p.bag[0],False)
    g.rng.random()
    assert observation(g,'south')==before
    assert 'rng' not in before and 'hand' not in before['players']['north']
    assert not observation(g,'north')['legal_action_codes']


def test_truncation_is_not_terminal_win_and_cannot_step_again():
    e=WarChestEnv(4,max_decisions=1)
    result=e.step(e.legal_action_codes()[0],expected_revision=0)
    assert result.truncated and not result.terminated and set(result.rewards.values())=={0.0}
    assert e.done and not e.legal_action_codes()
    assert e.observe()['legal_action_codes']==[]
    assert e.observe_packed().truncated and not e.observe_packed().legal_action_codes
    assert result.decision_player==e._game.decision
    with pytest.raises(ValueError): e.step(0,expected_revision=1)


def test_illegal_stale_and_bad_codes_are_atomic():
    e=WarChestEnv(4)
    before=state_digest(e._game)
    for code,revision in [(e.legal_action_codes()[0],99),(-1,0),(True,0),(1.0,0)]:
        with pytest.raises(ValueError): e.step(code,expected_revision=revision)
        assert state_digest(e._game)==before


def test_env_branches_identical_future_draws_without_shared_state():
    e=WarChestEnv(6)
    h=e.clone()
    for _ in range(20):
        assert e.legal_action_codes()==h.legal_action_codes()
        code=e.legal_action_codes()[0]
        e.step(code,expected_revision=e.revision)
        h.step(code,expected_revision=h.revision)
    assert state_digest(e._game)==state_digest(h._game)
    e.step(e.legal_action_codes()[0],expected_revision=e.revision)
    assert e.revision==h.revision+1


def test_replay_rejects_tampered_data():
    e=WarChestEnv(6,record_trace=True)
    e.step(e.legal_action_codes()[0],expected_revision=0)
    trace=e.export_trace()
    trace['decisions'][0]['state_digest']='wrong'
    with pytest.raises(ValueError): replay(trace)


def test_four_player_random_conservation_stress():
    rng=random.Random(40)
    for seed in range(40):
        g=new_game(seed,player_count=4,setup='random',record_events=False)
        for _ in range(800):
            acts=legal_actions(g)
            assert acts and len(acts)==len(set(acts))
            apply_action(g,rng.choice(acts))
            if g.winner: break


@pytest.mark.parametrize('players,seed,winner,steps',[(2,10,'north',287),(4,16,'north',403)])
def test_natural_complete_matches_and_terminal_team_rewards(players,seed,winner,steps):
    e=WarChestEnv(seed,setup='random',player_count=players,record_trace=True,verify=True)
    rng=random.Random(seed)
    result=None
    for _ in range(steps):
        result=e.step(rng.choice(e.legal_action_codes()),expected_revision=e.revision)
    assert result.terminated and not result.truncated
    assert e._game.winner==winner and not e.legal_action_codes()
    for seat,reward in result.rewards.items():
        assert reward==(1.0 if e._game.teams[seat]==winner else -1.0)
    assert state_digest(replay(e.export_trace()))==state_digest(e._game)


def test_snapshot_and_export_do_not_share_mutable_state():
    e=WarChestEnv(1,record_trace=True,max_decisions=1)
    saved=e.trusted_snapshot()
    saved['teams']['south']='north'
    assert e._game.teams['south']=='south'
    e.step(e.legal_action_codes()[0],expected_revision=0)
    exported=e.export_trace()
    exported['initial_state']['teams']['south']='wrong'
    exported['decisions'][0]['state_digest']='wrong'
    assert e.export_trace()['initial_state']['teams']['south']=='south'
    assert e.export_trace()['decisions'][0]['state_digest']!='wrong'


@pytest.mark.parametrize('players',[2,4])
def test_packed_observation_buffers_match_visible_state(players):
    from backend.env import COORDS, COIN_ID, PHASE_ID
    e=WarChestEnv(10,player_count=players,setup='random')
    rng=random.Random(10)
    for _ in range(300):
        for seat in e._game.players:
            p=e.observe_packed(seat)
            g=e._game
            assert isinstance(p.board,bytes) and len(p.board)==47*5
            assert len(p.players)==players*69 and len(p.own)==51
            assert p.context[4]==PHASE_ID[g.phase] and p.context[-1]==e.revision
            for i,xy in enumerate(COORDS[1:]):
                row=p.board[i*5:(i+1)*5]
                u=g.units.get(xy)
                assert row[3]==(COIN_ID[u.kind] if u else 0)
                assert row[4]==(u.count if u else 0)
            assert p.legal_action_codes==(e.legal_action_codes() if seat==g.decision else ())
        if e.done: break
        e.step(rng.choice(e.legal_action_codes()),expected_revision=e.revision)


def test_packed_observation_hides_opponents_unknown_composition():
    from backend.env import packed_observation
    g=new_game(7)
    p=g.players['north']
    before=packed_observation(g,'south')
    p.bag[0],p.hand[0]=p.hand[0],p.bag[0]
    assert packed_observation(g,'south')==before
