"""
sql_validator.py — SQL Validator Agent.

Bọc :class:`ValidatorTool`: kiểm tra an toàn, hợp lệ theo schema và cú
pháp. Kết quả kiểm tra được lưu vào ``state`` (qua cờ ``success`` tạm
thời và danh sách ``errors``) để orchestrator quyết định có cần kích
hoạt Self-Correction hay không.
"""

from __future__ import annotations

from .base import BaseAgent
from ..state import AgentState
from ..tool_manager import ToolManager


class SQLValidatorAgent(BaseAgent):
    name = "sql_validator"
    role = "Kiểm tra an toàn, schema và cú pháp của câu SQL"

    def __init__(self, tools: ToolManager | None = None):
        self.tools = tools or ToolManager()
        self.last_ok = False
        self.last_message = ""

    def act(self, state: AgentState) -> None:
        schema_map = self.tools.schema(state.db_path).schema_map()
        tool = self.tools.validator(state.db_path, schema_map=schema_map)
        ok, msg = tool.run(state.sql)
        self.last_ok = ok
        self.last_message = msg
        if ok:
            state.mark_task("Kiểm tra an toàn", "done")
            state.mark_task("Thực thi SQL", "running")
            state.add_step(self.name, "done", "SQL hợp lệ", 0)
        else:
            state.mark_task("Kiểm tra an toàn", "error")
            state.errors.append(msg)
            state.add_step(self.name, "error", msg, 0)
