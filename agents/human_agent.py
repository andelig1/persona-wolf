"""人类玩家Agent

支持 CLI input 和 API 参数两种输入方式
"""
from typing import Optional, Dict, Any

from .base_agent import BaseAgent
from memory.memory_manager import AgentMemory


class HumanAgent(BaseAgent):
    """人类玩家Agent - 不使用LLM或ReAct推理

    通过 API 层传入人类决策，或 CLI 模式下使用 input()
    """

    def __init__(self, agent_id: int, role: str, name: str = None):
        super().__init__(agent_id, role, name)
        self.memory = AgentMemory(agent_id)

    def speak(self, game_state: dict, human_input: str = "", **kwargs) -> str:
        """返回人类发言"""
        if human_input:
            return human_input
        return input("请输入发言: ")

    def vote(self, game_state: dict, human_vote: int = None, **kwargs) -> Optional[int]:
        """返回人类投票"""
        if human_vote is not None:
            return human_vote
        alive = game_state.get("alive_players", [])
        while True:
            try:
                target = int(input("投票给: "))
                if target in alive and target != self.id:
                    return target
                print("无效选择")
            except ValueError:
                print("请输入数字")

    def night_action(self, game_state: dict, human_action: dict = None, **kwargs) -> Optional[Dict[str, Any]]:
        """返回人类夜晚行动"""
        if human_action is not None:
            return human_action

        # CLI 回退
        if self.role == "狼人":
            alive = game_state.get("alive_players", [])
            print(f"存活玩家: {[p for p in alive if p != self.id]}")
            while True:
                try:
                    target = int(input("选择击杀目标: "))
                    if target in alive and target != self.id:
                        return {"type": "kill", "target": target}
                    print("无效选择")
                except ValueError:
                    print("请输入数字")

        elif self.role == "预言家":
            alive = game_state.get("alive_players", [])
            print(f"存活玩家: {[p for p in alive if p != self.id]}")
            while True:
                try:
                    target = int(input("选择查验目标: "))
                    if target in alive and target != self.id:
                        return {"type": "check", "target": target}
                    print("无效选择")
                except ValueError:
                    print("请输入数字")

        elif self.role == "女巫":
            witch_target = kwargs.get("werewolf_target")
            has_save = kwargs.get("has_save", True)
            if witch_target is not None:
                print(f"{witch_target}号被狼人袭击了！")
                if has_save:
                    choice = input("是否使用解药救人？(y/n): ").lower()
                    if choice == 'y':
                        return {"type": "save", "target": witch_target}
            has_poison = kwargs.get("has_poison", True)
            if has_poison:
                choice = input("是否使用毒药？(y/n): ").lower()
                if choice == 'y':
                    alive = game_state.get("alive_players", [])
                    target = int(input("毒杀目标: "))
                    if target in alive:
                        return {"type": "poison", "target": target}

        return None
