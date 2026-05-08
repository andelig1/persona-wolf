"""游戏主流程 API

供 B组（界面交互组）调用 A组 的核心逻辑
委托给 GameEngine 实现，AI Agent 使用 ReAct 推理
"""
import uuid
from typing import Optional, List, Dict

from core.game_engine import GameEngine
from .models import (
    GameState, Event, EventType, Phase,
    NightResult, DayResult, VoteResult,
)
from .exceptions import (
    GameNotFoundError, InvalidPhaseError,
    InvalidPlayerError, GameAlreadyOverError,
)


# 全局游戏存储: game_id -> (GameEngine, GameState)
_games: Dict[str, tuple] = {}


def init_game(num_players: int = 4, human_player_id: int = 0) -> GameState:
    """初始化游戏"""
    game_id = str(uuid.uuid4())[:8]

    engine = GameEngine(num_players, human_player_id)
    engine.initialize()

    state = _engine_to_state(game_id, engine)
    _games[game_id] = (engine, state)
    return state


def get_game_state(game_id: str) -> GameState:
    """获取当前游戏状态"""
    if game_id not in _games:
        raise GameNotFoundError(f"游戏 {game_id} 不存在")
    engine, state = _games[game_id]
    # 同步引擎状态到 API state
    _sync_state(state, engine)
    return state


def night_step(
    game_id: str,
    user_werewolf_target: Optional[int] = None,
    user_seer_target: Optional[int] = None,
    user_witch_save: bool = False,
    user_witch_poison: Optional[int] = None,
) -> NightResult:
    """执行黑夜阶段"""
    engine, state = _get_engine_and_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    human_actions = {
        "werewolf_target": user_werewolf_target,
        "seer_target": user_seer_target,
        "witch_save_choice": 'y' if user_witch_save else 'n',
        "witch_poison": user_witch_poison,
    }

    result = engine.night_step(human_actions)
    _sync_state(state, engine)

    events = [
        Event(type=EventType.KILL, player_id=-1,
              content=f"狼人击杀了 {result['killed']} 号" if result['killed'] else "平安夜",
              target=result.get('killed')),
    ]
    if result.get('saved'):
        events.append(Event(type=EventType.SAVE, player_id=-1,
                            content=f"女巫救活了 {result['killed']} 号"))
    if result.get('checked'):
        events.append(Event(type=EventType.CHECK, player_id=-1,
                            content=f"预言家查验了 {result['checked']} 号",
                            target=result['checked']))
    if result.get('poisoned'):
        events.append(Event(type=EventType.POISON, player_id=-1,
                            content=f"女巫毒杀了 {result['poisoned']} 号",
                            target=result['poisoned']))

    state.history.extend(events)

    return NightResult(
        killed=result.get('killed') if not result.get('saved') else None,
        saved=result.get('saved', False),
        poisoned=result.get('poisoned'),
        checked=result.get('checked'),
        checked_role=result.get('checked_role'),
        events=events,
        game_over=result.get('dead', []) and engine.is_game_over(),
    )


def day_step(game_id: str, user_speak: str) -> DayResult:
    """执行白天阶段（发言）"""
    engine, state = _get_engine_and_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    result = engine.day_step(human_speech=user_speak)
    _sync_state(state, engine)

    speeches = []
    for s in result.get("speeches", []):
        speeches.append(Event(
            type=EventType.SPEAK,
            player_id=s["player_id"],
            content=s["content"],
        ))

    state.history.extend(speeches)

    return DayResult(
        speeches=speeches,
        events=[],
        game_over=False,
    )


def vote_step(game_id: str, user_vote: int) -> VoteResult:
    """执行投票阶段"""
    engine, state = _get_engine_and_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    result = engine.vote_step(human_vote=user_vote)
    _sync_state(state, engine)

    events = []
    votes = result.get("votes", {})
    for target, count in votes.items():
        events.append(Event(
            type=EventType.VOTE,
            player_id=-1,
            content=f"{target} 号获得 {count} 票",
            target=target,
        ))

    if result.get("eliminated") is not None:
        events.append(Event(
            type=EventType.ELIMINATE,
            player_id=-1,
            content=f"{result['eliminated']} 号被投票出局",
            target=result['eliminated'],
        ))

    state.history.extend(events)

    return VoteResult(
        votes=votes,
        eliminated=result.get("eliminated"),
        tie=result.get("eliminated") is None and bool(votes),
        events=events,
        game_over=result.get("game_over", False),
    )


def get_history(game_id: str) -> List[Event]:
    """获取历史事件"""
    state = get_game_state(game_id)
    return state.history


def check_win(game_id: str) -> Optional[str]:
    """检查胜负"""
    engine, state = _get_engine_and_state(game_id)
    winner = engine.get_winner()
    if winner:
        state.winner = winner
    return winner


# ============ 内部辅助 ============

def _get_engine_and_state(game_id: str) -> tuple:
    if game_id not in _games:
        raise GameNotFoundError(f"游戏 {game_id} 不存在")
    return _games[game_id]


def _engine_to_state(game_id: str, engine: GameEngine) -> GameState:
    """从GameEngine创建API GameState"""
    gs = engine.get_game_state()
    phase_map = {
        "waiting": Phase.WAITING, "night": Phase.NIGHT,
        "day": Phase.DAY, "vote": Phase.VOTE, "ended": Phase.ENDED,
    }
    return GameState(
        game_id=game_id,
        day=gs["day"],
        phase=phase_map.get(gs["phase"], Phase.WAITING),
        alive_players=gs["alive_players"],
        player_roles=gs["player_roles"],
        player_names=gs["player_names"],
        history=[
            Event(type=EventType.START, player_id=-1,
                  content=f"游戏开始！共{engine.num_players}名玩家")
        ],
        current_player=engine.human_player_id,
    )


def _sync_state(state: GameState, engine: GameEngine):
    """同步GameEngine状态到API GameState"""
    gs = engine.get_game_state()
    phase_map = {
        "waiting": Phase.WAITING, "night": Phase.NIGHT,
        "day": Phase.DAY, "vote": Phase.VOTE, "ended": Phase.ENDED,
    }
    state.day = gs["day"]
    state.phase = phase_map.get(gs["phase"], Phase.WAITING)
    state.alive_players = gs["alive_players"]
    state.player_roles = gs["player_roles"]
    state.player_names = gs["player_names"]
    if engine.winner:
        state.winner = engine.winner
