"""工具系统

为ReAct Agent提供可调用的工具
"""
from typing import List
from langchain_core.tools import StructuredTool

from .common_tools import create_common_tools
from .werewolf_tools import create_werewolf_tools
from .seer_tools import create_seer_tools
from .witch_tools import create_witch_tools
from .villager_tools import create_villager_tools


def create_tools_for_role(role: str, memory, game_state_provider,
                          inference_engine) -> List[StructuredTool]:
    """根据角色创建完整工具集（通用工具 + 角色专属工具）"""
    common = create_common_tools(memory, game_state_provider, inference_engine)
    role_tool_map = {
        "狼人": create_werewolf_tools,
        "预言家": create_seer_tools,
        "女巫": create_witch_tools,
        "村民": create_villager_tools,
    }
    factory = role_tool_map.get(role, create_villager_tools)
    return common + factory(memory, game_state_provider, inference_engine)


__all__ = ["create_tools_for_role"]
