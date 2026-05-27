"""预言家策略"""
import random
from typing import List, Optional, Dict


class SeerStrategy:
    """预言家角色的启发式策略"""

    def suggest_vote(self, memory, alive_players: list,
                     wolf_teammates: list = None) -> Optional[int]:
        """投票：优先投已查验的狼人，否则投最可疑的"""
        candidates = [p for p in alive_players if p != memory.agent_id]
        if not candidates:
            return None
        # 优先投已确认的狼人
        for pid, role in memory.role_knowledge.items():
            if role == "狼人" and pid in candidates:
                return pid
        # 投嫌疑度最高的
        suspicion = memory.get_suspicion_levels()
        return max(candidates, key=lambda p: suspicion.get(p, 0))

    def suggest_night_action(self, memory, alive_players: list,
                             kwargs: dict = None) -> Optional[Dict]:
        """夜晚查验：第一晚随机选择，之后优先查最可疑的未查验玩家"""
        kwargs = kwargs or {}
        day = kwargs.get("day", 1)
        
        candidates = [p for p in alive_players
                      if p != memory.agent_id and p not in memory.role_knowledge]
        if not candidates:
            return None
        
        # 第一晚：随机选择查验目标
        if day == 1:
            target = random.choice(candidates)
        # 非第一晚：优先查嫌疑度最高的
        else:
            suspicion = memory.get_suspicion_levels()
            target = max(candidates, key=lambda p: suspicion.get(p, 0))
        
        return {"type": "check", "target": target}

    def generate_speech(self, memory, game_state: dict, personality: str) -> str:
        """回退发言"""
        fallbacks = {
            "rational": "我有些线索，但还不太确定，先观察一下。",
            "agitative": "3号你很可疑！我手上有信息！",
            "conservative": "我...可能知道点什么...但不确定该不该说...",
            "impulsive": "大家觉得谁可疑？我也想听听意见。",
            "slacker": "嗯...不太好说...",
        }
        return fallbacks.get(personality, "我再观察一下。")

    def get_role_guidance(self) -> str:
        return ("你的真实身份是预言家。每晚可以偷偷查验一个人的身份，知道他是好人还是狼人。"
                "你的查验结果很重要，但别太早暴露自己是预言家——狼人会优先杀你。"
                "看准时机再公布你的查验结果。")
