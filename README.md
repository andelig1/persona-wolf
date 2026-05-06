# 单人狼人杀 · 多Agent人格博弈系统

## 开发请跳转到最后查看 九、注意

> 一个基于多Agent建模的狼人杀游戏框架，支持单人游玩，AI玩家具备独立人格与动态博弈能力。

---

## 项目状态

> **开发中** - 核心逻辑已完成，API层已实现，界面开发中

| 模块 | 状态 | 说明 |
|------|------|------|
| `core/` | 简单完成 | 游戏引擎、阶段控制、规则判定 |
| `agents/` | 🔄 进行中 | Agent基类已完成，LLM接入待实现 |
| `memory/` | 🔄 进行中 | 记忆存储已实现，推理引擎待完善 |
| `interaction/` | 简单完成 | 发言管理、投票管理 |
| `api/` | ✅ 新增 | 前后端接口层，供B组调用 |
| `app.py` | 🔄 进行中 | Streamlit界面（B组开发） |

---

## 一、项目文件结构

```
persona-wolf/
├── api/                        # 前后端接口层
│   ├── __init__.py             # API 导出
│   ├── game_api.py             # 游戏主流程 API
│   ├── models.py               # 数据结构定义
│   └── exceptions.py           # 异常定义
│
├── core/                       # 游戏核心（裁判系统）
│   ├── game_engine.py          # 主引擎
│   ├── phase_controller.py     # 阶段切换
│   ├── role_manager.py         # 角色分配
│   └── rule_checker.py         # 规则校验
│
├── agents/                     # AI玩家模块
│   ├── base_agent.py           # Agent 基类
│   ├── human_agent.py          # 人类玩家
│   ├── player_agent.py         # 【待实现】接LLM的Agent
│   ├── personalities/          # 人格系统
│   │   ├── aggressive.py       # 激进型
│   │   ├── rational.py         # 理性型
│   │   ├── hesitant.py         # 犹豫型
│   │   └── follower.py         # 跟风型
│   └── strategies/             # 角色策略
│       ├── werewolf_strategy.py # 狼人策略
│       ├── villager_strategy.py # 村民策略
│       ├── seer_strategy.py     # 预言家策略
│       └── witch_strategy.py    # 女巫策略
│
├── memory/                     # 记忆与推理
│   ├── memory_manager.py       # 记忆存储
│   ├── inference_engine.py     # 推理引擎
│   └── event_recorder.py       # 事件记录
│
├── interaction/                # 交互模块
│   ├── dialogue_manager.py     # 发言管理
│   ├── dynamic_speaker.py      # 发言顺序
│   └── vote_manager.py         # 投票管理
│
├── utils/                      # 工具
│   ├── config_loader.py        # 配置加载
│   ├── logger.py               # 日志
│   └── helpers.py              # 辅助函数
│
├── config/                     # 配置文件
│   └── game_config.yaml        # 游戏配置
│
├── demo/                       # 示例
│   ├── simple_run.py           # 无界面快速测试
│   └── cli_demo.py             # 命令行演示
│
├── tests/                      # 测试
│
├── app.py                      # 【待实现】Streamlit 界面入口
├── main.py                     # 游戏入口
└── requirements.txt            # 依赖
```

---

## 二、技术架构

### 2.1 核心技术栈

| 技术 | 用途 |
|------|------|
| **Python 3.10+** | 基础语言 |
| **LangChain** | Agent 开发框架，管理 prompt 和 chain |
| **LLM API** | DeepSeek / 通义千问 / Gemini（生成AI发言） |
| **Streamlit** | Web 界面（B组开发） |
| **ReAct** | 推理机制 |
| **Memory** | 对话记忆管理 |

### 2.2 LLM 调用架构

```
                    +------------------+
                    |   Streamlit      |
                    |   前端 (B组)      |
                    +--------+---------+
                             |
                             | API 调用
                             v
                    +------------------+
                    |   api/           |
                    |   游戏API        |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
        +---------+    +---------+    +---------+
        | Player  |    | Memory  |    | Rules   |
        | Agent   |    | Module  |    | Module  |
        +----+----+    +---------+    +---------+
             |
             | LLM 调用
             v
        +---------+
        | DeepSeek |
        | / Gemini |
        +---------+
```

