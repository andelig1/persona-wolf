"""预言家专属工具"""
from typing import List
from langchain_core.tools import StructuredTool


def create_seer_tools(memory, game_state_provider, inference_engine) -> List[StructuredTool]:

    def _review_investigation_results() -> str:
        """回顾所有查验结果"""
        if not memory.role_knowledge:
            return "你还没有查验过任何人。"
        lines = []
        for pid, role in memory.role_knowledge.items():
            lines.append(f"{pid}号: {role}")
        return "你的查验记录:\n" + "\n".join(lines)

    review_investigation_results = StructuredTool.from_function(
        func=_review_investigation_results,
        name="review_investigation_results",
        description="回顾你过去的所有查验结果。"
    )

    def _decide_who_to_check() -> str:
        """建议下一个查验目标"""
        state = game_state_provider.get_state()
        alive = [p for p in state.get("alive_players", [])
                 if p != memory.agent_id and p not in memory.role_knowledge]
        if not alive:
            return "没有可查验的目标了。"
        suspicion = memory.get_suspicion_levels()
        sorted_targets = sorted(alive, key=lambda p: suspicion.get(p, 0), reverse=True)
        lines = []
        for pid in sorted_targets:
            sus = suspicion.get(pid, 0)
            lines.append(f"{pid}号 (嫌疑度: {sus:.1f})")
        return "查验目标建议（按嫌疑度排序）:\n" + "\n".join(lines)

    decide_who_to_check = StructuredTool.from_function(
        func=_decide_who_to_check,
        name="decide_who_to_check",
        description="根据嫌疑度建议下一个要查验的玩家。"
    )

    return [review_investigation_results, decide_who_to_check]
