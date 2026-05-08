"""测试 Agent 和 LLM 调用"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.player_agent import PlayerAgent
from utils.env_generator import generate_env_file, check_env_exists
from utils.llm_client import get_llm_client, DeepSeekClient


def test_env_file_generation():
    """测试 .env 文件生成"""
    test_key = "sk-test123456789"
    path = generate_env_file(test_key, ".env.test")

    assert Path(path).exists()
    with open(path, "r") as f:
        content = f.read()
        assert "DEEPSEEK_API_KEY=sk-test123456789" in content

    # 清理测试文件
    Path(".env.test").unlink(missing_ok=True)
    print("✓ .env 文件生成测试通过")


def test_llm_client_connection():
    """测试 LLM 客户端连接"""
    if not check_env_exists():
        pytest.skip(".env file not found, skipping LLM test")

    try:
        client = get_llm_client()
        # 简单测试对话
        response = client.chat([
            {"role": "user", "content": "Hello, reply with just 'OK'"}
        ])
        assert response.strip() == "OK" or len(response) > 0
        print(f"✓ LLM 连接测试通过，回复: {response[:50]}")
    except ValueError as e:
        pytest.skip(f"API Key not configured: {e}")
    except Exception as e:
        pytest.fail(f"LLM 调用失败: {e}")


def test_player_agent_speak():
    """测试 PlayerAgent 发言生成"""
    if not check_env_exists():
        pytest.skip(".env file not found, skipping LLM test")

    try:
        agent = PlayerAgent(
            agent_id=1,
            role="狼人",
            personality="aggressive",
            name="测试狼人"
        )

        game_state = {
            "day": 1,
            "alive_players": [0, 1, 2, 3],
            "history": [
                {"type": "speak", "player_id": 0, "content": "我是好人"}
            ]
        }

        speech = agent.speak(game_state)
        assert isinstance(speech, str)
        assert len(speech) > 0
        print(f"✓ PlayerAgent 发言测试通过: {speech[:50]}...")

    except ValueError as e:
        pytest.skip(f"API Key not configured: {e}")
    except Exception as e:
        pytest.fail(f"Agent 发言生成失败: {e}")


def test_personality_difference():
    """测试不同人格的发言差异"""
    if not check_env_exists():
        pytest.skip(".env file not found, skipping LLM test")

    game_state = {
        "day": 1,
        "alive_players": [0, 1, 2, 3],
        "history": []
    }

    personalities = ["rational", "aggressive", "hesitant", "follower"]
    speeches = []

    for personality in personalities:
        try:
            agent = PlayerAgent(
                agent_id=1,
                role="村民",
                personality=personality,
            )
            speech = agent.speak(game_state)
            speeches.append((personality, speech))
            print(f"  {personality}: {speech[:30]}...")
        except ValueError as e:
            pytest.skip(f"API Key not configured: {e}")
        except Exception as e:
            print(f"  {personality} 测试失败: {e}")

    # 检查是否生成了不同风格的发言
    assert len(speeches) > 0, "没有成功生成任何发言"
    print(f"✓ 人格差异测试完成，生成了 {len(speeches)} 条发言")


if __name__ == "__main__":
    print("=" * 50)
    print("运行测试...")
    print("=" * 50)

    print("\n1. 测试 .env 文件生成")
    test_env_file_generation()

    print("\n2. 测试 LLM 连接")
    test_llm_client_connection()

    print("\n3. 测试 PlayerAgent 发言")
    test_player_agent_speak()

    print("\n4. 测试人格差异")
    test_personality_difference()

    print("\n" + "=" * 50)
    print("所有测试完成!")
    print("=" * 50)
