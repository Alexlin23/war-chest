"""Deterministic War Chest base-game rules; no network/model dependencies.

Default: original Royal Guard. Reactions and bonus actions are explicit choices.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field, replace
import random
from functools import lru_cache
from typing import Optional

Coord = tuple[int, int]
DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
HEXS = frozenset((q, r) for q in range(-3, 4) for r in range(-3, 4) if abs(q+r) <= 3)
NORTH_BASES = ((-1, -2), (2, -3))
SOUTH_BASES = ((-2, 3), (1, 2))
NEUTRAL_BASES = ((-1, 1), (1, -1), (-2, 0), (2, 0), (-3, 2), (3, -2))
OBJECTIVES = frozenset((*NORTH_BASES, *SOUTH_BASES, *NEUTRAL_BASES))
FULL_HEXS = HEXS | frozenset(((-5,2),(-5,3),(-4,1),(-4,2),(-4,3),
                            (5,-2),(5,-3),(4,-1),(4,-2),(4,-3)))
FULL_OBJECTIVES = OBJECTIVES | frozenset(((-4,1),(4,-1),(-5,3),(5,-3)))
ROSTERS = {"south": ("swordsman", "pikeman", "crossbowman", "light_cavalry"),
           "north": ("archer", "cavalry", "lancer", "scout")}
BATTLES = {
    'gaugamela': {'south':('knight','light_cavalry','pikeman','marshall'),
                 'north':('cavalry','footman','mercenary','royal_guard')},
    'bannockburn': {'south':('light_cavalry','pikeman','warrior_priest','swordsman'),
                   'north':('archer','cavalry','lancer','footman')},
    'crecy': {'south':('archer','ensign','knight','royal_guard'),
             'north':('cavalry','crossbowman','lancer','scout')},
}
COIN_TOTALS = {"archer": 4, "berserker": 5, "cavalry": 4, "crossbowman": 5,
    "ensign": 5, "footman": 5, "knight": 4, "lancer": 4, "light_cavalry": 5,
    "marshall": 5, "mercenary": 5, "pikeman": 4, "royal_guard": 5,
    "scout": 5, "swordsman": 5, "warrior_priest": 4}
NAMES = {"swordsman": ("剑士", "剑"), "pikeman": ("长枪兵", "枪"),
    "crossbowman": ("弩手", "弩"), "light_cavalry": ("轻骑兵", "轻"),
    "archer": ("弓箭手", "弓"), "cavalry": ("骑兵", "骑"),
    "lancer": ("枪骑兵", "冲"), "scout": ("侦察兵", "侦"),
    "berserker": ("狂战士", "狂"), "ensign": ("军旗手", "旗"),
    "footman": ("步兵", "步"), "knight": ("骑士", "铠"),
    "marshall": ("元帅", "帅"), "mercenary": ("雇佣兵", "佣"),
    "royal_guard": ("皇家卫队", "卫"), "warrior_priest": ("战斗牧师", "牧"),
    "royal": ("皇家币", "王")}
KINDS = tuple(COIN_TOTALS)
UNIT_RULES = {
    'archer':'战术攻击恰好两格外的敌军，可以越过中间单位；不能普通攻击。',
    'berserker':'操纵后可弃置自身一枚增援币再操纵，允许连动，必须保留最后一币。',
    'cavalry':'战术先移动一格，再攻击移动后相邻的敌军。',
    'crossbowman':'可普通攻击；战术攻击直线两格外敌军，中间必须为空。',
    'ensign':'战术指挥两格内友军移动一格，终点仍须在军旗手两格内。',
    'footman':'最多部署两支步兵；战术让各支步兵分别执行一次操纵。',
    'knight':'只有至少两枚棋币的敌方单位才能攻击骑士。',
    'lancer':'战术沿同一直线移动一或两格后攻击前方敌军；不能普通攻击。',
    'light_cavalry':'战术移动两步，途中不能穿过单位。',
    'marshall':'战术让两格内友军执行普通攻击，并触发该友军的攻击后能力。',
    'mercenary':'招募雇佣兵棋币后，可让已部署的雇佣兵额外操纵一次。',
    'pikeman':'受到相邻攻击时，同时移除攻击者一枚棋币。',
    'royal_guard':'原版可弃置皇家币移动一格；受攻击时可从供应移除一币抵挡。',
    'scout':'除己方据点外，也能部署到友军相邻的空格。',
    'swordsman':'攻击后若仍存活，可额外移动一格。',
    'warrior_priest':'攻击或控制后抽一枚棋币，必须立即使用。',
}
assert sum(COIN_TOTALS.values()) == 74


def hexdist(a, b):
    dq, dr = b[0]-a[0], b[1]-a[1]
    return max(abs(dq), abs(dr), abs(dq+dr))


NEIGHBORS = {a: tuple((a[0]+q, a[1]+r) for q, r in DIRECTIONS
                     if (a[0]+q, a[1]+r) in HEXS) for a in HEXS}
FULL_NEIGHBORS = {a: tuple((a[0]+q,a[1]+r) for q,r in DIRECTIONS
    if (a[0]+q,a[1]+r) in FULL_HEXS) for a in FULL_HEXS}
DISTANCES = {(a, b): hexdist(a, b) for a in FULL_HEXS for b in FULL_HEXS}


def nearby(a):
    return NEIGHBORS[a]


def loc(a):
    return f"{a[0]},{a[1]}"


def other(side):
    return "south" if side == "north" else "north"


def board_hexes(game):
    return FULL_HEXS if len(game.players) == 4 else HEXS


def _neighbors(game, xy):
    return FULL_NEIGHBORS[xy] if len(game.players) == 4 else NEIGHBORS[xy]


def team(game, side):
    return game.teams[side]


def friendly(game, a, b):
    return team(game, a) == team(game, b)


@dataclass(frozen=True, slots=True)
class Action:
    op: str
    coin: str = ""
    src: Optional[Coord] = None
    dst: Optional[Coord] = None
    aux: Optional[Coord] = None
    recruit: str = ""


@lru_cache(maxsize=65536)
def _action(op, coin="", src=None, dst=None, aux=None, recruit=""):
    return Action(op, coin, src, dst, aux, recruit)


@dataclass(slots=True)
class Unit:
    owner: str
    kind: str
    count: int = 1


@dataclass(slots=True)
class Player:
    name: str
    army: tuple[str, ...]
    bag: list[str]
    hand: list[str]
    discard: list[tuple[str, bool]]
    supply: dict[str, int]
    removed: Counter = field(default_factory=Counter)


@dataclass(frozen=True, slots=True)
class Task:
    kind: str
    side: str
    src: Optional[Coord] = None
    dst: Optional[Coord] = None
    coin: str = ""
    remaining: tuple[Coord, ...] = ()


@dataclass(slots=True)
class GameState:
    players: dict[str, Player]
    units: dict[Coord, Unit]
    objective_owner: dict[Coord, Optional[str]]
    initiative: str
    decision: str
    rng: random.Random
    round_no: int = 1
    initiative_moved: bool = False
    phase: str = "main"
    pending_unit: Optional[Coord] = None
    winner: Optional[str] = None
    revision: int = 0
    events: list[tuple[str, str]] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    royal_guard_version: str = "original"
    record_events: bool = True
    teams: dict[str, str] = field(default_factory=lambda: {"south":"south", "north":"north"})
    turn_order: tuple[str, ...] = ("south", "north")
    control_target: int = 6
    draft_pool: tuple[str, ...] = ()
    draft_order: tuple[str, ...] = ()
    draft_index: int = 0


def _log(g, message, category="info"):
    if g.record_events:
        g.events.append((message, category))


def new_game(seed=0, *, rosters=None, setup="recommended", initiative=None,
             royal_guard_version="original", record_events=True, player_count=2,
             draft_first=None):
    rng = random.Random(seed)
    if royal_guard_version not in ("original", "revised"):
        raise ValueError("unknown Royal Guard edition")
    if player_count not in (2, 4):
        raise ValueError("player_count must be 2 or 4")
    if setup in BATTLES:
        if player_count!=2 or rosters is not None:
            raise ValueError('historical setups require two players and no custom rosters')
        rosters=BATTLES[setup]
    if setup == "draft":
        if rosters is not None:
            raise ValueError("draft cannot have preset rosters")
        game = new_game(seed, setup="random", initiative=initiative,
            royal_guard_version=royal_guard_version, record_events=record_events,
            player_count=player_count)
        pool = tuple(k for p in game.players.values() for k in p.army)
        first = draft_first or game.rng.choice(game.turn_order)
        if first not in game.players:
            raise ValueError("invalid draft_first")
        order = game.turn_order
        i = order.index(first)
        seats = order[i:]+order[:i]
        if player_count == 2:
            a,b = seats
            draft_order = (a,b,b,a,a,b,b,a)
            game.initiative = b
        else:
            a,b,c,d = seats
            draft_order = (a,b,c,d,d,c,b,a,b,c,d,a)
        for p in game.players.values():
            p.army, p.bag, p.hand, p.supply = (), ["royal"], [], {}
        game.draft_pool, game.draft_order = pool, draft_order
        game.phase, game.decision = "draft", first
        game.events.clear()
        _log(game, "基础版选兵开始")
        check_invariants(game)
        return game
    sides = ("south", "north") if player_count == 2 else ("south", "north", "south2", "north2")
    if rosters is None:
        if setup == "recommended" and player_count == 2:
            rosters = ROSTERS
            initiative = initiative or "south"
        elif setup == "random" or (setup == "recommended" and player_count == 4):
            per_player = 4 if player_count == 2 else 3
            cards = rng.sample(KINDS, per_player*player_count)
            rosters = {s: tuple(cards[i*per_player:(i+1)*per_player]) for i,s in enumerate(sides)}
        else:
            raise ValueError("unknown setup")
    if set(rosters) != set(sides):
        raise ValueError("incorrect army seats")
    cards = [k for roster in rosters.values() for k in roster]
    per_player = 4 if player_count == 2 else 3
    if (any(len(v) != per_player for v in rosters.values()) or len(set(cards)) != per_player*player_count
            or not set(cards) <= set(KINDS)):
        raise ValueError("armies need four distinct base units each, without duplicates")
    if initiative is None:
        initiative = rng.choice(sides)
    if initiative not in rosters:
        raise ValueError("invalid initiative")
    players = {}
    for side in sides:
        roster = tuple(rosters[side])
        bag = ["royal"] + [kind for kind in roster for _ in range(2)]
        names = {"south":"南境军团", "north":"北境守军", "south2":"南境友军", "north2":"北境友军"}
        players[side] = Player(names[side],
            roster, bag, [], [], {kind: COIN_TOTALS[kind]-2 for kind in roster})
    owners = {xy: None for xy in sorted(FULL_OBJECTIVES if player_count == 4 else OBJECTIVES)}
    owners.update({xy: "north" for xy in NORTH_BASES})
    owners.update({xy: "south" for xy in SOUTH_BASES})
    if player_count == 4:
        owners[(-4,1)], owners[(4,-1)] = "north", "south"
    game = GameState(players, {}, owners, initiative, initiative, rng,
                     royal_guard_version=royal_guard_version, record_events=record_events,
                     teams={s: "south" if s.startswith("south") else "north" for s in sides},
                     turn_order=sides, control_target=6 if player_count == 2 else 8)
    _start_round(game)
    _log(game, f"基础版{player_count}人对局开始")
    check_invariants(game)
    return game


def clone(game):
    """Independent branch, including RNG and suspended decisions."""
    rng = random.Random.__new__(random.Random)
    rng.setstate(game.rng.getstate())
    return replace(game, players={s: replace(p, bag=p.bag.copy(), hand=p.hand.copy(),
        discard=p.discard.copy(), supply=p.supply.copy(), removed=p.removed.copy())
        for s, p in game.players.items()}, units={xy: replace(u) for xy, u in game.units.items()},
        objective_owner=game.objective_owner.copy(), rng=rng,
        events=game.events.copy(), tasks=game.tasks.copy(), teams=game.teams.copy())


def _draw_one(game, side):
    player = game.players[side]
    if not player.bag:
        player.bag.extend(kind for kind, _ in player.discard)
        player.discard.clear()
    if not player.bag:
        return None
    index = game.rng.randrange(len(player.bag))
    coin = player.bag[index]
    player.bag[index] = player.bag[-1]
    player.bag.pop()
    return coin


def _start_round(game):
    game.initiative_moved = False
    game.decision = game.initiative
    for side in sorted(game.players):
        player = game.players[side]
        assert not player.hand
        for _ in range(3):
            coin = _draw_one(game, side)
            if coin is None:
                break
            player.hand.append(coin)
    game.phase = "main"
    game.pending_unit = None


def _next(game, actor):
    order = game.turn_order
    i = order.index(actor)
    for offset in range(1, len(order)+1):
        side = order[(i+offset) % len(order)]
        if game.players[side].hand:
            game.decision = side
            return
    game.round_no += 1
    _start_round(game)


def _can_attack(game, src, target, strength=None):
    u, enemy = game.units.get(src), game.units.get(target)
    return bool(u and enemy and not friendly(game, u.owner, enemy.owner)
                and (enemy.kind != "knight" or (u.count if strength is None else strength) >= 2))


def _normal(game, src, coin="", strength=None):
    u = game.units[src]
    out = []
    for dst in _neighbors(game, src):
        if dst not in game.units:
            out.append(_action("move", coin, src, dst))
        elif u.kind not in ("archer", "lancer") and _can_attack(game, src, dst, strength):
            out.append(_action("attack", coin, src, dst))
    if src in game.objective_owner and game.objective_owner[src] != team(game, u.owner):
        out.append(_action("control", coin, src))
    return out


def _maneuvers(game, src, coin=""):
    u = game.units[src]
    kind = u.kind
    out = _normal(game, src, coin)
    if kind == "archer":
        out.extend(_action("shot", coin, src, dst) for dst in sorted(game.units)
            if DISTANCES[src, dst] == 2 and _can_attack(game, src, dst))
    elif kind == "crossbowman":
        for dx, dy in DIRECTIONS:
            mid, dst = (src[0]+dx, src[1]+dy), (src[0]+2*dx, src[1]+2*dy)
            if mid in board_hexes(game) and mid not in game.units and dst in board_hexes(game) and _can_attack(game, src, dst):
                out.append(_action("shot", coin, src, dst))
    elif kind == "light_cavalry":
        destinations = {}
        for via in _neighbors(game, src):
            if via in game.units:
                continue
            for dst in _neighbors(game, via):
                if dst == src or dst not in game.units:
                    destinations.setdefault(dst, via)
        out.extend(_action("move_two", coin, src, dst, via) for dst, via in sorted(destinations.items()))
    elif kind in ("cavalry", "lancer"):
        for dx, dy in DIRECTIONS:
            p = src
            for _ in range(2 if kind == "lancer" else 1):
                p = (p[0]+dx, p[1]+dy)
                if p not in board_hexes(game) or p in game.units:
                    break
                victims = _neighbors(game, p) if kind == "cavalry" else ((p[0]+dx, p[1]+dy),)
                out.extend(_action("charge", coin, src, p, v) for v in victims
                    if v in board_hexes(game) and _can_attack(game, src, v))
    elif kind in ("ensign", "marshall"):
        for friend, unit in sorted(game.units.items()):
            if friend == src or not friendly(game, unit.owner, u.owner) or DISTANCES[src, friend] > 2:
                continue
            for a in _normal(game, friend):
                if kind == "ensign" and a.op == "move" and DISTANCES[src, a.dst] <= 2:
                    out.append(_action("command_move", coin, friend, a.dst, src))
                elif kind == "marshall" and a.op == "attack":
                    out.append(_action("command_attack", coin, friend, a.dst, src))
    elif kind == "footman":
        positions = tuple(x for x, v in sorted(game.units.items()) if v.owner == u.owner and v.kind == kind)
        if len(positions) == 2 and any(_normal(game, x) for x in positions):
            out.append(_action("footman_tactic", coin, src))
    return out


def _royal_moves(game, side):
    src = next((xy for xy, u in game.units.items() if u.owner == side and u.kind == "royal_guard"), None)
    if src is None:
        return []
    if game.royal_guard_version == "original":
        return [_action("royal_move", "royal", src, dst) for dst in _neighbors(game, src) if dst not in game.units]
    paths = {dst: None for dst in _neighbors(game, src) if dst not in game.units}
    for via in _neighbors(game, src):
        if via not in game.units:
            for dst in _neighbors(game, via):
                if dst == src or dst not in game.units:
                    paths.setdefault(dst, via)
    return [_action("royal_move", "royal", src, dst, via) for dst, via in sorted(paths.items())
            if game.objective_owner.get(dst) == team(game, side)]


def _coin_actions(game, coins):
    side = game.decision
    player = game.players[side]
    out = []
    for coin in sorted(set(coins)):
        out.append(_action("pass", coin))
        if not friendly(game, game.initiative, side) and not game.initiative_moved:
            out.append(_action("initiative", coin))
        out.extend(_action("recruit", coin, recruit=k) for k in player.army if player.supply[k] > 0)
        if coin == "royal":
            out.extend(_royal_moves(game, side))
            continue
        positions = [xy for xy, u in sorted(game.units.items()) if u.owner == side and u.kind == coin]
        if len(positions) < (2 if coin == "footman" else 1):
            slots = {xy for xy, owner in game.objective_owner.items() if owner == team(game, side) and xy not in game.units}
            if coin == "scout":
                for xy, u in game.units.items():
                    if friendly(game, u.owner, side):
                        slots.update(n for n in _neighbors(game, xy) if n not in game.units)
            out.extend(_action("deploy", coin, dst=xy) for xy in sorted(slots))
        for src in positions:
            out.append(_action("bolster", coin, src))
            out.extend(_maneuvers(game, src, coin))
    seen_footman = False
    result = []
    for a in out:
        if a.op == "footman_tactic":
            if seen_footman:
                continue
            seen_footman = True
        result.append(a)
    return result


def legal_actions(game):
    if game.winner:
        return []
    if game.phase == "draft":
        return [_action("draft", recruit=k) for k in game.draft_pool]
    if not game.tasks:
        return _coin_actions(game, game.players[game.decision].hand)
    t = game.tasks[-1]
    if t.kind == "forced_coin":
        return _coin_actions(game, (t.coin,))
    if t.kind == "guard_defense":
        return [_action("guard_board", src=t.dst), _action("guard_supply", src=t.dst)]
    if t.kind == "sword_bonus":
        return [_action("finish_bonus")] + [_action("bonus_move", src=t.src, dst=to)
            for to in _neighbors(game, t.src) if to not in game.units]
    if t.kind == "berserk_bonus":
        return [_action("finish_bonus")] + _normal(game, t.src, strength=game.units[t.src].count-1)
    if t.kind == "mercenary_bonus":
        return [_action("finish_bonus")] + _maneuvers(game, t.src)
    if t.kind == "footman_bonus":
        return [a for src in t.remaining if src in game.units for a in _normal(game, src)]
    raise RuntimeError(f"unsettled task {t.kind}")


def _remove_board_coin(game, xy, *, discard=False):
    unit = game.units[xy]
    unit.count -= 1
    player = game.players[unit.owner]
    if discard:
        player.discard.append((unit.kind, True))
    else:
        player.removed[unit.kind] += 1
    if not unit.count:
        del game.units[xy]


def _after_maneuver(game, src, kind, side, op):
    if kind == "warrior_priest" and op in ("attack", "control"):
        game.tasks.append(Task("priest_draw", side))
    if src in game.units:
        if kind == "swordsman" and op == "attack":
            game.tasks.append(Task("sword_bonus", side, src))
        elif kind == "berserker" and game.units[src].count > 1:
            game.tasks.append(Task("berserk_bonus", side, src))


def _attack(game, src, dst):
    atk, defender = game.units[src], game.units[dst]
    game.tasks.append(Task("after_attack", atk.owner, src, coin=atk.kind))
    if defender.kind == "royal_guard" and game.players[defender.owner].supply[defender.kind] > 0:
        game.tasks.append(Task("guard_defense", defender.owner, src, dst))
    else:
        _resolve_strike(game, src, dst, False)


def _resolve_strike(game, src, dst, use_supply):
    atk, defender = game.units[src], game.units[dst]
    retaliate = defender.kind == "pikeman" and DISTANCES[src, dst] == 1
    _log(game, f"{game.players[atk.owner].name}的{NAMES[atk.kind][0]}攻击{NAMES[defender.kind][0]}", "capture")
    if use_supply:
        p = game.players[defender.owner]
        p.supply[defender.kind] -= 1
        p.removed[defender.kind] += 1
        _log(game, "皇家卫队从供应区移除一枚棋币抵挡攻击", "capture")
    else:
        _remove_board_coin(game, dst)
    if retaliate:
        _remove_board_coin(game, src)


def _execute_maneuver(game, a):
    unit = game.units[a.src]
    kind, side = unit.kind, unit.owner
    if a.op in ("move", "move_two", "royal_move", "command_move"):
        game.units[a.dst] = game.units.pop(a.src)
        _log(game, f"{game.players[side].name}移动{NAMES[kind][0]}", "move")
        _after_maneuver(game, a.dst, kind, side, "move")
    elif a.op == "control":
        faction = team(game, side)
        game.objective_owner[a.src] = faction
        _log(game, f"{game.players[side].name}控制据点 {loc(a.src)}", "control")
        if sum(v == faction for v in game.objective_owner.values()) == game.control_target:
            game.winner = faction
        else:
            _after_maneuver(game, a.src, kind, side, "control")
    elif a.op in ("attack", "shot", "command_attack"):
        _attack(game, a.src, a.dst)
    elif a.op == "charge":
        game.units[a.dst] = game.units.pop(a.src)
        _attack(game, a.dst, a.aux)
    elif a.op == "footman_tactic":
        positions = tuple(x for x, u in sorted(game.units.items()) if u.owner == side and u.kind == "footman")
        game.tasks.append(Task("footman_bonus", side, remaining=positions))
    else:
        raise RuntimeError(f"unknown maneuver {a.op}")


def _settle(game):
    """Run forced effects, pausing before each real player choice."""
    if game.winner:
        game.tasks.clear()
        game.phase = "main"
        game.pending_unit = None
        return
    while game.tasks:
        t = game.tasks[-1]
        if t.kind == "end_turn":
            game.tasks.pop()
            _next(game, t.side)
        elif t.kind == "after_attack":
            game.tasks.pop()
            _after_maneuver(game, t.src, t.coin, t.side, "attack")
        elif t.kind == "priest_draw":
            game.tasks.pop()
            coin = _draw_one(game, t.side)
            if coin is not None:
                game.players[t.side].hand.append(coin)
                game.tasks.append(Task("forced_coin", t.side, coin=coin))
                _log(game, "战斗牧师抽取并立即使用一枚棋币")
        elif t.kind == "footman_bonus" and not any(
                xy in game.units and _normal(game, xy) for xy in t.remaining):
            game.tasks.pop()
        elif t.kind in ("berserk_bonus", "mercenary_bonus", "sword_bonus") and t.src not in game.units:
            game.tasks.pop()
        else:
            game.decision = t.side
            game.phase = t.kind
            game.pending_unit = t.src
            return
    game.phase = "main"
    game.pending_unit = None


def apply_action(game, action):
    """Safe public entry: reject illegal actions before touching state."""
    if action not in legal_actions(game):
        raise ValueError("illegal action")
    _apply_legal_action(game, action)
    check_invariants(game)


def _apply_legal_action(game, action):
    """Internal fast path: caller selected from this exact state's legal list."""
    actor = game.decision
    player = game.players[actor]
    if game.phase == "draft":
        kind = action.recruit
        player.army += (kind,)
        player.bag.extend((kind,kind))
        player.supply[kind] = COIN_TOTALS[kind]-2
        game.draft_pool = tuple(k for k in game.draft_pool if k != kind)
        game.draft_index += 1
        _log(game, f"{player.name}选择{NAMES[kind][0]}")
        if game.draft_pool:
            game.decision = game.draft_order[game.draft_index]
        else:
            _start_round(game)
        game.revision += 1
        return
    t = game.tasks.pop() if game.tasks else None
    if t and t.kind == "guard_defense":
        _resolve_strike(game, t.src, t.dst, action.op == "guard_supply")
    elif t and t.kind == "sword_bonus":
        if action.op == "bonus_move":
            game.units[action.dst] = game.units.pop(action.src)
            _log(game, "剑士执行攻击后的额外移动", "move")
    elif t and t.kind in ("berserk_bonus", "mercenary_bonus", "footman_bonus"):
        if action.op != "finish_bonus":
            if t.kind == "berserk_bonus":
                _remove_board_coin(game, t.src, discard=True)
            elif t.kind == "footman_bonus":
                remaining = tuple(x for x in t.remaining if x != action.src)
                if remaining:
                    game.tasks.append(replace(t, remaining=remaining))
            _execute_maneuver(game, action)
    else:
        if t is None:
            game.tasks.append(Task("end_turn", actor))
        else:
            assert t.kind == "forced_coin"
        player.hand.remove(action.coin)
        if action.op in ("pass", "initiative", "recruit"):
            player.discard.append((action.coin, False))
        elif action.op not in ("deploy", "bolster"):
            player.discard.append((action.coin, True))
        if action.op == "initiative":
            game.initiative = actor
            game.initiative_moved = True
            _log(game, f"{player.name}夺得先手标记")
        elif action.op == "recruit":
            player.supply[action.recruit] -= 1
            player.discard.append((action.recruit, True))
            _log(game, f"{player.name}公开招募{NAMES[action.recruit][0]}")
            if action.recruit == "mercenary":
                for xy, u in game.units.items():
                    if u.owner == actor and u.kind == "mercenary":
                        game.tasks.append(Task("mercenary_bonus", actor, xy))
                        break
        elif action.op == "deploy":
            game.units[action.dst] = Unit(actor, action.coin)
            _log(game, f"{player.name}部署{NAMES[action.coin][0]}", "move")
        elif action.op == "bolster":
            game.units[action.src].count += 1
            _log(game, f"{player.name}增援{NAMES[action.coin][0]}", "move")
        elif action.op == "pass":
            _log(game, f"{player.name}弃置一枚棋币")
        else:
            _execute_maneuver(game, action)
    _settle(game)
    game.revision += 1


