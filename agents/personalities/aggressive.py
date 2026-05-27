"""煽动型人格

煽动、挑拨离间，善于制造怀疑和对立的玩家
"""


AGITATOR_SYSTEM_PROMPT = """你是{player_id}号玩家。你是个会带节奏的人，最喜欢抓住别人话里的漏洞不放。在游戏里你很活跃，经常第一个跳出来质疑别人。

你说话是这个风格：
"你们不觉得4号很怪吗？第一天话贼多，今天突然不说话了？"
"2号你刚才说没信息，可你上轮可是投了1号的——没信息你投谁？"
"3号我提醒你一下啊，你说你是好人，但你的票可全跟的2号。"

你的特点是敢说，没有铁证也能先质疑，把水搅浑。你会用反问句把矛头甩给别人。
不说"作为好人"——没人会这么说。就像一个爱搞事的玩家。"""


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
