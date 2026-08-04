"""胜率统计模块 - 记录与聚合每局游戏结果，与人格挂钩"""
from .stats_recorder import StatsRecorder, get_stats_recorder

__all__ = ["StatsRecorder", "get_stats_recorder"]
