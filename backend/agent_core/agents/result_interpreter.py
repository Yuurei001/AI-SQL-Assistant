"""
result_interpreter.py — Result Interpreter Agent.

Diễn giải bảng kết quả sang ngôn ngữ tự nhiên cho người dùng không rành
kỹ thuật: sinh đoạn tóm tắt, đặt nhãn thân thiện cho cột, giải thích ý
nghĩa cột, và chuẩn bị dữ liệu biểu đồ nếu phù hợp. Phần tóm tắt dùng
LLM (mock được khi test); phần biểu đồ dùng luật cố định.
"""

from __future__ import annotations

import json
import re

from .base import BaseAgent
from ..state import AgentState
from .. import llm


def make_chart_spec(df):
    """Sinh cấu hình biểu đồ cột nếu dữ liệu phù hợp, ngược lại None."""
    if df is None or len(df) == 0 or len(df) > 40:
        return None
    numeric = df.select_dtypes(include="number").columns.tolist()
    text = df.select_dtypes(include=["object", "string"]).columns.tolist()
    if not numeric or not text:
        return None
    x_col, y_col = text[0], numeric[0]
    return {
        "type": "bar",
        "x_col": x_col,
        "y_col": y_col,
        "data": df[[x_col, y_col]].head(20).to_dict(orient="list"),
    }


def _build_prompt(question, sql, columns, raw_schema, sample_rows):
    cols_spec = ", ".join(f'"{c}": "natural-language header"' for c in columns)
    means_spec = ", ".join(f'"{c}": "short business meaning"' for c in columns)
    return f"""You are a data analyst explaining a query result to a non-technical user.

DATABASE SCHEMA:
{raw_schema}

USER QUESTION: {question}

SQL THAT WAS RUN:
{sql}

RESULT COLUMNS: {", ".join(columns)}

SAMPLE OF THE RESULT (first rows):
{sample_rows}

Return ONLY valid JSON (no markdown) with this exact shape:
{{
  "summary": "2-3 sentences answering the question",
  "labels": {{ {cols_spec} }},
  "columns": {{ {means_spec} }}
}}"""


class ResultInterpreterAgent(BaseAgent):
    name = "result_interpreter"
    role = "Diễn giải kết quả sang ngôn ngữ tự nhiên + biểu đồ"

    def act(self, state: AgentState) -> None:
        df = state.df
        state.chart = make_chart_spec(df)

        if df is None or len(df) == 0:
            state.summary = "Truy vấn không trả về dòng dữ liệu nào."
            state.mark_task("Diễn giải kết quả", "done")
            state.mark_task("Tổng hợp phản hồi", "running")
            state.add_step(self.name, "done", "Không có dữ liệu để diễn giải", 0)
            return

        try:
            sample = df.head(5).to_csv(index=False)
            prompt = _build_prompt(
                state.question, state.sql, list(df.columns),
                state.raw_schema, sample,
            )
            raw = llm.complete(prompt)
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```$", "", raw).strip()
            data = json.loads(raw)
            state.summary = str(data.get("summary", "")).strip()
            state.labels = {str(k): str(v) for k, v in data.get("labels", {}).items()}
            state.columns_info = {
                str(k): str(v) for k, v in data.get("columns", {}).items()
            }
        except Exception:
            # Fallback: vẫn trả kết quả, chỉ thiếu phần diễn giải LLM.
            state.summary = f"Truy vấn trả về {len(df)} dòng kết quả."

        state.mark_task("Diễn giải kết quả", "done")
        state.mark_task("Tổng hợp phản hồi", "running")
        state.add_step(self.name, "done", state.summary[:80], 0)
