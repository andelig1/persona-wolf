"""配置管理 - 从 .env 加载环境变量"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 获取项目根目录
ROOT_DIR = Path(__file__).parent.parent

# 加载 .env 文件（如果存在）
_env_file = ROOT_DIR / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
else:
    # 尝试加载 .env.example
    _env_example = ROOT_DIR / ".env.example"
    if _env_example.exists():
        load_dotenv(_env_example, verbose=True)


class LLMConfig:
    """LLM 配置"""

    # DeepSeek
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")

    # 通义千问
    TONGQI_API_KEY = os.getenv("TONGQI_API_KEY", "")
    TONGQI_API_BASE = os.getenv("TONGQI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    @classmethod
    def get_deepseek_key(cls) -> str:
        if not cls.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY not found in .env")
        return cls.DEEPSEEK_API_KEY

    @classmethod
    def has_llm_config(cls) -> bool:
        """检查是否配置了至少一个 LLM"""
        return bool(cls.DEEPSEEK_API_KEY or cls.TONGQI_API_KEY or cls.GEMINI_API_KEY)


class GameConfig:
    """游戏配置"""

    # 默认玩家数量
    DEFAULT_NUM_PLAYERS = int(os.getenv("DEFAULT_NUM_PLAYERS", "4"))

    # 人类玩家 ID
    HUMAN_PLAYER_ID = int(os.getenv("HUMAN_PLAYER_ID", "0"))

    # LLM Temperature
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
