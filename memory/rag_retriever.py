"""RAG 精检索器 —— 用相关记忆替代全量历史注入

核心思路：当前 format_for_prompt() 把全部历史一次注入 Prompt，大几百行文本
导致 LLM 注意力稀释、容易张冠李戴。RAGRetriever 改为"只注入最相关的 top-K 条"。

检索策略（轻量，不依赖 embedding 模型）：
  1. 关键词重叠打分 —— 玩家编号、天数、事件类型匹配
  2. 时效性加权 —— 越近的事件权重越高
  3. 重要度加权 —— 死亡/查验 > 发言/投票 > 阶段切换
  4. LLM 相关性终判（可选）—— 对于关键查询，由 LLM 判断哪条记忆最相关
"""
import re
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass, field
from .memory_manager import MemoryEntry


@dataclass
class ScoredEntry:
    """带分数的记忆条目"""
    entry: MemoryEntry
    score: float
    match_reasons: List[str] = field(default_factory=list)


class RAGRetriever:
    """轻量 RAG 检索器

    为 AgentMemory 增加精检索能力：给定查询上下文（如"第3天发言，存活1,3,5,6号"），
    返回最相关的 top-K 条记忆，而非全部历史。

    使用方式：
        retriever = RAGRetriever(agent_memory)
        relevant = retriever.retrieve("现在是第3天发言，怀疑3号", top_k=5)
    """

    # 事件类型基础权重（重要度）
    EVENT_WEIGHTS = {
        "death": 1.0,
        "eliminate": 0.95,
        "check_result": 0.9,
        "kill": 0.85,
        "speak": 0.5,
        "vote": 0.6,
        "system": 0.2,
        "phase_change": 0.1,
    }

    def __init__(self, agent_memory):
        """绑定到某个 Agent 的私有记忆"""
        self.memory = agent_memory

    def retrieve(self, query: str, top_k: int = 5,
                 day: int = None, event_type: str = None,
                 exclude_self_speech: bool = True,
                 agent_id: int = None) -> List[MemoryEntry]:
        """混合检索：关键词重叠 + 时效性 + 重要度

        Args:
            query: 当前上下文描述（如"第3天第1轮发言，存活1,3,5,6号"）
            top_k: 返回条数
            day: 可选，只检索指定天数
            event_type: 可选，只检索指定事件类型
            exclude_self_speech: 是否排除自己的发言（避免循环引用）
            agent_id: 当前 Agent 的 ID（用于排除自己发言）

        Returns:
            按相关性排序的记忆列表
        """
        # Step 1: 从查询中提取关键词
        query_entities = self._extract_entities(query)

        # Step 2: 对每条记忆打分
        scored: List[ScoredEntry] = []
        for entry in self.memory.events:
            # 结构化过滤
            if day is not None and entry.metadata.get("day") != day:
                continue
            if event_type and entry.event_type != event_type:
                continue
            if exclude_self_speech and agent_id is not None:
                if entry.event_type == "speak" and entry.metadata.get("player_id") == agent_id:
                    continue

            score, reasons = self._score_entry(entry, query_entities)
            if score > 0:
                scored.append(ScoredEntry(entry, score, reasons))

        # Step 3: 按分数降序排列
        scored.sort(key=lambda x: -x.score)

        return [s.entry for s in scored[:top_k]]

    def retrieve_for_verification(self, claim: str, top_k: int = 3) -> Tuple[List[MemoryEntry], str]:
        """事实核查专用检索：在记忆中搜索支撑或反驳 claim 的证据

        Args:
            claim: 待核查的陈述（如"3号在第2天投了1号"）
            top_k: 返回条数

        Returns:
            (相关记忆列表, 检索摘要)
        """
        claim_entities = self._extract_entities(claim)

        # 对 claim 中的每个实体做精确匹配检索
        player_ids = claim_entities.get("player_ids", [])
        days = claim_entities.get("days", [])

        scored: List[ScoredEntry] = []
        for entry in self.memory.events:
            # 精确匹配：claim 中的玩家编号和天数
            entry_pid = entry.metadata.get("player_id", 0)
            entry_target = entry.metadata.get("target", 0)
            entry_day = entry.metadata.get("day", 0)

            score = 0.0
            reasons = []

            # 玩家匹配
            for pid in player_ids:
                if entry_pid == pid or entry_target == pid:
                    score += 0.4
                    reasons.append(f"player_match:{pid}")

            # 天数匹配
            if days and entry_day in days:
                score += 0.3
                reasons.append(f"day_match:{entry_day}")

            # 事件类型匹配（claim 中提到"投"→看重 vote 事件）
            claim_lower = claim.lower()
            if any(w in claim_lower for w in ["投", "票", "vote"]) and entry.event_type == "vote":
                score += 0.2
                reasons.append("type:vote")
            if any(w in claim_lower for w in ["说", "发言", "speak", "话"]) and entry.event_type == "speak":
                score += 0.2
                reasons.append("type:speak")
            if any(w in claim_lower for w in ["死", "杀", "刀", "kill"]) and entry.event_type in ("death", "kill"):
                score += 0.25
                reasons.append("type:death")

            # 内容关键词重叠
            content_overlap = self._keyword_overlap(claim, entry.content)
            score += content_overlap * 0.2
            if content_overlap > 0.3:
                reasons.append(f"content_overlap:{content_overlap:.2f}")

            # 重要度加权
            base_weight = self.EVENT_WEIGHTS.get(entry.event_type, 0.3)
            score *= base_weight

            if score > 0.15:
                scored.append(ScoredEntry(entry, score, reasons))

        scored.sort(key=lambda x: -x.score)
        entries = [s.entry for s in scored[:top_k]]

        # 生成检索摘要供 self-reflection 使用
        if entries:
            summary_parts = []
            for e in entries:
                day = e.metadata.get("day", "?")
                summary_parts.append(f"[第{day}天][{e.event_type}] {e.content}")
            summary = "\n".join(summary_parts)
        else:
            summary = "未找到相关记录——这个说法在记忆中找不到依据。"

        return entries, summary

    def retrieve_context_for_speak(self, game_state: dict, agent_id: int,
                                   day: int, top_k: int = 8) -> List[MemoryEntry]:
        """发言前的专用检索：构建当前发言最需要的上下文

        策略：
        - 今天的发言 + 投票（最重要）
        - 昨天的死亡事件
        - 自己的策略笔记和信念
        - 排除自己今天的发言（避免循环）
        """
        alive = game_state.get("alive_players", [])
        query = f"第{day}天 存活玩家:{alive} 发言阶段"

        # 1. 核心检索：今天的事件
        today_entries = self.retrieve(
            query, top_k=top_k, day=day,
            exclude_self_speech=True, agent_id=agent_id
        )

        # 2. 补充：昨天的关键事件（死亡、查验）
        yesterday = self.retrieve(
            f"第{day-1}天 死亡 查验",
            top_k=3, day=day - 1,
            event_type=None
        )

        # 合并去重
        seen = set()
        result = []
        for entry in today_entries + yesterday:
            key = (entry.event_type, entry.content[:50])
            if key not in seen:
                seen.add(key)
                result.append(entry)

        return result[:top_k]

    def format_retrieved_context(self, entries: List[MemoryEntry]) -> str:
        """将检索到的记忆格式化为可注入 Prompt 的精简文本"""
        if not entries:
            return "暂无相关记录。"

        # 按天数分组
        groups: Dict[int, List[MemoryEntry]] = {}
        for e in entries:
            d = e.metadata.get("day", 1)
            groups.setdefault(d, []).append(e)

        lines = []
        for d in sorted(groups.keys()):
            lines.append(f"=== 第{d}天 ===")
            for e in groups[d]:
                et = e.event_type
                label = {"speak": "发言", "vote": "投票", "death": "死亡",
                         "kill": "击杀", "eliminate": "出局",
                         "check_result": "查验", "system": "系统"}.get(et, et)
                lines.append(f"  [{label}] {e.content}")
            lines.append("")

        lines.append("--- 以上为精选记录，发言时如实引用，勿编造。 ---")
        return "\n".join(lines)

    # ============ 内部方法 ============

    def _extract_entities(self, text: str) -> dict:
        """从文本中提取实体"""
        text = str(text)
        entities = {
            "player_ids": [],
            "days": [],
        }
        # 提取玩家编号
        for m in re.finditer(r'(\d+)\s*号', text):
            pid = int(m.group(1))
            if 0 < pid < 100 and pid not in entities["player_ids"]:
                entities["player_ids"].append(pid)
        # 提取天数
        for m in re.finditer(r'第\s*(\d+)\s*天', text):
            d = int(m.group(1))
            if d not in entities["days"]:
                entities["days"].append(d)
        return entities

    def _score_entry(self, entry: MemoryEntry, query_entities: dict) -> Tuple[float, List[str]]:
        """对单条记忆打分"""
        score = 0.0
        reasons = []

        entry_text = entry.content
        entry_pid = entry.metadata.get("player_id", 0)
        entry_target = entry.metadata.get("target", 0)
        entry_day = entry.metadata.get("day", 0)

        # 1. 实体匹配
        for pid in query_entities.get("player_ids", []):
            if entry_pid == pid or entry_target == pid:
                score += 0.25
                reasons.append(f"pid:{pid}")

        # 2. 天数匹配
        for d in query_entities.get("days", []):
            if entry_day == d:
                score += 0.2
                reasons.append(f"day:{d}")

        # 3. 关键词重叠
        content_lower = entry_text.lower()
        query_lower = " ".join(str(v) for v in query_entities.values())
        overlap = self._keyword_overlap(query_lower, content_lower)
        score += overlap * 0.15
        if overlap > 0.3:
            reasons.append(f"kw:{overlap:.2f}")

        # 4. 时效性加权（越近越高）
        recency = min(entry_day / max(1, entry_day + 2), 1.0)
        score *= (0.5 + 0.5 * recency)

        # 5. 事件类型重要度
        base_weight = self.EVENT_WEIGHTS.get(entry.event_type, 0.3)
        score *= base_weight

        return score, reasons

    @staticmethod
    def _keyword_overlap(text_a: str, text_b: str) -> float:
        """计算两段文本的关键词重叠率（简化版 TF-IDF）"""
        # 提取中文/英文关键词（2字以上）
        words_a = set(re.findall(r'[一-鿿]{2,}|\d+|[a-zA-Z]+', str(text_a)))
        words_b = set(re.findall(r'[一-鿿]{2,}|\d+|[a-zA-Z]+', str(text_b)))
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        return len(intersection) / min(len(words_a), len(words_b))
