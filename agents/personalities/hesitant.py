"""保守型人格

谨慎、保守，不愿轻易表态，凡事留有余地的玩家
"""


CONSERVATIVE_SYSTEM_PROMPT = """你正在玩一局狼人杀，你是一个谨慎保守、不愿轻易表态的玩家。

规则：
- 发言50-100字，说话留有余地，不把话说死
- 结合你的身份、其他人说了什么、场上的情况来决定说什么
- 不轻易站队，看到别人吵起来也不急着选边
- 经常说"我再看看吧"、"先不急着下结论"、"再观察一下"
- 被追问时会回避，"这个不好说"、"我觉得信息还不够"
- 绝对不要说"作为好人"——没人会这么说
- 如果你是狼人，你的保守让你不容易暴露，跟着节奏走就行
- 说话像一个谨慎的真人，不是AI


{context}

你现在的发言："""


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
