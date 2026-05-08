"""全局事件记录器

记录游戏中所有可见事件，由GameEngine持有
"""
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class GameEvent:
    """游戏事件"""
    event_id: int
    event_type: str       # "speak", "vote", "kill", "eliminate", "check", "save", "poison"
    player_id: int        # 发起者
    content: str
    target: Optional[int] = None
    day: int = 0
    phase: str = ""
    visibility: str = "public"  # "public", "werewolf", "seer", "witch"


class EventRecorder:
    """全局事件记录器

    GameEngine 持有一个实例。每次事件后 GameEngine 调用 record()，
    然后通过 _distribute_to_memories() 推送到相关 Agent 的 AgentMemory。
    """

    def __init__(self):
        self.events: List[GameEvent] = []
        self._next_id: int = 0

    def record(self, event_type: str, player_id: int, content: str,
               target: int = None, day: int = 0, phase: str = "",
               visibility: str = "public") -> GameEvent:
        """记录一个游戏事件"""
        event = GameEvent(
            event_id=self._next_id,
            event_type=event_type,
            player_id=player_id,
            content=content,
            target=target,
            day=day,
            phase=phase,
            visibility=visibility,
        )
        self._next_id += 1
        self.events.append(event)
        return event

    def get_events(self, event_type: str = None, day: int = None,
                   visibility: str = None) -> List[GameEvent]:
        """查询事件"""
        results = self.events
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if day is not None:
            results = [e for e in results if e.day == day]
        if visibility:
            results = [e for e in results if e.visibility == visibility]
        return results

    def get_events_for_agent(self, agent_id: int, agent_role: str,
                             alive_players: List[int]) -> List[GameEvent]:
        """返回对特定Agent可见的事件"""
        visible = []
        for e in self.events:
            if e.visibility == "public":
                visible.append(e)
            elif e.visibility == "werewolf" and agent_role == "狼人":
                visible.append(e)
            elif e.visibility == "seer" and agent_id == e.player_id:
                visible.append(e)
            elif e.visibility == "witch" and agent_role == "女巫":
                visible.append(e)
        return visible

    def format_events(self, events: List[GameEvent] = None) -> str:
        """格式化事件为可读文本"""
        target_events = events or self.events
        if not target_events:
            return "暂无事件。"
        lines = []
        for e in target_events:
            lines.append(f"[第{e.day}天{e.phase}] {e.content}")
        return "\n".join(lines)

    def clear(self):
        """清空记录"""
        self.events = []
        self._next_id = 0
