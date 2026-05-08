"""发言管理器

管理白天阶段的发言流程
"""
from typing import List, Dict


class DialogueManager:
    """管理白天阶段的发言顺序和收集"""

    def __init__(self):
        pass

    def get_speaking_order(self, alive_players: list,
                           strategy: str = "sequential") -> list:
        """返回发言顺序"""
        if strategy == "sequential":
            return alive_players.copy()
        elif strategy == "random":
            import random
            order = alive_players.copy()
            random.shuffle(order)
            return order
        return alive_players.copy()

    def collect_speeches(self, agents: dict, alive_players: list,
                         human_player_id: int = 0,
                         human_speech: str = None) -> list:
        """收集所有存活玩家的发言"""
        speeches = []
        for pid in self.get_speaking_order(alive_players):
            agent = agents[pid]
            if pid == human_player_id:
                content = human_speech or ""
            else:
                content = agent.speak({})
            speeches.append({"player_id": pid, "content": content})
        return speeches
