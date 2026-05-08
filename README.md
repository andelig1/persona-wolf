# 多智能体狼人杀 · ReAct 人格博弈系统

## 开发请跳转到最后查看 九、注意

> 基于多 Agent 架构的狼人杀游戏框架。每个 AI 玩家是独立的智能体，拥有记忆、工具和人格。发言使用直接 LLM 调用（快速稳定），投票和夜晚行动使用 LangGraph ReAct 推理（工具辅助决策）。

---

## 项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| `core/` | 基本完成 | 游戏引擎(裁判模式)、阶段控制、规则判定 |
| `agents/` | 基本完成 | ReActWerewolfAgent、HumanAgent、工具系统、人格系统、角色策略 |
| `memory/` | 基本完成 | AgentMemory(per-agent)、EventRecorder(全局)、InferenceEngine |
| `interaction/` | 基本完成 | 发言管理、动态发言顺序、投票管理 |
| `api/` | 进行中 | 前后端接口层，委托GameEngine实现 |
| `utils/` | 基本完成 | LLM客户端、配置管理、.env生成器 |

---

## 一、项目文件结构

```
persona-wolf/
├── api/                        # 前后端接口层
│   ├── __init__.py             # API 导出
│   ├── game_api.py             # 游戏主流程 API（委托GameEngine）
│   ├── models.py               # 数据结构定义
│   └── exceptions.py           # 异常定义
│
├── core/                       # 游戏核心（裁判系统）
│   ├── game_engine.py          # 主引擎（裁判模式 + 多轮讨论）
│   ├── phase_controller.py     # 阶段切换
│   ├── role_manager.py         # 角色分配
│   └── rule_checker.py         # 规则校验
│
├── agents/                     # AI玩家模块
│   ├── base_agent.py           # Agent 基类
│   ├── react_agent.py          # ReActWerewolfAgent 核心
│   ├── human_agent.py          # 人类玩家Agent（支持CLI和API两种输入）
│   ├── player_agent.py         # 旧版PlayerAgent（保留兼容）
│   ├── ai_agent.py             # 旧版简单AI（保留兼容）
│   ├── tools/                  # 工具系统（ReAct推理中调用）
│   │   ├── __init__.py         # 工具工厂 create_tools_for_role()
│   │   ├── common_tools.py     # 6个通用工具（查看历史/存活/分析发言/投票记录/嫌疑度/角色知识）
│   │   ├── werewolf_tools.py   # 狼人工具（查看队友/击杀优先级）
│   │   ├── seer_tools.py       # 预言家工具（查验记录/建议目标）
│   │   ├── witch_tools.py      # 女巫工具（药水状态/救/毒分析）
│   │   └── villager_tools.py   # 村民工具（找出可疑玩家）
│   ├── personalities/          # 人格系统（5种人格，加权随机）
│   │   ├── rational.py         # 理性型（权重4，最常见）
│   │   ├── aggressive.py       # 煽动型（权重3）
│   │   ├── hesitant.py         # 保守型（权重2）
│   │   ├── follower.py         # 冲动型（权重2）
│   │   └── slacker.py          # 划水型（权重1，最少见）
│   └── strategies/             # 角色策略（LLM失败时回退）
│       ├── werewolf_strategy.py
│       ├── seer_strategy.py
│       ├── villager_strategy.py
│       └── witch_strategy.py
│
├── memory/                     # 记忆与推理
│   ├── memory_manager.py       # AgentMemory（per-agent记忆+嫌疑度+角色知识）
│   ├── inference_engine.py     # InferenceEngine（LLM分析发言/投票模式）
│   └── event_recorder.py       # EventRecorder（全局事件记录+可见性控制）
│
├── interaction/                # 交互模块
│   ├── dialogue_manager.py     # 发言管理
│   ├── dynamic_speaker.py      # 动态发言顺序
│   └── vote_manager.py         # 投票管理
│
├── utils/                      # 工具
│   ├── config.py               # 配置管理
│   ├── env_generator.py        # 自动生成.env文件
│   ├── llm_client.py           # DeepSeek LLM 客户端（LangChain ChatOpenAI）
│   └── ...
│
├── config/                     # 配置文件
├── demo/                       # 示例
├── tests/                      # 测试
├── main.py                     # CLI 游戏入口
└── requirements.txt            # 依赖
```

---

## 二、技术架构

### 2.1 核心技术栈

| 技术 | 用途 |
|------|------|
| **Python 3.10+** | 基础语言 |
| **LangChain** | Agent 开发框架 |
| **LangGraph** | `create_react_agent` 实现 ReAct 推理循环 |
| **DeepSeek API** | LLM 驱动 AI 玩家的发言、投票和夜晚行动 |
| **ReAct** | Thought -> Action(工具) -> Observation -> ... -> Final Answer |
| **Memory** | Per-agent 记忆系统 + 嫌疑度追踪 |

