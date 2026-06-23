"""
response_generator.py — Response Generator Agent.

Agent cuối cùng: gom toàn bộ sản phẩm của pipeline trong ``state`` thành
một đối tượng phản hồi (dict) sẵn sàng trả về cho tầng web/JSON, bao gồm
cả **timeline trạng thái các agent** để giao diện hiển thị.
"""

from __future__ import annotations

import pandas as pd

from .base import BaseAgent
from ..state import AgentState

MAX_ROWS = 500


class ResponseGeneratorAgent(BaseAgent):
    name = "response_generator"
    role = "Tổng hợp phản hồi cuối cùng cho người dùng"

    def act(self, state: AgentState) -> None:
        if getattr(state, "should_query_database", True):
            state.success = state.df is not None
            state.mark_task(
                "Tổng hợp phản hồi",
                "done" if state.success else "error",
            )
            if state.success and state.retries:
                state.mark_task("Tự sửa lỗi", "done")
            state.add_step(
                self.name, "done" if state.success else "error",
                "Hoàn tất phản hồi", 0,
            )
        else:
            state.success = True
            state.summary = state.direct_response or ""
            state.mark_task(
                "Hoàn tất phản hồi",
                "done",
            )
            state.add_step(
                self.name, "done",
                "Hoàn tất phản hồi", 0,
            )

    # Không nằm trong act() vì cần trả giá trị; orchestrator gọi sau cùng.
    def build_payload(self, state: AgentState) -> dict:
        df = state.df

        def pretty(col: str) -> str:
            lbl = state.labels.get(col)
            return lbl if lbl else str(col).replace("_", " ").strip().capitalize()

        data_list: list[dict] = []
        if df is not None and len(df) > 0:
            disp = df.head(MAX_ROWS).copy()
            disp.columns = [pretty(c) for c in disp.columns]
            data_list = disp.where(pd.notnull(disp), None).to_dict(orient="records")

        return {
            "success": state.success,
            "question": state.question,
            "plan": state.plan,
            "sql": state.sql,
            "summary": state.summary,
            "data": data_list,
            "chart": state.chart,
            "columns_info": state.columns_info,
            "total_rows": 0 if df is None else len(df),
            "steps": state.steps,
            "task_status": state.task_status,
            "retries": state.retries,
            "retry_events": state.retry_events,
            "errors_corrected": state.errors,
            "execution_ms": state.execution_ms,
            "conversation_id": state.conversation_id,
            "error": None if state.success else (state.final_error or "Truy vấn thất bại"),
        }
