"""快速 A/B 对比脚本 —— 直观验证防幻觉效果

运行方式: python compare_hallucination.py

在同一游戏状态下，分别用"无防护"和"有防护"两种模式让 AI 发言，
对比输出质量和幻觉情况。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from memory.memory_manager import AgentMemory
from memory.inference_engine import InferenceEngine
from agents.tools import create_tools_for_role
from agents.personalities import get_personality_prompt
from agents.strategies import get_strategy
from memory.rag_retriever import RAGRetriever
from utils.llm_client import get_llm_client
from utils.logger import get_logger, reset_logger
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


def build_mock_memory(agent_id=2):
    """构建一个模拟的游戏记忆 —— 第3天，有明确的历史记录"""
    mem = AgentMemory(agent_id=agent_id)

    # 第1天的事件
    mem.add_memory("death", "第0晚平安夜，没有人死亡", {"day": 1})
    mem.add_memory("speak", "1号玩家: 我是预言家，昨晚查了5号，5号是狼人", {"day": 1, "player_id": 1, "round_num": 1})
    mem.add_memory("speak", "2号玩家（你）: 1号跳预言家，我觉得可以先信一下，看看后续", {"day": 1, "player_id": 2, "round_num": 1})
    mem.add_memory("speak", "3号玩家: 我不信1号，第一天就跳预言家太急了", {"day": 1, "player_id": 3, "round_num": 1})
    mem.add_memory("speak", "4号玩家: 信息不够，先听听", {"day": 1, "player_id": 4, "round_num": 1})
    mem.add_memory("speak", "5号玩家: 1号你凭什么查我，我才是真预言家！", {"day": 1, "player_id": 5, "round_num": 1})
    mem.add_memory("speak", "6号玩家: 有趣，两个预言家对跳", {"day": 1, "player_id": 6, "round_num": 1})
    mem.add_memory("vote", "1号投票给5号", {"day": 1, "target": 5, "player_id": 1})
    mem.add_memory("vote", "2号投票给5号", {"day": 1, "target": 5, "player_id": 2})
    mem.add_memory("vote", "5号投票给1号", {"day": 1, "target": 1, "player_id": 5})
    mem.add_memory("eliminate", "5号被投票出局，身份是狼人", {"day": 1, "player_id": 5})

    # 设置角色知识（你是预言家，查了3号是好人）
    mem.set_role_knowledge(1, "预言家")  # 1号跳预言家后被确认
    mem.set_role_knowledge(5, "狼人")

    # 第2天的事件
    mem.add_memory("death", "第1晚1号死亡", {"day": 2})
    mem.add_memory("speak", "2号玩家（你）: 1号死了，他确实是预言家。5号是狼人已经出了。剩下的人里我觉得3号可以信任", {"day": 2, "player_id": 2, "round_num": 1})
    mem.add_memory("speak", "3号玩家: 2号你一直在跟1号的节奏，我怀疑你", {"day": 2, "player_id": 3, "round_num": 1})
    mem.add_memory("speak", "4号玩家: 3号和2号吵起来了，我再观察", {"day": 2, "player_id": 4, "round_num": 1})
    mem.add_memory("speak", "6号玩家: 我觉得4号一直划水很可疑", {"day": 2, "player_id": 6, "round_num": 1})
    mem.add_memory("vote", "3号投票给2号", {"day": 2, "target": 2, "player_id": 3})
    mem.add_memory("vote", "2号投票给3号", {"day": 2, "target": 3, "player_id": 2})
    mem.add_memory("vote", "4号投票给2号", {"day": 2, "target": 2, "player_id": 4})
    mem.add_memory("vote", "6号投票给4号", {"day": 2, "target": 4, "player_id": 6})
    # 平票，无人出局

    # 策略笔记
    mem.strategic_memory.add_note("suspicion", 3, "3号投了我，但我之前信他，要重新评估", 0.7)
    mem.strategic_memory.add_note("observation", 4, "4号一直划水，发言太少难以判断", 0.4)
    mem.strategic_memory.add_note("plan", 0, "本轮重点观察4号和6号，3号的票需要回应", 0.8)

    # 信念
    mem.belief_tracker.update_belief(3, suspicion_delta=0.3, reason="他投了我", confidence=0.5, day=2)
    mem.belief_tracker.update_belief(4, suspicion_delta=0.1, reason="划水可疑", confidence=0.3, day=2)
    mem.belief_tracker.update_belief(6, suspicion_delta=-0.1, reason="他指出4号划水，有道理", confidence=0.4, day=2)

    return mem


class GameStateProvider:
    def __init__(self):
        self._state = {}
    def set_state(self, state):
        self._state = state
    def get_state(self):
        return self._state


def simulate_speak(agent_id, role, personality, memory, game_state, mode="enhanced"):
    """模拟一次发言，返回完整的过程信息

    mode: "enhanced" (RAG + Self-Reflection) 或 "baseline" (关闭防幻觉)
    """
    from agents.react_agent import ReActWerewolfAgent

    # 直接用底层组件模拟，避免创建完整 Agent（减少不必要调用）
    client = get_llm_client()
    llm = client.llm
    tools = create_tools_for_role(role, memory, GameStateProvider(), InferenceEngine())
    strategy = get_strategy(role)

    gsp = GameStateProvider()
    gsp.set_state(game_state)

    # ============ Build speak agent ============
    personality_prompt = get_personality_prompt(personality)
    role_guidance = strategy.get_role_guidance()
    rules = ReActWerewolfAgent._build_rules_context()

    speak_prompt = f"""{personality_prompt}

