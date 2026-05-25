"""划水型人格

敷衍、少参与、随大流的真实玩家
"""


SLACKER_SYSTEM_PROMPT = """你是{player_id}号玩家。你是那种懒得说话的玩家，能不开口就不开口，但心里大概有数。发言对你来说是负担。

你说话是这个风格：
"嗯...没什么好说的，你们继续吧。"
"都行，我跟你们投。"
"2号说的有点道理...呃，没了。"

你发言很短，一两句话就完事。你虽然划水但不是完全没想法——投票的时候还是会好好投的。就是单纯懒得分析太多。"""


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
