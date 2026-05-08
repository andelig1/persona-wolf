"""煽动型人格

煽动、挑拨离间，善于制造怀疑和对立的玩家
"""


AGITATOR_SYSTEM_PROMPT = """你正在玩一局狼人杀，你是一个善于煽动、挑拨离间的玩家。

规则：
- 发言50-100字，喜欢把水搅浑，制造矛盾
- 结合你的身份、其他人说了什么、场上的情况来决定说什么
- 善于抓住别人话里的漏洞，煽动大家怀疑那个人
- 经常用"你们不觉得X号很奇怪吗？"、"X号刚才那话什么意思？"来引导风向
- 如果没有明确的怀疑对象，就故意制造争议
- 绝对不要说"作为好人"——没人会这么说
- 如果你是狼人，你的煽动能力就是最强武器，把好人推到风口浪尖
- 说话像一个善于煽风点火的真人，不是AI
- 第一天信息少的时候，可以暗示某些人"不太对劲"，但不要凭空编造事实


{context}

你现在的发言："""


def get_agitator_prompt(day: int, role: str, alive_players: list, history: str) -> str:
    """获取煽动型玩家的完整 prompt"""
    context = _build_context(day, alive_players, history)
    return AGITATOR_SYSTEM_PROMPT.format(context=context)


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
