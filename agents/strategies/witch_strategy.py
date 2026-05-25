"""女巫策略"""
import random
from typing import List, Optional, Dict


class WitchStrategy:
    """女巫角色的启发式策略"""

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
        """夜晚决策：解药/毒药
        
        策略：
        1. 救人：不一定救，根据嫌疑度和随机性决定
        2. 毒人：毒嫌疑度最高的，但需要达到一定阈值
        """
        kwargs = kwargs or {}
        werewolf_target = kwargs.get("werewolf_target")
        has_save = kwargs.get("has_save", True)
        has_poison = kwargs.get("has_poison", True)
        day = kwargs.get("day", 1)

        # 有解药且有人被杀：不一定救，根据情况决定
        if has_save and werewolf_target is not None:
            suspicion = memory.get_suspicion_levels()
            sus = suspicion.get(werewolf_target, 0)
            
            # 决策逻辑：
            # 1. 如果目标是自己，优先救（高概率）
            if werewolf_target == memory.agent_id:
                # 第一晚自救概率稍低（防止被狼人自刀骗药）
                if day == 1:
                    if random.random() < 0.7:  # 70%概率自救
                        return {"type": "save", "target": werewolf_target}
                # 之后每晚被刀都高概率自救
                else:
                    if random.random() < 0.95:  # 95%概率自救
                        return {"type": "save", "target": werewolf_target}
            # 2. 如果目标嫌疑很低（好人可能性大），较高概率救（50%）
            elif sus < 0.2:
                if random.random() < 0.5:
                    return {"type": "save", "target": werewolf_target}
            # 3. 如果目标嫌疑中等，较低概率救（20%）
            elif sus < 0.5:
                if random.random() < 0.2:
                    return {"type": "save", "target": werewolf_target}
            # 4. 嫌疑很高则不救

        # 有毒药：毒嫌疑度最高的，但需要达到一定阈值且有一定随机性
        if has_poison:
            candidates = [p for p in alive_players if p != memory.agent_id]
            if candidates:
                suspicion = memory.get_suspicion_levels()
                most_sus = max(candidates, key=lambda p: suspicion.get(p, 0))
                # 嫌疑度高且随机决定使用毒药
                if suspicion.get(most_sus, 0) > 0.5 and random.random() < 0.7:
                    return {"type": "poison", "target": most_sus}

        return None

    def generate_speech(self, memory, game_state: dict, personality: str) -> str:
        """回退发言"""
        fallbacks = {
            "rational": "大家注意分析发言逻辑，别被带节奏。",
            "agitative": "4号你到底在藏什么？说清楚！",
            "conservative": "我可能知道一些信息...但不太确定该不该说...",
            "impulsive": "对对，我也这么想的。",
            "slacker": "嗯...随便吧...",
        }
        return fallbacks.get(personality, "大家注意分析。")

    def get_role_guidance(self) -> str:
        return ("你的真实身份是女巫。你有一瓶解药和一瓶毒药，各只能用一次。"
                "晚上你会知道狼人杀了谁，你可以选择救他或者毒别人。"
                "解药留给重要的好人，毒药毒最可疑的家伙。第一晚一般能自救。")
