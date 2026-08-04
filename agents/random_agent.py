"""RandomAgent - 纯机器随机决策基线

所有决策（发言/投票/夜晚行动）在合法目标中均匀随机选取，不做任何 LLM 调用。
用于与 ReAct 智能体的胜率做对照实验。

复用 ReActWerewolfAgent 的初始化（strategy/memory/personality 均继承），
保证引擎的 agent.strategy 异常回退不会崩溃；仅重写三个决策方法。
"""
import random
from typing import Dict, List, Optional

from .react_agent import ReActWerewolfAgent


class RandomAgent(ReActWerewolfAgent):
    """零智能随机决策 Agent"""

    is_random = True

    _SPEECH_POOL = [
        "我暂时没有太多信息，先观望一下大家。",
        "目前看不出谁可疑，我再听听看。",
        "我保持中立，一切以投票结果为准。",
        "我没有特别的发现，先不轻易下结论。",
        "感觉局势还不太明朗，我保留意见。",
    ]

    def speak(self, game_state: dict, **kwargs) -> str:
        """随机发言：从固定句池中挑一句"""
        self.game_state_provider.set_state(game_state)
        return random.choice(self._SPEECH_POOL)

    def vote(self, game_state: dict, **kwargs) -> Optional[int]:
        """随机投票：在合法目标中均匀随机选一个（排除自己；狼人排除队友）"""
        self.game_state_provider.set_state(game_state)
        alive = game_state.get("alive_players", [])
        tie_options = kwargs.get("vote_options")
        wolf_teammates = kwargs.get("wolf_teammates", [])

        exclude = {self.id}
        if self.role == "狼人" and wolf_teammates:
            exclude.update(wolf_teammates)
        candidates = [p for p in (tie_options if tie_options else alive) if p not in exclude]
        if not candidates:
            return None
        return random.choice(candidates)

    def night_action(self, game_state: dict, **kwargs) -> Optional[Dict[str, object]]:
        """随机夜晚行动：按角色在合法目标中均匀随机"""
        self.game_state_provider.set_state(game_state)
        alive = game_state.get("alive_players", [])
        others = [p for p in alive if p != self.id]

        if self.role == "狼人":
            wolves = kwargs.get("wolf_teammates") or []
            safe = [p for p in others if p not in wolves]
            if not safe:
                return None
            return {"type": "kill", "target": random.choice(safe)}

        if self.role == "预言家":
            if not others:
                return None
            return {"type": "check", "target": random.choice(others)}

        if self.role == "女巫":
            has_save = kwargs.get("has_save", False)
            has_poison = kwargs.get("has_poison", False)
            wolf_target = kwargs.get("werewolf_target")

            # 解药：刀口存在且有解药时 50% 概率救人
            if has_save and wolf_target is not None and random.random() < 0.5:
                return {"type": "save"}

            # 毒药：有药时 30% 概率毒人（不毒自己与刀口目标）
            if has_poison:
                if wolf_target is not None and random.random() < 0.3:
                    poison_candidates = [p for p in others if p != wolf_target]
                else:
                    poison_candidates = others
                if poison_candidates and random.random() < 0.3:
                    return {"type": "poison", "target": random.choice(poison_candidates)}
            return None

        # 村民无夜晚行动
        return None
