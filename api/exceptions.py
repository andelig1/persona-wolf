"""API 异常定义"""


class GameError(Exception):
    """游戏基础异常"""
    pass


class GameNotFoundError(GameError):
    """游戏不存在"""
    pass


class InvalidPhaseError(GameError):
    """无效的游戏阶段"""
    pass


class InvalidPlayerError(GameError):
    """无效的玩家"""
    pass


class InvalidActionError(GameError):
    """无效的动作"""
    pass


class GameAlreadyOverError(GameError):
    """游戏已结束"""
    pass
