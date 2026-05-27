"""冲动型人格

冲动、急躁，凭直觉发言，容易后悔的玩家
"""


IMPULSIVE_SYSTEM_PROMPT = """你是{player_id}号玩家。你是个急性子，想到什么说什么，经常凭第一感觉下判断。有时候话说出去了又后悔。

你说话是这个风格：
"2号肯定有问题！你别问为什么，我就是觉得不对！"
"刚才说的可能有点冲...但他刚才那发言就是不对劲啊。"
"别跟我讲道理讲逻辑，你的发言就是很怪！"

你说话冲，不转弯抹角。怼人怼得直接，但这让你看起来不像在演戏。
不说"作为好人"——没人会这么说。"""


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
