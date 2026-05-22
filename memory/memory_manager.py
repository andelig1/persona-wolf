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

    def format_for_prompt(self, day: int = None, limit: int = None) -> str:
        """格式化为可注入prompt的文本 - 包含完整的游戏历史"""
        events = self.get_history(day=day, limit=limit)
        if not events:
            return "暂无记录。"
        
        # 按天数分组整理记忆
        day_groups = {}
        for e in events:
            event_day = e.metadata.get("day", 1)
            if event_day not in day_groups:
                day_groups[event_day] = {
                    "night_actions": [],
                    "speeches": [],
                    "votes": [],
                    "deaths": []
                }
            
            if e.event_type == "death":
                day_groups[event_day]["night_actions"].append(e)
            elif e.event_type == "kill":
                day_groups[event_day]["night_actions"].append(e)
            elif e.event_type == "speak":
                day_groups[event_day]["speeches"].append(e)
            elif e.event_type == "vote":
                day_groups[event_day]["votes"].append(e)
            elif e.event_type == "eliminate":
                day_groups[event_day]["deaths"].append(e)
        
        # 格式化输出（按天数顺序）
        lines = []
        for d in sorted(day_groups.keys()):
            group = day_groups[d]
            lines.append(f"\n=== 第{d}天 ===")
            
            # 夜晚行动结果
            if group["night_actions"]:
                lines.append("【夜晚】")
                for e in group["night_actions"]:
                    lines.append(f"  {e.content}")
            
            # 白天发言
            if group["speeches"]:
                lines.append("\n【白天发言】")
                for e in group["speeches"]:
                    lines.append(f"  {e.content}")
            
            # 投票记录
            if group["votes"]:
                lines.append("\n【投票】")
                for e in group["votes"]:
                    lines.append(f"  {e.content}")
            
            # 死亡信息
            if group["deaths"]:
                lines.append("\n【出局】")
                for e in group["deaths"]:
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
        """基于事件类型的启发式嫌疑度更新
        
        核心原则：
        1. 发言内容分析是主要依据（权重最高）
        2. 投票行为是辅助依据（权重次之）
        3. 死亡/出局是终结性依据
        """
        if event_type == "vote":
            target = metadata.get("target")
            if target is not None:
                self.update_suspicion(target, 0.03, "被投票")  # 降低权重
        
        elif event_type == "speak":
            speaker = metadata.get("player_id")
            if speaker is not None and speaker != self.agent_id:
                day = metadata.get("day", 1)
                round_num = metadata.get("round_num", 1)
                position = metadata.get("position", 1)
                total_speakers = metadata.get("total_speakers", 6)
                self._analyze_speech_for_suspicion(
                    speaker, content,
                    day=day, round_num=round_num,
                    position=position, total_speakers=total_speakers
                )
        
        elif event_type == "death":
            # 死亡玩家的嫌疑度归零（死人不会是狼）
            target = metadata.get("target")
            if target is not None:
                self.suspicion_levels[target] = 0.0
        
        elif event_type == "eliminate":
            # 被投票出局的玩家，根据身份调整嫌疑度
            target = metadata.get("player_id")
            if target is not None:
                # 如果被投票出局，说明大家认为他可疑
                self.update_suspicion(target, 0.2, "被投票出局")

    def _analyze_speech_for_suspicion(self, speaker: int, content: str,
                                       day: int = 1, round_num: int = 1,
                                       position: int = 1, total_speakers: int = 6) -> None:
        """深度分析发言内容，综合评估嫌疑度

        分析维度：
        1. 逻辑连贯性 - 是否有合理的推理链
        2. 信息价值 - 是否提供有价值的信息
        3. 行为一致性 - 是否与之前的发言/投票一致
        4. 角色声称 - 是否声称特殊身份
        5. 指控合理性 - 指控是否有依据

        新增考虑因素：
        - 发言轮次：第一天第一轮信息较少，降低期望
        - 发言位置：第一位置发言没有前人可参考，降低期望
        """
        content_lower = content.lower()
        score = 0.0

        is_early_game = (day == 1 and round_num == 1)
        is_first_speaker = (position == 1)

        early_game_len_threshold = 10 if (is_early_game and is_first_speaker) else 15
        early_game_accusation_threshold = 5 if (is_early_game and is_first_speaker) else 3

        # === 1. 逻辑连贯性分析 ===
        logical_indicators = ["因为", "所以", "理由是", "证据是", "我认为", "我的观点是"]
        contradiction_indicators = ["但是", "然而", "不过", "却"]

        if any(indicator in content_lower for indicator in logical_indicators):
            score -= 0.05
        if content_lower.count("？") > 2 or content_lower.count("。") == 0:
            score += 0.03

        # === 2. 信息价值分析 ===
        info_indicators = ["昨晚", "查验", "查杀", "金水", "救人", "毒", "刀"]
        if any(indicator in content_lower for indicator in info_indicators):
            score -= 0.08
        if len(content) < early_game_len_threshold:
            if not (is_early_game and is_first_speaker):
                score += 0.05

        # === 3. 指控行为分析 ===
        accusation_words = ["狼人", "狼", "可疑", "怀疑", "投", "出", "票", "出局"]
        accusation_count = sum(content_lower.count(word) for word in accusation_words)

        if accusation_count >= early_game_accusation_threshold:
            score += 0.08
        elif accusation_count == 1:
            score += 0.01

        # === 4. 角色声称分析 ===
        role_claims = ["预言家", "女巫", "神职", "金水", "查杀"]
        if any(claim in content_lower for claim in role_claims):
            if "预言家" in content_lower:
                if "查验" in content_lower or "金水" in content_lower or "查杀" in content_lower:
                    score += 0.01
                else:
                    if is_early_game:
                        score += 0.03
                    else:
                        score += 0.08

        # === 5. 跟风行为分析 ===
        follow_indicators = ["我同意", "我也觉得", "跟票", "跟着投"]
        if any(indicator in content_lower for indicator in follow_indicators):
            if not is_first_speaker:
                score += 0.02

        # === 6. 攻击性分析 ===
        aggressive_words = ["肯定是", "绝对是", "必须投", "赶紧出"]
        if any(word in content_lower for word in aggressive_words):
            score += 0.05

        # === 7. 矛盾检测 ===
        contradiction_count = sum(content_lower.count(word) for word in contradiction_indicators)
        if contradiction_count >= 2:
            score += 0.06

        if score != 0:
            self.update_suspicion(speaker, max(-0.15, min(0.15, score)), "发言分析")
