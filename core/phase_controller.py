"""游戏阶段控制"""
from enum import Enum
from typing import List, Optional


class Phase(Enum):
    """游戏阶段"""
    WAITING = "waiting"
    NIGHT = "night"
    DAY = "day"
    VOTE = "vote"
    ENDED = "ended"


class PhaseController:
    """阶段控制器 - 管理游戏阶段的切换"""

    def __init__(self):
        self.current_phase = Phase.WAITING
        self.day = 1
        self.night_order = ["狼人", "预言家", "女巫"]
        self.current_night_action = 0

    def start_game(self):
        """开始游戏，进入夜晚"""
        self.day = 1
        self.current_phase = Phase.NIGHT
        self.current_night_action = 0

    def get_next_phase(self) -> Phase:
        """获取下一个阶段"""
        if self.current_phase == Phase.NIGHT:
            return Phase.DAY
        elif self.current_phase == Phase.DAY:
            return Phase.VOTE
        elif self.current_phase == Phase.VOTE:
            return Phase.NIGHT
        return self.current_phase

    def next_phase(self):
        """切换到下一阶段"""
        if self.current_phase == Phase.NIGHT:
            self.current_phase = Phase.DAY
        elif self.current_phase == Phase.DAY:
            self.current_phase = Phase.VOTE
        elif self.current_phase == Phase.VOTE:
            self.current_phase = Phase.NIGHT
            self.day += 1

    def get_night_action_role(self) -> Optional[str]:
        """获取当前夜晚行动的角色"""
        if self.current_phase != Phase.NIGHT:
            return None
        if self.current_night_action >= len(self.night_order):
            return None
        return self.night_order[self.current_night_action]

    def advance_night_action(self):
        """推进夜晚行动顺序"""
        self.current_night_action += 1
        if self.current_night_action >= len(self.night_order):
            self.current_night_action = 0

    def is_game_over(self) -> bool:
        """检查是否结束"""
        return self.current_phase == Phase.ENDED

    def end_game(self, winner: str):
        """结束游戏"""
        self.current_phase = Phase.ENDED

    def reset(self):
        """重置阶段控制器"""
        self.current_phase = Phase.WAITING
        self.day = 1
        self.current_night_action = 0

    def get_state(self) -> dict:
        """获取阶段状态"""
        return {
            "day": self.day,
            "phase": self.current_phase.value,
            "night_action_role": self.get_night_action_role(),
        }

    def __repr__(self):
        return f"PhaseController(day={self.day}, phase={self.current_phase.value})"