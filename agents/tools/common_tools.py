"""所有角色通用的工具

ReAct Agent 在推理过程中调用这些工具获取信息
"""
from typing import List
from langchain_core.tools import StructuredTool


def create_common_tools(memory, game_state_provider, inference_engine) -> List[StructuredTool]:
    """创建所有角色共有的工具"""

    def _review_game_history(event_type: str = "", day: str = "") -> str:
        """查看过去的游戏记录"""
        filter_type = event_type if event_type else None
        filter_day = int(day) if day.isdigit() else None
        events = memory.get_history(event_type=filter_type, day=filter_day, limit=20)
        if not events:
            return "没有找到历史记录。"
        # 直接使用过滤后的 events 构建输出（修复 event_type 过滤无效的 bug）
        lines = []
        for e in events:
            day_label = f"第{e.metadata.get('day', 1)}天"
            lines.append(f"[{day_label}][{e.event_type}] {e.content}")
        return "\n".join(lines)

    review_game_history = StructuredTool.from_function(
        func=_review_game_history,
        name="review_game_history",
        description="查看过去的游戏记录，包括发言、投票、击杀等。可按事件类型(发言/投票/击杀)或天数筛选。"
    )

    def _check_alive_players() -> str:
        """查看当前存活玩家"""
        state = game_state_provider.get_state()
        alive = state.get("alive_players", [])
        total = state.get("num_players", len(alive))
        return f"存活玩家: {', '.join([f'{p}号玩家' for p in alive])} (共{total}人，存活{len(alive)}人)"

    check_alive_players = StructuredTool.from_function(
        func=_check_alive_players,
        name="check_alive_players",
        description="查看当前还有哪些玩家存活。"
    )

    def _analyze_player_speech(player_id: str, speech_content: str = "") -> str:
        """分析某玩家的发言是否可疑

        参数:
        - player_id: 玩家编号（如1、2、3）
        - speech_content: 可选，该玩家本轮发言内容
        """
        import re
        # 容错：从player_id中提取数字（支持"3"、"3号"、"3号玩家"等）
        try:
            pid = int(player_id)
        except (ValueError, TypeError):
            nums = re.findall(r'\d+', str(player_id))
            pid = int(nums[0]) if nums else 0
        if pid <= 0:
            return f"无效的玩家编号: {player_id}，请提供有效的玩家编号"
        speeches = memory.get_history(event_type="speak", player_id=pid, limit=5)
        if not speeches and not speech_content:
            return f"没有找到{pid}号玩家的发言记录。"
        combined = speech_content or " ".join(e.content for e in speeches)
        return inference_engine.analyze_speech(combined, pid)

    analyze_player_speech = StructuredTool.from_function(
        func=_analyze_player_speech,
        name="analyze_player_speech",
        description="分析某玩家的发言是否有可疑之处，寻找逻辑矛盾或隐藏意图。参数: player_id(玩家编号，如1、2)"
    )

    def _check_vote_history(day: str = "") -> str:
        """查看投票记录"""
        filter_day = int(day) if day.isdigit() else None
        votes = memory.get_history(event_type="vote", day=filter_day)
        if not votes:
            return "没有找到投票记录。"
        lines = []
        for v in votes:
            lines.append(v.content)
        return "\n".join(lines)

    check_vote_history = StructuredTool.from_function(
        func=_check_vote_history,
        name="check_vote_history",
        description="查看过去的投票记录，分析投票模式。"
    )

    def _check_suspicion_levels() -> str:
        """查看各玩家嫌疑度（仅存活玩家）"""
        state = game_state_provider.get_state()
        alive = state.get("alive_players", [])
        return memory.format_suspicion_report(alive_players=alive)

    check_suspicion_levels = StructuredTool.from_function(
        func=_check_suspicion_levels,
        name="check_suspicion_levels",
        description="查看你对每个存活玩家的嫌疑程度判断（百分比）。"
    )

    def _recall_role_knowledge() -> str:
        """回忆特殊角色信息（如预言家查验结果）"""
        if not memory.role_knowledge:
            return "你还没有获得任何角色信息。"
        lines = []
        for pid, role in memory.role_knowledge.items():
            lines.append(f"{pid}号玩家的真实身份: {role}")
        return "\n".join(lines)

    recall_role_knowledge = StructuredTool.from_function(
        func=_recall_role_knowledge,
        name="recall_role_knowledge",
        description="回忆你通过特殊能力获得的角色信息，比如预言家的查验结果。"
    )

    return [
        review_game_history,
        check_alive_players,
        analyze_player_speech,
        check_vote_history,
        check_suspicion_levels,
        recall_role_knowledge,
    ]
