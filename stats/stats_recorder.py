"""胜率记录与聚合

原始战绩以 JSONL 追加模式写入 stats/win_rates.jsonl（每局一行，追加 O(1)，不重写全文件）；
聚合结果写入 stats/summary.json（每次查看胜率时刷新，可直接打开查看）。
CLI 批量与 Web 共享同一份数据。
"""
import json
import os
import threading
from typing import Dict, List, Optional

# 五个人格 + 随机基准，固定展示顺序
PERSONALITY_ORDER = [
    "rational", "agitative", "conservative", "impulsive", "slacker",
]
PERSONALITY_CN = {
    "rational": "理性型",
    "agitative": "煽动型",
    "conservative": "保守型",
    "impulsive": "冲动型",
    "slacker": "划水型",
    "random_baseline": "随机基准",
}

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_PATH = os.path.join(_BASE_DIR, "stats", "win_rates.jsonl")
DEFAULT_SUMMARY_PATH = os.path.join(_BASE_DIR, "stats", "summary.json")
LEGACY_PATH = os.path.join(_BASE_DIR, "stats", "win_rates.json")


class StatsRecorder:
    """游戏战绩记录器（JSONL 追加 + 摘要缓存，线程安全）"""

    def __init__(self, data_path: str = None, summary_path: str = None):
        self.data_path = data_path or DEFAULT_DATA_PATH
        self.summary_path = summary_path or DEFAULT_SUMMARY_PATH
        self._lock = threading.Lock()
        self._ensure_files()

    # ==================== 文件管理 ====================

    def _ensure_files(self) -> None:
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        self._migrate_legacy()
        if not os.path.exists(self.data_path):
            open(self.data_path, "w", encoding="utf-8").close()
        if not os.path.exists(self.summary_path):
            self._write_json(self.summary_path, {"next_id": 0})

    def _migrate_legacy(self) -> None:
        """把旧版 win_rates.json 中的战绩迁移到 JSONL，旧文件改名 .bak 避免重复处理"""
        if not os.path.exists(LEGACY_PATH):
            return
        games = []
        try:
            with open(LEGACY_PATH, encoding="utf-8") as f:
                games = json.load(f).get("games", [])
        except (json.JSONDecodeError, FileNotFoundError):
            games = []
        if games:
            with open(self.data_path, "a", encoding="utf-8") as f:
                for g in games:
                    g.pop("id", None)  # id 会重新分配
                    f.write(json.dumps(g, ensure_ascii=False) + "\n")
        try:
            os.rename(LEGACY_PATH, LEGACY_PATH + ".bak")
        except OSError:
            pass

    def _load_games(self) -> List[dict]:
        games = []
        if not os.path.exists(self.data_path):
            return games
        with open(self.data_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    games.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return games

    @staticmethod
    def _write_json(path: str, data: dict) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # 原子替换，避免读到半截文件

    def _read_meta(self) -> dict:
        try:
            with open(self.summary_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    # ==================== 记录 ====================

    def record_game(self, winner: str, roles: Dict[int, str],
                    personalities: Dict[int, str], mode: str = "react",
                    human_player_id: Optional[int] = None) -> None:
        """记录一局游戏结果（O(1) 追加一行，不重写全文件）

        Args:
            winner: "好人" 或 "狼人"
            roles: {pid: role}
            personalities: {pid: personality_key}（RandomAgent 记作 random_baseline）
            mode: "react" / "random"
            human_player_id: 真人玩家的 pid（全 AI 批量局传 None，不计入玩家胜率）
        """
        if winner not in ("好人", "狼人"):
            return
        if not roles:
            return

        with self._lock:
            record = {
                "id": self._next_id(),
                "mode": mode,
                "winner": winner,
                "roles": {str(k): v for k, v in roles.items()},
                "personalities": {str(k): v for k, v in personalities.items()},
                "human_player_id": int(human_player_id) if human_player_id else None,
            }
            with open(self.data_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            # 只更新 next_id，不做全量聚合，保证追加是 O(1)
            meta = self._read_meta()
            meta["next_id"] = record["id"]
            self._write_json(self.summary_path, meta)

    def _next_id(self) -> int:
        try:
            return int(self._read_meta().get("next_id", 0)) + 1
        except (ValueError, TypeError):
            return len(self._load_games()) + 1

    # ==================== 聚合 ====================

    def get_summary(self) -> dict:
        """聚合全部战绩，并刷新 summary.json 缓存（可直接打开查看）"""
        games = self._load_games()
        summary = self._aggregate(games)
        with self._lock:
            summary["next_id"] = self._read_meta().get("next_id", len(games))
            self._write_json(self.summary_path, summary)
        return summary

    def _aggregate(self, games: List[dict]) -> dict:
        """聚合：人格胜率 + 真人玩家胜率 + 整体

        人格/整体按所有玩家槽位统计；玩家胜率仅统计真人玩家（human_player_id）的局。
        """
        # 人格统计
        perso_agg = {key: self._empty_agg() for key in PERSONALITY_ORDER}
        perso_agg["random_baseline"] = self._empty_agg()

        # 真人玩家统计（good/bad 结构与人格一致）
        user_agg = self._empty_agg()

        total = len(games)
        total_slots = 0  # 全体玩家槽位（每局 N 个角色槽）
        overall_wins = 0

        for g in games:
            winner = g.get("winner")
            mode = g.get("mode", "react")
            human_pid = g.get("human_player_id")

            for pid_str, role in g.get("roles", {}).items():
                pid = int(pid_str)
                perso_key = g.get("personalities", {}).get(pid_str)
                if not perso_key or perso_key not in perso_agg:
                    perso_key = "rational"
                # 随机模式下人格归入 random_baseline 对照行
                if mode == "random":
                    perso_key = "random_baseline"

                side = "bad" if role == "狼人" else "good"
                won = (role == "狼人" and winner == "狼人") or \
                      (role != "狼人" and winner == "好人")
                total_slots += 1
                if won:
                    overall_wins += 1

                self._accumulate(perso_agg[perso_key], side, won)

                # 真人玩家胜率：仅累加人类玩家的局
                if human_pid and pid == int(human_pid):
                    self._accumulate(user_agg, side, won)

        personalities_out = []
        for key in list(perso_agg.keys()):
            agg = perso_agg[key]
            if agg["games"] == 0:
                continue
            personalities_out.append(self._agg_row(key, PERSONALITY_CN.get(key, key), agg))

        player_out = None
        if user_agg["games"] > 0:
            player_out = self._agg_row("player", "你（真人玩家）", user_agg)

        return {
            "total_games": total,
            "overall": {
                # 整体胜率按全体玩家槽位统计（每局 N 个槽位各记一胜/一负）
                "games": total_slots,
                "wins": overall_wins,
                "win_rate": self._rate(overall_wins, total_slots),
            },
            "personalities": personalities_out,
            "player": player_out,
        }

    def _agg_row(self, key: str, name: str, agg: dict) -> dict:
        return {
            "key": key,
            "name": name,
            "games": agg["games"],
            "wins": agg["wins"],
            "win_rate": self._rate(agg["wins"], agg["games"]),
            "good": {
                "games": agg["good"]["games"],
                "wins": agg["good"]["wins"],
                "win_rate": self._rate(agg["good"]["wins"], agg["good"]["games"]),
            },
            "bad": {
                "games": agg["bad"]["games"],
                "wins": agg["bad"]["wins"],
                "win_rate": self._rate(agg["bad"]["wins"], agg["bad"]["games"]),
            },
        }

    @staticmethod
    def _empty_agg() -> dict:
        return {
            "games": 0, "wins": 0,
            "good": {"games": 0, "wins": 0},
            "bad": {"games": 0, "wins": 0},
        }

    @staticmethod
    def _accumulate(agg: dict, side: str, won: bool) -> None:
        agg["games"] += 1
        if won:
            agg["wins"] += 1
        agg[side]["games"] += 1
        if won:
            agg[side]["wins"] += 1

    @staticmethod
    def _rate(wins: int, games: int) -> float:
        return round(wins * 100.0 / games, 1) if games else 0.0


_recorder: Optional[StatsRecorder] = None


def get_stats_recorder() -> StatsRecorder:
    """获取全局单例"""
    global _recorder
    if _recorder is None:
        _recorder = StatsRecorder()
    return _recorder
