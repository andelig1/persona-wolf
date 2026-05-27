# 多智能体狼人杀 · ReAct 人格博弈系统
# 开发请务必查看最后的注意
> 基于多 Agent 架构的狼人杀游戏框架。每个 AI 玩家是独立的智能体，拥有记忆、工具和人格。
> **全部决策（发言/投票/夜晚行动）均使用 LangGraph ReAct 推理 + 工具辅助**，
> 其中发言采用两阶段架构（ReAct 分析 → 直接 LLM 生成）确保输出干净。

---

## 项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| `core/` | 完成 | 游戏引擎（裁判模式 + 流式 SSE）、阶段控制、胜负判定 |
| `agents/` | 完成 | ReActWerewolfAgent、HumanAgent、工具系统、人格系统、角色策略 |
| `memory/` | 完成 | AgentMemory（per-agent）、策略记忆、信念追踪、InferenceEngine |
| `utils/` | 完成 | LLM客户端（DeepSeek）、日志系统、配置管理、内容过滤 |
| `api/` | 完成 | 前后端接口层、SSE 流式推送、RESTful API |
| `frontend/` | 完成 | Web 界面（星空主题）、SSE 实时推送、观战模式 |
| `config/` | 完成 | 游戏配置（YAML） |

---

## 一、项目文件结构

```
persona-wolf/
├── core/                       # 游戏核心（裁判系统）
│   ├── game_engine.py          # 主引擎（流式 SSE + 同步双模式、发言/投票/夜晚流程、平票 PK）
│   ├── phase_controller.py     # 阶段切换（Night → Day → Vote → End）
│   ├── role_manager.py         # 角色分配
│   └── rule_checker.py         # 胜负判定

├── agents/                     # AI 玩家模块
│   ├── base_agent.py           # Agent 基类
│   ├── react_agent.py          # ReActWerewolfAgent（核心，全部决策用 ReAct）
│   ├── human_agent.py          # 人类玩家 Agent
│   ├── tools/                  # 工具系统（ReAct 推理中调用）
│   │   ├── __init__.py         # create_tools_for_role() 工厂
│   │   ├── common_tools.py     # 通用工具
│   │   ├── agent_tools.py      # Agent 主动工具（策略笔记/信念更新/目标设定/回忆）
│   │   ├── werewolf_tools.py   # 狼人工具
│   │   ├── seer_tools.py       # 预言家工具
│   │   ├── witch_tools.py      # 女巫工具
│   │   └── villager_tools.py   # 村民工具
│   ├── personalities/          # 人格系统（5种，随机分配）
│   │   ├── __init__.py         # get_personality_prompt()
│   │   ├── rational.py         # 理性型
│   │   ├── aggressive.py       # 煽动型
│   │   ├── hesitant.py         # 保守型
│   │   ├── follower.py         # 冲动型
│   │   └── slacker.py          # 划水型
│   └── strategies/             # 角色策略（LLM 失败时回退）
│       ├── __init__.py         # get_strategy() + STRATEGY_MAP
│       ├── werewolf_strategy.py
│       ├── seer_strategy.py
│       ├── villager_strategy.py
│       └── witch_strategy.py

├── memory/                     # 记忆与推理
│   ├── memory_manager.py       # AgentMemory（per-agent 记忆 + 嫌疑度 + 角色知识）
│   ├── agent_memory.py         # StrategicMemory + BeliefTracker（策略笔记 + 信念追踪）
│   ├── inference_engine.py     # InferenceEngine（LLM 分析发言/投票模式）
│   └── event_recorder.py       # EventRecorder（全局事件记录）

├── api/                        # 前后端接口层
│   ├── __init__.py             # 模块导出
│   ├── game_api.py             # 游戏主流程 API（初始化、夜晚/白天/投票、流式 SSE）
│   ├── models.py               # 数据结构（GameState、Event、Night/Day/VoteResult）
│   └── exceptions.py           # 异常定义（GameNotFound、InvalidPhase 等）

├── frontend/                   # Web 前端
│   ├── index.html              # 主页面（星空主题 UI）
│   ├── css/style.css           # 样式（夜晚主题、系统消息、观战模式）
│   └── js/game.js              # 游戏逻辑（SSE 流读取、实时渲染、观战自动推进）

├── config/                     # 配置文件
│   ├── __init__.py
│   └── game_config.yaml        # 游戏参数配置

├── utils/                      # 工具
│   ├── config.py               # 配置管理
│   ├── env_generator.py        # 自动生成 .env 文件
│   ├── filter_utils.py         # 内容过滤（脏话词库）
│   ├── llm_client.py           # DeepSeek LLM 客户端（LangChain ChatOpenAI）
│   └── logger.py               # 游戏日志系统（工具调用/推理阶段/错误记录）

├── server.py                   # Flask Web 服务器（SSE 端点、RESTful API）
├── main.py                     # CLI 游戏入口
├── requirements.txt            # Python 依赖
└── .env.example                # API Key 配置模板
```

