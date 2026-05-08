"""动态发言顺序

根据游戏动态决定发言顺序
"""
from typing import List, Dict
import random


class DynamicSpeakerOrder:
    """动态发言顺序管理器"""

    def get_order(self, alive_players: list, suspicion_levels: dict = None,
                  strategy: str = "sequential") -> list:
        """返回发言顺序

        strategy:
        - "sequential": 按ID顺序
        - "random": 随机顺序
        - "suspicion": 最可疑的人最后发言（压力大）
        """
        if strategy == "sequential" or not suspicion_levels:
            return alive_players.copy()
        elif strategy == "random":
            order = alive_players.copy()
            random.shuffle(order)
            return order
        elif strategy == "suspicion":
            return sorted(alive_players,
                          key=lambda p: suspicion_levels.get(p, 0))
        return alive_players.copy()