### 2.2 多智能体架构

```
                    +------------------+
                    |   GameEngine     |
                    |   (裁判模式)      |
                    +--------+---------+
                             |
              +--------------+--------------+--------------+
              |              |              |              |
              v              v              v              v
        +----------+  +----------+  +----------+  +----------+
        | Agent 0  |  | Agent 1  |  | Agent 2  |  | Agent 3  |
        | (Human)  |  | (AI)     |  | (AI)     |  | (AI)     |
        |          |  | 记忆     |  | 记忆     |  | 记忆     |
        |          |  | 工具     |  | 工具     |  | 工具     |
        |          |  | 人格     |  | 人格     |  | 人格     |
        +----------+  +-----+----+  +-----+----+  +-----+----+
                            |              |              |
                     speak: 直接LLM   直接LLM        直接LLM
                     vote:  ReAct推理  ReAct推理      ReAct推理
                     night: ReAct推理  ReAct推理      ReAct推理
                            v              v              v
                       +---------+    +---------+    +---------+
                       | DeepSeek|    | DeepSeek|    | DeepSeek|
                       +---------+    +---------+    +---------+
```

每个 AI Agent 拥有独立的：
- **记忆 (AgentMemory)**：追踪发言、投票、嫌疑度、角色知识
- **工具 (Tools)**：review_game_history, analyze_player_speech, check_suspicion_levels 等
- **人格 (Personality)**：5种人格驱动不同的发言风格（加权随机）
- **策略 (Strategy)**：角色专属的启发式回退逻辑

### 2.3 发言与决策的不同策略

**speak() — 直接 LLM 调用**：记忆、别人的发言、嫌疑度直接注入 prompt，一次 LLM 调用搞定。快速（3-8秒）且稳定，AI 能看到并回应其他人的发言。

```
System Prompt:
  人格设定 + 角色信息 + 记忆摘要 + 嫌疑判断 + 角色知识
User Prompt:
  天数/轮次 + 指导语(第一天不乱指控) + 本轮之前其他人的发言

→ 一次 LLM 调用 → 发言内容
```

**vote() / night_action() — ReAct 推理**：通过 Thought→Action→Observation 循环，使用工具获取信息后决策。适合需要深入分析的场景。

```
Agent 收到任务: "现在是投票阶段，请使用工具分析后决定投谁"

Thought: 我需要看看谁最可疑
Action: check_suspicion_levels()
Observation: 2号: 有些可疑(0.3), 3号: 不太确定(0.0)

Thought: 让我回顾一下2号的发言
Action: review_game_history(event_type="speak")
Observation: 2号: 我觉得3号有问题...

Final Answer: 2
```

### 2.4 游戏流程

```
GameEngine.run()
    │
    ├── night_step(human_actions)
    │   ├── 狼人: ReAct推理选择击杀目标
    │   ├── 预言家: ReAct推理选择查验目标
    │   ├── 女巫: ReAct推理决定救/毒
    │   └── 分发事件到Agent记忆
    │
    ├── discussion_phase()  ← 多轮讨论，不是每人只说一句
    │   ├── 第1轮: 所有人发言（AI看到别人的发言并回应）
    │   ├── 用户选择: 继续讨论 or 输入 vote 进入投票
    │   ├── 第2轮: AI基于第1轮发言继续讨论
    │   ├── ...（最多5轮）
    │   └── 进入投票
    │
    └── vote_step(human_vote)
        ├── 各Agent ReAct推理投票
        ├── 计票、处决
        └── 检查胜负
```

**多轮讨论机制**：白天不是每人说一句就进入投票，而是多轮讨论。每轮所有人发言后，用户可以继续发言讨论，也可以输入 `vote` 进入投票阶段。AI 在后续轮次能看到并回应之前所有人的发言。

### 2.5 核心 Agent 接口

所有 Agent 实现 BaseAgent 的三个接口：

| 接口 | 调用时机 | AI实现方式 | Human实现 |
|------|----------|-----------|-----------|
| `speak(game_state, round_num, previous_speeches)` | 白天发言 | 直接LLM调用，记忆/发言/嫌疑度注入prompt | CLI input |
| `vote(game_state)` | 投票阶段 | ReAct推理+工具 | CLI input |
| `night_action(game_state)` | 夜晚阶段 | ReAct推理+工具 | CLI input |

### 2.6 人格系统

| 人格 | 文件 | 权重 | 特点 |
|------|------|------|------|
| 理性型 | `personalities/rational.py` | 4（最常见） | 冷静分析，质疑有理有据 |
| 煽动型 | `personalities/aggressive.py` | 3 | 善于挑拨离间，制造怀疑和对立 |
| 保守型 | `personalities/hesitant.py` | 2 | 谨慎不轻易表态，凡事留有余地 |
| 冲动型 | `personalities/follower.py` | 2 | 凭直觉发言，容易冲动下判断 |
| 划水型 | `personalities/slacker.py` | 1（最少见） | 敷衍了事，能少说就少说 |

