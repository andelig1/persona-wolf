"""数据结构定义"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum


class Phase(str, Enum):
    """游戏阶段"""
    WAITING = "waiting"
    NIGHT = "night"
    DAY = "day"
    VOTE = "vote"
    ENDED = "ended"


class EventType(str, Enum):
    """事件类型"""
    SPEAK = "speak"
    VOTE = "vote"
    KILL = "kill"
    CHECK = "check"
    SAVE = "save"
    POISON = "poison"
    ELIMINATE = "eliminate"
    START = "start"


@dataclass
class Event:
    """游戏事件"""
    type: EventType
    player_id: int
    content: str = ""
    target: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "player_id": self.player_id,
            "content": self.content,
            "target": self.target,
        }


@dataclass
class GameState:
    """游戏状态"""
    game_id: str
    day: int = 1
    phase: Phase = Phase.WAITING
    alive_players: List[int] = field(default_factory=list)
    player_roles: Dict[int, str] = field(default_factory=dict)
    player_names: Dict[int, str] = field(default_factory=dict)
    history: List[Event] = field(default_factory=list)
    winner: Optional[str] = None
    current_player: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "day": self.day,
            "phase": self.phase.value,
            "alive_players": self.alive_players,
            "player_roles": self.player_roles,
            "player_names": self.player_names,
            "history": [e.to_dict() for e in self.history],
            "winner": self.winner,
            "current_player": self.current_player,
        }


@dataclass
class NightResult:
    """黑夜阶段结果"""
    killed: Optional[int] = None
    saved: bool = False
    poisoned: Optional[int] = None
    checked: Optional[int] = None
    checked_role: Optional[str] = None
    events: List[Event] = field(default_factory=list)
    game_over: bool = False

    def to_dict(self) -> dict:
        return {
            "killed": self.killed,
            "saved": self.saved,
            "poisoned": self.poisoned,
            "checked": self.checked,
            "checked_role": self.checked_role,
            "events": [e.to_dict() for e in self.events],
            "game_over": self.game_over,
        }


@dataclass
class DayResult:
    """白天阶段结果"""
    speeches: List[Event] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)
    game_over: bool = False

    def to_dict(self) -> dict:
        return {
            "speeches": [e.to_dict() for e in self.speeches],
            "events": [e.to_dict() for e in self.events],
            "game_over": self.game_over,
        }


@dataclass
class VoteResult:
    """投票阶段结果"""
    votes: Dict[int, int] = field(default_factory=dict)
    eliminated: Optional[int] = None
    tie: bool = False
    events: List[Event] = field(default_factory=list)
    game_over: bool = False

    def to_dict(self) -> dict:
        return {
            "votes": self.votes,
            "eliminated": self.eliminated,
            "tie": self.tie,
            "events": [e.to_dict() for e in self.events],
            "game_over": self.game_over,
        }
