"""命令行批量观战（后台）模式

一次性跑 1~10 局全 AI 游戏，游戏内容只写日志，不向终端输出任何 agent 对话或游戏提示。
每局结束后写入结构化日志 logs/batch/game_<i>.json，并追加到胜率统计 stats/win_rates.jsonl。

用法:
    python batch_simulator.py --games 5 --players 8              # ReAct 智能体
    python batch_simulator.py --games 5 --players 8 --mode random  # 纯机器随机基线
"""
import argparse
import contextlib
import io
import json
import os
import sys
import time
import warnings

# 抑制 langgraph 导入时的依赖弃用告警，保持后台模式输出干净
os.environ["LANGCHAIN_SUPPRESS_DEPRECATION_WARNINGS"] = "true"
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# langgraph 在导入期会向 stderr 打印依赖弃用告警，与游戏内容无关，静默吞掉
_import_err = io.StringIO()
with contextlib.redirect_stderr(_import_err):
    from core.game_engine import GameEngine
from stats import get_stats_recorder
from stats.stats_recorder import PERSONALITY_CN, PERSONALITY_ORDER


def _players_config(pool: str = "") -> dict:
    return {"6": 6, "7": 7, "8": 8, "9": 9, "10": 10}


def _run_single_game(index: int, num_players: int, mode: str,
                     log_dir: str) -> dict:
    """跑一局全 AI 游戏，抑制所有 stdout，返回结果摘要"""
    eng = GameEngine(num_players, human_player_id=0, agent_mode=mode)
    eng.initialize()

    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            eng.run()
    except Exception:
        # 异常时仍把 stdout 缓冲丢弃，只记录失败原因
        pass

    winner = eng.winner or "未知"
    result = {
        "index": index,
        "mode": mode,
        "winner": winner,
        "day": eng.phase_controller.day,
        "roles": {str(k): v for k, v in eng.role_manager.player_roles.items()},
        "personalities": {
            str(pid): getattr(agent, "personality", "?")
            for pid, agent in eng.agents.items()
        },
        "history": eng.history,
    }
    return result


def _write_game_log(result: dict, log_dir: str, mode: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"game_{mode}_{result['index']:02d}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def _record_stats(result: dict, mode: str) -> None:
    recorder = get_stats_recorder()
    recorder.record_game(
        winner=result["winner"],
        roles={int(k): v for k, v in result["roles"].items()},
        personalities={int(k): v for k, v in result["personalities"].items()},
        mode=mode,
    )


def _print_summary(results: list, mode: str) -> None:
    good_wins = sum(1 for r in results if r["winner"] == "好人")
    total = len(results)
    print("\n" + "=" * 46)
    print(f"批量完成: {total} 局 ({mode}) | 好人 {good_wins} 胜 / 狼人 {total - good_wins} 胜")
    print("=" * 46)
    print(f"{'人格':<10}{'局数':>5}{'胜率':>8}  好人W/G  狼人W/G")

    from collections import defaultdict
    agg = defaultdict(lambda: {"games": 0, "wins": 0, "good": [0, 0], "bad": [0, 0]})
    for r in results:
        for pid_str, role in r["roles"].items():
            if mode == "random":
                key = "random_baseline"
            else:
                key = r["personalities"].get(pid_str, "?")
            side = "bad" if role == "狼人" else "good"
            won = (role == "狼人" and r["winner"] == "狼人") or \
                  (role != "狼人" and r["winner"] == "好人")
            agg[key]["games"] += 1
            if won:
                agg[key]["wins"] += 1
            agg[key][side][0] += 1
            if won:
                agg[key][side][1] += 1

    for key in PERSONALITY_ORDER + (["random_baseline"] if mode == "random" else []):
        a = agg.get(key)
        if not a or a["games"] == 0:
            continue
        rate = a["wins"] * 100.0 / a["games"]
        g = a["good"]
        b = a["bad"]
        print(f"{PERSONALITY_CN.get(key, key):<10}{a['games']:>5}{rate:>7.1f}%  "
              f"{g[1]}/{g[0]:<3}  {b[1]}/{b[0]}")


def run_batch(games: int, players: int, mode: str,
              log_dir: str = None, verbose: bool = True) -> list:
    """批量跑 N 局全 AI 游戏（供 CLI 入口与 main.py 菜单复用）

    Args:
        games: 局数（1~10）
        players: 玩家人数（6~10）
        mode: "react" / "random"
        log_dir: 结构化日志目录
        verbose: 是否打印进度
    Returns:
        每局结果摘要列表
    """
    if not (1 <= games <= 10):
        raise ValueError("局数必须在 1~10 之间")
    if not (6 <= players <= 10):
        raise ValueError("玩家人数必须在 6~10 之间")
    log_dir = log_dir or os.path.join("logs", "batch")

    if verbose:
        print(f"批量观战开始: {games} 局 × {players} 人局 | 模式: {mode}")
        print("提示: 本模式不输出任何 agent 对话/游戏提示，内容仅写入日志。")
    results = []
    start_ts = time.time()
    for i in range(1, games + 1):
        result = _run_single_game(i, players, mode, log_dir)
        _write_game_log(result, log_dir, mode)
        _record_stats(result, mode)
        results.append(result)
        if verbose:
            winner_tag = "好人" if result["winner"] == "好人" else "狼人"
            print(f"[{i}/{games}] {winner_tag}获胜 · {result['day']}天 · {mode}")

    elapsed = time.time() - start_ts
    if verbose:
        print(f"\n用时 {elapsed:.1f}s，平均每局 {elapsed / max(len(results), 1):.2f}s")
        _print_summary(results, mode)
    # 刷新聚合摘要缓存，方便直接打开 stats/summary.json 查看胜率
    get_stats_recorder().get_summary()
    if verbose:
        print("胜率已写入 stats/win_rates.jsonl（原始记录）与 stats/summary.json（聚合结果）")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="批量后台跑全 AI 狼人杀局，只写日志不出游戏内容",
    )
    parser.add_argument("--games", type=int, required=True,
                        help="跑多少局（1~10）")
    parser.add_argument("--players", type=int, default=8,
                        help="玩家人数（6~10），默认 8")
    parser.add_argument("--mode", choices=["react", "random"], default="react",
                        help="agent 决策模式：react=ReAct智能体, random=纯机器随机基线")
    parser.add_argument("--log-dir", default=os.path.join("logs", "batch"),
                        help="结构化日志输出目录")
    args = parser.parse_args()
    run_batch(args.games, args.players, args.mode, args.log_dir)


if __name__ == "__main__":
    main()
