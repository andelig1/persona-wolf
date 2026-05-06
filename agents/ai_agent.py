"""AI玩家"""
import random
from .base_agent import BaseAgent

class AIAgent(BaseAgent):
    def __init__(self, agent_id, role, personality="rational", name=None):
        super().__init__(agent_id, role, name)
        self.personality = personality

    def speak(self, game_state):
        others = [p for p in game_state["alive_players"] if p != self.id]
        if not others:
            return "我是好人"

        if self.personality == "aggressive":
            target = random.choice(others)
            return f"我强烈怀疑{target}号是狼人！"
        elif self.personality == "hesitant":
            target = random.choice(others)
            return f"我觉得{target}号有点可疑...但不确定..."
        else:
            return "我是好人，大家不要投我"

    def vote(self, game_state):
        others = [p for p in game_state["alive_players"] if p != self.id]
        return random.choice(others) if others else None

    def night_action(self, game_state, target=None):
        """夜晚行动
        Args:
            game_state: 游戏状态
            target: 可选，狼人击杀目标（传给女巫用）
        """
        if self.role == "狼人":
            others = [p for p in game_state["alive_players"] if p != self.id]
            return random.choice(others) if others else None
        elif self.role == "女巫":
            # target 是狼人击杀的目标
            if target and random.random() < 0.5:
                return True  # 表示救人
        return None