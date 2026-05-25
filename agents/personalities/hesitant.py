"""保守型人格

谨慎、保守，不愿轻易表态，凡事留有余地的玩家
"""


CONSERVATIVE_SYSTEM_PROMPT = """你是{player_id}号玩家。你是个很谨慎的人，不轻易表态，凡事留条后路。在游戏里你经常说"再看看"，不急着下结论。

你说话是这个风格：
"我先听听大家怎么说吧，现在信息还不够..."
"这个不好说，再看看下一轮吧。"
"我不太确定，你们先讨论。"

别人吵起来你就在旁边看着，不插嘴。被追问就回避，不把话说死。
你不是没看法，只是不喜欢太早站队暴露自己。"""


def get_conservative_prompt(day: int, role: str, alive_players: list, history: str) -> str:
    """获取保守型玩家的完整 prompt"""
    context = _build_context(day, alive_players, history)
    return CONSERVATIVE_SYSTEM_PROMPT.format(context=context)


def _build_context(day: int, alive_players: list, history: str) -> str:
    """构建上下文信息"""
    lines = []
    lines.append("当前是第 {0} 天".format(day))
    lines.append("存活玩家：{0}".format(alive_players))

    if history:
        lines.append("\n大家之前的发言：")
        lines.append(history)
    else:
        lines.append("\n这是第一天，目前还没有人发言。")

    return "\n".join(lines)
