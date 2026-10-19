"""Local-development FastAPI adapter for the server-authoritative War Chest frontend.

WARNING: Only for trusted localhost development. Private saves live in SQLite.
Do not expose the dev room-creator / bearer join links on a public network.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from typing import Literal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .engine import (Action, GameState, NAMES, KINDS, COIN_TOTALS, UNIT_RULES, board_hexes,
                     clone, legal_actions, loc, new_game, team, _apply_legal_action, check_invariants)
from .storage import GameStore
from .state import RULESET_VERSION

app = FastAPI(title="War Chest base-game server", version="0.3.0")
STORE=GameStore(os.environ.get('WARCHEST_DB',str(Path(__file__).parent/'data'/'games.sqlite3')))
PHASE_LABELS={'main':'行动阶段','draft':'选择兵种','sword_bonus':'剑士额外移动',
    'berserk_bonus':'狂战士连动','mercenary_bonus':'雇佣兵额外行动',
    'footman_bonus':'步兵协同行动','forced_coin':'战斗牧师立即用币','guard_defense':'皇家卫队防御选择'}


@dataclass
class Room:
    game: GameState
    invites: dict[str,str]
    secret: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    lock: RLock = field(default_factory=RLock)
    action_revision: int = -1
    action_tokens: dict[str,Action] = field(default_factory=dict)
    action_views: list[dict] = field(default_factory=list)

ROOMS: dict[str,Room] = {}
SESSIONS: dict[str,tuple[str,str]] = {}
REGISTRY_LOCK=RLock()
SESSION_COOKIE="warchest_session"
DEV_ENABLED=os.environ.get("WARCHEST_DEV", "1")=="1"
ALLOWED_ORIGINS=set(os.environ.get("WARCHEST_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8000,http://127.0.0.1:5173,http://127.0.0.1:8000").split(","))


class ActionRequest(BaseModel):
    model_config = {'extra':'forbid'}
    action_id: str = Field(strict=True,min_length=16, max_length=128)
    expected_revision: int = Field(strict=True,ge=0)


class CreateRequest(BaseModel):
    model_config = {'extra':'forbid'}
    setup: Literal['recommended','random','draft','gaugamela','bannockburn','crecy'] = 'recommended'
    player_count: Literal[2,4] = 2
    seed: Optional[int] = None
    rosters: Optional[dict[str,list[str]]] = None
    initiative: Optional[str] = None
    draft_first: Optional[str] = None
    royal_guard_version: Literal['original','revised'] = 'original'


def _room(game_id: str) -> Room:
    with REGISTRY_LOCK:
        room=ROOMS.get(game_id)
        if room is None:
            saved=STORE.load_game(game_id)
            if saved:
                game,invites,secret=saved
                room=ROOMS[game_id]=Room(game,invites,secret)
    if room is None:
        raise HTTPException(404,"对局不存在或服务器已重启")
    return room


def _seat(request:Request, game_id:str) -> str:
    session=request.cookies.get(SESSION_COOKIE)
    if not session:
        raise HTTPException(401,"请使用创建对局页面提供的席位链接加入游戏")
    with REGISTRY_LOCK:
        identity=SESSIONS.get(session)
        if not identity:
            identity=STORE.load_session(session)
            if identity: SESSIONS[session]=identity
    if not identity or identity[0]!=game_id:
        raise HTTPException(403,"该会话没有本局的席位权限")
    return identity[1]


def _sign(room:Room, gid:str, game:GameState, act:Action)->str:
    message=json.dumps([gid,game.revision,game.decision,act.op,act.coin,act.src,
        act.dst,act.aux,act.recruit],ensure_ascii=False,separators=(",",":"))
    return hmac.new(room.secret,message.encode(),hashlib.sha256).hexdigest()


def _show_action(room:Room,gid:str, game:GameState,a:Action)->dict:
    labels={"pass":"跳过","initiative":"夺取先手","recruit":"招募","deploy":"部署",
            "bolster":"增援","move":"移动","attack":"攻击","control":"占领据点",
            "shot":"远程射击","move_two":"轻骑兵战术","charge":"冲锋战术",
            "bonus_move":"剑士额外移动","finish_bonus":"放弃额外行动",
            "command_move":"军旗手指挥移动","command_attack":"元帅指挥攻击",
            "footman_tactic":"步兵协同战术","royal_move":"皇家币移动卫队",
            "guard_board":"从卫队移除棋币","guard_supply":"从供应移除棋币抵挡",
            "draft":"选择兵种"}
    groups={"pass":"other","initiative":"initiative","recruit":"recruit",
            "deploy":"deploy","bolster":"deploy","move":"maneuver","attack":"maneuver",
            "control":"maneuver","shot":"special","move_two":"special",
            "charge":"special","bonus_move":"special","finish_bonus":"other"}
    icons={"pass":"pass","initiative":"flag","recruit":"recruit","deploy":"deploy",
            "bolster":"shield","move":"move","attack":"attack","control":"flag",
            "shot":"tactic","move_two":"move","charge":"attack",
            "bonus_move":"move","finish_bonus":"pass"}
    name=NAMES.get(a.coin,("",""))[0]
    tail=f" · {name}" if name else ""
    desc=[]
    if a.src:desc.append(f"起点 {loc(a.src)}")
    if a.dst:desc.append(f"目标 {loc(a.dst)}")
    if a.aux:desc.append(f"额外位置 {loc(a.aux)}")
    if a.recruit:
        desc.append(f"{'兵种' if a.op=='draft' else '招募'} {NAMES[a.recruit][0]}")
        if a.op=='draft': desc.append(UNIT_RULES[a.recruit])
    if a.op.startswith('guard_') and game.tasks:
        desc.append(f"攻击来自 {loc(game.tasks[-1].src)}")
    if not desc:desc=["由服务器裁决，无需选择棋盘目标"]
    targets=[loc(k) for k in (a.dst,a.aux) if k]
    return {"id":_sign(room,gid,game,a),"label":labels[a.op]+tail,
            "description":" · ".join(desc),"group":groups.get(a.op,'special'),
            "payment_coin_type":a.coin or None,"source_hex_id":loc(a.src) if a.src else None,
            "target_hex_ids":targets,"highlight_hex_ids":targets,
            "presentation_icon":icons.get(a.op,'tactic'),"confirm_text":labels[a.op]+tail}


def _view(room:Room,gid:str,seat:str)->dict:
    game=room.game
    board=[]
    for q,r in sorted(board_hexes(game),key=lambda h:(h[1],h[0])):
        xy=(q,r)
        unit=game.units.get(xy)
        uv=None
        if unit:
            name,short=NAMES[unit.kind]
            uv={"unit_type":unit.kind,"name":name,"short_name":short,
                "owner_id":unit.owner,"team_id":team(game,unit.owner),"count":unit.count,"symbol":short}
        board.append({"id":loc(xy),"q":q,"r":r,
            "terrain":"objective" if xy in game.objective_owner else "normal",
            "owner_id":game.objective_owner.get(xy),"unit":uv})
    players=[]
    for side in game.turn_order:
        p=game.players[side]
        faction=team(game,side)
        players.append({"id":side,"side":faction,"team_id":faction,"name":p.name,
            "color_name":"赤铜" if faction=="south" else "曜石",
            "control_count":sum(o==faction for o in game.objective_owner.values()),
            "control_target":game.control_target,"bag_count":len(p.bag),"discard_count":len(p.discard),
            "supply_count":sum(p.supply.values()),"hand_count":len(p.hand),
            "faceup_discard":[{"unit_type":kind,"name":NAMES[kind][0],"count":count}
                for kind,count in sorted(Counter(kind for kind,visible in p.discard if visible).items())],
            "board_unit_count":sum(u.owner==side for u in game.units.values()),
            "is_viewer":seat==side,"is_ally":team(game,seat)==faction,
            "army":[{"unit_type":kind,"name":NAMES[kind][0],"short_name":NAMES[kind][1],
                "available":p.supply[kind],"symbol":NAMES[kind][1],
                "description":('修订版：皇家币移动一至两步到己方据点；受攻击时可从供应移除一币抵挡。'
                    if kind=='royal_guard' and game.royal_guard_version=='revised' else UNIT_RULES[kind])}
                for kind in p.army]})
    my_hand=[{"id":f"hand-{i}-{kind}","unit_type":kind,"label":NAMES[kind][0],
              "short_name":NAMES[kind][1],"symbol":NAMES[kind][1],"is_royal":kind=="royal"}
             for i,kind in enumerate(game.players[seat].hand)]
    actions=_choices(room,gid) if game.decision==seat and not game.winner else []
    events=[{"id":f"e-{idx}","time_label":"公开行动","text":msg,"type":cat}
            for idx,(msg,cat) in reversed(list(enumerate(game.events[-120:],start=max(0,len(game.events)-120))))]
    return {"schema_version":1,"game_id":gid,"revision":game.revision,
            "ruleset_label":f"基础版16兵种 · {len(game.players)}人 · 卫队{'原版' if game.royal_guard_version=='original' else '修订版'}",
            "ruleset_version":RULESET_VERSION,"viewer_team_id":team(game,seat),
            "winner_team_id":game.winner,"player_count":len(game.players),
            "status":"finished" if game.winner else "active",
            "winner_player_id":game.winner,"viewer_player_id":seat,
            "decision_player_id":None if game.winner else game.decision,
            "initiative_player_id":game.initiative,"round":game.round_no,
            "phase_label":PHASE_LABELS[game.phase],
            "instruction":("对局已结束" if game.winner else
                "等待其他玩家行动" if game.decision!=seat else
                "选择一名兵种加入你的军团" if game.phase=='draft' else
                "选择从卫队或供应区移除棋币，抵挡本次攻击" if game.phase=='guard_defense' else
                "必须立即使用刚抽到的棋币，请从可用行动中选择" if game.phase=='forced_coin' else
                "选择另一支步兵执行操纵" if game.phase=='footman_bonus' else
                "选择额外行动，或放弃后继续对局" if game.phase!='main' else
                "选择一项行动，然后确认执行"),
            "board":board,"players":players,"hand":my_hand,
            "legal_actions":actions,"events":events,
            "server_time":datetime.now(timezone.utc).isoformat()}


def _choices(room:Room,gid:str):
    if room.action_revision!=room.game.revision:
        actions=legal_actions(room.game)
        room.action_views=[_show_action(room,gid,room.game,a) for a in actions]
        room.action_tokens={v['id']:a for v,a in zip(room.action_views,actions)}
        room.action_revision=room.game.revision
    return room.action_views


@app.middleware("http")
async def no_cache(request:Request,call_next):
    response=await call_next(request)
    response.headers["Cache-Control"]="no-store"
    return response


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/api/v1/dev")


@app.get("/api/v1/health")
def health():
    return {"ok":True,"scope":"base_16_cards","ruleset_version":RULESET_VERSION,
            "games_in_memory":len(ROOMS),"dev_enabled":DEV_ENABLED}


@app.get('/api/v1/rules')
def rules():
    return {'ruleset_version':RULESET_VERSION,'player_counts':[2,4],
        'units':[{'unit_type':k,'name':NAMES[k][0],'coins':COIN_TOTALS[k],
                  'description':UNIT_RULES[k]} for k in KINDS],
        'royal_guard_default':'original','expansions':[]}


@app.get('/api/v1/dev', include_in_schema=False)
def dev_page():
    if not DEV_ENABLED: raise HTTPException(404,'dev disabled')
    return RedirectResponse(os.environ.get('WARCHEST_FRONTEND_URL','http://localhost:5173'))


@app.post("/api/v1/dev/games")
def create_game(request:Request,payload:Optional[CreateRequest]=None):
    if not DEV_ENABLED:raise HTTPException(404,"dev disabled")
    origin=request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(403,"不允许的请求来源")
    gid="g-"+secrets.token_hex(5)
    config=(payload or CreateRequest()).model_dump()
    seed=config.pop('seed')
    try:
        game=new_game(secrets.randbits(32) if seed is None else seed,**config)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    invites={side:secrets.token_urlsafe(32) for side in game.players}
    with REGISTRY_LOCK:
        room=Room(game,invites)
        STORE.save_game(gid,game,invites,room.secret)
        ROOMS[gid]=room
    return {"game_id":gid,"south_join_url":f"/api/v1/dev/join/{gid}/south/{invites['south']}",
            "north_join_url":f"/api/v1/dev/join/{gid}/north/{invites['north']}",
            "join_urls":{s:f"/api/v1/dev/join/{gid}/{s}/{token}" for s,token in invites.items()}}


@app.get("/api/v1/dev/join/{gid}/{side}/{invite}")
def dev_join(gid:str,side:str,invite:str,request:Request):
    if not DEV_ENABLED:raise HTTPException(404,"dev disabled")
    room=_room(gid)
    if side not in room.invites or not hmac.compare_digest(room.invites.get(side,""),invite):
        raise HTTPException(403,"席位邀请无效")
    token=secrets.token_urlsafe(32)
    with REGISTRY_LOCK:
        STORE.save_session(token,gid,side)
        SESSIONS[token]=(gid,side)
    front_url=os.environ.get("WARCHEST_FRONTEND_URL","http://localhost:5173")
    response=RedirectResponse(f"{front_url}/?game={gid}",status_code=303)
    response.set_cookie(SESSION_COOKIE,token,httponly=True,secure=False,samesite="strict",path="/",max_age=60*60*24*30)
    return response


@app.get("/api/v1/games/{gid}/view")
def view(gid:str,request:Request):
    seat=_seat(request,gid)
    room=_room(gid)
    with room.lock:
        return _view(room,gid,seat)


@app.post("/api/v1/games/{gid}/actions")
def action(gid:str,request:Request,payload:ActionRequest):
    origin=request.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        raise HTTPException(403,"CSRF校验失败：Origin不允许")
    seat=_seat(request,gid)
    room=_room(gid)
    with room.lock:
        game=room.game
        if payload.expected_revision!=game.revision:
            raise HTTPException(409,"局面版本已经更新")
        if game.winner or game.decision!=seat:
            raise HTTPException(403,"目前不是你的行动阶段")
        # Valid tokens are re-derived exclusively from the authoritative engine.
        _choices(room,gid)
        chosen=room.action_tokens.get(payload.action_id)
        if chosen is None:raise HTTPException(400,"行动ID无效或已失效")
        next_game=clone(game)
        try:
            _apply_legal_action(next_game,chosen)
            check_invariants(next_game)
        except (ValueError,AssertionError) as exc:
            raise HTTPException(422,"引擎拒绝行动，状态保持不变") from exc
        STORE.save_game(gid,next_game,room.invites,room.secret,action=chosen,actor=game.decision)
        room.game=next_game
        return {"view":_view(room,gid,seat)}


@app.get('/api/v1/games/{gid}/replay')
def export_replay(gid:str,request:Request):
    _seat(request,gid)
    room=_room(gid)
    with room.lock:
        if not room.game.winner:
            raise HTTPException(409,'对局结束后才能导出含隐藏信息的完整回放')
        return STORE.load_trace(gid,room.game)
