"""游戏入口 - 命令行版本

多智能体狼人杀游戏，每个AI玩家使用 ReAct 推理 + 记忆 + 工具
运行方式: python main.py
"""
import random
from core.game_engine import GameEngine
from utils.env_generator import generate_env_file, check_env_exists


def setup_api_key():
    """引导用户设置 API Key"""
    print("=" * 50)
    print("单人狼人杀 - LLM 版本")
    print("=" * 50)

    if check_env_exists():
        print("[OK] 检测到 .env 配置文件")
        return True

    print("\n未检测到 .env 配置文件")
    print("请输入 DeepSeek API Key (sk-...)：")
    api_key = input().strip()

    if not api_key:
        print("未输入 API Key，将使用简化模式运行（不调用 LLM）")
        return False

    try:
        generate_env_file(api_key)
        print("[OK] .env 文件已生成")
        return True
    except ValueError as e:
        print("[ERROR] API Key 格式错误: {0}".format(e))
        return False


def choose_num_players():
    """选择玩家数量"""
    print("\n请选择玩家人数（6-10人）：")

    while True:
        choice = input("请输入数字: ").strip()
        try:
            num = int(choice)
            if 6 <= num <= 10:
                return num
            print("无效选择，人数必须在 6-10 之间")
        except:
            print("请输入数字")


def get_role_config(num_players: int) -> list:
    """根据人数获取角色配置"""
    if num_players == 6:
        return ["狼人", "狼人", "预言家", "女巫", "村民", "村民"]
    elif num_players == 7:
        return ["狼人", "狼人", "预言家", "女巫", "村民", "村民", "村民"]
    elif num_players == 8:
        return ["狼人", "狼人", "预言家", "女巫", "女巫", "村民", "村民", "村民"]
    elif num_players == 9:
        return ["狼人", "狼人", "狼人", "预言家", "女巫", "村民", "村民", "村民", "村民"]
    elif num_players == 10:
        return ["狼人", "狼人", "狼人", "预言家", "女巫", "女巫", "村民", "村民", "村民", "村民"]
    else:
        # 默认返回6人配置
        return ["狼人", "狼人", "预言家", "女巫", "村民", "村民"]


def choose_or_random_role(roles: list):
    """让人类玩家选择身份或随机"""
    print("\n请选择你的身份：")
    print("  0. 随机分配")
    for i, role in enumerate(roles):
        print("  {0}. {1}".format(i + 1, role))

    while True:
        choice = input("\n请输入数字: ").strip()
        try:
            idx = int(choice)
            if idx == 0:
                return None  # 随机
            if 1 <= idx <= len(roles):
                return roles[idx - 1]
        except:
            pass
        print("无效选择")


def assign_roles_with_choice(num_players: int, human_player_id: int, chosen_role: str = None):
    """分配角色，支持人类玩家选择身份"""
    roles = get_role_config(num_players)

    if chosen_role and chosen_role in roles:
        # 玩家选择了身份
        roles.remove(chosen_role)
        random.shuffle(roles)
        player_roles = [chosen_role] + roles
    else:
        # 随机分配
        random.shuffle(roles)
        player_roles = roles

    return player_roles


def print_roles(eng: GameEngine):
    """显示玩家角色分配（游戏开始时）"""
    print("\n" + "=" * 50)
    print("游戏开始！记住你的身份：")
    print("=" * 50)

    human_role = eng.role_manager.get_player_role(eng.human_player_id)

    for pid, role in eng.role_manager.player_roles.items():
        name = eng.role_manager.player_names.get(pid, f"玩家{pid}")
        if pid == eng.human_player_id:
            print("[你] {0}: {1} <-- 这是你的身份！".format(name, role))
        else:
            print("{0}: {1}".format(name, role))

    # 如果人类是狼人，显示队友信息
    if human_role == "狼人":
        wolves = [pid for pid, r in eng.role_manager.player_roles.items()
                  if r == "狼人" and pid != eng.human_player_id]
        if wolves:
            teammates = [f"{pid}号({eng.role_manager.player_names.get(pid, f'玩家{pid}')})"
                         for pid in wolves]
            print("\n你的狼人队友: {0}".format(", ".join(teammates)))
            print("夜晚你们一起选择击杀目标，白天不要投票给队友！")

    print("=" * 50)
    input("\n按回车开始游戏...")


def main():
    # 检查/设置 API Key
    has_api_key = setup_api_key()

    # 选择玩家数量
    num_players = choose_num_players()
    human_player_id = 1  # 始终是玩家1（从1开始计数）

    print("\n开始游戏 ({0}人局)...".format(num_players))

    # 创建游戏引擎
    eng = GameEngine(num_players=num_players, human_player_id=human_player_id)

    # 角色选择
    available_roles = get_role_config(num_players)
    chosen_role = choose_or_random_role(available_roles)

    # 初始化游戏（只调用一次）
    eng.initialize_with_roles(chosen_role)

    # 显示角色分配
    print_roles(eng)

    # 运行游戏
    try:
        winner = eng.run()

        # 游戏结束
        print("\n" + "=" * 50)
        print(f"🏆 [WINNER] 游戏结束！{winner}获胜！")
        print("=" * 50)

        # 显示存活玩家状态
        print("\n👥 最终存活：")
        for pid in eng.alive_players:
            role = eng.role_manager.get_player_role(pid)
            name = eng.role_manager.player_names.get(pid, f"玩家{pid}")
            # 人类玩家显示为"玩家X（你）"
            display_name = f"玩家{pid}（你）" if pid == eng.human_player_id else name
            print(f"   ├─ {display_name}: {role}")

        # 显示所有玩家身份
        print("\n🃏 所有玩家身份：")
        for pid in sorted(eng.role_manager.player_roles.keys()):
            role = eng.role_manager.get_player_role(pid)
            name = eng.role_manager.player_names.get(pid, f"玩家{pid}")
            # 人类玩家显示为"玩家X（你）"
            display_name = f"玩家{pid}（你）" if pid == eng.human_player_id else name
            print(f"   ├─ {display_name}: {role}")

    except KeyboardInterrupt:
        print("\n\n游戏被用户中断")


if __name__ == "__main__":
    main()