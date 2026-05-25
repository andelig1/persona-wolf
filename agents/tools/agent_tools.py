"""Agent 主动行动工具

提供写操作能力：记录策略笔记、更新玩家信念、设定目标、回忆策略
让 Agent 不仅仅是被动查询，还能主动记录推理结论和规划行动
"""
from typing import List
from langchain_core.tools import StructuredTool


def create_agent_tools(memory, game_state_provider=None, inference_engine=None) -> List[StructuredTool]:
    """创建 Agent 主动行动工具（所有角色通用）"""

    def _record_strategy_note(category: str, target: str, content: str, priority: float = 0.5) -> str:
        """记录策略笔记，跨轮次保存你的推理结论

        参数:
        - category: 笔记类型 - suspicion/plan/observation/ally/threat
        - target: 目标玩家编号，0表示全局（不针对特定玩家）
        - content: 笔记内容
        - priority: 重要程度 0-1
        """
        # 容错：中英文类别名
        _cat_aliases = {
            "suspicion": "suspicion", "怀疑": "suspicion", "可疑": "suspicion",
            "plan": "plan", "计划": "plan", "方案": "plan", "目标": "plan",
            "observation": "observation", "观察": "observation", "记录": "observation",
            "ally": "ally", "盟友": "ally", "同伴": "ally", "队友": "ally",
            "threat": "threat", "威胁": "threat", "危险": "threat",
        }
        cat = _cat_aliases.get(category.lower().strip())
        if not cat:
            return f"无效的笔记类型: {category}，可选: suspicion/plan/observation/ally/threat"

        # 容错：支持非数字target（"全局"→0，"all"→0）
        try:
            pid = int(target)
        except (ValueError, TypeError):
            t = str(target).lower().strip()
            if t in ("全局", "all", "global", "整体", "全场", "大家", ""):
                pid = 0
            else:
                import re
                nums = re.findall(r'\d+', str(t))
                if nums:
                    pid = int(nums[0])
                else:
                    return f"无效的玩家编号: {target}（请填数字，0=全局）"

        p = max(0.0, min(1.0, float(priority))) if priority is not None else 0.5

        memory.strategic_memory.add_note(cat, pid, content, p)
        target_label = f"{pid}号玩家" if pid > 0 else "全局"
        return f"已记录[{cat}]: 关于{target_label}：{content[:60]}"

    record_strategy_note = StructuredTool.from_function(
        func=_record_strategy_note,
        name="record_strategy_note",
        description="记录策略笔记，跨轮次保存推理结论。参数：category(suspicion/plan/observation/ally/threat)，target(玩家编号，填0表示全局)，content(笔记内容)，priority(0-1重要度)"
    )

    def _update_player_belief(target: str, direction: str, reason: str) -> str:
        """更新对某玩家的信念判断，记录你怀疑或信任他的理由

        参数:
        - target: 玩家编号
        - direction: suspicious(更可疑) 或 trusted(更可信) 或 neutral(中性)
        - reason: 判断理由
        """
        # 容错：从target中提取数字
        try:
            pid = int(target)
        except (ValueError, TypeError):
            import re
            nums = re.findall(r'\d+', str(target))
            if nums:
                pid = int(nums[0])
            else:
                return f"无效的玩家编号: {target}（请填数字，如1、2、3）"

        _dir_aliases = {
            "suspicious": "suspicious", "可疑": "suspicious", "怀疑": "suspicious",
            "更可疑": "suspicious", "trusted": "trusted", "信任": "trusted",
            "可信": "trusted", "更可信": "trusted", "neutral": "neutral",
            "中性": "neutral", "中立": "neutral", "不变": "neutral",
        }
        dir_key = _dir_aliases.get(direction.lower().strip())
        if not dir_key:
            return f"无效的方向: {direction}，可选: suspicious/trusted/neutral"

        direction_map = {"suspicious": 0.15, "trusted": -0.15, "neutral": 0.0}
        delta = direction_map[dir_key]
        memory.update_suspicion(pid, delta, reason)
        memory.strategic_memory.add_note("suspicion", pid, reason, 0.7)

        dir_label = {"suspicious": "更可疑", "trusted": "更可信", "neutral": "中性调整"}[dir_key]
        return f"已更新对{pid}号玩家的判断: {dir_label}，理由: {reason}"

    update_player_belief = StructuredTool.from_function(
        func=_update_player_belief,
        name="update_player_belief",
        description="更新对某玩家的信念判断。参数：target(玩家编号)，direction(suspicious/trusted/neutral)，reason(理由)"
    )

    def _set_round_goal(goal: str, approach: str) -> str:
        """设定本轮的目标和实现策略

        参数:
        - goal: 本轮目标（如"引导大家怀疑3号玩家"或"保护自己不暴露狼人身份"）
        - approach: 实现策略（如"发言中暗示3号行为可疑，但不要太直接"）
        """
        memory.strategic_memory.add_note(
            "plan", 0,
            f"目标: {goal}\n策略: {approach}",
            0.9
        )
        return f"已设定本轮目标: {goal}\n策略: {approach}"

    set_round_goal = StructuredTool.from_function(
        func=_set_round_goal,
        name="set_round_goal",
        description="设定本轮的目标和策略。目标会帮助你保持策略连贯性，让你的发言和投票围绕同一个方向。参数: goal(本轮目标), approach(实现策略)"
    )

    def _recall_strategy(category: str = "") -> str:
        """回忆之前的策略笔记和目标

        参数:
        - category: 筛选类型，留空返回全部。可选: suspicion/plan/observation/ally/threat
        """
        cat = category.lower().strip() if category else None
        _cat_map = {
            "suspicion": "suspicion", "怀疑": "suspicion", "可疑": "suspicion",
            "plan": "plan", "计划": "plan", "目标": "plan",
            "observation": "observation", "观察": "observation",
            "ally": "ally", "盟友": "ally", "队友": "ally",
            "threat": "threat", "威胁": "threat",
        }
        if cat:
            cat = _cat_map.get(cat)
            if not cat:
                return f"无效的类型: {category}，可选: suspicion/plan/observation/ally/threat"
        return memory.strategic_memory.format_for_prompt(category=cat)

    recall_strategy = StructuredTool.from_function(
        func=_recall_strategy,
        name="recall_strategy",
        description="回忆之前记录的策略笔记。参数：category(suspicion/plan/observation/ally/threat)，留空返回全部"
    )

    return [record_strategy_note, update_player_belief, set_round_goal, recall_strategy]
