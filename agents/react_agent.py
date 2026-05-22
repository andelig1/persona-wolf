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

        # 1. 从记忆中提取完整上下文（包含所有夜晚行动和白天发言）
        memory_context = self.memory.format_for_prompt()  # 不限制数量，获取完整历史
        suspicion_report = self.memory.format_suspicion_report()
        role_knowledge = ""
        if self.memory.role_knowledge:
            for pid, role in self.memory.role_knowledge.items():
                role_knowledge += f"\n你查到{pid}号是{role}。"

        # 2. 本轮已发言内容（实时更新，包括人类玩家的发言）
        current_round_speeches = ""
        if previous_speeches:
            lines = []
            for s in previous_speeches:
                sname = s.get('name', f"{s.get('player_id', '?')}号")
                lines.append(f"{sname}: {s.get('content', '')}")
            current_round_speeches = "\n本轮已发言：\n" + "\n".join(lines)

        # 3. 根据天数和轮次给出不同指导
        if day == 1 and round_num == 1:
            day_guidance = self._get_day1_round1_guidance()
        elif day == 1:
            day_guidance = "第一天信息还不多，可以回应别人的发言，有依据再怀疑人。"
        else:
            day_guidance = "根据发言和投票记录分析，有依据地质疑可疑的人。"

        # 4. 构建完整 prompt
        personality_prompt = get_personality_prompt(self.personality)
        role_guidance = self.strategy.get_role_guidance()

        system_content = f"""{personality_prompt}

你的身份: {self.role}
你是 {self.id} 号玩家。
{role_guidance}

游戏历史记录（包含所有夜晚行动和白天发言）:
{memory_context}

嫌疑判断:
{suspicion_report}
{role_knowledge}
{day_guidance}"""

        # 4. 根据人格调整语气指导
        personality_guide = self._get_personality_speaking_guide()

        user_content = f"""第{day}天第{round_num}轮发言，存活玩家: {alive}。

{current_round_speeches}

{personality_guide}

目前的狼人杀的游戏规则是：
1.只有狼人、村民、女巫、预言家这四种身份角色
2.狼人每晚必须选择刀一个人，不能够自己刀自己阵营的，也不能够空刀就是不刀人
3.女巫一晚只能够使用一种药，使用了毒药就不能使用解药，使用了解药就不能够使用毒药
4.预言家存活的情况下，每一晚都可以查验一位玩家的身份

⚠️ 发言规则（严格禁止，违者视为违规）：
1. 你只能评论和引用【已发言玩家】在下面"本轮已发言"中明确展示的内容
2. 如果"本轮已发言"中没有提到某位玩家说了什么，你就不能声称那位玩家说了什么
3. 严禁提及、暗示、或假设【还未发言玩家】说了什么；不要质疑或询问"为什么x号不说话"之类的问题，因为还没轮到他们发言
4. 严禁编造、歪曲、夸大已发言玩家的原话内容
5. 游戏是顺序发言制，每个人轮流发言，轮到的人才发言

📢 核心发言准则：
本局为明牌狼人杀，所有已出局玩家身份全部公开透明。
- 你的所有发言优先做有条理身份推理加身份表明（身份表露自由策略规则）
- 推理过程必须结合已死亡玩家公开身份作为核心依据
- 仅在被其他玩家质疑、踩身份、反驳你观点时，主动加入自证话术
- 局势需要带队、理清全场逻辑时，可以主动亮明自身真实身份，带动全场好人统一逻辑、梳理狼坑

💬 发言语气 & 逻辑优化要求（改掉吵架感、发散感）：
- 禁止情绪化对线、抬杠、指责式吵架发言，摒弃口语化偏激怼人话术
- 所有怀疑、站队、点评其他玩家，必须附带清晰依据，每一个观点都要结合在场玩家言行 +出局玩家已知身份双重佐证
- 全场发言围绕同一条逻辑线推进，前后观点保持连贯统一，不随意乱改怀疑对象、不漫无目的发散乱盘人
- 发言风格偏向理性分析流，以梳理局势、理顺众人发言矛盾为主，温和博弈而非对立争吵

💬 局面判断 + 发言内容绑定规则
- 当场上玩家立场混乱、多人摇摆、局势模糊不清时，主动在发言里自然梳理投票逻辑
- 投票逻辑融入日常口语，贴合自身人设，不生硬机械；投票理由必须和你前面做出的身份推理一一对应
- 关键轮次（预言家对跳、平安夜、即将出人轮、神牌容易被扛推轮），发言必须同时包含结合死者身份的完整身份推理 + 清晰本轮投票思路
- 普通平稳轮次，精简发言，只做基础身份梳理即可

🎭 身份表露策略（权重）：
可自主灵活选择身份暴露程度，三种模式附带默认执行权重，对局中可随场面动态调整倾向
- 隐瞒身份 (30%)：全程提及自身具体神职、狼人任何身份信息，全程低调平稳表水，不主动抢视角、不主动带队，降低自身焦点度，适合前期局势不明、自身身份易被针对时使用
- 模糊身份 (45%)：仅对外统一表明自己属于好人阵营，绝不透露预言家、女巫、猎人等具体神职底牌，狼人也只伪装成普通好人立场；保留自身真实身份空间，进退灵活，适配绝大多数平稳对局轮次
- 明确亮明身份 (25%)：仅触发指定关键场景时启用：自身被多人集体质疑踩打、场上逻辑混乱无人带队、己方阵营陷入劣势、关键轮次需要稳定好人视角、保护核心好人队友时，直接公开自身真实身份带队梳理逻辑、统一投票方向
身份表露可以循序渐进，前期模糊认好人隐藏底牌，中后期根据局势变化再选择跳明真实身份

狼人阵营统一策略：全程伪装好人视角，永久隐藏狼身份，优先选择模糊好人身份表水，绝不主动暴露狼阵营

🔍 明牌局专属推理规则：
- 所有身份盘查、狼坑划分、玩家身份判定，必须优先参考已经出局玩家的公开真实身份
- 结合出局好人数量、出局狼人数量、出局神职身份，反向倒推剩余存活玩家的身份概率与行为动机
- 利用已死玩家身份核对场上玩家发言真伪，验证其他人立场是否符合阵营逻辑，以此加固自身推理可信度

🔍 分场景固定发言结构：
- 无人质疑常规发言：结合出局玩家公开身份，梳理场上玩家发言漏洞 + 行为疑点，完成身份推理即可
- 遭到他人质疑发言：先平和回应对方质疑点完成自证，再继续延续自身结合死者身份的原有逻辑推理
- 局势混乱关键轮发言：结合死者身份做身份推理 + 全场局势梳理 + 自然带出本轮统一投票逻辑
- 带队轮次发言：亮明自身身份，结合全场已公开死亡身份整合正确逻辑，引导好人统一视角、统一投票

请发言，50-100字，像真人聊天一样自然，逻辑清晰，不要像AI。可以引用之前的发言进行回应。"""

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
        day = game_state.get("day", 1)
        alive = game_state.get("alive_players", [])
        candidates = [p for p in alive if p != self.id]

        memory_context = self.memory.format_for_prompt(limit=20)
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