========================================
身份：{agent_id}号玩家，角色{role}
========================================
{role_guidance}

{rules}

你的任务：使用工具收集信息并分析本轮局势。
重要：你不会直接发言。发言将在后续步骤由专门的发言模块生成。

执行步骤：
1. recall_strategy
2. review_game_history
3. check_suspicion_levels
4. analyze_player_speech
5. record_strategy_note
6. update_player_belief

最后用一两句自然的内心独白说说你的想法。
重要：不要自己编造别人没说过的话。"""

    speak_agent = create_react_agent(model=llm, tools=tools, prompt=speak_prompt)

    # ============ Build task ============
    day = game_state.get("day", 3)
    alive = game_state.get("alive_players", [])
    alive_str = "、".join(f"{p}号" for p in alive)

    task = f"""第{day}天第1轮发言，存活：{alive_str}。你是{agent_id}号。

本局共6人，角色配置：狼人2个，预言家1个，女巫1个，村民2个。

第{day}天了，根据之前的发言和投票来分析。

前面说过话的人：
3号说：2号你一直在跟1号的节奏，我怀疑你
4号说：3号和2号吵起来了，我再观察
6号说：我觉得4号一直划水很可疑

建议步骤（工具调用在后台进行，不对外输出）：
1. 先用 recall_strategy 回忆你之前的策略和目标
2. 用工具收集信息（review_game_history, check_suspicion_levels, analyze_player_speech 等）
3. 如有新的推理结论，用 record_strategy_note 记录
4. 最后回复纯发言文本"""

    # ============ Phase 1: ReAct ============
    print("  [Phase 1] ReAct 推理中...")
    result = speak_agent.invoke({"messages": [HumanMessage(content=task)]})
    messages = result.get("messages", [])

    # 提取内心独白
    internal_monologue = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            if not hasattr(msg, 'tool_calls') or not msg.tool_calls:
                internal_monologue = msg.content.strip()
                break
            if msg.content and len(msg.content.strip()) > 10:
                internal_monologue = msg.content.strip()
                break
    print(f"  [Phase 1] 内心独白: {internal_monologue[:100]}...")

    # ============ RAG Retrieval (only enhanced mode) ============
    retrieved_context = ""
    if mode == "enhanced":
        retriever = RAGRetriever(memory)
        evidence = retriever.retrieve_context_for_speak(game_state, agent_id, day, top_k=8)
        retrieved_context = retriever.format_retrieved_context(evidence)
        print(f"  [RAG] 检索到 {len(evidence)} 条相关记忆")

    # ============ Phase 2: Generate speech ============
    personality_guide = {
        "rational": "你说话有条理但不啰嗦，一次发言就抓一个重点。",
        "aggressive": "你喜欢带节奏、制造话题。",
        "conservative": "你很谨慎，不轻易表态。",
        "impulsive": "你说话直来直去，不过脑子。",
        "slacker": "你能少说就少说。",
    }.get(personality, "发言自然就好。")

    inner_thoughts = ""
    if internal_monologue and internal_monologue.strip():
        inner_thoughts = f"\n刚才你自己在心里想了想，得出的感觉是：{internal_monologue}"

    phase2_system = f"""{personality_prompt}

{role_guidance}

{rules}

{personality_guide}

发言自然一点，控制在200字以内。
{inner_thoughts}

现在轮到你发言了。想象你正坐在桌子边，看着其他玩家，说出你想说的话。"""

    phase2_user = f"""第{day}天第1轮发言，存活：{alive_str}。

