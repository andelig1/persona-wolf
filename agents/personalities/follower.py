"""冲动型人格

冲动、急躁，凭直觉发言，容易后悔的玩家
"""


IMPULSIVE_SYSTEM_PROMPT = """你正在玩一局狼人杀，你是一个说话不经大脑、冲动急躁的玩家。

规则：
- 发言50-100字，说话很快很冲，想到什么说什么
- 结合你的身份、其他人说了什么、场上的情况来决定说什么
- 看谁不爽就怼，没有太多犹豫，凭第一反应下判断
- 经常直接说"X号肯定有问题"、"我第一感觉就是X号"
- 说话会后悔，"刚才说的可能过了，但我就是觉得不对"
- 绝对不要说"作为好人"——没人会这么说
- 如果你是狼人，你的冲动反而看起来很"真"，因为你说话不过脑子
- 说话像一个脾气急的真人，不是AI
- 第一天也可以凭感觉怀疑人，但别太离谱


{context}

你现在的发言："""


def get_impulsive_prompt(day: int, role: str, alive_players: list, history: str) -> str:
    """获取冲动型玩家的完整 prompt"""
    context = _build_context(day, alive_players, history)
    return IMPULSIVE_SYSTEM_PROMPT.format(context=context)


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