---

## 二、技术架构

### 2.1 核心技术栈

| 技术 | 用途 |
|------|------|
| **Python 3.10+** | 基础语言 |
| **LangChain + LangGraph** | `create_react_agent` 实现 ReAct 推理循环 |
| **DeepSeek API** | LLM 驱动 AI 玩家的所有决策 |
| **ReAct** | Thought → Action(工具) → Observation → ... → Final Answer |
| **Per-agent Memory** | 私有记忆 + 策略笔记 + 信念追踪 |

### 2.2 多智能体架构

```
                    ┌──────────────────────┐
                    │     GameEngine        │
                    │     (裁判 + 广播)      │
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ 玩家1    │        │ 玩家2    │        │ 玩家N    │
    │ Human    │        │ ReAct    │        │ ReAct    │
    │ Agent    │        │ Agent    │        │ Agent    │
    └──────────┘        └────┬─────┘        └────┬─────┘
                             │                   │
                      ┌──────┴──────┐     ┌──────┴──────┐
                      │ 私有记忆    │     │ 私有记忆    │
                      │ 策略笔记    │     │ 策略笔记    │
                      │ 信念追踪    │     │ 信念追踪    │
                      │ ReAct推理   │     │ ReAct推理   │
                      │ 人格设定    │     │ 人格设定    │
                      └─────────────┘     └─────────────┘
```

每个 AI Agent 拥有独立的：记忆 · 工具 · 人格 · 策略 · ReAct 推理循环。
Agent 之间不直接通信——GameEngine 收集决策后按角色权限广播到各 Agent 的私有记忆。

### 2.3 发言：两阶段架构

LLM 容易把推理过程混入发言，因此采用**两阶段架构**彻底分离"分析"和"说话"：

```
阶段1: ReAct Agent（内部，不对外）
  ├─ recall_strategy      回忆策略
  ├─ review_game_history  查看历史
  ├─ check_suspicion_levels 查看嫌疑度
  ├─ analyze_player_speech  分析发言
  ├─ record_strategy_note   记录新推理
  └─ update_player_belief   更新信念
        │
        ▼ 提取工具查询结果
        │
阶段2: 直接 LLM 调用（无工具、无 ReAct 循环）
  └─ 严格 System Prompt → 输出纯发言文本
```

阶段 2 的 LLM 调用只有一个任务："基于分析结果，说出发言"，格式控制远比 ReAct 的最终输出可靠。

### 2.4 投票 / 夜晚行动：ReAct 推理

投票和夜晚行动使用标准的 LangGraph ReAct 循环，Agent 通过 Thought→Action→Observation 多次迭代后做出决策。

**投票机制：**
- 实际投票人数 < 存活人数/3 时跳过 → 无人出局
- 否则最高票者出局并公布身份
- 平票 → PK发言 → 重投（仅可投平票候选人），三轮平票无人出局
- 首轮可弃权，平票重投不可弃权
- Agent 投票时注入本轮自己的发言原文，使投票与发言立场自然对齐

**夜晚行动：**
- 狼人：必须刀人，不能空刀。通过 `analyze_kill_priority` 工具查看击杀优先级（候选人独立归一化百分比）
- 预言家：选择查验目标，结果记录在 `role_knowledge` 中
- 女巫：获知死者后决定是否使用解药/毒药，每夜最多用一瓶

