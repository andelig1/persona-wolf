"""API 模块 - 前后端接口层

供 B组（界面交互组）调用 A组 的核心逻辑
"""
from .game_api import (
    init_game,
    get_game_state,
    night_step,
    day_step,
    vote_step,
    get_history,
    check_win,
)
from .models import GameState, Event, NightResult, DayResult, VoteResult

__all__ = [
    "init_game",
    "get_game_state",
    "night_step",
    "day_step",
    "vote_step",
    "get_history",
    "check_win",
    "GameState",
    "Event",
    "NightResult",
    "DayResult",
    "VoteResult",
]