def check_invariants(game):
    assert game.decision in game.players
    assert set(game.units) <= board_hexes(game)
    assert set(game.objective_owner) == (FULL_OBJECTIVES if len(game.players)==4 else OBJECTIVES)
    assert set(game.objective_owner.values()) <= {None, "north", "south"}
    assert all(u.count > 0 and u.kind in game.players[u.owner].army for u in game.units.values())
    assert (not game.tasks and game.phase in ("main", "draft")) or (game.tasks and game.phase == game.tasks[-1].kind)
    for side, p in game.players.items():
        assert set(p.supply) == set(p.army)
        assert all(isinstance(v, int) and v >= 0 for v in p.supply.values())
        assert set(p.bag + p.hand + [k for k, _ in p.discard]) <= {*p.army, "royal"}
        counts = Counter(p.bag) + Counter(p.hand) + Counter(k for k, _ in p.discard)
        for u in game.units.values():
            if u.owner == side:
                counts[u.kind] += u.count
        for kind in p.army:
            assert counts[kind]+p.supply[kind]+p.removed[kind] == COIN_TOTALS[kind], (kind, counts)
            assert sum(u.owner == side and u.kind == kind for u in game.units.values()) <= (2 if kind == "footman" else 1)
        assert counts["royal"] == 1
        assert sum(x == team(game, side) for x in game.objective_owner.values()) <= game.control_target
    if game.winner:
        assert sum(x == game.winner for x in game.objective_owner.values()) == game.control_target
    if game.tasks:
        assert game.tasks[-1].side == game.decision
