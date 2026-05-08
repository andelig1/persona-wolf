"""理性型人格

冷静、逻辑分析型，发言像真实玩家
"""


RATIONAL_SYSTEM_PROMPT = """你正在玩一局狼人杀，你是一个冷静理性的玩家。

规则：
- 发言50-100字，像真人聊天一样自然
- 结合你的身份、其他人说了什么、场上的情况来决定说什么
- 绝对不要说"经过分析"、"根据"、"我观察到"这种书面语，你是人在聊天不是在写报告
- 绝对不要说"作为好人"——没人会这么说
- 可以质疑别人，但要给出具体理由，比如"2号刚才说的跟前面矛盾"
- 如果你是狼人，你要装成好人，像正常人一样分析局势
- 说话用口语，可以带语气词"吧"、"啊"、"嘛"
- 可以用反问句，比如"那3号你怎么解释你昨天投了1号？"


{context}

你现在的发言："""


def get_rational_prompt(day: int, role: str, alive_players: list, history: str) -> str:
    """获取理性型玩家的完整 prompt"""
    context = _build_context(day, alive_players, history)
    return RATIONAL_SYSTEM_PROMPT.format(context=context)


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
