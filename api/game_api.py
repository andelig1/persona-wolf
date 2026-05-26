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


def get_role_config(num_players: int) -> list:
    """根据人数获取角色配置"""
    if num_players == 6:
        return ["狼人", "狼人", "预言家", "女巫", "村民", "村民"]
    elif num_players == 7:
        return ["狼人", "狼人", "预言家", "女巫", "村民", "村民", "村民"]
    elif num_players == 8:
        return ["狼人", "狼人", "预言家", "女巫", "女巫", "村民", "村民", "村民"]
    elif num_players == 9:
        return ["狼人", "狼人", "狼人", "预言家", "女巫", "村民", "村民", "村民", "村民"]
    elif num_players == 10:
        return ["狼人", "狼人", "狼人", "预言家", "女巫", "女巫", "村民", "村民", "村民", "村民"]
    else:
        # 默认返回6人配置
        return ["狼人", "狼人", "预言家", "女巫", "村民", "村民"]


def init_game(num_players: int = 4, human_player_id: int = 0, human_role: str = None) -> GameState:
    """初始化游戏"""
    game_id = str(uuid.uuid4())[:8]

    engine = GameEngine(num_players, human_player_id)
    if human_role:
        engine.initialize_with_roles(human_role)
    else:
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


def set_werewolf_target(game_id: str, target: int) -> dict:
    """设置狼人击杀目标（用于分步执行夜晚阶段）"""
    engine, state = _get_engine_and_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    if state.phase != Phase.NIGHT:
        raise InvalidPhaseError("当前不是夜晚阶段")

    # 直接设置狼人击杀目标
    engine.werewolf_kill_target = target
    
    # 记录到记忆
    wolves = engine.role_manager.get_alive_by_role("狼人", engine.alive_players)
    if wolves:
        engine._distribute_info_to_memories(
            "kill", f"狼人选择击杀{target}号",
            target=target, visibility="werewolf",
            player_id=wolves[0],
        )

    _sync_state(state, engine)
    return {"werewolf_kill_target": target}


