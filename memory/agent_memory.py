"""Agent 策略记忆与信念追踪系统

提供跨轮次持久化的推理结论、目标规划和结构化玩家信念
"""
from typing import List, Optional, Dict
from dataclasses import dataclass, field


@dataclass
class StrategyNote:
    """Agent 主动记录的策略笔记"""
    timestamp: int
    category: str       # "suspicion" | "plan" | "observation" | "ally" | "threat"
    target: int         # 目标玩家编号（0 = 全局）
    content: str        # 笔记内容
    priority: float     # 0-1，重要程度


@dataclass
class PlayerBelief:
    """对某玩家的结构化信念"""
    player_id: int
    suspicion: float = 0.0                                  # [-1, 1]
    suspected_role: Optional[str] = None                    # 推测的角色
    reasons: List[str] = field(default_factory=list)        # 怀疑/信任的理由
    last_updated_day: int = 0
    confidence: float = 0.0                                 # 信念置信度 [0, 1]


class StrategicMemory:
    """策略记忆 — Agent 的推理结论和计划，跨轮次持久化"""

    def __init__(self):
        self.notes: List[StrategyNote] = []
        self._counter = 0

    def add_note(self, category: str, target: int, content: str, priority: float = 0.5) -> None:
        self._counter += 1
        self.notes.append(StrategyNote(
            timestamp=self._counter,
            category=category,
            target=target,
            content=content,
            priority=max(0.0, min(1.0, priority)),
        ))

    def get_notes(self, category: str = None, target: int = None, limit: int = None) -> List[StrategyNote]:
        results = self.notes
        if category:
            results = [n for n in results if n.category == category]
        if target is not None:
            results = [n for n in results if n.target == target]
        if limit:
            results = results[-limit:]
        return results

    def format_for_prompt(self, category: str = None) -> str:
        """格式化为可注入 prompt 的文本"""
        notes = self.get_notes(category=category)
        if not notes:
            return "暂无策略笔记。"

        # 按类别分组
        groups: Dict[str, List[StrategyNote]] = {}
        for note in notes:
            groups.setdefault(note.category, []).append(note)

        category_labels = {
            "suspicion": "怀疑判断",
            "plan": "目标计划",
            "observation": "观察记录",
            "ally": "盟友判断",
            "threat": "威胁评估",
        }

        lines = []
        for cat, cat_notes in groups.items():
            label = category_labels.get(cat, cat)
            lines.append(f"【{label}】")
            for note in cat_notes:
                if note.target > 0:
                    lines.append(f"  - {note.target}号玩家: {note.content}")
                else:
                    lines.append(f"  - {note.content}")
            lines.append("")

        return "\n".join(lines)


class BeliefTracker:
    """信念追踪 — 对每个玩家形成结构化的信念"""

    def __init__(self):
        self.beliefs: Dict[int, PlayerBelief] = {}

    def update_belief(self, player_id: int, suspicion_delta: float = None,
                      suspected_role: str = None, reason: str = None,
                      confidence: float = None, day: int = 0) -> None:
        """更新或创建玩家信念"""
        if player_id not in self.beliefs:
            self.beliefs[player_id] = PlayerBelief(player_id=player_id)

        belief = self.beliefs[player_id]

        if suspicion_delta is not None:
            belief.suspicion = max(-1.0, min(1.0, belief.suspicion + suspicion_delta))

        if suspected_role is not None:
            belief.suspected_role = suspected_role

        if reason is not None:
            # 避免重复理由
            if reason not in belief.reasons:
                belief.reasons.append(reason)
            # 最多保留 5 条理由
            if len(belief.reasons) > 5:
                belief.reasons = belief.reasons[-5:]

        if confidence is not None:
            belief.confidence = max(0.0, min(1.0, confidence))

        if day > 0:
            belief.last_updated_day = day

    def get_belief(self, player_id: int) -> Optional[PlayerBelief]:
        return self.beliefs.get(player_id)

    def format_belief_report(self) -> str:
        """格式化信念报告，用于注入 prompt"""
        if not self.beliefs:
            return "暂无玩家信念判断。"

        lines = []
        for pid in sorted(self.beliefs.keys()):
            belief = self.beliefs[pid]

            if belief.suspicion > 0.5:
                sus_label = "高度可疑"
            elif belief.suspicion > 0.2:
                sus_label = "有些可疑"
            elif belief.suspicion > -0.2:
                sus_label = "不太确定"
            else:
                sus_label = "比较可信"

            lines.append(f"{pid}号玩家:")
            lines.append(f"  嫌疑度: {sus_label}({belief.suspicion:.2f})")

            if belief.suspected_role:
                lines.append(f"  推测角色: {belief.suspected_role}")

            if belief.reasons:
                lines.append("  理由:")
                for r in belief.reasons:
                    lines.append(f"    - {r}")

            if belief.confidence > 0:
                lines.append(f"  置信度: {belief.confidence:.0%}")

            lines.append("")

        return "\n".join(lines)