### 2.5 游戏流程

```
GameEngine.run()
    │
    ├── night_step()
    │   ├── 狼人: ReAct 推理选择击杀目标（必须刀人）
    │   ├── 预言家: ReAct 推理选择查验目标
    │   ├── 女巫: ReAct 推理决定救/毒
    │   ├── 执行死亡 → 检查胜负（狼人>=好人→狼赢）
    │   └── 广播事件到各 Agent 记忆（夜晚死亡不公布身份）
    │
    ├── discussion_phase()
    │   ├── 从死者下家开始发言（无人死亡从1号开始）
    │   ├── 每轮所有人发言（AI 看到之前发言并回应）
    │   └── 进入投票
    │
    └── vote_step()
        ├── 各 Agent ReAct 推理投票（可弃权）
        ├── 投票人数 < 存活/3 → 跳过，无人出局
        ├── 计票 → 平票 → PK发言 → 重投（三轮平票无人出局）
        ├── 处决 → 公布身份
        └── 检查胜负
```

### 2.6 核心 Agent 接口

| 接口 | 调用时机 | AI 实现方式 |
|------|----------|------------|
| `speak(game_state, ...)` | 白天发言 | **两阶段**：ReAct 推理 + 直接 LLM 生成 |
| `vote(game_state, ...)` | 投票阶段 | ReAct 推理 + 工具 + 策略记忆 |
| `night_action(game_state, ...)` | 夜晚阶段 | ReAct 推理 + 工具 + 策略记忆 |

所有接口 LLM 失败时回退到角色策略（Strategy）的启发式方法。

### 2.7 人格系统

| 人格 | 文件 | 特点 |
|------|------|------|
| 理性型 | `rational.py` | 冷静分析，质疑有理有据 |
| 煽动型 | `aggressive.py` | 善于挑拨离间，制造怀疑和对立 |
| 保守型 | `hesitant.py` | 谨慎不轻易表态，凡事留有余地 |
| 冲动型 | `follower.py` | 凭直觉发言，容易冲动下判断 |
| 划水型 | `slacker.py` | 敷衍了事，能少说就少说 |

随机分配，权重由 `core/game_engine.py` 的 `_create_agents()` 控制。

### 2.8 工具系统

**通用工具（全部角色）：**

| 工具 | 功能 |
|------|------|
| `review_game_history` | 查看历史发言/投票/击杀记录 |
| `check_alive_players` | 查看存活玩家列表 |
| `analyze_player_speech` | 分析某玩家发言是否可疑 |
| `check_vote_history` | 查看投票记录 |
| `check_suspicion_levels` | 查看各玩家嫌疑度 |
| `recall_role_knowledge` | 回忆角色特殊信息（如查验结果） |

**Agent 主动工具（全部角色）——策略记忆与信念追踪：**

| 工具 | 功能 |
|------|------|
| `record_strategy_note` | 记录策略笔记（跨轮次保留） |
| `update_player_belief` | 更新对某玩家的信念判断 |
| `set_round_goal` | 设定本轮目标与策略 |
| `recall_strategy` | 回忆之前的策略笔记 |

**角色专属工具：**

| 角色 | 工具 |
|------|------|
| 狼人 | `discuss_with_teammate`（查看队友）、`analyze_kill_priority`（击杀优先级） |
| 预言家 | `review_investigation_results`（查验记录）、`decide_who_to_check`（建议目标） |
| 女巫 | `check_potions`（药水状态）、`analyze_save_decision`、`analyze_poison_target` |
| 村民 | `identify_suspicious_players`（找出最可疑玩家） |

### 2.9 日志系统

`utils/logger.py` — 游戏日志记录器，每局独立日志文件。

所有 Agent 工具调用、ReAct 推理阶段、错误信息都写入 `logs/game_YYYYMMDD_HHMMSS.log`，
带时间戳和游戏上下文（天数/阶段/轮次/玩家编号/角色）。

### 2.10 游戏规则

