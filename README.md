明白了！你需要的是一个**面向组员的README**，重点是让他们快速理解项目框架、各模块职责、数据流向，以及知道自己该负责哪部分、如何与其他模块对接。

下面是精简后的README：

---

# 单人狼人杀 · 多Agent人格博弈系统

> 一个基于多Agent建模的狼人杀游戏框架，支持单人游玩，AI玩家具备独立人格与动态博弈能力。

---

## 一、项目目标

本项目将狼人杀从传统多人游戏转化为**单人可玩的AI博弈系统**。核心目标：

- 用户作为唯一人类玩家，其余由AI扮演
- 每个AI具备独立的人格特征与决策逻辑
- AI能够记忆历史信息、推理判断、动态调整策略
- 呈现高沉浸感、高复玩性的游戏体验

---

## 二、整体架构

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                      （程序入口）                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      core/（游戏核心）                        │
│  GameEngine → PhaseController → RuleChecker → RoleManager   │
│    （总控）      （阶段切换）      （胜负判定）   （角色分配）   │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   agents/       │ │   memory/       │ │  interaction/   │
│  AI玩家模块      │ │   记忆模块       │ │   交互模块       │
│                 │ │                 │ │                 │
│ • BaseAgent     │ │ • 记忆存储       │ │ • 发言管理       │
│ • HumanAgent    │ │ • 事件记录       │ │ • 动态顺序       │
│ • AIAgent       │ │ • 推理引擎       │ │ • 投票管理       │
│ • 人格系统       │ │                 │ │                 │
│ • 策略系统       │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 模块职责一览

| 模块 | 职责 | 关键类 |
|------|------|--------|
| **core** | 游戏流程控制、规则仲裁、胜负判定 | GameEngine, PhaseController, RuleChecker |
| **agents** | 定义AI和人类玩家的行为逻辑 | BaseAgent, AIAgent, HumanAgent |
| **memory** | 管理AI的记忆、提供推理能力 | MemoryManager, InferenceEngine |
| **interaction** | 管理发言顺序、投票流程 | DialogueManager, VoteManager |
| **utils** | 配置加载、日志、通用工具 | ConfigLoader, Logger |
| **config** | 游戏参数、AI人格参数 | YAML配置文件 |

---

## 三、核心模块详解

### 1. core/ — 游戏引擎（裁判系统）

**职责**：作为游戏的“裁判”，控制整个对局的流程，不关心AI具体怎么决策。

**核心类及其职责**：

| 类 | 职责 |
|----|------|
| GameEngine | 主引擎，协调各模块，执行游戏主循环 |
| PhaseController | 控制夜晚/白天/投票阶段的切换 |
| RuleChecker | 校验规则（如投票是否合法），判定胜负 |
| RoleManager | 游戏开始前分配角色 |

**数据流向**：
- GameEngine 从 agents 获取每个玩家的行动（发言、投票、夜晚操作）
- GameEngine 调用 RuleChecker 判定是否结束
- GameEngine 将阶段信息广播给所有 Agent

---

### 2. agents/ — AI玩家模块（最重要）

**职责**：定义每个玩家（AI或人类）如何做出决策。

**类继承关系**：

```
BaseAgent（抽象基类）
    ├── HumanAgent（人类玩家，通过命令行输入）
    └── AIAgent（AI玩家）
            ├── 包含 Personality（人格）
            └── 包含 Strategy（策略）
```

**三个核心接口**（所有Agent必须实现）：

| 接口 | 调用时机 | 返回值 |
|------|----------|--------|
| `speak()` | 白天阶段轮到该玩家发言 | 字符串（发言内容） |
| `vote()` | 投票阶段 | 整数（投票目标ID） |
| `night_action()` | 夜晚阶段 | 字典（行动类型+目标） |

**人格系统**：决定AI的“性格”，影响发言风格和决策倾向

| 人格 | 特征 | 对行为的影响 |
|------|------|-------------|
| 激进型 | 强势、主动 | 发言肯定、主动攻击、易插话 |
| 理性型 | 冷静、逻辑 | 分析式发言、投票谨慎 |
| 犹豫型 | 摇摆、不确定 | 发言模糊、可能临时改票 |
| 跟风型 | 从众、附和 | 倾向跟随多数人投票 |

**策略系统**：根据角色（狼人/村民/预言家/女巫）决定具体行为逻辑

- 不同角色有不同目标（狼人伪装、预言家找出狼人）
- 策略会调用记忆模块获取历史信息
- 策略会参考人格参数调整行为

---

### 3. memory/ — 记忆与推理模块

**职责**：让AI能够“记住”并“思考”。

**核心能力**：

| 能力 | 说明 |
|------|------|
| 记录发言 | 谁在什么时候说了什么 |
| 记录投票 | 谁投了谁 |
| 怀疑度计算 | 基于行为给每个玩家打分 |
| 矛盾检测 | 发现玩家前后发言不一致 |

**数据流向**：
- GameEngine 将每轮发言和投票结果发送给 MemoryManager
- AIAgent 在决策时向 InferenceEngine 询问“谁最可疑”

---

### 4. interaction/ — 交互模块

**职责**：管理玩家之间的交流秩序。