### 2.3 Human-in-the-loop

```
用户输入 → API → AI处理 → 返回结果 → 前端展示
    ^                              |
    |______________________________|
           (轮询刷新 2-3秒)
```

### 2.4 Agent 三大接口

所有 Agent 必须实现以下三个接口：

| 接口 | 调用时机 | 参数 | 返回值 |
|------|----------|------|--------|
| `speak(game_state)` | 白天发言阶段 | 游戏状态 | 字符串（发言内容） |
| `vote(game_state)` | 投票阶段 | 游戏状态 | 整数（投票目标ID） |
| `night_action(game_state)` | 夜晚阶段 | 游戏状态 | 字典（行动类型+目标） |

---

## 三、API 接口文档

### 3.1 初始化

```python
from api import init_game

state = init_game(num_players=4, human_player_id=0)
```

**返回** `GameState`:
```python
{
    "game_id": "a1b2c3d4",
    "day": 1,
    "phase": "night",
    "alive_players": [0, 1, 2, 3],
    "player_roles": {0: "村民", 1: "狼人", 2: "预言家", 3: "女巫"},
    "player_names": {0: "你", 1: "玩家1", 2: "玩家2", 3: "玩家3"},
    "history": [...],
    "current_player": 0
}
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

result = day_step(
    game_id="a1b2c3d4",
    user_speak="我认为2号玩家很可疑..."
)
```

### 3.5 投票阶段

```python
from api import vote_step

result = vote_step(
    game_id="a1b2c3d4",
    user_vote=1  # 投票目标
)
```

### 3.6 查询历史

```python
from api import get_history

events = get_history(game_id)
```

### 3.7 检查胜负

```python
from api import check_win

winner = check_win(game_id)  # 返回: "好人" / "狼人" / None
```

---

## 四、数据结构

### Event (事件)

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | str | `speak` \| `vote` \| `kill` \| `check` \| `save` \| `poison` \| `eliminate` |
| `player_id` | int | 事件发起玩家 |
| `content` | str | 事件内容 |
| `target` | int | 目标玩家（可选） |

### Phase (阶段)

| 值 | 说明 |
|----|------|
| `waiting` | 等待开始 |
| `night` | 黑夜阶段 |
| `day` | 白天发言阶段 |
| `vote` | 投票阶段 |
| `ended` | 游戏结束 |

---

## 五、分工

| 组员 | 负责 | 输出 |
|------|------|------|
| A组（3人） | 核心逻辑 | `player_agent.py`, `rules.py`, `memory.py` |
| B组（2人） | 界面交互 | `app.py`, `interface.py` |

### A组 开发顺序
1. `player_agent.py` - 接LLM的Agent实现
2. `rules.py` - 完善狼人杀规则
3. `memory.py` - 记忆与推理

### B组 开发顺序
1. `app.py` - Streamlit 基础框架
2. 调用 `api/` 接入核心逻辑
3. 完善 UI/UX

---

## 六、运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行无界面测试
python -m api.game_api

# 3. 运行命令行演示
python demo/simple_run.py

# 4. 运行完整游戏（界面开发完成后）
streamlit run app.py
```

---

## 七、待办事项

- [ ] `agents/player_agent.py` - 接入 LLM 生成发言
- [ ] `core/rules.py` - 完善狼人杀规则
- [ ] `memory/inference_engine.py` - 推理引擎
- [ ] `app.py` - Streamlit 界面开发

---

## 八、常见问题

### Q1: 如何新增一个角色？
1. `config/game_config.yaml` 添加角色数量
2. `agents/strategies/` 新增该角色的策略类
3. `api/game_api.py` 的 `night_step()` 添加该角色的夜晚逻辑

### Q3: 如何调整 AI 人格？
修改 `agents/personalities/` 下各人格类的 `System Prompt`

## 九、注意
### 1. api key
```
直接创建.env文件，复制并填入APIKEY：DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx
```
可以参考 `.env.example`
### 2. 不要上传配置文件
### 3. 不要直接从github网站下载zip，可以用git命令或者GitHub Desktop拉取，不然没有共同提交历史比较麻烦
### 4. 不要随便提交到其他分支，不同分支用于区分版本或测试