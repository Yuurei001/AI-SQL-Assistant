"""
sql_executor.py — SQL Executor Agent.

Bọc :class:`ExecutorTool` (có timeout) để chạy câu SQL đã được tối ưu
bởi :class:`OptimizerTool`. Nếu thực thi lỗi/timeout, agent ghi lỗi vào
``state.errors`` và đặt ``state.df = None`` để orchestrator kích hoạt
Self-Correction. Agent **không ném exception ra ngoài**.
"""

from __future__ import annotations

from .base import BaseAgent
from ..state import AgentState
from ..tool_manager import ToolManager


class SQLExecutorAgent(BaseAgent):
    name = "sql_executor"
    role = "Tối ưu nhẹ rồi thực thi SQL (có timeout)"

    def __init__(self, tools: ToolManager | None = None):
        self.tools = tools or ToolManager()
        self.optimizer = self.tools.optimizer()
        self.last_error: str | None = None

    def act(self, state: AgentState) -> None:
        optimized, warns = self.optimizer.run(state.sql)
        state.sql = optimized

        executor = self.tools.executor(
            state.db_path,
            timeout_seconds=state.timeout_seconds,
        )
        df, error = executor.run(optimized)
        self.last_error = error

        if error is None:
            state.df = df
            state.columns = list(df.columns) if df is not None else []
            state.mark_task("Thực thi SQL", "done")
            state.mark_task("Diễn giải kết quả", "running")
            detail = f"Trả về {0 if df is None else len(df)} dòng"
            if warns:
                detail += " | " + "; ".join(warns)
            state.add_step(self.name, "done", detail, 0)
        else:
            state.df = None
            state.mark_task("Thực thi SQL", "error")
            state.errors.append(error)
            state.add_step(self.name, "error", error, 0)
