import copy
import pytest
from fastapi.testclient import TestClient
from backend.api import app,ROOMS

ORIGIN={'Origin':'http://localhost:5173'}


def setup():
    p=TestClient(app)
    d=p.post('/api/v1/dev/games',headers=ORIGIN).json()
    south=TestClient(app);north=TestClient(app)
    south.cookies.update(south.get(d['south_join_url'],follow_redirects=False).cookies)
    north.cookies.update(north.get(d['north_join_url'],follow_redirects=False).cookies)
    return d['game_id'],south,north


def test_two_players_receive_separate_private_views():
    gid,a,b=setup()
    sa=a.get(f'/api/v1/games/{gid}/view').json()
    sb=b.get(f'/api/v1/games/{gid}/view').json()
    assert sa['viewer_player_id']=='south' and sb['viewer_player_id']=='north'
    assert len(sa['hand'])==3 and len(sb['hand'])==3
    assert sa['decision_player_id']==sb['decision_player_id']=='south'
    assert sa['legal_actions'] and not sb['legal_actions']
    assert 'bag' not in sa and 'bag' not in sb
    assert 'discard' not in sa and 'discard' not in sb
    assert 'no-store' in a.get(f'/api/v1/games/{gid}/view').headers['cache-control']
    assert set(sa)==set(sb)


def test_anonymous_and_out_of_turn_requests_denied():
    gid,a,b=setup()
    noauth=TestClient(app)
    assert noauth.get(f'/api/v1/games/{gid}/view').status_code==401
    choice=a.get(f'/api/v1/games/{gid}/view').json()['legal_actions'][0]
    assert b.post(f'/api/v1/games/{gid}/actions',json={'action_id':choice['id'],'expected_revision':0},headers=ORIGIN).status_code==403
    assert ROOMS[gid].game.revision==0


def test_valid_submission_revision_conflict_replay_and_csrf():
    gid,a,b=setup()
    endpoint=f'/api/v1/games/{gid}/actions'
    choice=a.get(f'/api/v1/games/{gid}/view').json()['legal_actions'][0]
    payload={'action_id':choice['id'],'expected_revision':0}
    assert a.post(endpoint,json=payload).status_code==403  # origin header required
    assert ROOMS[gid].game.revision==0
    res=a.post(endpoint,json=payload,headers=ORIGIN)
    assert res.status_code==200,res.text
    assert res.json()['view']['revision']==1
    assert a.post(endpoint,json=payload,headers=ORIGIN).status_code==409
    assert ROOMS[gid].game.revision==1
    stale={'action_id':choice['id'],'expected_revision':1}
    assert a.post(endpoint,json=stale,headers=ORIGIN).status_code in (400,403)


def test_forged_action_and_wrong_seat_cannot_modify_game():
    gid,a,b=setup()
    endpoint=f'/api/v1/games/{gid}/actions'
    before=copy.deepcopy(ROOMS[gid].game)
    assert a.post(endpoint,json={'action_id':'f'*64,'expected_revision':0},headers=ORIGIN).status_code==400
    assert ROOMS[gid].game.revision==before.revision
    assert ROOMS[gid].game.players['south'].hand==before.players['south'].hand


def test_facedown_coin_identity_not_revealed_to_opponent():
    gid,a,b=setup()
    sa=a.get(f'/api/v1/games/{gid}/view').json()
    secret_coin=sa['hand'][0]['unit_type']
    act=next(x for x in sa['legal_actions'] if x['group']=='other' and x['payment_coin_type']==secret_coin)
    result=a.post(f'/api/v1/games/{gid}/actions',json={'action_id':act['id'],'expected_revision':0},headers=ORIGIN)
    assert result.status_code==200
    opponent=b.get(f'/api/v1/games/{gid}/view').json()
    south=next(p for p in opponent['players'] if p['id']=='south')
    assert south['discard_count']==1
    assert south['faceup_discard']==[]
    assert len(opponent['hand'])==3  # only opponent's own hand
    assert 'coin-' not in str(opponent['events'])


def test_duplicate_simultaneous_actions_only_one_commits():
    from concurrent.futures import ThreadPoolExecutor
    gid,a,b=setup()
    v=a.get(f'/api/v1/games/{gid}/view').json()
    payload={'action_id':v['legal_actions'][0]['id'],'expected_revision':0}
    def send(_):
        return a.post(f'/api/v1/games/{gid}/actions',json=payload,headers=ORIGIN).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(send,range(2)))
    assert sorted(statuses)==[200,409]
    assert ROOMS[gid].game.revision==1


def test_restart_restores_board_sessions_and_action_signatures():
    from backend.api import SESSIONS
    gid,a,b=setup()
    v=a.get(f'/api/v1/games/{gid}/view').json()
    ROOMS.pop(gid)
    SESSIONS.clear()
    again=a.get(f'/api/v1/games/{gid}/view').json()
    assert again['legal_actions']==v['legal_actions']
    result=a.post(f'/api/v1/games/{gid}/actions',headers=ORIGIN,
        json={'action_id':v['legal_actions'][0]['id'],'expected_revision':0})
    assert result.status_code==200
    ROOMS.pop(gid)
    assert b.get(f'/api/v1/games/{gid}/view').json()['revision']==1