⚠️【关键】投票必须与本轮发言保持一致：
1. 首先，明确你在本轮发言中的立场和观点
2. 然后，查看其他玩家在本轮的发言内容
3. 如果你本轮发言中支持/认可了某位玩家，就【绝对不能】投票给那位玩家
4. 如果你本轮发言中怀疑/质疑了某位玩家，那位玩家才是合理的投票目标
5. 禁止随机投票或违背本轮发言立场的投票

示例正确逻辑：
- 如果你说"2号说得有道理"，就不能投2号
- 如果你说"3号发言很奇怪"，可以考虑投3号
- 如果你全程没有质疑任何人，就投你认为最可疑的人

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
        
        # 获取天数信息，用于策略决策
        day = game_state.get("day", 1)
        kwargs["day"] = day

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

    def _get_day1_round1_guidance(self) -> str:
        """根据人格返回第一天第一轮的发言指导"""
        guides = {
            "rational": (
                "这是第一天第一轮，大家信息都很少。\n"
                "你可以冷静分析一下场上的情况，说说自己对平安夜的看法。\n"
                "不需要急着指控别人，可以先听听大家的发言。"
            ),
            "agitative": (
                "这是第一天第一轮，信息不多但正好是你带节奏的好时机。\n"
                "你可以暗示某些人'有点奇怪'，把水搅浑。\n"
                "不需要有实质证据，先制造话题和争议。"
            ),
            "conservative": (
                "这是第一天第一轮，大家都没什么信息。\n"
                "你可以简单说两句，比如'信息太少，我先听听'。\n"
                "不要急着表态，保持观望就好。"
            ),
            "impulsive": (
                "这是第一天第一轮，凭直觉说话就行！\n"
                "你觉得谁看着不对劲就直接说，不用犹豫。\n"
                "第一感觉往往是对的，说出你的想法！"
            ),
            "slacker": (
                "这是第一天第一轮，确实没什么好说的。\n"
                "你就随便说一两句话，比如'嗯'、'信息太少了'。\n"
                "虽然划水，但投票时还是会做基本判断，帮好人阵营。"
            ),
        }
        return guides.get(self.personality, guides["rational"])

    def _get_personality_speaking_guide(self) -> str:
        """根据人格返回不同的语气和行为指导"""
        guides = {
            "rational": (
                "发言风格：冷静理性分析，像一个善于思考的真实玩家。\n"
                "说话有条理，善于分析局势，结合他人发言进行逻辑推理。\n"
                "可以质疑别人，但会给出具体理由。\n"
                "语气中性，不极端，像正常聊天。"
            ),
            "agitative": (
                "发言风格：善于煽动、制造矛盾，像一个活跃的意见领袖。\n"
                "喜欢抓住别人话里的漏洞，暗示某些人'不太对劲'。\n"
                "会把水搅浑，制造话题和争议。\n"
                "说话带节奏，敢表达立场，不害怕对立。"
            ),
            "conservative": (
                "发言风格：谨慎保守，不轻易表态，像一个稳重的老玩家。\n"
                "经常说'我再看看'、'先不急着下结论'。\n"
                "不轻易站队，给自己留有余地。\n"
                "说话平稳，不极端，不当出头鸟。"
            ),
            "impulsive": (
                "发言风格：冲动急躁，想到什么说什么，像一个直来直去的玩家。\n"
                "凭第一反应下判断，说话不过脑子。\n"
                "经常直接说'X号肯定有问题'、'我就觉得X号不对'。\n"
                "说话冲，敢怼人，不怕得罪人。"
            ),
            "slacker": (
                "发言风格：划水敷衍，说话很少，像一个休闲玩家。\n"
                "发言简短，经常就一两句话，比如'嗯'、'都行'、'信息太少了'。\n"
                "不会主动分析，但心里还是希望能帮好人赢的。\n"
                "投票时会做基本判断，不会乱投。"
            ),
        }
        return guides.get(self.personality, guides["rational"])

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