| 类 | 职责 |
|----|------|
| DialogueManager | 记录所有发言历史 |
| DynamicSpeaker | 决定发言顺序（可打破固定顺序） |
| VoteManager | 收集投票、计票、处理平票 |

---

## 四、游戏流程（数据流视角）

```
1. 初始化阶段
   RoleManager 分配角色 → 创建 Agent 实例 → GameEngine 持有所有 Agent

2. 夜晚阶段
   GameEngine.phase_controller 调用 night_phase()
   → 依次询问狼人/预言家/女巫的 night_action()
   → 收集结果 → 应用结果（杀人/查验/救人等）

3. 白天阶段
   GameEngine.phase_controller 调用 day_phase()
   → 依次调用每个存活 Agent 的 speak()
   → DialogueManager 记录发言

4. 投票阶段
   GameEngine.phase_controller 调用 vote_phase()
   → 依次调用每个存活 Agent 的 vote()
   → VoteManager 计票 → 确定出局者

5. 胜负判定
   RuleChecker 检查条件 → 返回结果 → 结束或继续
```

---

## 五、各模块之间的接口约定

为保证协作时不产生冲突，模块之间通过**明确定义的接口**通信：

### Agent → GameEngine
Agent 不主动调用 GameEngine，只被动响应三个接口：
- `speak(game_state)`
- `vote(candidates, game_state)`
- `night_action(game_state)`

### GameEngine → Agent
GameEngine 通过上述三个接口获取决策，通过 `game_state` 字典传递信息。

### GameEngine → Memory
GameEngine 在每轮结束后调用 `memory.record_event()` 记录信息。

### Agent → Memory
Agent 决策时可以调用 `memory.get_suspicion()` 等查询接口。

### Agent → Personality/Strategy
Agent 内部组合人格和策略对象，决策时委托给它们。

---

## 六、配置文件说明

| 文件 | 作用 |
|------|------|
| `config/game_config.yaml` | 游戏人数、角色配置、阶段时长 |
| `config/agent_personalities.yaml` | 各人格的参数（发言风格、投票稳定度等） |

修改配置文件即可调整游戏规则，无需改动代码。

---

## 七、后期扩展方向与分工建议

### 可扩展的方向

| 方向 | 涉及模块 | 难度 | 优先级 |
|------|----------|------|--------|
| 新增角色（如猎人、白痴） | core, agents/strategies | ⭐⭐ | 高 |
| 增强记忆推理 | memory | ⭐⭐⭐ | 高 |
| 动态发言顺序 | interaction | ⭐⭐ | 中 |
| 接入LLM（大模型生成发言） | agents/llm_agent | ⭐⭐⭐ | 中 |
| 可视化界面 | 新增 frontend 模块 | ⭐⭐⭐ | 中 |
| 语音交互 | 新增 speech 模块 | ⭐⭐⭐⭐ | 低 |

### 分工建议

| 组员 | 负责模块 | 具体内容 |
|------|----------|----------|
| A | core | 游戏引擎、阶段控制、规则判定 |
| B | agents（基础） | BaseAgent、AIAgent、HumanAgent |
| C | agents（人格） | 四种人格类的实现 |
| D | agents（策略） | 各角色的策略逻辑 |
| E | memory | 记忆存储、推理引擎 |
| F | interaction | 发言管理、投票管理 |
| G | 测试与集成 | 单元测试、模块集成 |

### 协作流程

1. 组长建立仓库，提供 `BaseAgent`、`GameEngine` 空接口
2. 各成员基于接口实现自己的模块
3. 每周合并一次，运行 `demo/simple_run.py` 验证
4. 最后统一集成

---

## 八、快速验证方法

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行快速测试（自动运行一局，无人类交互）
python demo/simple_run.py

# 3. 运行完整游戏（自己作为玩家）
python main.py
```

---

## 九、常见问题

### Q1：我的模块需要调用其他模块的功能，但那个模块还没实现怎么办？
使用接口定义和 Mock 对象。例如，你需要 `memory` 但还没实现，可以先写一个假的 `DummyMemory` 返回默认值。

### Q2：如何确保我的修改不破坏现有功能？
运行 `tests/` 下的单元测试。每次合并前必须保证测试通过。

### Q3：游戏状态 `game_state` 里包含什么？
```python
game_state = {
    "alive_players": [0,1,2,3],  # 存活玩家ID列表
    "day": 2,                     # 当前天数
    "phase": "day",               # 当前阶段: night/day/vote
    "history": [...]              # 最近的事件记录
}
```

### Q4：新增一个角色需要改哪些地方？
1. `config/game_config.yaml` 添加角色数量
2. `agents/strategies/` 新增该角色的策略类
3. `core/phase_controller.py` 添加该角色的夜晚行动（如有）
4. `core/rule_checker.py` 如有特殊胜负条件需修改

---

## 十、项目总结

本项目通过**模块化设计**和**接口约定**，将狼人杀拆解为可独立开发的多个子系统：

- **core** 负责“裁判逻辑”
- **agents** 负责“玩家行为”
- **memory** 负责“记忆与推理”
- **interaction** 负责“交流秩序”

各模块之间通过清晰的接口通信，成员可以并行开发自己的部分，最后统一集成。这种架构既保证了MVP能快速跑通，也为后续扩展（新角色、LLM、可视化等）预留了空间。