def execute_wolf_action(game_id: str) -> dict:
    """让狼人AI自动执行击杀行动（当人类不是狼人时调用）"""
    import traceback
    
    engine, state = _get_engine_and_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    if state.phase != Phase.NIGHT:
        raise InvalidPhaseError("当前不是夜晚阶段")

    # 检查人类玩家是否是狼人
    human_role = engine.role_manager.get_player_role(engine.human_player_id)
    print(f"[execute_wolf_action] 人类玩家角色: {human_role}")
    
    if human_role == "狼人":
        raise InvalidPlayerError("人类玩家是狼人，请手动选择击杀目标")

    # 获取狼人列表
    wolves = engine.role_manager.get_alive_by_role("狼人", engine.alive_players)
    print(f"[execute_wolf_action] 狼人列表: {wolves}")
    
    if not wolves:
        return {"werewolf_kill_target": None, "message": "没有存活的狼人"}

    # 获取游戏状态供AI决策
    game_state = engine.get_game_state()
    
    # 让狼人AI执行行动
    wolf_agent = engine.agents[wolves[0]]
    print(f"[execute_wolf_action] 调用狼人AI: {wolf_agent}")
    
    action = None
    try:
        print(f"[execute_wolf_action] 开始调用 night_action...")
        action = wolf_agent.night_action(game_state, wolf_teammates=wolves)
        print(f"[execute_wolf_action] night_action 返回: {action}")
    except Exception as e:
        # LLM调用失败，使用策略回退
        print(f"[execute_wolf_action] night_action 异常: {str(e)}")
        traceback.print_exc()
        print(f"[execute_wolf_action] 使用策略回退...")
        action = wolf_agent.strategy.suggest_night_action(
            wolf_agent.memory, 
            game_state.get("alive_players", []),
            {"wolf_teammates": wolves}
        )
        print(f"[execute_wolf_action] 策略回退返回: {action}")
    
    if action and action.get("type") == "kill":
        engine.werewolf_kill_target = action.get("target")
        print(f"[execute_wolf_action] 狼人AI选择击杀: {engine.werewolf_kill_target} 号玩家")
        
        # 记录到记忆
        engine._distribute_info_to_memories(
            "kill", f"狼人选择击杀{engine.werewolf_kill_target}号",
            target=engine.werewolf_kill_target, visibility="werewolf",
            player_id=wolves[0],
        )
    else:
        print(f"[execute_wolf_action] 没有获取到击杀行动，使用随机选择")
        # 如果AI没有选择目标，随机选择一个
        alive = game_state.get("alive_players", [])
        candidates = [p for p in alive if p not in wolves]
        print(f"[execute_wolf_action] 可选目标: {candidates}")
        
        if candidates:
            import random
            engine.werewolf_kill_target = random.choice(candidates)
            print(f"[execute_wolf_action] 狼人AI随机选择击杀: {engine.werewolf_kill_target} 号玩家")
            
            engine._distribute_info_to_memories(
                "kill", f"狼人选择击杀{engine.werewolf_kill_target}号",
                target=engine.werewolf_kill_target, visibility="werewolf",
                player_id=wolves[0],
            )
        else:
            engine.werewolf_kill_target = None
            print(f"[execute_wolf_action] 没有可选目标")

    _sync_state(state, engine)
    return {"werewolf_kill_target": engine.werewolf_kill_target}


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

    # 添加法官提示词事件
    current_day = engine.phase_controller.day
    state.history.append(Event(
        type=EventType.SYSTEM,
        player_id=-1,
        content=f"🌙 第 {current_day} 天夜晚到来..."
    ))
    state.history.append(Event(
        type=EventType.SYSTEM,
        player_id=-1,
        content=f"☽ 所有人请闭眼"
    ))

    # 检查是否有狼人存活
    has_wolves = len(engine.role_manager.get_alive_by_role("狼人", engine.alive_players)) > 0
    if has_wolves:
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🐺 狼人请睁眼"
        ))
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🐺 狼人请闭眼"
        ))

    # 检查是否有预言家存活
    has_seers = len(engine.role_manager.get_alive_by_role("预言家", engine.alive_players)) > 0
    if has_seers:
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🔮 预言家请睁眼"
        ))
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🔮 预言家请闭眼"
        ))

    # 检查是否有女巫存活
    has_witches = len(engine.role_manager.get_alive_by_role("女巫", engine.alive_players)) > 0
    if has_witches:
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🧪 女巫请睁眼"
        ))
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🧪 女巫请闭眼"
        ))

    state.history.append(Event(
        type=EventType.SYSTEM,
        player_id=-1,
        content=f"☀️ 所有人请睁眼"
    ))

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

    # 夜晚结束后检查胜负（与CLI的run()保持一致）
    winner = engine.rule_checker.check_win_condition(engine.alive_players)
    game_over = winner is not None
    if game_over:
        engine.winner = winner
        engine.phase_controller.end_game(winner)
        events.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🏆 {winner} 胜利！"
        ))
        _sync_state(state, engine)

    return NightResult(
        killed=result.get('killed') if not result.get('saved') else None,
        saved=result.get('saved', False),
        poisoned=result.get('poisoned'),
        checked=result.get('checked'),
        checked_role=result.get('checked_role'),
        events=events,
        game_over=game_over,
    )


