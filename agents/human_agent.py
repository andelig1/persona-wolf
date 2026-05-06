"""人类玩家"""
from .base_agent import BaseAgent

class HumanAgent(BaseAgent):
    def speak(self, game_state):
        print(f"\n[你的回合] 身份: {self.role}")
        return input("请输入发言: ")

    def vote(self, game_state):
        print(f"\n存活玩家: {game_state['alive_players']}")
        while True:
            try:
                target = int(input("投票给: "))
                if target in game_state['alive_players'] and target != self.id:
                    return target
                print("无效选择")
            except:
                print("请输入数字")

    def night_action(self, game_state, target=None):
        """夜晚行动
        Args:
            game_state: 游戏状态
            target: 可选，狼人击杀目标（传给女巫用）
        """
        if self.role == "狼人":
            print(f"\n存活玩家: {[p for p in game_state['alive_players'] if p != self.id]}")
            while True:
                try:
                    return int(input("选择击杀目标: "))
                except:
                    print("请输入数字")
        elif self.role == "女巫" and target:
            print(f"\n{target}号被狼人袭击了！")
            choice = input("是否使用解药救人？(y/n): ").lower()
            return choice == 'y'
        return None