"""狼人策略"""
import random
from typing import List, Optional, Dict


class WerewolfStrategy:
    """狼人角色的启发式策略，LLM失败时的回退"""

    def suggest_vote(self, memory, alive_players: list,
                     wolf_teammates: list = None) -> Optional[int]:
        """投票：避开队友，优先投威胁大的好人"""
        wolf_teammates = wolf_teammates or []
        candidates = [p for p in alive_players
                      if p != memory.agent_id and p not in wolf_teammates]
        if not candidates:
            return None
        suspicion = memory.get_suspicion_levels()
        # 狼人想投掉对自己有威胁的人（怀疑自己的人）
        # suspicion为负表示该玩家怀疑我方
        threatened_by = [p for p in candidates if suspicion.get(p, 0) < -0.2]
        if threatened_by:
            return random.choice(threatened_by)
        return random.choice(candidates)

    def suggest_night_action(self, memory, alive_players: list,
                             kwargs: dict = None) -> Optional[Dict]:
        """夜晚击杀：优先预言家 > 激进指控者 > 随机"""
        kwargs = kwargs or {}
        wolf_teammates = kwargs.get("wolf_teammates", [])
        candidates = [p for p in alive_players
                      if p != memory.agent_id and p not in wolf_teammates]
        if not candidates:
            return None
        # 优先杀已查验出狼人的预言家
        for pid, role in memory.role_knowledge.items():
            if pid in candidates and role == "预言家":
                return {"type": "kill", "target": pid}
        # 杀对自己威胁最大的人
        suspicion = memory.get_suspicion_levels()
        threatened = [p for p in candidates if suspicion.get(p, 0) < -0.3]
        if threatened:
            return {"type": "kill", "target": random.choice(threatened)}
        return {"type": "kill", "target": random.choice(candidates)}

    def generate_speech(self, memory, game_state: dict, personality: str) -> str:
        """LLM失败时的回退发言"""
        fallbacks = {
            "rational": "我觉得大家冷静想想，目前信息还不够下结论。",
            "agitative": "2号你解释一下你刚才说的！",
            "conservative": "我...也不太确定，先听听大家怎么说吧...",
            "impulsive": "嗯，前面说得对，我也这么觉得。",
            "slacker": "嗯...随便吧。",
        }
        return fallbacks.get(personality, "先听听大家怎么说。")

    def get_role_guidance(self) -> str:
        """角色提示（注入system prompt）"""
        return ("你的真实身份是狼人。夜晚你和同伴会一起杀一个人。"
                "白天你要装作是个普通村民，像其他人一样分析怀疑对象。"
                "投票时别投自己的狼同伴。发言时可以悄悄把注意力引到好人那边。"
                "注意：夜晚不能空刀，不能杀自己的狼同伴。")
