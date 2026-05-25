"""女巫专属工具"""
from typing import List
from langchain_core.tools import StructuredTool


def create_witch_tools(memory, game_state_provider, inference_engine) -> List[StructuredTool]:

    def _check_potions() -> str:
        """查看剩余药水"""
        state = game_state_provider.get_state()
        has_save = state.get("witch_has_save", False)
        has_poison = state.get("witch_has_poison", False)
        return f"解药(救人): {'有' if has_save else '已用'}, 毒药(毒杀): {'有' if has_poison else '已用'}"

    check_potions = StructuredTool.from_function(
        func=_check_potions,
        name="check_potions",
        description="查看你剩余的药水情况（解药和毒药）。"
    )

    def _analyze_save_decision() -> str:
        """分析是否值得使用解药"""
        state = game_state_provider.get_state()
        killed = state.get("werewolf_kill_target")
        if killed is None:
            return "今晚没有人被袭击。"
        suspicion = memory.get_suspicion_levels()
        sus = suspicion.get(killed, 0)
        if sus > 35:
            return f"被杀的是{killed}号玩家，怀疑占比较高({sus:.0f}%)，可能不值得救。"
        elif sus < 15:
            return f"被杀的是{killed}号玩家，怀疑占比很低({sus:.0f}%)，很可能是重要好人，值得救！"
        else:
            return f"被杀的是{killed}号玩家，怀疑占比中性({sus:.0f}%)，自己判断。"

    analyze_save_decision = StructuredTool.from_function(
        func=_analyze_save_decision,
        name="analyze_save_decision",
        description="分析被杀的人是否值得使用解药救。"
    )

    def _analyze_poison_target() -> str:
        """分析毒杀目标"""
        state = game_state_provider.get_state()
        if not state.get("witch_has_poison", False):
            return "你已经没有毒药了。"
        alive = [p for p in state.get("alive_players", []) if p != memory.agent_id]
        suspicion = memory.get_suspicion_levels()
        sorted_targets = sorted(alive, key=lambda p: suspicion.get(p, 0), reverse=True)
        lines = []
        for pid in sorted_targets[:3]:
            sus = suspicion.get(pid, 0)
            lines.append(f"{pid}号玩家 (怀疑占比 {sus:.0f}%)")
        return "毒杀目标建议（按嫌疑度排序）:\n" + "\n".join(lines)

    analyze_poison_target = StructuredTool.from_function(
        func=_analyze_poison_target,
        name="analyze_poison_target",
        description="分析最佳毒杀目标。"
    )

    return [check_potions, analyze_save_decision, analyze_poison_target]
