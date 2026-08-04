"""游戏入口 - 命令行版本

多智能体狼人杀游戏，每个AI玩家使用 ReAct 推理 + 记忆 + 工具

提供四种模式：
  1. 开始游戏        —— 交互式游玩一局
  2. 批量观战(ReAct)  —— 后台跑 1~10 局全 AI，只写日志
  3. 随机决策对照     —— 后台跑 1~10 局纯机器随机基线
  4. 查看胜率        —— 打印人格/真人玩家的战绩

运行方式: python main.py
"""
import random
from core.game_engine import GameEngine
from utils.env_generator import generate_env_file, check_env_exists
from batch_simulator import run_batch
from stats import get_stats_recorder


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


def play_interactive():
    """交互式游玩一局"""
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

    # 记录本局到胜率统计（真人玩家）
    from api.game_api import record_game_if_finished
    try:
        record_game_if_finished(eng)
    except Exception:
        pass


def choose_batch_params() -> tuple:
    """让用户选择批量轮数与人数"""
    while True:
        try:
            games = int(input("要跑几局（1~10）: ").strip())
            if 1 <= games <= 10:
                break
            print("无效选择，局数必须在 1~10 之间")
        except ValueError:
            print("请输入数字")
    players = choose_num_players()
    return games, players


def print_stats_summary():
    """打印胜率汇总"""
    summary = get_stats_recorder().get_summary()
    print("\n" + "=" * 52)
    print(f"📊 胜率统计 | 共 {summary['total_games']} 局")
    print("=" * 52)

    overall = summary['overall']
    print(f"整体胜率: {overall['win_rate']}%  "
          f"(玩家槽位 {overall['wins']}/{overall['games']})")

    persos = summary['personalities']
    if persos:
        print("\n人格胜率:")
        print(f"  {'人格':<10}{'局数':>5}{'胜率':>9}  好人W/G  狼人W/G")
        for p in persos:
            print(f"  {p['name']:<10}{p['games']:>5}{p['win_rate']:>8.1f}%  "
                  f"{p['good']['wins']}/{p['good']['games']:<3}  "
                  f"{p['bad']['wins']}/{p['bad']['games']}")

    player = summary['player']
    if player:
        print("\n我的胜率（真人玩家）:")
        print(f"  {player['name']}: 总胜率 {player['win_rate']}%  "
              f"好人 {player['good']['wins']}/{player['good']['games']}  "
              f"狼人 {player['bad']['wins']}/{player['bad']['games']}")
    else:
        print("\n我的胜率: 暂无记录（玩过带人类的局后才会统计）")

    print("\n提示: stats/win_rates.jsonl 为每局原始记录，stats/summary.json 为聚合结果，均可直接打开查看")


def show_menu():
    """打印主菜单"""
    print("\n" + "=" * 52)
    print("  🐺 多智能体狼人杀 — 主菜单")
    print("=" * 52)
    print("  1. 🎮 开始一局游戏（交互模式）")
    print("  2. 👁 批量观战（ReAct 智能体，后台跑多局）")
    print("  3. 🎲 随机决策对照（纯机器随机基线）")
    print("  4. 📊 查看胜率")
    print("  0. 🚪 退出")
    print("-" * 52)


def main():
    # 检查/设置 API Key
    setup_api_key()

    while True:
        show_menu()
        choice = input("请选择模式: ").strip()

        if choice == "1":
            play_interactive()
        elif choice == "2":
            games, players = choose_batch_params()
            try:
                run_batch(games, players, mode="react")
            except KeyboardInterrupt:
                print("\n批量观战已中断")
        elif choice == "3":
            games, players = choose_batch_params()
            try:
                run_batch(games, players, mode="random")
            except KeyboardInterrupt:
                print("\n批量观战已中断")
        elif choice == "4":
            print_stats_summary()
        elif choice in ("0", "q", "exit", "退出"):
            print("再见！")
            break
        else:
            print("无效选择，请输入 1~4 或 0")


if __name__ == "__main__":
    main()
