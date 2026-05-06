"""游戏入口 - MVP版"""
import random
from core.game_engine import GameEngine
from agents.ai_agent import AIAgent
from agents.human_agent import HumanAgent


def main():
    # 角色配置
    roles = ["狼人", "预言家", "女巫", "村民"]
    random.shuffle(roles)

    # 创建玩家（0号是人类）
    agents = []
    for i, role in enumerate(roles):
        if i == 0:
            agents.append(HumanAgent(i, role, "你"))
        else:
            personalities = ["aggressive", "rational", "hesitant"]
            personality = random.choice(personalities)
            agents.append(AIAgent(i, role, personality, f"AI_{i}"))

    # 显示角色分配
    print("=" * 50)
    print("游戏开始！记住你的身份：")
    for a in agents:
        print(f"玩家{a.id}: {a.role} ({a.name})")
    print("=" * 50)

    # 运行游戏
    game = GameEngine(agents)
    winner = game.run()
    print(f"\n胜利方: {winner}")


if __name__ == "__main__":
    main()