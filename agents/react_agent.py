"""ReAct Werewolf Agent - 多智能体核心

speak()/vote()/night_action() 均使用 ReAct 推理 + 工具辅助决策
支持策略记忆、信念追踪和目标规划
"""
import re
from typing import Optional, Dict, Any, List

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from .base_agent import BaseAgent
from memory.memory_manager import AgentMemory
from memory.inference_engine import InferenceEngine
from agents.tools import create_tools_for_role
from agents.personalities import get_personality_prompt
from agents.strategies import get_strategy
from utils.logger import get_logger


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

    - speak()/vote()/night_action(): 均使用 LangGraph ReAct 推理 + 工具辅助
    - 策略记忆: 跨轮次持久化推理结论和目标
    - 信念追踪: 对每个玩家形成结构化信念
    - 目标规划: 每轮设定目标，推理围绕目标展开
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
        self._agent = None  # ReAct Agent（用于vote/night_action）
        self._speak_agent = None  # ReAct Agent（用于speak）

    # ==================== 通用辅助方法 ====================

    @staticmethod
    def _build_rules_context() -> str:
        """游戏规则概述 — 注入所有 system prompt"""
        return """【本局狼人杀规则 - 必须遵守】
强制规则：
1. 狼人每夜必须刀一个人，不允许空刀，没有空刀的机制
2. 女巫解药毒药各一瓶，每夜最多用一瓶
3. 预言家每夜必须查验一个人

一般规则：
- 胜利：狼人数>好人数→狼赢；狼人数=好人数且好人全是村民→狼赢；狼人全灭→好人赢
- 回合：夜晚(狼→预→女)→白天发言→投票→循环
- 投票：实际投票人数<存活人数/3时跳过；否则最高票者淘汰并公布身份
- 夜晚死亡不公布身份，白天投票出局公布身份
- 平票→PK发言→重投，三轮平票无人出局；可弃权
- 发言顺序：从死者下家开始，无人死亡从1号开始"""

    def _get_current_goals(self) -> str:
        """从策略记忆中提取当前目标"""
        active_plans = self.memory.strategic_memory.get_notes(category="plan", limit=3)
        if active_plans:
            lines = []
            for note in active_plans:
                lines.append(f"- {note.content}")
            return "\n你的当前目标和策略:\n" + "\n".join(lines)
        return ""

    def _get_belief_report(self) -> str:
        """获取信念报告"""
        report = self.memory.belief_tracker.format_belief_report()
        if report and report != "暂无玩家信念判断。":
            return f"\n你对各玩家的判断:\n{report}"
        return ""

    def _build_recommended_steps(self, action_type: str) -> str:
        """构建推荐的工具使用步骤"""
        if action_type == "speak":
            return """建议步骤（工具调用在后台进行，不对外输出）：
1. 先用 recall_strategy 回忆你之前的策略和目标
2. 用工具收集信息（review_game_history, check_suspicion_levels, analyze_player_speech 等）
3. 如有新的推理结论，用 record_strategy_note 记录
4. 最后回复纯发言文本"""
        elif action_type == "vote":
            return """建议步骤：
1. 先用 recall_strategy 回忆你的策略
2. 回顾本轮发言（review_game_history）
3. 检查你对各玩家的信念（check_suspicion_levels）
4. 确保投票与你的发言立场一致
5. 回复一个玩家编号，或回复"弃权"跳过"""
        else:  # night_action
            return """建议步骤：
1. 先用 recall_strategy 回忆你的策略
2. 用工具分析局势
3. 如果有新的推理结论，用 record_strategy_note 记录
4. 执行你的夜晚行动"""

    def _log_tool_calls(self, messages, context: str = "agent"):
        """将 Agent 工具调用写入日志文件"""
        logger = get_logger()
        call_count = 0
        for msg in messages:
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    call_count += 1
                    name = tc.get('name', '?')
                    args = tc.get('args', {})
                    logger.tool_call(name, args, agent_id=self.id,
                                     agent_role=self.role, action=context)
            elif isinstance(msg, ToolMessage):
                logger.tool_result(
                    str(msg.content) if msg.content else '(empty)',
                    agent_id=self.id, agent_role=self.role, action=context,
                )
        if call_count > 0:
            logger.tool_summary(call_count, agent_id=self.id,
                                agent_role=self.role, action=context)

    # ==================== speak: 两阶段架构 ====================
    #
    # 阶段1 - ReAct Agent 推理: 用工具收集信息、分析局势、更新策略记忆
    # 阶段2 - 直接 LLM 调用:   基于推理结果，生成纯发言文本
    #
    # 为什么这样设计：ReAct Agent 在最终回复中经常混入思考过程，
    # 因为 LLM 将"内部推理"和"对外发言"放在同一轮输出中。将两者分离后，
    # 阶段2 的 LLM 调用没有工具、没有 ReAct 循环，只做一个简单任务：
    # "根据分析结果，说出你的发言"。格式控制比 ReAct 的最终输出可靠得多。

    def _build_speak_agent(self):
        """创建阶段1的 ReAct Agent（仅用于推理+工具调用，不负责发言）"""
        from utils.llm_client import get_llm_client
        client = get_llm_client()
        llm = client.llm

        self._speak_agent = create_react_agent(
            model=llm,
            tools=self.tools,
            prompt=self._build_speak_react_prompt(),
        )

    def _build_speak_react_prompt(self) -> str:
        """阶段1 System Prompt — 只做分析，不输出发言"""
        personality_prompt = get_personality_prompt(self.personality)
        role_guidance = self.strategy.get_role_guidance()

        return f"""{personality_prompt}

========================================
身份：{self.id}号玩家，角色{self.role}
========================================
{role_guidance}

{self._build_rules_context()}

你的任务：使用工具收集信息并分析本轮局势。
重要：你不会直接发言。发言将在后续步骤由专门的发言模块生成。

执行步骤：
1. recall_strategy — 回忆之前的策略和目标
2. review_game_history — 查看游戏历史和发言记录
3. check_suspicion_levels — 了解各玩家嫌疑度
4. analyze_player_speech — 分析关键玩家的发言
5. record_strategy_note — 记录新的推理结论
6. update_player_belief — 更新对玩家的判断

最后用一两句自然的内心独白说说你的想法。
比如："我觉得2号可疑，他昨天投得没道理"、"先听听再说，现在信息还不够"。

重要：不要自己编造别人没说过的话。"""

    def _extract_internal_monologue(self, messages) -> str:
        """从 Phase 1 消息中提取内部独白（最后 AIMessage 的非工具内容）"""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                if not hasattr(msg, 'tool_calls') or not msg.tool_calls:
                    return msg.content.strip()
                if msg.content and len(msg.content.strip()) > 10:
                    return msg.content.strip()
        # 回退：取最后一条有内容的 AIMessage
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content.strip()[:500]
        return ""

    def _generate_clean_speech(self, task_description: str, internal_monologue: str,
                                game_state: dict, kwargs: dict) -> str:
        """阶段2 — 直接 LLM 调用，生成纯发言（无工具、无 ReAct）"""
        from utils.llm_client import get_llm_client
        client = get_llm_client()
        llm = client.llm

        personality_prompt = get_personality_prompt(self.personality, self.id)
        role_guidance = self.strategy.get_role_guidance()
        personality_guide = self._get_personality_speaking_guide()
        speech_length_guide = self._get_speech_length_guide()

        inner_thoughts = ""
        if internal_monologue and internal_monologue.strip():
            inner_thoughts = f"\n刚才你自己在心里想了想，得出的感觉是：{internal_monologue}"

        system = f"""{personality_prompt}

{role_guidance}

{self._build_rules_context()}

{personality_guide}

{speech_length_guide}
{inner_thoughts}

现在轮到你发言了。想象你正坐在桌子边，看着其他玩家，说出你想说的话。
发言自然一点，控制在200字以内。"""

        user = task_description + "\n\n直接说出你的发言："

        try:
            response = llm.invoke([
                SystemMessage(content=system),
                HumanMessage(content=user),
            ])
            text = response.content.strip() if response.content else ""
            return self._clean_speech_output(text)
        except Exception as e:
            get_logger().error(f"_generate_clean_speech: {type(e).__name__}: {e}",
                               agent_id=self.id, agent_role=self.role)
            return ""

    def _clean_speech_output(self, text: str) -> str:
        """安全网：清理发言中的思考前缀和元语言（针对阶段2的意外输出）"""
        if not text:
            return text

        # 移除常见思考前缀
        leading_patterns = [
            r'^(好了?[，,]?\s*)(现在\s*)?我\s*(来|先)?\s*(说[说两句]*|发言|讲话|开口)[。，,]*\s*',
            r'^(好的?[，,]?\s*)(那\s*)?我\s*(发言|说话|来讲)[了啦][。，,]*\s*',
            r'^(行|好|嗯|OK)[，,]\s*(那\s*)?我\s*(发言|说话|来说|来讲)[了啦]?[。，,]*\s*',
            r'^作为(村民|狼人|预言家|女巫|好人|坏人)[，,]\s*我[要会想].*?[。，]\s*',
            r'^我[的要会想][把要会].*?(搅浑|引导|制造|带节奏|伪装|策略).*?[。，]\s*',
            r'^我[的要会想]策略[是：:].*?[。，]\s*',
            r'^(好了?[，,]?\s*)(现在\s*)?我\s*(的)?\s*(分析|推理|判断|结论|想法)(是|如下)[：:]*\s*',
            r'^(根据|基于|通过)\s*(工具|查询|分析|信息).*?[。，,]\s*',
            r'^(我的\s*)?(目标|计划)(是|：).*?[。，,]\s*',
            r'^本轮\s*(分析|推理|判断|结论|策略).*?[。，,]\s*',
        ]

        for pattern in leading_patterns:
            cleaned = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
            if cleaned != text and len(cleaned) >= 5:
                return cleaned.strip()

        # 超长文本尝试找发言分隔点
        if len(text) > 200:
            split_markers = [
                r'(?:^|\n)\s*(?:发言[：:]|最终发言[：:]|说话[：:])\s*',
            ]
            for marker in split_markers:
                parts = re.split(marker, text, maxsplit=1, flags=re.IGNORECASE)
                if len(parts) > 1:
                    candidate = parts[-1].strip()
                    if 10 <= len(candidate) <= 200:
                        return candidate

        return text.strip()

    def _invoke_speak_agent(self, task_description: str, game_state: dict = None,
                            kwargs: dict = None, phase2_user_message: str = None) -> str:
        """两阶段发言：
        阶段1 — ReAct Agent 用工具分析局势（不生成发言）
        阶段2 — 直接 LLM 调用生成纯发言
        """
        game_state = game_state or {}
        kwargs = kwargs or {}
        if phase2_user_message is None:
            phase2_user_message = task_description
        try:
            if self._speak_agent is None:
                self._build_speak_agent()

            # === 阶段1: ReAct Agent 推理 + 工具调用 ===
            logger = get_logger()
            logger.phase("阶段1: ReAct推理开始", agent_id=self.id,
                         agent_role=self.role, action="speak")
            result = self._speak_agent.invoke({
                "messages": [HumanMessage(content=task_description)]
            })
            messages = result.get("messages", [])
            self._log_tool_calls(messages, "speak")

            # === 阶段2: 提取内部独白，直接 LLM 生成发言 ===
            logger.phase("阶段2: 生成发言", agent_id=self.id,
                         agent_role=self.role, action="speak")
            internal_monologue = self._extract_internal_monologue(messages)
            speech = self._generate_clean_speech(
                phase2_user_message, internal_monologue, game_state, kwargs
            )

            if speech:
                logger.speak_result(speech, agent_id=self.id,
                                    agent_role=self.role)
                return speech
            else:
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        cleaned = self._clean_speech_output(msg.content.strip())
                        if cleaned:
                            return cleaned
                return ""
        except Exception as e:
            get_logger().error(f"_invoke_speak_agent: {type(e).__name__}: {e}",
                               agent_id=self.id, agent_role=self.role)
            return ""

    def speak(self, game_state: dict, **kwargs) -> str:
        """生成发言 - 两阶段架构：ReAct 推理 + 直接 LLM 生成"""
        self.game_state_provider.set_state(game_state)
        day = game_state.get("day", 1)
        alive = game_state.get("alive_players", [])
        round_num = kwargs.get("round_num", 1)
        previous_speeches = kwargs.get("previous_speeches", [])

        # 日志轮次：特殊轮次不显示"第99轮"等内部值
        if round_num >= 99:
            get_logger().set_context(day=day, phase={99: "PK发言", 100: "平票后发言"}.get(round_num, "白天"))
        else:
            get_logger().set_context(day=day, phase="白天", round=round_num)

        # 本轮已发言 — 区分自己和他人，避免身份混淆
        current_round_speeches = ""
        if previous_speeches:
            lines = []
            for s in previous_speeches:
                pid = s.get('player_id', '?')
                content = s.get('content', '')
                if pid == self.id:
                    lines.append(f"你刚才说：{content}")
                else:
                    lines.append(f"{pid}号说：{content}")
            current_round_speeches = "\n前面说过话的人：\n" + "\n".join(lines)

        if day == 1 and round_num == 1:
            day_guidance = self._get_day1_round1_guidance()
        elif day == 1:
            day_guidance = "第一天信息还不多。"
        else:
            day_guidance = f"第{day}天了，根据之前的发言和投票来分析。"

        # Day 1 时间锚：防止LLM说"昨天"
        day_note = ""
        if day == 1:
            day_note = '\n注意：这是第一天，还没有「昨天」。不要提昨天的事。'

        alive_str = "、".join(f"{p}号" for p in alive)

        # 本局信息
        all_roles = game_state.get("player_roles", {})
        num = game_state.get("num_players", len(alive))
        role_counts = {}
        for r in all_roles.values():
            role_counts[r] = role_counts.get(r, 0) + 1
        role_summary = ", ".join(f"{r}{c}个" for r, c in sorted(role_counts.items()))
        game_info = f"本局共{num}人，角色配置：{role_summary}。"

        # ===== Phase 1 task: 给 ReAct Agent（含分析上下文）=====
        current_goals = self._get_current_goals()
        belief_report = self._get_belief_report()

        phase1_task = f"""第{day}天第{round_num}轮发言，存活：{alive_str}。你是{self.id}号。

{game_info}

{current_round_speeches}

{day_guidance}
{current_goals}
{belief_report}

{self._build_recommended_steps("speak")}"""

        # ===== Phase 2 message: 给发言生成（只含游戏上下文，不含分析）=====
        phase2_user_message = f"""第{day}天第{round_num}轮发言，存活：{alive_str}。{day_note}

{current_round_speeches}

{day_guidance}"""

        try:
            response = self._invoke_speak_agent(
                phase1_task, game_state, kwargs, phase2_user_message
            )
            if not response:
                get_logger().error("speak: 返回空，回退到策略发言",
                                   agent_id=self.id, agent_role=self.role)
                return self.strategy.generate_speech(self.memory, game_state, self.personality)
            return response
        except Exception as e:
            get_logger().error(f"speak: {type(e).__name__}: {e}",
                               agent_id=self.id, agent_role=self.role)
            return self.strategy.generate_speech(self.memory, game_state, self.personality)

    # ==================== vote/night_action: ReAct推理 ====================

    def _build_agent(self):
        """创建 LangGraph ReAct Agent（用于 vote/night_action）"""
        from utils.llm_client import get_llm_client
        client = get_llm_client()
        llm = client.llm

        self._agent = create_react_agent(
            model=llm,
            tools=self.tools,
            prompt=self._build_react_prompt(),
        )

    def _build_react_prompt(self) -> str:
        """构建 vote/night_action ReAct Agent 的 system prompt"""
        personality_prompt = get_personality_prompt(self.personality, self.id)
        role_guidance = self.strategy.get_role_guidance()

        return f"""{personality_prompt}

{role_guidance}

{self._build_rules_context()}

你可以使用策略记忆系统跨轮次保存和回忆你的推理结论。
引用别人发言时必须如实复述，不要编造别人没说过的话。直接说"X号"就行。"""

    def _invoke_agent(self, task_description: str, context: str = "agent") -> str:
        """调用 ReAct Agent 执行推理循环"""
        try:
            if self._agent is None:
                self._build_agent()
            get_logger().phase(f"ReAct推理开始", agent_id=self.id,
                               agent_role=self.role, action=context)
            result = self._agent.invoke({
                "messages": [HumanMessage(content=task_description)]
            })
            messages = result.get("messages", [])
            self._log_tool_calls(messages, context)
            for msg in reversed(messages):
                if hasattr(msg, 'content') and msg.content and isinstance(msg, AIMessage):
                    return msg.content
            return ""
        except Exception as e:
            get_logger().error(f"_invoke_agent: {type(e).__name__}: {e}",
                               agent_id=self.id, agent_role=self.role)
            return ""

    def vote(self, game_state: dict, **kwargs) -> Optional[int]:
        """ReAct推理投票 + 策略记忆"""
        self.game_state_provider.set_state(game_state)
        day = game_state.get("day", 1)
        alive = game_state.get("alive_players", [])
        # 平票重投时只能投平票候选人
        tie_options = kwargs.get("vote_options")
        candidates = [p for p in (tie_options if tie_options else alive) if p != self.id]

        get_logger().set_context(day=day, phase="投票")

        # 注入策略记忆和信念
        current_goals = self._get_current_goals()
        belief_report = self._get_belief_report()

        # 获取本轮自己的发言（确保投票与发言一致）
        my_speech = ""
        speeches_this_round = self.memory.get_history(event_type="speak", day=day)
        if not speeches_this_round:
            speeches_this_round = self.memory.get_history(event_type="speak")
        for s in (speeches_this_round or []):
            if s.metadata.get('player_id') == self.id:
                my_speech = s.content
                break

        # 队友提醒（告知但不强制）
        teammate_reminder = ""
        wolf_teammates = kwargs.get("wolf_teammates", [])
        if self.role == "狼人" and wolf_teammates:
            others = [t for t in wolf_teammates if t != self.id]
            if others:
                teammate_reminder = f"\n你的狼队友是: {', '.join(f'{t}号' for t in others)}。"

        task = f"""你是{self.id}号玩家。

现在是投票阶段。存活: {', '.join([f'{p}号' for p in alive])}，可投: {candidates}。{teammate_reminder}
{current_goals}
{belief_report}

你本轮发言说的是：「{my_speech}」"""

        if my_speech:
            task += """

上面是你本轮说的话。想想你刚刚表态了谁可疑、谁可信，投票时自然会投那个你觉得最像狼的人。"""
        else:
            task += """

你本轮没有发言记录，根据嫌疑判断来投票。"""

        # 弃权提示：仅首轮投票提供，平票重投时不建议弃权
        tie_break = kwargs.get("vote_options")
        if tie_break:
            task += f"""

现在是平票重投，你只能在 {tie_break} 中选择一个投票，不能投其他人。"""
        else:
            task += """

你可以投票，也可以选择弃权（回复"弃权"），但如果有一定的线索，请不要轻易选择弃权，投票是决定胜利的重要手段，实在没有线索时再选择弃权。"""

        task += f"""

{self._build_recommended_steps("vote")}"""

        response = self._invoke_agent(task, "vote")
        target = self._parse_vote_target(response, candidates)

        if target == -1:
            # 主动弃权
            return None
        if target is None:
            wolf_teammates = kwargs.get("wolf_teammates", [])
            target = self.strategy.suggest_vote(self.memory, alive, wolf_teammates)

        return target

    def night_action(self, game_state: dict, **kwargs) -> Optional[Dict[str, Any]]:
        """ReAct推理执行夜晚行动"""
        self.game_state_provider.set_state(game_state)
        alive = game_state.get("alive_players", [])

        # 获取天数信息，用于策略决策
        day = game_state.get("day", 1)
        kwargs["day"] = day

        get_logger().set_context(day=day, phase="夜晚")

        # 注入策略记忆和信念
        current_goals = self._get_current_goals()
        belief_report = self._get_belief_report()

        identity_reminder = f"【你是{self.id}号玩家】"

        task_map = {
            "狼人": f"{identity_reminder}\n现在是夜晚阶段。你是狼人，存活玩家: {', '.join([f'{p}号玩家' for p in alive])}。\n注意：必须刀一个人。选择你要击杀的目标。回复格式: 杀X号\n{current_goals}\n{belief_report}",
            "预言家": f"{identity_reminder}\n现在是夜晚阶段。你是预言家，存活玩家: {', '.join([f'{p}号玩家' for p in alive])}。使用工具分析，然后选择一个要查验的人。回复格式: 查X号\n{current_goals}\n{belief_report}",
            "女巫": f"{identity_reminder}\n现在是夜晚阶段。你是女巫。使用工具分析，然后决定是否使用药水。\n{current_goals}\n{belief_report}",
            "村民": "现在是夜晚阶段。你是村民，没有夜晚行动。回复: 无行动",
        }

        task = task_map.get(self.role, "现在是夜晚阶段，你没有特殊行动。")
        task += f"\n\n{self._build_recommended_steps('night_action')}"

        response = self._invoke_agent(task, "night")
        action = self._parse_night_action(response, alive)

        if action is None:
            action = self.strategy.suggest_night_action(self.memory, alive, kwargs)

        return action

    def _get_day1_round1_guidance(self) -> str:
        """根据人格返回第一天第一轮的发言指导"""
        guides = {
            "rational": "第一天第一轮，大家都还没什么信息。你可以说说对平安夜的看法，不用急着指认谁。",
            "agitative": "第一天第一轮，信息少正好可以带节奏。先抛点话头出来试探一下。",
            "conservative": "第一天第一轮，你本来就谨慎，现在更不用急着说话，先听听。",
            "impulsive": "第一天第一轮，想说什么就说，怕啥。第一感觉说出来就完了。",
            "slacker": "第一天第一轮，随便说句就行，信息太少也分析不出啥。",
        }
        return guides.get(self.personality, guides["rational"])

    def _get_personality_speaking_guide(self) -> str:
        """根据人格返回不同的语气指导（带对话示例）"""
        guides = {
            "rational": (
                "你说话有条理但不啰嗦，一次发言就抓一个重点。比如'2号你昨天投1号今天又说1号不像狼，这不矛盾吗？'。\n"
                "别把每个人的发言都点评一遍，挑你觉得最可疑或最关键的一个人说就行。"
            ),
            "agitative": (
                "你喜欢带节奏、制造话题。比如'你们不觉得4号今天反常吗？平时话挺多的今天一句不说'。\n"
                "你会把矛头引到别人身上，用反问句逼对方回应。说的话听着有道理但实质是在搅浑水。"
            ),
            "conservative": (
                "你很谨慎，不轻易表态。比如'先不急着投吧，再看看'、'这个不好说，信息还不够'。\n"
                "别人吵起来你就在旁边观察，不插嘴。被追问就回避，不把话说死。"
            ),
            "impulsive": (
                "你说话直来直去，不过脑子。比如'2号肯定有问题！我就是觉得'、'你别解释了，越解释越像'。\n"
                "想到什么说什么，说错了也无所谓，可能后面又改了。怼人很直接，这反而让你看起来不像在演。"
            ),
            "slacker": (
                "你能少说就少说。通常就一两句：'嗯……没什么想法，你们说吧'、'都行，我跟你们投'。\n"
                "你不是完全没看法，只是懒得说太多。投票时还是会认真选一下。"
            ),
        }
        return guides.get(self.personality, guides["rational"])

    def _get_speech_length_guide(self) -> str:
        """根据人格返回不同的发言篇幅指导（软性要求）"""
        guides = {
            "rational": "发言简明扼要，说清楚最想怀疑或信任的那个人就行，不用面面俱到。",
            "agitative": "你话比较多，喜欢带节奏，可以多说几句。",
            "conservative": "你不太爱说话，发言短一点，简单表达就行。",
            "impulsive": "你想到什么说什么，不用组织太多语言。",
            "slacker": "你特别不爱说话，能少说就少说，一两句应付一下。",
        }
        return guides.get(self.personality, "发言自然就好。")

    # ==================== 解析工具 ====================

    def _parse_vote_target(self, response: str, candidates: list) -> Optional[int]:
        """解析投票目标。返回 -1=弃权, None=解析失败, int=目标玩家编号"""
        if not response:
            return None
        # 检测弃权
        if re.search(r'弃权|不投|跳过|pass|skip|abstain', response, re.IGNORECASE):
            return -1
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