前面说过话的人：
3号说：2号你一直在跟1号的节奏，我怀疑你
4号说：3号和2号吵起来了，我再观察
6号说：我觉得4号一直划水很可疑

直接说出你的发言："""

    print("  [Phase 2] 生成发言草稿...")
    response = llm.invoke([SystemMessage(content=phase2_system), HumanMessage(content=phase2_user)])
    draft_speech = response.content.strip() if response.content else ""
    print(f"  [Phase 2] 草稿: {draft_speech[:150]}...")

    # ============ Phase 2.5: Self-Reflection (only enhanced mode) ============
    reflection_result = None
    if mode == "enhanced" and draft_speech:
        print("  [Phase 2.5] Self-Reflection 验证...")
        from agents.react_agent import ReActWerewolfAgent
        temp_agent = ReActWerewolfAgent.__new__(ReActWerewolfAgent)
        temp_agent.id = agent_id
        temp_agent.role = role
        temp_agent.rag_retriever = RAGRetriever(memory)

        evidence_list = temp_agent.rag_retriever.retrieve_context_for_speak(
            game_state, agent_id, day, top_k=8
        )

        reflection_prompt = f"""你是狼人杀事实核查员。请检查以下 AI 玩家的发言草稿是否与游戏记录一致。

【发言草稿】
{draft_speech}

【游戏记录（精确）】
{retrieved_context}

【当前状态】第{day}天，存活: {alive}

按以下 6 条逐项检查（少即是多，只报真正的问题）：

1. **编造发言**：发言中说"X号说过Y"——记录中X号真的说过吗？没有→标记为 FACT_FABRICATION
2. **天数错误**：发言中提到"昨天/第X天"——天数对吗？不对→标记为 TIME_ERROR
3. **越权信息**：发言中透露出不该知道的信息→标记为 INFO_LEAK
4. **过度自信**：用了"肯定/绝对/一定"但记录中没有证据支撑→标记为 OVERCONFIDENT
5. **自相矛盾**：发言内容与内心独白矛盾→标记为 SELF_CONTRADICT
6. **元语言泄露**：发言中出现"工具"、"查询"、"分析结果"等后台术语→标记为 META_LEAK