游戏规则通过 `_build_rules_context()` 注入到所有 Agent 的 system prompt 中，确保 AI 不完全依赖预训练知识推理。

**强制规则：**
1. 狼人每夜必须刀一个人，绝对不允许空刀
2. 女巫解药和毒药各一瓶，每夜最多用一瓶。解药可自救
3. 预言家每夜必须查验一个人，结果只有"好人"或"狼人"

**一般规则：**

| 类别 | 规则 |
|------|------|
| 胜利条件 | 狼人>好人→狼赢；狼人=好人且无神职→狼赢；狼人全灭→好人赢 |
| 回合结构 | 夜晚(狼→预→女) → 白天发言 → 投票 → 循环 |
| 投票机制 | 实际投票人数 < 存活人数/3 时跳过；否则最高票者出局并公布身份 |
| 平票处理 | PK发言 → 重投（仅可投平票候选人），三轮平票无人出局 |
| 死亡信息 | 夜晚死亡不公布身份，白天投票出局公布身份 |
| 发言顺序 | 从死者下家开始，无人死亡从 1 号开始 |
| 弃权 | 首轮投票可弃权，平票重投不可弃权 |

动态信息（本局人数、角色分布）通过 task description 注入。

### 2.11 嫌疑度系统（百分比模式）

怀疑值采用**百分比归一化**——所有存活玩家的嫌疑占比总和 = 100%。对某人怀疑增加，其他人的占比自动降低。仅计算存活玩家，死人自动排除。

### 2.12 防幻觉措施

| 措施 | 位置 |
|------|------|
| 发言分析只根据原文，信息不足时直说"无法判断" | `InferenceEngine.analyze_speech()` |
| 游戏历史末尾追加"以上是精确记录，不要编造" | `format_for_prompt()` |
| System prompt 多处强调"不要编造别人没说过的话" | `_build_speak_react_prompt`、`_build_react_prompt` |
| Day 1 时间锚"还没有「昨天」" | `speak()` 的 task |
| 人格示例中去掉"昨天"改为"上轮" | `personalities/` |

---

## 三、运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
# 创建 .env 文件，填入 DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx
# 或直接运行 main.py，按提示输入 key 自动生成 .env

# 3. 运行
python server.py
```

---

## 四、常见问题

### Q1: 如何新增一个角色？
1. `agents/strategies/` 新增该角色的策略类
2. `agents/tools/` 新增该角色的专属工具
3. `agents/tools/__init__.py` 的 `create_tools_for_role` 中注册
4. `core/role_manager.py` 添加角色配置

### Q2: 如何调整 AI 人格？
修改 `agents/personalities/` 下各人格的 System Prompt

### Q3: 如何调整人格出现概率？
修改 `core/game_engine.py` 中 `_create_agents()` 的 `all_personalities` 列表

### Q4: 平票会怎样？
平票候选人进行 PK 发言 → 其余玩家发言 → 重新投票（仅可投平票候选人）。三轮平票无人出局。

### Q5: 运行时卡住了？
10 秒内是正常的，LLM 在连接。如果超过 30 秒，检查 API Key 和网络。

---

## 五、可以考虑添加的功能

### 重要
- agent直接通信，如投票时启用多轮协商讨论、狼人夜晚交流
- 将人格差异体现到工具调用上，而不仅仅是提示词差异

### 额外
- 增加agent性格嵌套，比如 性格：[冷静、暴躁、内向]，行为方式：[逻辑推理、跟风、胡言乱语]，两个矩阵相乘可以得到9种不同的agent
- 难度选项
- 用户查看 Agent 的思考链
- 模型切换支持
- 增加人格评估，看看哪个人格的胜率最高

---

## 六、注意

### 1. API Key
直接运行 main.py，填入 key 会自动创建 .env
或者直接创建 .env 文件：`DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx`
参考 `.env.example`

### 2. 不要上传配置文件（.env、logs/ 等）

### 3. 不要直接从 GitHub 网站下载 zip，用 git 命令或 GitHub Desktop 拉取

### 4. 不要随便提交到其他分支

### 5. 测试
python server.py
