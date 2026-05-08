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
        """夜晚决策：解药/毒药"""
        kwargs = kwargs or {}
        werewolf_target = kwargs.get("werewolf_target")
        has_save = kwargs.get("has_save", True)
        has_poison = kwargs.get("has_poison", True)

        # 有解药且有人被杀：根据嫌疑度决定是否救
        if has_save and werewolf_target is not None:
            suspicion = memory.get_suspicion_levels()
            sus = suspicion.get(werewolf_target, 0)
            # 被杀的人嫌疑低就救
            if sus < 0.3:
                return {"type": "save", "target": werewolf_target}

        # 有毒药：毒嫌疑度最高的
        if has_poison:
            candidates = [p for p in alive_players if p != memory.agent_id]
            if candidates:
                suspicion = memory.get_suspicion_levels()
                most_sus = max(candidates, key=lambda p: suspicion.get(p, 0))
                if suspicion.get(most_sus, 0) > 0.5:
                    return {"type": "poison", "target": most_sus}

        return None

    def generate_speech(self, memory, game_state: dict, personality: str) -> str:
        """回退发言"""
        fallbacks = {
            "rational": "大家注意分析发言逻辑，别被带节奏。",
            "aggressive": "4号你到底在藏什么？说清楚！",
            "hesitant": "我可能知道一些信息...但不太确定该不该说...",
            "follower": "对对，我也这么想的。",
            "slacker": "嗯...随便吧...",
        }
        return fallbacks.get(personality, "大家注意分析。")

    def get_role_guidance(self) -> str:
        return ("你是女巫！你有一瓶解药（可以救被杀的人）和一瓶毒药（可以毒杀一个人），"
                "每瓶只能用一次。晚上你会知道谁被狼人杀了。"
                "解药要留给重要的好人，毒药要毒最可疑的人。"
                "注意：第一晚通常可以自救，之后要谨慎使用。")
