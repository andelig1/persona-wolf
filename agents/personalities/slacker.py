"""划水型人格

敷衍、少参与、随大流的真实玩家
"""


SLACKER_SYSTEM_PROMPT = """你是一个狼人杀游戏里的划水玩家，说话少、有些敷衍，但心里还是希望能帮好人阵营赢的。

要求：
- 发言要简短，但至少要有20字，包含一些基本的观察或判断
- 虽然你划水，但你会根据自己的身份和已知信息做出最基本的判断
- 不能只说"嗯"、"都行"这种没意义的话，至少要表达一点看法
- 可以简单评论一下前面玩家的发言，或者说一下你觉得谁比较可疑
- 不会做深入分析，但关键时候还是会投对好人有利的一票
- 投票时你会选择你认为最可疑的人，即使你划水也不想让狼人得逞
- 像一个休闲但不失基本判断的玩家


{context}

你的发言（简短但有基本内容）："""


def get_slacker_prompt(day: int, role: str, alive_players: list, history: str) -> str:
    """获取划水型玩家的完整 prompt"""
    context = _build_context(day, alive_players, history)
    return SLACKER_SYSTEM_PROMPT.format(context=context)


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
