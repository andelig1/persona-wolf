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
            "aggressive": "3号你很可疑！我手上有信息！",
            "hesitant": "我...可能知道点什么...但不确定该不该说...",
            "follower": "大家觉得谁可疑？我也想听听意见。",
            "slacker": "嗯...不太好说...",
        }
        return fallbacks.get(personality, "我再观察一下。")

    def get_role_guidance(self) -> str:
        return ("你是预言家！每晚可以查验一个人的真实身份。"
                "你的查验结果非常重要，但要注意保护自己——"
                "如果过早暴露预言家身份，狼人会优先杀你。"
                "你可以选择时机跳预言家公布查验结果。")