def test_configured_four_player_draft_and_rules_catalogue():
    client=TestClient(app)
    rules=client.get('/api/v1/rules').json()
    assert len(rules['units'])==16 and sum(u['coins'] for u in rules['units'])==74
    created=client.post('/api/v1/dev/games',json={'seed':42,'setup':'draft','player_count':4},headers=ORIGIN)
    assert created.status_code==200
    d=created.json()
    assert len(d['join_urls'])==4
    for seat,url in d['join_urls'].items():
        player=TestClient(app)
        player.get(url,follow_redirects=False)
        v=player.get(f"/api/v1/games/{d['game_id']}/view").json()
        assert len(v['players'])==4 and len(v['board'])==47
        assert not v['hand'] and v['phase_label']=='选择兵种'
        assert bool(v['legal_actions'])==(v['decision_player_id']==seat)


def test_invalid_setup_rejected_without_creating_room():
    client=TestClient(app)
    count=len(ROOMS)
    for body in [{'player_count':3},{'setup':'nobility'},
                 {'rosters':{'south':['archer']*4,'north':['scout']*4}}]:
        assert client.post('/api/v1/dev/games',json=body,headers=ORIGIN).status_code==422
    assert len(ROOMS)==count


def test_storage_failure_does_not_commit_memory_state(monkeypatch):
    from backend.api import STORE
    gid,a,b=setup()
    v=a.get(f'/api/v1/games/{gid}/view').json()
    def fail(*args,**kwargs): raise OSError('simulated disk failure')
    monkeypatch.setattr(STORE,'save_game',fail)
    import pytest
    with pytest.raises(OSError):
        a.post(f'/api/v1/games/{gid}/actions',json={'action_id':v['legal_actions'][0]['id'],'expected_revision':0},headers=ORIGIN)
    assert ROOMS[gid].game.revision==0


def test_guard_defender_only_gets_own_reaction_and_resume():
    from backend.api import Room
    from backend.tests.test_base_units import fixture,unit,hand,choose
    from backend.engine import apply_action
    gid,a,b=setup()
    g=fixture(('swordsman',),('royal_guard',))
    unit(g,'south','swordsman',(0,0))
    unit(g,'north','royal_guard',(1,0))
    hand(g,'south','swordsman')
    apply_action(g,choose(g,'attack'))
    room=ROOMS[gid]
    room.game=g
    room.action_revision=-1
    va=a.get(f'/api/v1/games/{gid}/view').json()
    vb=b.get(f'/api/v1/games/{gid}/view').json()
    assert not va['legal_actions'] and len(vb['legal_actions'])==2
    assert vb['phase_label']=='皇家卫队防御选择'
    chosen=vb['legal_actions'][1]
    r=b.post(f'/api/v1/games/{gid}/actions',json={'action_id':chosen['id'],'expected_revision':1},headers=ORIGIN)
    assert r.status_code==200
    v=a.get(f'/api/v1/games/{gid}/view').json()
    assert v['phase_label']=='剑士额外移动' and v['legal_actions']


@pytest.mark.parametrize('players,seed,steps',[(2,1,318),(4,16,403)])
def test_complete_match_over_authenticated_api(players,seed,steps):
    import random
    creator=TestClient(app)
    d=creator.post('/api/v1/dev/games',headers=ORIGIN,
        json={'setup':'random','player_count':players,'seed':seed}).json()
    clients={}
    for seat,url in d['join_urls'].items():
        clients[seat]=TestClient(app)
        clients[seat].get(url,follow_redirects=False)
    gid=d['game_id']
    chooser=random.Random(seed)
    for _ in range(steps):
        g=ROOMS[gid].game
        c=clients[g.decision]
        v=c.get(f'/api/v1/games/{gid}/view').json()
        selected=chooser.choice(v['legal_actions'])
        r=c.post(f'/api/v1/games/{gid}/actions',headers=ORIGIN,
            json={'action_id':selected['id'],'expected_revision':v['revision']})
        assert r.status_code==200,r.text
    assert ROOMS[gid].game.winner=='north'
    for seat,c in clients.items():
        v=c.get(f'/api/v1/games/{gid}/view').json()
        assert v['status']=='finished' and not v['legal_actions']
        assert v['winner_team_id']=='north' and v['decision_player_id'] is None
    from backend.env import replay
    from backend.state import state_digest
    saved=clients['south'].get(f'/api/v1/games/{gid}/replay')
    assert saved.status_code==200
    assert len(saved.json()['decisions'])==steps
    assert state_digest(replay(saved.json()))==state_digest(ROOMS[gid].game)


def test_active_replay_is_not_available_to_players():
    gid,a,b=setup()
    assert a.get(f'/api/v1/games/{gid}/replay').status_code==409
    assert TestClient(app).get(f'/api/v1/games/{gid}/replay').status_code==401