def day_step(game_id: str, user_speak: str) -> DayResult:
    """执行白天阶段（发言）- 使用engine.day_step()方法，与CLI版本保持一致"""
    engine, state = _get_engine_and_state(game_id)

    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    if state.phase != Phase.DAY:
        raise InvalidPhaseError("当前不是白天阶段")

    # 添加天亮提示词
    current_day = engine.phase_controller.day
    state.history.append(Event(
        type=EventType.SYSTEM,
        player_id=-1,
        content=f"☀️ 第 {current_day} 天到来..."
    ))

    # 检查昨晚是否有人死亡
    if engine.last_night_dead and len(engine.last_night_dead) > 0:
        dead_names = [f"{pid}号" for pid in engine.last_night_dead]
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"💀 昨夜，{', '.join(dead_names)}玩家死亡..."
        ))
    else:
        state.history.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🌙 昨夜是平安夜"
        ))

    # 设置人类玩家的发言内容（用于_handle_human_speech）
    engine.human_speech = user_speak

    # 调用engine的day_step方法（与CLI版本相同）
    result = engine.day_step(round_num=1, previous_speeches=[])
    all_speeches = result["speeches"]

    # 转换为Event格式
    speeches = []
    for s in all_speeches:
        speeches.append(Event(
            type=EventType.SPEAK,
            player_id=s["player_id"],
            content=s["content"],
        ))

    # 将所有发言添加到历史
    state.history.extend(speeches)

    # 进入投票阶段（同时更新engine和state）
    engine.phase_controller.next_phase()  # 从DAY切换到VOTE
    state.history.append(Event(
        type=EventType.SYSTEM,
        player_id=-1,
        content=f"🗳️ 投票环节"
    ))

    # 同步状态到GameState
    _sync_state(state, engine)

    return DayResult(
        speeches=speeches,
        events=[],
        game_over=False,
    )


def vote_step(game_id: str, user_vote: int) -> VoteResult:
    """执行投票阶段"""
    engine, state = _get_engine_and_state(game_id)

    print(f"[调试] 投票前的 phase: {state.phase}")
    
    if state.phase == Phase.ENDED:
        raise GameAlreadyOverError("游戏已结束")

    result = engine.vote_step(human_vote=user_vote)
    
    print(f"[调试] engine.vote_step 返回 result: {result}")
    print(f"[调试] engine.phase_controller.current_phase: {engine.phase_controller.current_phase}")
    
    _sync_state(state, engine)
    
    print(f"[调试] _sync_state 后的 state.phase: {state.phase}")

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

    # 添加投票结果的法官提示词
    if result.get("eliminated") is not None:
        events.insert(0, Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"📊 投票结果：{votes}"
        ))
    elif len(votes) > 0:
        events.insert(0, Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"⚖️ 平票！无人出局"
        ))

    # 如果游戏结束，添加游戏结束提示词
    if result.get("game_over") and result.get("winner"):
        events.append(Event(
            type=EventType.SYSTEM,
            player_id=-1,
            content=f"🏆 {result['winner']} 胜利！"
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
    speaking_order = engine._get_speaking_order() if hasattr(engine, '_get_speaking_order') else []
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
        witch_has_save=gs.get("witch_has_save", True),
        witch_has_poison=gs.get("witch_has_poison", True),
        werewolf_kill_target=gs.get("werewolf_kill_target"),
        speaking_order=speaking_order,
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
    state.witch_has_save = gs.get("witch_has_save", True)
    state.witch_has_poison = gs.get("witch_has_poison", True)
    state.werewolf_kill_target = gs.get("werewolf_kill_target")
    state.speaking_order = engine._get_speaking_order() if hasattr(engine, '_get_speaking_order') else []
    
    # 同步引擎的 history 到 state.history
    event_type_map = {
        "speak": EventType.SPEAK,
        "vote": EventType.VOTE,
        "kill": EventType.KILL,
        "eliminate": EventType.ELIMINATE,
        "check": EventType.CHECK,
        "save": EventType.SAVE,
        "poison": EventType.POISON,
    }
    
    # 记录已存在的 SYSTEM 事件（法官提示词）
    existing_system_events = [e for e in state.history if e.type == EventType.SYSTEM]
    
    # 转换引擎的 history 事件
    engine_events = [
        Event(
            type=event_type_map.get(e.get("type"), EventType.SPEAK),
            player_id=e.get("player_id", -1),
            content=e.get("content", ""),
            target=e.get("target")
        )
        for e in engine.history
    ]
    
    # 合并事件：保留 SYSTEM 事件 + 引擎的 history 事件
    state.history = existing_system_events + engine_events
