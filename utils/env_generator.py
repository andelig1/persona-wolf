"""自动生成 .env 文件

用户提供 API Key 后，自动创建 .env 文件
"""
import os
from pathlib import Path


def generate_env_file(api_key: str, file_path: str = None) -> str:
    """生成 .env 文件

    Args:
        api_key: DeepSeek API Key
        file_path: 可选，.env 文件路径，默认项目根目录

    Returns:
        str: .env 文件的完整路径
    """
    if not api_key or not api_key.startswith("sk-"):
        raise ValueError("Invalid API Key format. DeepSeek API Key should start with 'sk-'")

    # 获取项目根目录
    if file_path is None:
        root_dir = Path(__file__).parent.parent
        file_path = root_dir / ".env"
    else:
        file_path = Path(file_path)

    # 写入 .env 文件
    content = f"""# LLM API Keys (Auto-generated)
DEEPSEEK_API_KEY={api_key}

# Optional: Custom LLM endpoint (usually no need to change)
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

# LLM Settings
LLM_TEMPERATURE=0.7
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.strip())

    return str(file_path)


def check_env_exists() -> bool:
    """检查 .env 文件是否存在"""
    root_dir = Path(__file__).parent.parent
    env_file = root_dir / ".env"
    return env_file.exists()


def get_api_key_from_env() -> str:
    """从 .env 文件获取 API Key"""
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv("DEEPSEEK_API_KEY", "")


if __name__ == "__main__":
    # 测试用
    test_key = input("请输入 DeepSeek API Key: ").strip()
    try:
        path = generate_env_file(test_key)
        print(f".env 文件已生成: {path}")
    except ValueError as e:
        print(f"错误: {e}")
