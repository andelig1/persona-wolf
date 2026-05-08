"""策略模块

每个角色一个策略类，提供启发式回退逻辑和角色提示
"""
from .werewolf_strategy import WerewolfStrategy
from .seer_strategy import SeerStrategy
from .villager_strategy import VillagerStrategy
from .witch_strategy import WitchStrategy

STRATEGY_MAP = {
    "狼人": WerewolfStrategy,
    "预言家": SeerStrategy,
    "村民": VillagerStrategy,
    "女巫": WitchStrategy,
}


def get_strategy(role: str):
    """获取角色策略实例"""
    cls = STRATEGY_MAP.get(role, VillagerStrategy)
    return cls()


__all__ = [
    "WerewolfStrategy", "SeerStrategy",
    "VillagerStrategy", "WitchStrategy",
    "get_strategy",
]
