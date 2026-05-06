"""游戏主流程 API

供 B组（界面交互组）调用 A组 的核心逻辑
基于 GameEngine 实现分步骤控制
"""
import uuid
import random
from typing import Optional, List, Dict

from .models import (
    GameState, Event, EventType, Phase,
    NightResult, DayResult, VoteResult,
)
from .exceptions import (
    GameNotFoundError, InvalidPhaseError,
    InvalidPlayerError, GameAlreadyOverError,
)


# 全局游戏存储（生产环境应使用数据库）
_games: Dict[str, GameState] = {}


def init_game(num_players: int = 4, human_player_id: int = 0) -> GameState:
    """初始化游戏

    Args:
        num_players: 玩家数量，默认4人
        human_player_id: 人类玩家ID，默认0

    Returns:
        GameState: 初始游戏状态
    """
    game_id = str(uuid.uuid4())[:8]

    # 角色配置
    roles = ["狼人", "预言家", "女巫", "村民"][:num_players]
    random.shuffle(roles)

    # 创建玩家
    player_roles = {i: roles[i] for i in range(num_players)}
    player_names = {i: f"玩家{i}" for i in range(num_players)}
    player_names[human_player_id] = "你"

    alive_players = list(range(num_players))

    # 初始事件
    events = [
        Event(
            type=EventType.START,
            player_id=-1,
            content=f"游戏开始！共{num_players}名玩家",
        )
    ]

    state = GameState(
        game_id=game_id,
        day=1,
        phase=Phase.NIGHT,
        alive_players=alive_players,
        player_roles=player_roles,
        player_names=player_names,
        history=events,
        current_player=human_player_id,
    )

    _games[game_id] = state
    return state


def get_game_state(game_id: str) -> GameState:
    """获取当前游戏状态

    Args:
        game_id: 游戏ID

    Returns:
        GameState: 当前游戏状态
    """
    if game_id not in _games:
        raise GameNotFoundError(f"游戏 {game_id} 不存在")
    return _games[game_id]


def night_step(
    game_id: str,
    user_werewolf_target: Optional[int] = None,
    user_seer_target: Optional[int] = None,
    user_witch_save: bool = False,
    user_witch_poison: Optional[int] = None,
) -> NightResult:
    """执行黑夜阶段

    Args:
        game_id: 游戏ID
        user_werewolf_target: 用户（狼人）选择击杀的目标
        user_seer_target: 用户（预言家）选择查验的目标
        user_witch_save: 用户（女巫）是否救人
        user_witch_poison: 用户（女巫）选择毒的目标

    Returns:
        NightResult: 黑夜阶段结果
    """
    state = get_game_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    events: List[Event] = []
    killed: Optional[int] = None
    saved = False
    poisoned: Optional[int] = None
    checked: Optional[int] = None
    checked_role: Optional[str] = None

    # 狼人杀人
    werewolf_id = _find_player_by_role(state, "狼人", include_human=True)
    if werewolf_id is not None and werewolf_id in state.alive_players:
        # TODO: 接入LLM获取狼人决策，当前使用随机或用户输入
        if werewolf_id == state.current_player and user_werewolf_target:
            target = user_werewolf_target
        else:
            # AI狼人决策
            others = [p for p in state.alive_players if p != werewolf_id]
            target = random.choice(others) if others else None

        if target:
            killed = target
            events.append(Event(
                type=EventType.KILL,
                player_id=werewolf_id,
                content=f"狼人击杀了 {target} 号",
                target=target,
            ))

    # 预言家验人
    seer_id = _find_player_by_role(state, "预言家", include_human=True)
    if seer_id is not None and seer_id in state.alive_players:
        if seer_id == state.current_player and user_seer_target:
            target = user_seer_target
        else:
            others = [p for p in state.alive_players if p != seer_id]
            target = random.choice(others) if others else None

        if target:
            checked = target
            checked_role = state.player_roles[target]
            events.append(Event(
                type=EventType.CHECK,
                player_id=seer_id,
                content=f"预言家查验了 {target} 号，身份是 {checked_role}",
                target=target,
            ))

    # 女巫救人/毒人
    witch_id = _find_player_by_role(state, "女巫", include_human=True)
    if witch_id is not None and witch_id in state.alive_players:
        if witch_id == state.current_player:
            if killed is not None and user_witch_save:
                saved = True
                events.append(Event(
                    type=EventType.SAVE,
                    player_id=witch_id,
                    content=f"女巫救活了 {killed} 号",
                ))
            if user_witch_poison:
                poisoned = user_witch_poison
                events.append(Event(
                    type=EventType.POISON,
                    player_id=witch_id,
                    content=f"女巫毒杀了 {poisoned} 号",
                    target=poisoned,
                ))
        else:
            # AI女巫决策（简化版）
            if killed is not None and random.random() < 0.5:
                saved = True
                events.append(Event(
                    type=EventType.SAVE,
                    player_id=witch_id,
                    content=f"女巫救活了 {killed} 号",
                ))

    # 应用死亡
    dead_players = []
    if killed is not None and not saved:
        dead_players.append(killed)
    if poisoned is not None and poisoned in state.alive_players:
        dead_players.append(poisoned)

    for pid in dead_players:
        if pid in state.alive_players:
            state.alive_players.remove(pid)

    # 更新历史
    state.history.extend(events)

    # 检查胜负
    game_over = _check_game_over(state)
    if game_over:
        state.phase = Phase.ENDED
    else:
        state.phase = Phase.DAY

    state.current_player = state.alive_players[0] if state.alive_players else None

    return NightResult(
        killed=killed if not saved else None,
        saved=saved,
        poisoned=poisoned,
        checked=checked,
        checked_role=checked_role,
        events=events,
        game_over=game_over,
    )


