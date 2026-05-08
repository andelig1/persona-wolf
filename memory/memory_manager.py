"""每个Agent拥有的记忆系统

存储游戏事件、嫌疑度、角色知识，供工具在ReAct推理中查询
"""
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    """单条记忆"""
    timestamp: int
    event_type: str       # "speak", "vote", "kill", "death", "check_result", "eliminate"
    content: str
    metadata: dict = field(default_factory=dict)


class AgentMemory:
    """Per-agent 记忆系统

    每个 ReActWerewolfAgent 持有一个实例。GameEngine 通过 add_memory() 推送事件，
    Agent 的工具通过 get_history() / format_for_prompt() 等方法读取信息。
    """

    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.events: List[MemoryEntry] = []
        self.suspicion_levels: Dict[int, float] = {}   # player_id -> [-1.0, 1.0]
        self.role_knowledge: Dict[int, str] = {}        # player_id -> known_role (预言家查验)
        self._counter = 0

    def add_memory(self, event_type: str, content: str, metadata: dict = None) -> None:
        """记录游戏事件"""
        self._counter += 1
        entry = MemoryEntry(
            timestamp=self._counter,
            event_type=event_type,
            content=content,
            metadata=metadata or {},
        )
        self.events.append(entry)
        self._auto_update_suspicion(event_type, content, metadata or {})

    def get_history(self, event_type: str = None, day: int = None,
                    limit: int = None, player_id: int = None) -> List[MemoryEntry]:
        """检索记忆"""
        results = self.events
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if day is not None:
            results = [e for e in results if e.metadata.get("day") == day]
        if player_id is not None:
            results = [e for e in results
                       if e.metadata.get("player_id") == player_id
                       or e.metadata.get("target") == player_id]
        if limit:
            results = results[-limit:]
        return results

    def summarize(self) -> str:
        """简要概括记忆"""
        if not self.events:
            return "暂无记忆。"
        recent = self.events[-20:]
        lines = []
        for e in recent:
            lines.append(f"[{e.event_type}] {e.content}")
        return "\n".join(lines)

    def get_suspicion_levels(self) -> Dict[int, float]:
        return self.suspicion_levels.copy()

    def update_suspicion(self, player_id: int, delta: float, reason: str = "") -> None:
        """调整嫌疑度，夹到 [-1.0, 1.0]"""
        current = self.suspicion_levels.get(player_id, 0.0)
        new_val = max(-1.0, min(1.0, current + delta))
        self.suspicion_levels[player_id] = new_val

    def set_role_knowledge(self, player_id: int, role: str) -> None:
        """记录已知角色（如预言家查验结果）"""
        self.role_knowledge[player_id] = role
        if role == "狼人":
            self.update_suspicion(player_id, 0.8, "查验确认是狼人")
        else:
            self.update_suspicion(player_id, -0.5, "查验确认是好人")

    def format_for_prompt(self, day: int = None, limit: int = 20) -> str:
        """格式化为可注入prompt的文本"""
        events = self.get_history(day=day, limit=limit)
        if not events:
            return "暂无记录。"
        lines = []
        for e in events:
            lines.append(f"  {e.content}")
        return "\n".join(lines)

    def format_suspicion_report(self) -> str:
        """格式化嫌疑度报告"""
        if not self.suspicion_levels:
            return "暂无嫌疑判断。"
        lines = []
        for pid, sus in sorted(self.suspicion_levels.items(), key=lambda x: -x[1]):
            if sus > 0.5:
                label = "高度可疑"
            elif sus > 0.2:
                label = "有些可疑"
            elif sus > -0.2:
                label = "不太确定"
            else:
                label = "比较可信"
            lines.append(f"  {pid}号: {label}({sus:.1f})")
        return "\n".join(lines)

    def _auto_update_suspicion(self, event_type: str, content: str, metadata: dict) -> None:
        """基于事件类型的启发式嫌疑度更新"""
        if event_type == "vote":
            target = metadata.get("target")
            if target is not None:
                self.update_suspicion(target, 0.05, "被投票")