### 2.7 工具系统

| 工具 | 适用角色 | 功能 |
|------|----------|------|
| `review_game_history` | 全部 | 查看历史发言/投票/击杀记录 |
| `check_alive_players` | 全部 | 查看存活玩家列表 |
| `analyze_player_speech` | 全部 | 分析某玩家发言是否可疑 |
| `check_vote_history` | 全部 | 查看投票记录 |
| `check_suspicion_levels` | 全部 | 查看各玩家嫌疑度 |
| `recall_role_knowledge` | 全部 | 回忆角色特殊信息 |
| `discuss_with_teammate` | 狼人 | 查看狼人队友 |
| `analyze_kill_priority` | 狼人 | 分析击杀优先级 |
| `review_investigation_results` | 预言家 | 回顾查验结果 |
| `decide_who_to_check` | 预言家 | 建议查验目标 |
| `check_potions` | 女巫 | 查看剩余药水 |
| `analyze_save_decision` | 女巫 | 分析是否值得救人 |
| `analyze_poison_target` | 女巫 | 分析毒杀目标 |
| `identify_suspicious_players` | 村民 | 找出最可疑玩家 |

### 2.8 狼人队友信息

人类玩家是狼人时：
- 游戏开始 `print_roles()` 会显示"你的狼人队友: X号"
- 夜晚选择击杀目标时会提示队友，且不能杀队友

---

## 三、API 接口文档

### 3.1 初始化

```python
from api import init_game
state = init_game(num_players=4, human_player_id=0)
```

### 3.2 获取游戏状态

```python
from api import get_game_state
state = get_game_state(game_id)
```

### 3.3 黑夜阶段

```python
from api import night_step
result = night_step(
    game_id="a1b2c3d4",
    user_werewolf_target=2,      # 狼人：选择击杀目标
    user_seer_target=3,          # 预言家：选择查验目标
    user_witch_save=True,        # 女巫：是否救人
    user_witch_poison=None,      # 女巫：是否毒人
)
```

### 3.4 白天发言

```python
from api import day_step
result = day_step(game_id="a1b2c3d4", user_speak="3号你说的含含糊糊的")
```

### 3.5 投票阶段

```python
from api import vote_step
result = vote_step(game_id="a1b2c3d4", user_vote=3)
```

### 3.6 查询历史 & 检查胜负

```python
from api import get_history, check_win
events = get_history(game_id)
winner = check_win(game_id)  # "好人" / "狼人" / None
```

---

## 四、运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
# 创建 .env 文件，填入 DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx

# 3. 运行命令行版本
python main.py

# 4. 运行测试
python -m pytest tests/
```

---

## 五、分工

| 组员 | 负责 | 输出 |
|------|------|------|
| A组（3人） | 核心逻辑 | `react_agent.py`, `memory/`, `strategies/`, `tools/` |
| B组（2人） | 界面交互 | `app.py`, `interface.py` |

---

## 六、常见问题

### Q1: 如何新增一个角色？
1. `agents/strategies/` 新增该角色的策略类
2. `agents/tools/` 新增该角色的专属工具
3. `agents/tools/__init__.py` 的 `STRATEGY_MAP` 和 `create_tools_for_role` 中注册
4. `core/role_manager.py` 添加角色配置

### Q2: 如何调整 AI 人格？
修改 `agents/personalities/` 下各人格的 System Prompt

### Q3: 如何调整人格出现概率？
修改 `core/game_engine.py` 中 `_create_agents()` 的 `personality_weights` 字典

### Q4: 为什么发言用直接LLM而不是ReAct？
发言需要快（3-8秒）且稳定，ReAct循环（20-60秒）太慢。投票和夜晚行动需要深入分析，适合ReAct推理。

### Q5: 如何调整 AI 推理深度？
修改 `agents/react_agent.py` 中 `_build_agent()` 的 `create_react_agent` 参数

---

## 七、注意

### 1. api key
直接运行main.py，填入key会自动创建.env
或者直接创建.env文件，复制并填入APIKEY：DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx
可以参考 `.env.example`

### 2. 不要上传配置文件

### 3. 不要直接从github网站下载zip，可以用git命令或者GitHub Desktop拉取

### 4. 不要随便提交到其他分支

### 5. 测试
运行 `python main.py` 可以测试完整游戏流程
运行 `python -m pytest tests/` 可以运行LLM连接测试

### 6. 游戏中
运行时卡住10秒内是正常的，LLM在连接
目前还没有使用ReAct 推理，因为需要20~60s思考时间，太慢了还没加
