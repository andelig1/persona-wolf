"""DeepSeek LLM 客户端

使用 LangChain 调用 DeepSeek API
"""
import os
from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from utils.config import LLMConfig, GameConfig


class DeepSeekClient:
    """DeepSeek LLM 客户端"""

    _instance: Optional["DeepSeekClient"] = None
    _llm: Optional[ChatOpenAI] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._llm is None:
            self._initialize()

    def _initialize(self):
        """初始化 LLM"""
        api_key = LLMConfig.DEEPSEEK_API_KEY
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not found. Please run setup or check .env file")

        self._llm = ChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=LLMConfig.DEEPSEEK_API_BASE,
            temperature=GameConfig.LLM_TEMPERATURE,
        )

    @property
    def llm(self) -> ChatOpenAI:
        """获取 LLM 实例"""
        if self._llm is None:
            self._initialize()
        return self._llm

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> str:
        """发送对话请求

        Args:
            messages: 对话消息列表，格式 [{"role": "user", "content": "..."}]
            temperature: 可选，覆盖默认温度

        Returns:
            str: LLM 回复
        """
        # 转换消息格式
        langchain_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))

        # 临时覆盖 temperature
        if temperature is not None:
            original_temp = self._llm.temperature
            self._llm.temperature = temperature
            try:
                response = self._llm.invoke(langchain_messages)
            finally:
                self._llm.temperature = original_temp
        else:
            response = self._llm.invoke(langchain_messages)

        return response.content

    def generate_speech(
        self,
        system_prompt: str,
        game_context: str,
        personality: str = "rational",
    ) -> str:
        """生成发言

        Args:
            system_prompt: 系统提示（人格设定）
            game_context: 游戏上下文（历史发言、状态等）
            personality: 人格类型

        Returns:
            str: 生成的发言
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"当前游戏状态:\n{game_context}\n\n请作为{personality}型玩家发言，控制在50字以内。"},
        ]
        return self.chat(messages)

    def generate_vote_reasoning(
        self,
        system_prompt: str,
        game_context: str,
        candidates: List[int],
    ) -> Dict[int, float]:
        """生成投票决策

        Args:
            system_prompt: 系统提示
            game_context: 游戏上下文
            candidates: 可投票目标列表

        Returns:
            Dict[int, float]: 每个候选人的投票概率
        """
        candidates_str = ", ".join([f"{c}号" for c in candidates])
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"当前游戏状态:\n{game_context}\n\n可投票目标: {candidates_str}\n分析每个目标的可疑程度并给出投票建议。"},
        ]
        response = self.chat(messages)
        # 简化处理，返回随机权重（实际应解析 LLM 输出）
        import random
        weights = {c: random.random() for c in candidates}
        return weights


# 全局单例
_global_client: Optional[DeepSeekClient] = None


def get_llm_client() -> DeepSeekClient:
    """获取 LLM 客户端单例"""
    global _global_client
    if _global_client is None:
        _global_client = DeepSeekClient()
    return _global_client


def reset_llm_client():
    """重置 LLM 客户端（用于切换 API Key 后）"""
    global _global_client
    _global_client = None
    DeepSeekClient._llm = None
    DeepSeekClient._instance = None