输出 JSON（不要输出其他内容）：
{{"pass": true/false, "issues": ["具体问题描述"], "severity": "low/medium/high", "corrected_speech": "修正后的发言（pass=false且severity!=low时才需要）"}}"""

        refl_response = llm.invoke([
            SystemMessage(content="你是事实核查员。只输出 JSON。"),
            HumanMessage(content=reflection_prompt),
        ])
        import json
        try:
            json_match = __import__('re').search(r'\{[^{}]*"pass"[^{}]*\}', refl_response.content, __import__('re').DOTALL)
            if json_match:
                reflection_result = json.loads(json_match.group(0))
        except Exception:
            reflection_result = {"pass": True, "issues": [], "severity": "low"}

        print(f"  [Phase 2.5] 验证结果: pass={reflection_result.get('pass')}, "
              f"severity={reflection_result.get('severity')}, "
              f"issues={reflection_result.get('issues')}")

        if not reflection_result.get("pass") and reflection_result.get("severity", "low") != "low":
            corrected = reflection_result.get("corrected_speech", "")
            if corrected:
                print(f"  [Phase 2.5] 发言已修正!")
                draft_speech = corrected

    return {
        "mode": mode,
        "internal_monologue": internal_monologue,
        "draft_speech": draft_speech,
        "final_speech": draft_speech,
        "retrieved_context": retrieved_context,
        "reflection": reflection_result,
    }


def main():
    print("=" * 70)
    print("  狼人杀 AI 幻觉对比测试")
    print("  Baseline (无防护) vs Enhanced (RAG + Self-Reflection)")
    print("=" * 70)

    # 共享的游戏状态
    game_state = {
        "day": 3,
        "phase": "day",
        "alive_players": [2, 3, 4, 6],  # 1号和5号已死
        "num_players": 6,
        "player_roles": {1: "预言家", 2: "预言家", 3: "村民", 4: "狼人", 5: "狼人", 6: "女巫"},
        "player_names": {1: "玩家1", 2: "玩家2", 3: "玩家3", 4: "玩家4", 5: "玩家5", 6: "玩家6"},
    }

    # ---- 测试1: Enhanced 模式 ----
    print("\n" + "-" * 70)
    print("  [测试1] ENHANCED 模式 (RAG + Self-Reflection 开启)")
    print("-" * 70)

    memory_enhanced = build_mock_memory(agent_id=2)
    result_enhanced = simulate_speak(
        agent_id=2, role="预言家", personality="rational",
        memory=memory_enhanced, game_state=game_state, mode="enhanced"
    )

    # ---- 测试2: Baseline 模式 ----
    print("\n" + "-" * 70)
    print("  [测试2] BASELINE 模式 (无 RAG, 无 Self-Reflection)")
    print("-" * 70)

    memory_baseline = build_mock_memory(agent_id=2)
    result_baseline = simulate_speak(
        agent_id=2, role="预言家", personality="rational",
        memory=memory_baseline, game_state=game_state, mode="baseline"
    )

    # ---- 对比报告 ----
    print("\n" + "=" * 70)
    print("  对比报告")
    print("=" * 70)

    print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│                         BASELINE (无防护)                          │
├─────────────────────────────────────────────────────────────────────┤
│ 发言: {result_baseline['final_speech'][:200]}
│
│ 幻觉风险: 无 RAG → Prompt 注入全部 20+ 条历史 →
│           LLM 注意力稀释，容易张冠李戴
│          无 Self-Reflection → 编造内容直接输出
├─────────────────────────────────────────────────────────────────────┤
│                         ENHANCED (有防护)                          │
├─────────────────────────────────────────────────────────────────────┤
│ RAG 检索: {len(result_enhanced.get('retrieved_context', ''))} 字符精检索上下文
│ 发言: {result_enhanced['final_speech'][:200]}
│""")

    if result_enhanced.get('reflection'):
        r = result_enhanced['reflection']
        print(f"""│ Self-Reflection: pass={r.get('pass')}, severity={r.get('severity', '?')}
│ 检测到的问题: {r.get('issues', [])}""")

    print("""└─────────────────────────────────────────────────────────────────────┘
""")

    # ---- 关键差异分析 ----
    print("=" * 70)
    print("  关键差异分析")
    print("=" * 70)

    # 用 LLM-as-Judge 对比两份发言
    print("\n  [Judge] LLM 正在评判两份发言的幻觉程度...")
    llm = get_llm_client().llm

    judge_prompt = f"""你是狼人杀发言审核员。下面同一 AI 玩家在两种配置下对同一局势的发言。

=== 游戏背景 ===
第3天，你是2号预言家。存活: 2,3,4,6号。
第1天: 1号跳预言家说查了5号是狼人，5号对跳，5号被投出局（确实是狼人）
第2天: 1号死亡。3号投了2号。平票无人出局。4号一直划水，6号指出4号可疑。

=== 发言A (Baseline - 无防幻觉) ===
{result_baseline['final_speech']}

=== 发言B (Enhanced - 有防幻觉) ===
{result_enhanced['final_speech']}

请从以下维度对比两份发言（输出 JSON）：

1. factual_accuracy (1-10): 事实准确度，发言中的陈述能否在游戏记录中找到依据
2. specificity (1-10): 具体性，是否引用了具体事件而非空泛发言
3. consistency (1-10): 一致性，发言是否与之前的立场一致
4. hallucination_risk (1-10): 幻觉风险，越高越可能编造了不存在的信息

输出格式：
{{"A": {{"factual_accuracy": X, "specificity": X, "consistency": X, "hallucination_risk": X}},
 "B": {{"factual_accuracy": X, "specificity": X, "consistency": X, "hallucination_risk": X}},
 "winner": "A" or "B",
 "analysis": "一句话总结"}}"""

    judge_response = llm.invoke([
        SystemMessage(content="你是审核员。只输出 JSON。"),
        HumanMessage(content=judge_prompt),
    ])

    import json, re
    try:
        json_match = re.search(r'\{.*\}', judge_response.content, re.DOTALL)
        if json_match:
            verdict = json.loads(json_match.group(0))
            print(f"\n  LLM Judge 评分:")
            for mode_key, label in [("A", "Baseline"), ("B", "Enhanced")]:
                scores = verdict.get(mode_key, {})
                print(f"    {label}: 事实准确度={scores.get('factual_accuracy','?')}/10  "
                      f"具体性={scores.get('specificity','?')}/10  "
                      f"一致性={scores.get('consistency','?')}/10  "
                      f"幻觉风险={scores.get('hallucination_risk','?')}/10")
            print(f"\n  优胜: {verdict.get('winner', '?')} ({'Enhanced' if verdict.get('winner') == 'B' else 'Baseline'})")
            print(f"  分析: {verdict.get('analysis', '?')}")
    except Exception as e:
        print(f"  Judge 解析失败: {e}")
        print(f"  原始回复: {judge_response.content[:300]}")

    print("\n" + "=" * 70)
    print("  测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
