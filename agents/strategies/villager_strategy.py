"""村民策略"""
import random
from typing import List, Optional, Dict


class VillagerStrategy:
    """村民角色的启发式策略"""

    def suggest_vote(self, memory, alive_players: list,
                     wolf_teammates: list = None) -> Optional[int]:
        """投票：加权随机（而非确定性的max），避免所有村民投同一个人"""
        candidates = [p for p in alive_players if p != memory.agent_id]
        if not candidates:
            return None
        suspicion = memory.get_suspicion_levels()
        # 加权随机：嫌疑度越高的玩家被选中的概率越大，但不保证一定选中
        # 转换为正权重（suspicion 可能是负数）
        weights = []
        for p in candidates:
            s = suspicion.get(p, 0)
            # 将 [-1, 1] 映射到 [0.1, 2.0]，负数也有正权重
            w = max(0.1, s + 1.1)
            weights.append(w)
        total = sum(weights)
        if total <= 0:
            return random.choice(candidates)
        # 加权随机选择
        r = random.random() * total
        cumulative = 0
        for i, p in enumerate(candidates):
            cumulative += weights[i]
            if r <= cumulative:
                return p
        return candidates[-1]  # fallback

    def suggest_night_action(self, memory, alive_players: list,
                             kwargs: dict = None) -> Optional[Dict]:
        """村民没有夜晚行动"""
        return None

    def generate_speech(self, memory, game_state: dict, personality: str) -> str:
        """回退发言"""
        fallbacks = {
            "rational": "大家理性分析一下，别乱投。",
            "agitative": "谁在划水？站出来说清楚！",
            "conservative": "我...也不太确定谁可疑...",
            "impulsive": "前面说的有道理，我也这么想。",
            "slacker": "嗯...都行吧...",
        }
        return fallbacks.get(personality, "听听大家怎么说。")

    def get_role_guidance(self) -> str:
        return ("你的真实身份是普通村民，没有特殊能力。"
                "你只能靠听发言、看投票记录来找出狼人。"
                "你的每一票都很重要——别随便跟风投。")
