"""DeepSeek LLM 客户端

使用 LangChain 调用 DeepSeek API
"""
import os
from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage

from utils.config import LLMConfig, GameConfig


class DeepSeekChatOpenAI(ChatOpenAI):
    """兼容 DeepSeek 思考模式的 ChatOpenAI 子类

    DeepSeek 的思考模式模型在响应中返回 reasoning_content，并要求在后续多轮对话中
    传回该字段。LangGraph 的 ReAct Agent 在多轮工具调用中不会保留 reasoning_content，
    导致第二轮及后续 API 调用报 400 错误:
    "The reasoning_content in the thinking mode must be passed back to the API."

    解决方案（双重保障）：
    1. extra_body 中同时设置 enable_thinking=False 和 thinking={type:disabled}
    2. 在 _generate 中主动剥离消息里的 reasoning_content，防止 LangGraph 循环时带入
    """

    def __init__(self, **kwargs):
        extra_body = kwargs.pop('extra_body', {})
        extra_body.setdefault('enable_thinking', False)
        extra_body.setdefault('thinking', {'type': 'disabled'})
        kwargs['extra_body'] = extra_body
        super().__init__(**kwargs)

    @staticmethod
    def _strip_reasoning_content(msg: BaseMessage) -> BaseMessage:
        """从消息中移除 reasoning_content，避免多轮对话 400 错误"""
        ak = getattr(msg, 'additional_kwargs', None) or {}
        if 'reasoning_content' not in ak:
            return msg
        new_ak = {k: v for k, v in ak.items() if k != 'reasoning_content'}
        new_resp = {k: v for k, v in (getattr(msg, 'response_metadata', None) or {}).items()
                    if k != 'reasoning_content'}
        try:
            return msg.model_copy(update={
                'additional_kwargs': new_ak,
                'response_metadata': new_resp,
            })
        except AttributeError:
            msg_copy = msg.copy()
            msg_copy.additional_kwargs = new_ak
            msg_copy.response_metadata = new_resp
            return msg_copy

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        cleaned = [self._strip_reasoning_content(m) for m in messages]
        return super()._generate(cleaned, stop=stop, run_manager=run_manager, **kwargs)


class DeepSeekClient:
    """DeepSeek LLM 客户端"""

    _instance: Optional["DeepSeekClient"] = None
    _llm: Optional[DeepSeekChatOpenAI] = None

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

        self._llm = DeepSeekChatOpenAI(
            model="deepseek-v4-flash",
            api_key=api_key,
            base_url=LLMConfig.DEEPSEEK_API_BASE,
            temperature=GameConfig.LLM_TEMPERATURE,
        )

    @property
    def llm(self) -> DeepSeekChatOpenAI:
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

    # def generate_speech(
    #     self,
    #     system_prompt: str,
    #     game_context: str,
    #     personality: str = "rational",
    # ) -> str:
    #     """生成发言

    #     Args:
    #         system_prompt: 系统提示（人格设定）
    #         game_context: 游戏上下文（历史发言、状态等）
    #         personality: 人格类型

    #     Returns:
    #         str: 生成的发言
    #     """
    #     messages = [
    #         {"role": "system", "content": system_prompt},
    #         {"role": "user", "content": f"当前游戏状态:\n{game_context}\n\n请作为{personality}型玩家发言，控制在50字以内。"},
    #     ]
    #     return self.chat(messages)

    # def generate_vote_reasoning(
    #     self,
    #     system_prompt: str,
    #     game_context: str,
    #     candidates: List[int],
    # ) -> Dict[int, float]:
    #     """生成投票决策

    #     Args:
    #         system_prompt: 系统提示
    #         game_context: 游戏上下文
    #         candidates: 可投票目标列表

    #     Returns:
    #         Dict[int, float]: 每个候选人的投票概率
    #     """
    #     candidates_str = ", ".join([f"{c}号" for c in candidates])
    #     messages = [
    #         {"role": "system", "content": system_prompt},
    #         {"role": "user", "content": f"当前游戏状态:\n{game_context}\n\n可投票目标: {candidates_str}\n分析每个目标的可疑程度并给出投票建议。"},
    #     ]
    #     response = self.chat(messages)
    #     # 简化处理，返回随机权重（实际应解析 LLM 输出）
    #     import random
    #     weights = {c: random.random() for c in candidates}
    #     return weights


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
