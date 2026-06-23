"""
schema_analyzer.py — Schema Analyzer Agent.

Dùng :class:`SchemaTool` để đọc cấu trúc cơ sở dữ liệu, nạp mô tả
schema vào trạng thái và xác định sơ bộ các bảng có khả năng liên quan
tới câu hỏi (so khớp tên bảng/cột với từ trong câu hỏi). Đây là bước
"grounding" giúp SQL Generator sinh truy vấn bám sát schema thật.
"""

from __future__ import annotations

from .base import BaseAgent
from ..state import AgentState
from ..tool_manager import ToolManager


class SchemaAnalyzerAgent(BaseAgent):
    name = "schema_analyzer"
    role = "Phân tích schema, chọn bảng/cột liên quan tới câu hỏi"

    def __init__(self, tools: ToolManager | None = None):
        self.tools = tools or ToolManager()

    def act(self, state: AgentState) -> None:
        tool = self.tools.schema(state.db_path)
        state.raw_schema = tool.describe()

        schema_map = tool.schema_map()
        q = state.question.lower()
        relevant: list[str] = []
        for table, cols in schema_map.items():
            hit = table.lower() in q or any(c.lower() in q for c in cols)
            if hit:
                relevant.append(table)
        # Nếu không khớp được bảng nào, coi như tất cả đều có thể liên quan.
        state.relevant_tables = relevant or list(schema_map.keys())
        state.mark_task("Phân tích schema", "done")
        state.mark_task("Sinh câu truy vấn", "running")

        state.add_step(
            self.name, "done",
            "Bảng liên quan: " + ", ".join(state.relevant_tables), 0,
        )
