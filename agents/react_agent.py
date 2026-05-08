"""ReAct Werewolf Agent - 多智能体核心

speak() 使用直接 LLM 调用（快速+稳定），vote()/night_action() 使用 ReAct 推理（需要工具辅助决策）
"""
import re
import random
from typing import Optional, Dict, Any, List

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from .base_agent import BaseAgent
from memory.memory_manager import AgentMemory
from memory.inference_engine import InferenceEngine
from agents.tools import create_tools_for_role
from agents.personalities import get_personality_prompt
from agents.strategies import get_strategy


class GameStateProvider:
    """可变共享引用，GameEngine在调用Agent前更新，工具读取最新状态"""

    def __init__(self):
        self._state: dict = {}

    def set_state(self, state: dict) -> None:
        self._state = state

    def get_state(self) -> dict:
        return self._state


class ReActWerewolfAgent(BaseAgent):
    """狼人杀 AI 玩家

    - speak(): 直接 LLM 调用，记忆/发言/嫌疑度直接注入 prompt（快+稳定）
    - vote()/night_action(): LangGraph ReAct 推理 + 工具辅助（决策需要深入分析）
    """

    def __init__(self, agent_id: int, role: str, personality: str, name: str = None):
        super().__init__(agent_id, role, name)
        self.personality = personality

        self.memory = AgentMemory(agent_id)
        self.game_state_provider = GameStateProvider()
        self.inference_engine = InferenceEngine()
        self.tools = create_tools_for_role(
            role, self.memory, self.game_state_provider, self.inference_engine
        )
        self.strategy = get_strategy(role)
        self._agent = None  # ReAct Agent（仅用于vote/night_action）

    # ==================== speak: 直接LLM调用 ====================

    def speak(self, game_state: dict, **kwargs) -> str:
        """生成发言 - 直接 LLM 调用，把记忆/别人发言/嫌疑度全部注入 prompt

        不走 ReAct 循环，一次 LLM 调用搞定，快且稳定。
        """
        self.game_state_provider.set_state(game_state)
        day = game_state.get("day", 1)
        alive = game_state.get("alive_players", [])
        round_num = kwargs.get("round_num", 1)
        previous_speeches = kwargs.get("previous_speeches", [])

        # 1. 从记忆中提取上下文
        memory_context = self.memory.format_for_prompt(limit=15)
        suspicion_report = self.memory.format_suspicion_report()
        role_knowledge = ""
        if self.memory.role_knowledge:
            for pid, role in self.memory.role_knowledge.items():
                role_knowledge += f"\n你查到{pid}号是{role}。"

        # 2. 本轮之前其他人的发言
        prev_speeches_text = ""
        if previous_speeches:
            lines = []
            for s in previous_speeches:
                sname = s.get('name', f"{s.get('player_id', '?')}号")
                lines.append(f"{sname}: {s.get('content', '')}")
            prev_speeches_text = "\n本轮之前大家的发言：\n" + "\n".join(lines)

        # 3. 根据天数和轮次给出不同指导
        if day == 1 and round_num == 1:
            day_guidance = ("这是第一天第一轮，昨晚刚结束，大家信息都很少。"
                            "不要凭空怀疑人或指控别人，你没有依据。"
                            "可以说中性开场白，或者回应别人的话。"
                            "如果你是预言家且查到了狼人，可以考虑跳预言家。")
        elif day == 1:
            day_guidance = "第一天信息还不多，有依据再怀疑人，可以回应别人的发言。"
        else:
            day_guidance = "根据发言和投票记录分析，有依据地质疑可疑的人。"

        # 4. 构建完整 prompt
        personality_prompt = get_personality_prompt(self.personality)
        role_guidance = self.strategy.get_role_guidance()

        system_content = f"""{personality_prompt}

你的身份: {self.role}
你是 {self.id} 号玩家。
{role_guidance}

你的记忆:
{memory_context}

嫌疑判断:
{suspicion_report}
{role_knowledge}
{day_guidance}"""

        user_content = f"""第{day}天第{round_num}轮发言，存活玩家: {alive}。
{prev_speeches_text}

请发言，50-100字，像真人聊天，不要像AI。"""

        # 5. 直接 LLM 调用
        try:
            from utils.llm_client import get_llm_client
            client = get_llm_client()
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ]
            response = client.chat(messages, temperature=0.8)
            response = response.strip()
            if len(response) > 150:
                response = response[:147] + "..."
            return response
        except Exception:
            return self.strategy.generate_speech(self.memory, game_state, self.personality)

    # ==================== vote/night_action: ReAct推理 ====================

    def _build_agent(self):
        """创建 LangGraph ReAct Agent（仅用于 vote/night_action）"""
        from utils.llm_client import get_llm_client
        client = get_llm_client()
        llm = client.llm

        self._agent = create_react_agent(
            model=llm,
            tools=self.tools,
            prompt=self._build_react_prompt(),
        )

    def _build_react_prompt(self) -> str:
        """构建 ReAct Agent 的 system prompt"""
        personality_prompt = get_personality_prompt(self.personality)
        role_guidance = self.strategy.get_role_guidance()

        role_descriptions = {
            "狼人": "你是狼人。夜晚杀人、白天伪装成好人。",
            "预言家": "你是预言家。每晚可以查验一个人的真实身份。",
            "女巫": "你是女巫。有一瓶解药和一瓶毒药，每晚只能用一瓶。",
            "村民": "你是普通村民。通过发言和投票找出狼人。",
        }
        role_desc = role_descriptions.get(self.role, "你是普通村民。")

        return f"""{personality_prompt}

你的角色信息: {role_desc}
你是 {self.id} 号玩家。
{role_guidance}

你可以使用工具来获取游戏信息，帮助你做决策。
重要规则:
- 绝不说"作为好人"
- 如果你是狼人，要伪装成好人，投票不投队友"""

    def _invoke_agent(self, task_description: str) -> str:
        """调用 ReAct Agent 执行推理循环"""
        try:
            if self._agent is None:
                self._build_agent()
            result = self._agent.invoke({
                "messages": [HumanMessage(content=task_description)]
            })
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, 'content') and msg.content:
                    return msg.content
            return ""
        except Exception:
            return ""

    def vote(self, game_state: dict, **kwargs) -> Optional[int]:
        """ReAct推理投票 + 记忆上下文"""
        self.game_state_provider.set_state(game_state)
        alive = game_state.get("alive_players", [])
        candidates = [p for p in alive if p != self.id]

        # 记忆上下文直接注入
        memory_context = self.memory.format_for_prompt(limit=10)
        suspicion_report = self.memory.format_suspicion_report()
        role_knowledge = ""
        if self.memory.role_knowledge:
            for pid, role in self.memory.role_knowledge.items():
                role_knowledge += f"\n你查到{pid}号是{role}。"

        task = f"""现在是投票阶段。存活玩家: {alive}，你可以投: {candidates}。

你的记忆:
{memory_context}

嫌疑判断:
{suspicion_report}
{role_knowledge}

请使用工具分析，然后决定投谁。只回复一个玩家编号。"""

        response = self._invoke_agent(task)
        target = self._parse_vote_target(response, candidates)

        if target is None:
            wolf_teammates = kwargs.get("wolf_teammates", [])
            target = self.strategy.suggest_vote(self.memory, alive, wolf_teammates)

        return target

    def night_action(self, game_state: dict, **kwargs) -> Optional[Dict[str, Any]]:
        """ReAct推理执行夜晚行动"""
        self.game_state_provider.set_state(game_state)
        alive = game_state.get("alive_players", [])

        # 记忆上下文
        memory_context = self.memory.format_for_prompt(limit=10)
        suspicion_report = self.memory.format_suspicion_report()
        role_knowledge = ""
        if self.memory.role_knowledge:
            for pid, role in self.memory.role_knowledge.items():
                role_knowledge += f"\n你查到{pid}号是{role}。"

        context_block = f"\n\n你的记忆:\n{memory_context}\n\n嫌疑判断:\n{suspicion_report}\n{role_knowledge}"

        task_map = {
            "狼人": f"现在是夜晚阶段。你是狼人，存活玩家: {alive}。使用工具分析，然后选择一个要击杀的好人。回复格式: 杀X号{context_block}",
            "预言家": f"现在是夜晚阶段。你是预言家，存活玩家: {alive}。使用工具分析，然后选择一个要查验的人。回复格式: 查X号{context_block}",
            "女巫": f"现在是夜晚阶段。你是女巫。使用工具分析，然后决定是否使用药水。{context_block}",
            "村民": "现在是夜晚阶段。你是村民，没有夜晚行动。回复: 无行动",
        }

        task = task_map.get(self.role, "现在是夜晚阶段，你没有特殊行动。")
        response = self._invoke_agent(task)
        action = self._parse_night_action(response, alive)

        if action is None:
            action = self.strategy.suggest_night_action(self.memory, alive, kwargs)

        return action

    # ==================== 解析工具 ====================

    def _parse_vote_target(self, response: str, candidates: list) -> Optional[int]:
        if not response:
            return None
        for n in re.findall(r'(\d+)号', response):
            num = int(n)
            if num in candidates:
                return num
        for n in re.findall(r'\d+', response):
            num = int(n)
            if num in candidates:
                return num
        return None

    def _parse_night_action(self, response: str, alive: list) -> Optional[Dict[str, Any]]:
        if not response:
            return None
        candidates = [p for p in alive if p != self.id]

        if self.role == "狼人":
            match = re.search(r'杀\s*(\d+)\s*号', response) or re.search(r'(\d+)', response)
            if match:
                target = int(match.group(1))
                if target in candidates:
                    return {"type": "kill", "target": target}

        elif self.role == "预言家":
            match = re.search(r'查\s*(\d+)\s*号', response) or re.search(r'(\d+)', response)
            if match:
                target = int(match.group(1))
                if target in candidates:
                    return {"type": "check", "target": target}

        elif self.role == "女巫":
            if re.search(r'救|解药', response):
                numbers = re.findall(r'(\d+)', response)
                if numbers:
                    return {"type": "save", "target": int(numbers[0])}
                return {"type": "save"}
            if re.search(r'毒', response):
                numbers = re.findall(r'(\d+)', response)
                if numbers:
                    target = int(numbers[0])
                    if target in candidates:
                        return {"type": "poison", "target": target}

        return None
