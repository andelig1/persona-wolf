"""村民专属工具"""
from typing import List
from langchain_core.tools import StructuredTool


def create_villager_tools(memory, game_state_provider, inference_engine) -> List[StructuredTool]:

    def _identify_suspicious_players() -> str:
        """找出最可疑的玩家"""
        state = game_state_provider.get_state()
        alive = [p for p in state.get("alive_players", []) if p != memory.agent_id]
        if not alive:
            return "没有其他存活玩家。"
        suspicion = memory.get_suspicion_levels()
        sorted_players = sorted(alive, key=lambda p: suspicion.get(p, 0), reverse=True)
        lines = []
        for pid in sorted_players:
            sus = suspicion.get(pid, 0)
            if sus > 35:
                label = "高度可疑"
            elif sus > 20:
                label = "有些可疑"
            elif sus > 10:
                label = "不太确定"
            else:
                label = "比较可信"
            lines.append(f"{pid}号玩家 ({label}, 怀疑占比 {sus:.0f}%)")
        return "玩家可疑程度:\n" + "\n".join(lines)

    identify_suspicious_players = StructuredTool.from_function(
        func=_identify_suspicious_players,
        name="identify_suspicious_players",
        description="根据你的记忆和分析找出最可疑的玩家。"
    )

    return [identify_suspicious_players]
