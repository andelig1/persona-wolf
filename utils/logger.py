"""游戏日志模块

将所有 Agent 工具调用、ReAct 推理阶段、DEBUG 错误信息写入日志文件。
不输出到命令行，保持游戏界面干净。
"""
import os
import threading
from datetime import datetime
from typing import Optional


class GameLogger:
    """游戏日志记录器 — 线程安全单例"""

    _instance: Optional["GameLogger"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._log_dir = "logs"
        self._file = None
        self._file_path = None

        # 当前游戏上下文（由外部每轮更新）
        self.context = {
            "day": 0,
            "phase": "",
            "round": 0,
        }

    # ==================== 文件管理 ====================

    def _ensure_file(self):
        """确保日志文件已打开"""
        if self._file is not None:
            return
        os.makedirs(self._log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._file_path = os.path.join(self._log_dir, f"game_{ts}.log")
        self._file = open(self._file_path, "w", encoding="utf-8", buffering=1)

    @property
    def log_path(self) -> Optional[str]:
        return self._file_path

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    # ==================== 上下文管理 ====================

    def set_context(self, **kwargs):
        """更新当前上下文（day, phase, round, role 等）"""
        self.context.update(kwargs)

    def _ctx_str(self, extra: dict = None) -> str:
        """构建上下文字符串"""
        ctx = dict(self.context)
        if extra:
            ctx.update(extra)
        parts = []
        if ctx.get("day"):
            parts.append(f"第{ctx['day']}天")
        if ctx.get("phase") and ctx["phase"] not in ("speak", "vote", "night", "agent"):
            parts.append(ctx["phase"])
        if ctx.get("round"):
            parts.append(f"第{ctx['round']}轮")
        if ctx.get("agent_id"):
            role = ctx.get("agent_role", "")
            parts.append(f"{ctx['agent_id']}号{role}")
        if ctx.get("action"):
            parts.append(f"[{ctx['action']}]")
        return " ".join(parts)

    def _write(self, level: str, message: str, extra_ctx: dict = None):
        """写入一行日志"""
        self._ensure_file()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        ctx = self._ctx_str(extra_ctx)
        if ctx:
            line = f"[{ts}] [{level}] [{ctx}] {message}"
        else:
            line = f"[{ts}] [{level}] {message}"
        self._file.write(line + "\n")

    # ==================== 日志方法 ====================

    def info(self, message: str, **ctx):
        self._write("INFO", message, ctx)

    def error(self, message: str, **ctx):
        self._write("ERROR", message, ctx)

    def tool_call(self, name: str, args: dict, agent_id: int = None,
                  agent_role: str = None, action: str = "agent"):
        """记录工具调用"""
        brief_args = {}
        for k, v in args.items():
            s = str(v)
            brief_args[k] = s[:80] + "..." if len(s) > 80 else s
        self._write("TOOL", f"-> {name}({brief_args})", {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "action": action,
        })

    def tool_result(self, result: str, agent_id: int = None,
                    agent_role: str = None, action: str = "agent"):
        """记录工具返回"""
        preview = str(result)[:200] if result else "(empty)"
        self._write("TOOL", f"<- {preview}", {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "action": action,
        })

    def tool_summary(self, count: int, agent_id: int = None,
                     agent_role: str = None, action: str = "agent"):
        """记录工具调用总数"""
        self._write("TOOL", f"共调用 {count} 次工具", {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "action": action,
        })

    def phase(self, message: str, agent_id: int = None,
              agent_role: str = None, action: str = "agent"):
        """记录推理阶段转换"""
        self._write("PHASE", message, {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "action": action,
        })

    def speak_result(self, speech: str, agent_id: int = None,
                     agent_role: str = None):
        """记录发言生成结果"""
        preview = speech[:120] if speech else "(empty)"
        self._write("SPEAK", preview, {
            "agent_id": agent_id,
            "agent_role": agent_role,
            "action": "speak",
        })


# 模块级便捷函数
_logger = GameLogger()


def get_logger() -> GameLogger:
    return _logger


def reset_logger():
    """关闭并重置日志（用于新游戏）"""
    global _logger
    _logger.close()
    _logger = GameLogger()
