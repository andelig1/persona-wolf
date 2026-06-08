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
    """信念追踪 — 对每个玩家形成结构化的信念

    支持信念审计（Belief Audit）：新证据出现时重新评估所有旧信念，
    自动降级过时或矛盾的判断，防止 Agent 固守错误推理。
    """

    def __init__(self):
        self.beliefs: Dict[int, PlayerBelief] = {}
        self.audit_log: List[str] = []  # 审计历史

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

    def audit_beliefs(self, new_evidence: List[dict], current_day: int,
                      alive_players: List[int] = None) -> List[str]:
        """信念审计 —— 新证据出现后重新评估所有旧信念

        触发时机：夜晚死亡公布后、投票出局公布身份后、预言家跳身份后

        Args:
            new_evidence: [{"type": "death_role_reveal", "player_id": 3, "role": "预言家"}, ...]
            current_day: 当前天数
            alive_players: 当前存活玩家列表

        Returns:
            修正记录列表（可注入 Agent 记忆）
        """
        revisions = []

        for pid, belief in list(self.beliefs.items()):
            old_confidence = belief.confidence
            old_suspicion = belief.suspicion

            # === 规则1：死亡角色揭晓 → 重新评估对此人的判断 ===
            for ev in new_evidence:
                if ev.get("player_id") != pid:
                    continue

                etype = ev.get("type", "")

                if etype == "death_role_reveal":
                    revealed_role = ev.get("role", "")
                    # 之前怀疑的神职其实是好人 → 大幅降级
                    if revealed_role in ["预言家", "女巫"] and belief.suspicion > 0.3:
                        belief.suspicion = max(-0.5, belief.suspicion - 0.8)
                        belief.confidence *= 0.3
                        belief.suspected_role = revealed_role
                        revisions.append(
                            f"⚡信念修正: 之前怀疑{pid}号(置信{old_confidence:.0%})，"
                            f"但ta是{revealed_role}→嫌疑从{old_suspicion:.2f}降至{belief.suspicion:.2f}"
                        )
                    # 确认是狼人 → 之前信任的判断是错的
                    elif revealed_role == "狼人" and belief.suspicion < -0.2:
                        belief.suspicion = 1.0
                        belief.confidence = 1.0
                        belief.suspected_role = "狼人"
                        revisions.append(
                            f"⚡信念修正: 之前信任{pid}号(置信{old_confidence:.0%})，"
                            f"但ta是狼人→更新为完全不可信"
                        )
                    # 该玩家已死 → 冻结信念
                    belief.confidence = 0.99
                    belief.last_updated_day = current_day

                elif etype == "seer_claim":
                    # 有人跳预言家 → 提升对此人的关注但不直接信任
                    if belief.suspicion > 0.2:
                        belief.confidence *= 0.8
                        revisions.append(
                            f"⚡信念微调: {pid}号跳预言家，之前怀疑度{old_suspicion:.2f}，"
                            f"暂不改变但降低置信度→{belief.confidence:.0%}"
                        )

            # === 规则2：信念超过1.5天未更新 → 衰减置信度 ===
            days_stale = current_day - belief.last_updated_day
            if belief.last_updated_day > 0 and days_stale > 1.5:
                decay = max(0.3, 0.75 ** days_stale)
                new_conf = belief.confidence * decay
                if abs(new_conf - belief.confidence) > 0.05:
                    revisions.append(
                        f"⏳信念衰减: 对{pid}号的判断已{days_stale:.0f}天未更新，"
                        f"置信度从{belief.confidence:.0%}衰减至{new_conf:.0%}"
                    )
                belief.confidence = new_conf

            # === 规则3：低置信度(<30%)但有强怀疑(>0.5) → 标记为"直觉" ===
            if belief.confidence < 0.3 and abs(belief.suspicion) > 0.5:
                old_sus = belief.suspicion
                # 向中性靠拢（不确定就别太绝对）
                belief.suspicion *= 0.7
                if abs(old_sus - belief.suspicion) > 0.1:
                    revisions.append(
                        f"⚡信念校准: 对{pid}号的判断置信度仅{belief.confidence:.0%}，"
                        f"但嫌疑度{old_sus:.2f}过于极端，已向中性靠拢→{belief.suspicion:.2f}"
                    )

        # 记录审计日志
        if revisions:
            self.audit_log.append(f"[第{current_day}天] 审计修正 {len(revisions)} 条")

        return revisions

    def decay_old_beliefs(self, current_day: int) -> List[str]:
        """简易版：仅执行时效衰减，不依赖新证据"""
        revisions = []
        for pid, belief in list(self.beliefs.items()):
            days_stale = current_day - belief.last_updated_day
            if belief.last_updated_day > 0 and days_stale > 2:
                decay = max(0.3, 0.8 ** days_stale)
                new_conf = belief.confidence * decay
                if abs(new_conf - belief.confidence) > 0.05:
                    revisions.append(
                        f"对{pid}号的信念已{days_stale}天未更新，置信度→{new_conf:.0%}"
                    )
                belief.confidence = new_conf
        return revisions
