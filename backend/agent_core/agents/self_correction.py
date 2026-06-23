"""
self_correction.py — Self-Correction Agent (cốt lõi của Feedback Loop).

Khi Validator hoặc Executor báo lỗi, agent này:
  1. Đọc thông điệp lỗi (lỗi cú pháp SQLite, sai bảng/cột, timeout...).
  2. Phân tích và phân loại lỗi để đưa gợi ý sửa.
  3. Gọi LLM sinh lại câu SQL mới (dùng lại :func:`build_prompt` với
     ``error_context``).
Hệ thống **không dừng lại khi gặp lỗi** mà lặp lại tới ``max_retries``
lần — đây chính là cơ chế tự sửa (self-correction).
"""

from __future__ import annotations

from .base import BaseAgent
from ..state import AgentState
from .sql_generator import build_prompt, clean_sql, is_echo_query
from .. import llm


def classify_error(error: str) -> str:
    """Phân loại lỗi để gợi ý hướng sửa (reasoning của agent)."""
    e = (error or "").lower()
    if "timeout" in e or "vượt quá" in e:
        return "Truy vấn quá chậm — đơn giản hoá, thêm điều kiện lọc hoặc LIMIT."
    if "no such table" in e or "không tồn tại" in e and "bảng" in e:
        return "Sai tên bảng — dùng đúng tên bảng có trong schema."
    if "no such column" in e:
        return "Sai tên cột — dùng đúng tên cột có trong schema."
    if "syntax error" in e or "cú pháp" in e:
        return "Lỗi cú pháp — viết lại câu lệnh đúng chuẩn SQLite."
    return "Xem lại câu lệnh cho phù hợp với schema và mục tiêu câu hỏi."


class SelfCorrectionAgent(BaseAgent):
    name = "self_correction"
    role = "Phân tích lỗi và sinh lại SQL đúng (tự sửa)"

    def act(self, state: AgentState) -> None:
        last_error = state.errors[-1] if state.errors else "Unknown error"
        hint = classify_error(last_error)
        error_context = (
            f"Error: {last_error}\n"
            f"Failed query: {state.sql}\n"
            f"Hint: {hint}"
        )
        prompt = build_prompt(
            state.question, state.raw_schema, error_context=error_context
        )
        regenerated = clean_sql(llm.complete(prompt))
        
        if is_echo_query(regenerated):
            state.sql = ""
            state.final_error = "LLM tự sửa lỗi sinh câu truy vấn SQL giả lập (chào hỏi/echo) thay vì truy vấn database."
            state.add_step(self.name, "error", "Self-correction từ chối sinh SQL giả lập", 0)
            raise RuntimeError(state.final_error)
            
        state.sql = regenerated
        state.retries += 1
        state.retry_events.append(
            {
                "attempt": state.retries,
                "error": last_error,
                "analysis": hint,
                "regenerated_sql": state.sql,
            }
        )
        state.mark_task("Tự sửa lỗi", "running")
        state.mark_task("Kiểm tra an toàn", "running")
        state.mark_task("Thực thi SQL", "pending")
        state.add_step(
            self.name, "retry",
            f"Lần {state.retries}: {hint} → {state.sql}", 0,
        )
