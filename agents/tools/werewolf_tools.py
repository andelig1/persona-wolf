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
        return f"你的狼人队友是: {', '.join([f'{w}号玩家' for w in wolves])}。记住不要投票给队友！"

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
        # 只对候选人做归一化，确保百分比总和=100%
        raw_scores = memory.get_suspicion_levels()
        weights = {}
        for pid in candidates:
            score = raw_scores.get(pid, 0)
            weights[pid] = max(0.01, score + 1.0)  # [-1,1] → [0.01,2.0]
        total = sum(weights.values())
        lines = []
        for pid in candidates:
            pct = round(weights[pid] / total * 100, 1) if total > 0 else 0
            if pct > 35:
                tag = "高威胁"
            elif pct > 20:
                tag = "中等威胁"
            else:
                tag = "低威胁"
            lines.append(f"{pid}号玩家 (怀疑占比 {pct:.0f}%, {tag})")
        return "击杀优先级:\n" + "\n".join(lines)

    analyze_kill_priority = StructuredTool.from_function(
        func=_analyze_kill_priority,
        name="analyze_kill_priority",
        description="分析击杀优先级，找出对你威胁最大的好人玩家。"
    )

    return [discuss_with_teammate, analyze_kill_priority]
