"""PlayerAgent - 接 LLM 的 AI 玩家

使用 DeepSeek LLM 生成发言，具备人格特征
"""
import random
from typing import Optional, Dict, Any

from .base_agent import BaseAgent
from utils.llm_client import get_llm_client
from utils.config import GameConfig
from .personalities import (
    get_rational_prompt,
    get_aggressive_prompt,
    get_hesitant_prompt,
    get_follower_prompt,
)


class PlayerAgent(BaseAgent):
    """LLM 驱动的 AI 玩家"""

    def __init__(
        self,
        agent_id: int,
        role: str,
        personality: str = "rational",
        name: str = None,
    ):
        """
        Args:
            agent_id: 玩家ID
            role: 角色（狼人/预言家/女巫/村民）
            personality: 人格类型（rational/aggressive/hesitant/follower）
            name: 玩家名称
        """
        super().__init__(agent_id, role, name)
        self.personality = personality
        self._llm_client = None

    @property
    def llm_client(self):
        """获取 LLM 客户端"""
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    def _get_personality_prompt(self, game_state: Dict) -> str:
        """获取当前人格对应的完整 prompt"""
        day = game_state.get("day", 1)
        alive_players = game_state.get("alive_players", [])
        history = game_state.get("history_text", "")

        prompt_getters = {
            "rational": get_rational_prompt,
            "aggressive": get_aggressive_prompt,
            "hesitant": get_hesitant_prompt,
            "follower": get_follower_prompt,
        }

        getter = prompt_getters.get(self.personality, get_rational_prompt)
        return getter(day, self.role, alive_players, history)

    def _format_game_context(self, game_state: Dict) -> str:
        """格式化游戏上下文供 LLM 参考"""
        lines = [
            f"第 {game_state.get('day', 1)} 天",
            f"你是 {self.id} 号玩家，角色是 {self.role}",
            f"存活玩家: {game_state.get('alive_players', [])}",
        ]

        # 狼人需要知道队友信息
        if self.role == "狼人":
            wolf_teammates = game_state.get("wolf_teammates", [])
            teammates = [t for t in wolf_teammates if t != self.id]
            if teammates:
                lines.append(f"你的队友: {[f'{t}号' for t in teammates]}")
            lines.append("")
            lines.append("历史发言:")
        else:
            lines.append("")
            lines.append("历史发言:")

        history = game_state.get("history", [])
        for event in history[-10:]:  # 只看最近10条
            if event.get("type") == "speak":
                pid = event.get("player_id")
                content = event.get("content", "")
                lines.append(f"  {pid}号: {content}")

        return "\n".join(lines)

    def speak(self, game_state: Dict, **kwargs) -> str:
        """生成发言

        Args:
            game_state: 游戏状态，包含 day, alive_players, history 等
            **kwargs: 额外参数，包含 wolf_teammates（狼人队友列表）

        Returns:
            str: 生成的发言内容
        """
        try:
            # 传入队友信息供上下文使用
            wolf_teammates = kwargs.get("wolf_teammates", [])
            game_state["wolf_teammates"] = wolf_teammates

            # 构建完整 prompt
            game_state["history_text"] = self._format_game_context(game_state)
            full_prompt = self._get_personality_prompt(game_state)

            # 调用 LLM
            messages = [
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": "请发言，50字以内。"},
            ]

            response = self.llm_client.chat(
                messages,
                temperature=GameConfig.LLM_TEMPERATURE,
            )

            # 清理回复，限制长度
            response = response.strip()
            if len(response) > 100:
                response = response[:97] + "..."

            return response

        except Exception:
            # LLM 调用失败时返回默认发言
            return self._fallback_speak()

    def _fallback_speak(self) -> str:
        """LLM 调用失败时的备用发言"""
        fallback = {
            "rational": "我是好人，大家理性分析。",
            "aggressive": "我觉得2号很可疑！",
            "hesitant": "我有点不确定...让我再想想...",
            "follower": "大家都说得有道理...",
        }
        return fallback.get(self.personality, "我是好人。")

    def vote(self, game_state: Dict, **kwargs) -> Optional[int]:
        """投票决策

        Args:
            game_state: 游戏状态
            **kwargs: 额外参数，包含 wolf_teammates（狼人队友列表）

        Returns:
            int: 投票目标玩家 ID
        """
        alive_players = game_state.get("alive_players", [])
        wolf_teammates = kwargs.get("wolf_teammates", [])

        if len(alive_players) <= 1:
            return None

        # 排除自己
        candidates = [p for p in alive_players if p != self.id]
        if not candidates:
            return None

        # 狼人不投队友
        if self.role == "狼人" and wolf_teammates:
            candidates = [p for p in candidates if p not in wolf_teammates]
            if not candidates:
                return None

        try:
            # 狼人阵营，优先投好人
            if self.role == "狼人":
                return random.choice(candidates)

            # 好人的话，分析发言选择（目前简化处理为随机）
            return random.choice(candidates)

        except Exception:
            return random.choice(candidates)

    def night_action(self, game_state: Dict, **kwargs) -> Optional[Dict[str, Any]]:
        """夜晚行动

        Args:
            game_state: 游戏状态
            **kwargs: 额外参数，包含 wolf_teammates（狼人队友列表）

        Returns:
            Dict: 行动结果，包含 type 和 target
        """
        alive_players = game_state.get("alive_players", [])
        player_roles = game_state.get("player_roles", {})
        wolf_teammates = kwargs.get("wolf_teammates", [])

        if len(alive_players) <= 1:
            return None

        # 排除自己
        candidates = [p for p in alive_players if p != self.id]
        if not candidates:
            return None

        if self.role == "狼人":
            # 狼人杀人 - 不能杀其他狼人队友
            wolf_targets = [p for p in candidates
                           if player_roles.get(p) and player_roles.get(p) != "狼人"
                           and p not in wolf_teammates]
            if not wolf_targets:
                return None
            return {"type": "kill", "target": random.choice(wolf_targets)}

        elif self.role == "预言家":
            # 预言家查验 - 随机选一个
            target = random.choice(candidates)
            return {"type": "check", "target": target}

        elif self.role == "女巫":
            # 女巫决策（救人/毒人）
            witch_target = kwargs.get("target")  # 狼人杀的目标
            save = kwargs.get("save", False)

            if save and witch_target:
                return {"type": "save", "target": witch_target}

            return None

        return None


class RemoteAgent(BaseAgent):
    """远程玩家 Agent（供前端调用）

    接收前端传来的决策，不直接调用 LLM
    """

    def __init__(self, agent_id: int, role: str, name: str = None):
        super().__init__(agent_id, role, name)
        self.pending_speak = True  # 等待用户输入发言
        self.pending_vote = True   # 等待用户投票
        self.pending_action = True  # 等待用户夜晚行动

    def speak(self, game_state: Dict) -> str:
        """返回空字符串，实际由前端控制"""
        return ""

    def vote(self, game_state: Dict) -> Optional[int]:
        """返回 None，实际由前端控制"""
        return None

    def night_action(self, game_state: Dict, **kwargs) -> Optional[Dict[str, Any]]:
        """返回 None，实际由前端控制"""
        return None
