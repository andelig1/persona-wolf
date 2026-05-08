"""村民策略"""
import random
from typing import List, Optional, Dict


class VillagerStrategy:
    """村民角色的启发式策略"""

    def suggest_vote(self, memory, alive_players: list,
                     wolf_teammates: list = None) -> Optional[int]:
        """投票：投嫌疑度最高的"""
        candidates = [p for p in alive_players if p != memory.agent_id]
        if not candidates:
            return None
        suspicion = memory.get_suspicion_levels()
        return max(candidates, key=lambda p: suspicion.get(p, 0))

    def suggest_night_action(self, memory, alive_players: list,
                             kwargs: dict = None) -> Optional[Dict]:
        """村民没有夜晚行动"""
        return None

    def generate_speech(self, memory, game_state: dict, personality: str) -> str:
        """回退发言"""
        fallbacks = {
            "rational": "大家理性分析一下，别乱投。",
            "aggressive": "谁在划水？站出来说清楚！",
            "hesitant": "我...也不太确定谁可疑...",
            "follower": "前面说的有道理，我也这么想。",
            "slacker": "嗯...都行吧...",
        }
        return fallbacks.get(personality, "听听大家怎么说。")

    def get_role_guidance(self) -> str:
        return ("你是普通村民，没有特殊技能。"
                "通过发言和投票找出狼人，注意分析每个人的逻辑漏洞。"
                "你的投票很关键，不要浪费。")
