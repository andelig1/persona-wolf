"""狼人专属工具"""
from typing import List
from langchain_core.tools import StructuredTool


def create_werewolf_tools(memory, game_state_provider, inference_engine) -> List[StructuredTool]:

    def _discuss_with_teammate() -> str:
        """查看狼人队友信息"""
        state = game_state_provider.get_state()
        wolves = [pid for pid, role in state.get("player_roles", {}).items()
                  if role == "狼人" and pid in state.get("alive_players", [])
                  and pid != memory.agent_id]
        if not wolves:
            return "你没有存活的狼人队友了，独自行动。"
        return f"你的狼人队友是: {wolves}号。记住不要投票给队友！"

    discuss_with_teammate = StructuredTool.from_function(
        func=_discuss_with_teammate,
        name="discuss_with_teammate",
        description="查看你的狼人队友是谁，商量对策。"
    )

    def _analyze_kill_priority() -> str:
        """分析击杀优先级"""
        state = game_state_provider.get_state()
        alive = state.get("alive_players", [])
        wolf_teammates = [pid for pid, role in state.get("player_roles", {}).items()
                          if role == "狼人" and pid in alive]
        candidates = [p for p in alive if p not in wolf_teammates]
        if not candidates:
            return "没有可击杀的目标。"
        suspicion = memory.get_suspicion_levels()
        lines = []
        for pid in candidates:
            sus = suspicion.get(pid, 0)
            tag = "对你有威胁" if sus < -0.2 else "一般目标"
            lines.append(f"{pid}号 (嫌疑度: {sus:.1f}, {tag})")
        return "击杀优先级:\n" + "\n".join(lines)

    analyze_kill_priority = StructuredTool.from_function(
        func=_analyze_kill_priority,
        name="analyze_kill_priority",
        description="分析击杀优先级，找出对你威胁最大的好人玩家。"
    )

    return [discuss_with_teammate, analyze_kill_priority]
