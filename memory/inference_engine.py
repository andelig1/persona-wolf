"""推理引擎

LLM驱动的分析能力，供Agent工具在ReAct推理中调用
"""
from typing import Optional, Tuple, List, Dict


class InferenceEngine:
    """推理引擎 - 提供发言分析、投票模式分析等能力"""

    def __init__(self, llm_client=None):
        self._llm_client = llm_client

    def _get_llm(self):
        if self._llm_client is None:
            from utils.llm_client import get_llm_client
            self._llm_client = get_llm_client()
        return self._llm_client

    def analyze_speech(self, speech: str, speaker_id: int,
                       context: str = "") -> str:
        """分析玩家发言是否可疑

        Args:
            speech: 发言内容
            speaker_id: 发言者ID
            context: 额外上下文
        Returns:
            分析结论文本
        """
        try:
            llm = self._get_llm()
            messages = [
                {"role": "system", "content": "你是狼人杀分析助手。只根据发言原文分析，不要推测原文没有的内容。如果发言信息量少就说'信息不足难以判断'。回答30字以内。"},
                {"role": "user", "content": f"{speaker_id}号玩家说：{speech}\n{context}\n分析这段发言（不要编造原文没有的细节）："},
            ]
            return llm.chat(messages, temperature=0.3)
        except Exception:
            return f"无法分析{speaker_id}号的发言。"

    def analyze_voting_pattern(self, vote_history: List[Dict],
                               player_id: int) -> str:
        """分析玩家的投票模式"""
        player_votes = [v for v in vote_history if v.get("voter") == player_id]
        if not player_votes:
            return f"{player_id}号没有投票记录。"
        try:
            llm = self._get_llm()
            vote_text = "\n".join(
                f"第{v.get('day', '?')}天投了{v.get('target', '?')}号"
                for v in player_votes
            )
            messages = [
                {"role": "system", "content": "你是狼人杀分析师。根据投票记录判断玩家的阵营倾向，50字以内。"},
                {"role": "user", "content": f"{player_id}号的投票记录：\n{vote_text}\n分析其投票模式。"},
            ]
            return llm.chat(messages, temperature=0.3)
        except Exception:
            return f"{player_id}号的投票模式难以判断。"

    def suggest_suspicion(self, memory, target_id: int) -> Tuple[float, str]:
        """建议对某玩家的嫌疑度"""
        suspicion = memory.get_suspicion_levels().get(target_id, 0.0)
        if suspicion > 0.5:
            return suspicion, f"{target_id}号高度可疑"
        elif suspicion > 0.2:
            return suspicion, f"{target_id}号有些可疑"
        elif suspicion > -0.2:
            return suspicion, f"{target_id}号嫌疑不大"
        else:
            return suspicion, f"{target_id}号比较可信"