def day_step(game_id: str, user_speak: str) -> DayResult:
    """执行白天阶段（发言）

    Args:
        game_id: 游戏ID
        user_speak: 用户的发言内容

    Returns:
        DayResult: 白天阶段结果
    """
    state = get_game_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    speeches: List[Event] = []
    events: List[Event] = []

    # 用户发言
    if state.current_player == 0:  # 假设0号是人类
        speeches.append(Event(
            type=EventType.SPEAK,
            player_id=0,
            content=user_speak,
        ))

    # AI发言（TODO: 接入LLM）
    for pid in state.alive_players:
        if pid != state.current_player:
            # 简化版AI发言
            ai_content = _generate_ai_speak(pid, state)
            speeches.append(Event(
                type=EventType.SPEAK,
                player_id=pid,
                content=ai_content,
            ))

    state.history.extend(speeches)

    return DayResult(
        speeches=speeches,
        events=events,
        game_over=False,
    )


def vote_step(game_id: str, user_vote: int) -> VoteResult:
    """执行投票阶段

    Args:
        game_id: 游戏ID
        user_vote: 用户投票的目标

    Returns:
        VoteResult: 投票阶段结果
    """
    state = get_game_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    votes: Dict[int, int] = {}
    events: List[Event] = []

    # 收集所有玩家投票
    for pid in state.alive_players:
        if pid == state.current_player:
            # 用户投票
            target = user_vote
        else:
            # AI投票（简化版：随机）
            others = [p for p in state.alive_players if p != pid]
            target = random.choice(others) if others else None

        if target:
            votes[target] = votes.get(target, 0) + 1
            events.append(Event(
                type=EventType.VOTE,
                player_id=pid,
                content=f"玩家 {pid} 投票给 {target}",
                target=target,
            ))

    # 计票
    eliminated: Optional[int] = None
    tie = False
    if votes:
        max_votes = max(votes.values())
        candidates = [p for p, v in votes.items() if v == max_votes]

        if len(candidates) == 1:
            eliminated = candidates[0]
            state.alive_players.remove(eliminated)
            events.append(Event(
                type=EventType.ELIMINATE,
                player_id=-1,
                content=f"{eliminated} 号玩家被投票出局",
                target=eliminated,
            ))
        else:
            tie = True
            events.append(Event(
                type=EventType.ELIMINATE,
                player_id=-1,
                content=f"平票：{candidates}，无人出局",
            ))

    state.history.extend(events)

    # 检查胜负
    game_over = _check_game_over(state)
    if game_over:
        state.phase = Phase.ENDED
    else:
        state.phase = Phase.NIGHT
        state.day += 1

    return VoteResult(
        votes=votes,
        eliminated=eliminated,
        tie=tie,
        events=events,
        game_over=game_over,
    )


def get_history(game_id: str) -> List[Event]:
    """获取历史事件

    Args:
        game_id: 游戏ID

    Returns:
        List[Event]: 历史事件列表
    """
    state = get_game_state(game_id)
    return state.history


def check_win(game_id: str) -> Optional[str]:
    """检查胜负

    Args:
        game_id: 游戏ID

    Returns:
        Optional[str]: '好人' / '狼人' / None(游戏继续)
    """
    state = get_game_state(game_id)
    wolves = sum(1 for pid, role in state.player_roles.items()
                 if role == "狼人" and pid in state.alive_players)
    goods = sum(1 for pid in state.alive_players
                if state.player_roles.get(pid) != "狼人")

    if wolves == 0:
        state.winner = "好人"
        return "好人"
    if wolves >= goods:
        state.winner = "狼人"
        return "狼人"
    return None


# ============ 内部辅助函数 ============

def _find_player_by_role(state: GameState, role: str, include_human: bool = False) -> Optional[int]:
    """查找拥有指定角色的玩家ID"""
    for pid, r in state.player_roles.items():
        if r == role:
            if include_human or pid != state.current_player:
                return pid
    return None


def _check_game_over(state: GameState) -> bool:
    """检查游戏是否结束"""
    wolves = sum(1 for pid, role in state.player_roles.items()
                 if role == "狼人" and pid in state.alive_players)
    goods = sum(1 for pid in state.alive_players
                if state.player_roles.get(pid) != "狼人")

    return wolves == 0 or wolves >= goods


def _generate_ai_speak(player_id: int, state: GameState) -> str:
    """生成AI发言（简化版，正式版应接入LLM）"""
    personalities = ["aggressive", "rational", "hesitant", "follower"]
    personality = random.choice(personalities)

    others = [p for p in state.alive_players if p != player_id]
    if not others:
        return "我是好人..."

    target = random.choice(others)

    if personality == "aggressive":
        return f"我强烈怀疑{target}号是狼人！"
    elif personality == "hesitant":
        return f"我觉得{target}号有点可疑...但不确定..."
    elif personality == "follower":
        return "我觉得...大家都说得有道理..."
    else:
        return "我是好人，大家不要投我"
