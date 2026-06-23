"""
sql_generator.py — SQL Generator Agent.

Sinh câu lệnh SQL từ câu hỏi ngôn ngữ tự nhiên bằng LLM (Gemini).
Toàn bộ lời gọi LLM đi qua :func:`agent_core.llm.complete` nên có thể
mock khi kiểm thử. Agent cũng tham chiếu **Memory Tool** để hiểu ngữ
cảnh các câu hỏi trước đó.

Hàm :func:`build_prompt` và :func:`clean_sql` được tách riêng để
**Self-Correction Agent** tái sử dụng khi cần sinh lại SQL từ lỗi.
"""

from __future__ import annotations

import re

from .base import BaseAgent
from ..state import AgentState
from .. import llm


def clean_sql(raw: str) -> str:
    """Loại bỏ markdown/code-fence mà LLM hay kèm theo."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def build_prompt(
    question: str,
    raw_schema: str,
    memory_context: str = "",
    error_context: str = "",
) -> str:
    """Dựng prompt cho LLM. Nếu có *error_context* thì ở chế độ sửa lỗi."""
    base = f"""You are a senior SQLite developer.

DATABASE SCHEMA:
{raw_schema}

RULES:
- Output ONLY the raw SQL query.
- No markdown, no code fences, no explanation.
- Use exact table and column names.
- Only SELECT statements."""

    if memory_context:
        base += f"\n\n{memory_context}"

    if error_context:
        base += f"""

PREVIOUS FAILED QUERY ERROR:
{error_context}

Fix the error and generate the corrected SQL query."""

    base += f"\n\nQUESTION: {question}"
    return base


def is_echo_query(sql: str) -> bool:
    """Kiểm tra xem câu SQL có phải là dạng echo câu chào hỏi hay số vô nghĩa hay không."""
    norm_sql = (sql or "").upper().strip()
    # Khớp các dạng: SELECT 'text'; hoặc SELECT 1;
    m_literal = re.match(r"^SELECT\s+['\"](.*)['\"](?:\s*;?|\s+LIMIT\s+\d+\s*;?)$", norm_sql, re.IGNORECASE)
    m_number = re.match(r"^SELECT\s+\d+(?:\s*;?|\s+LIMIT\s+\d+\s*;?)$", norm_sql, re.IGNORECASE)
    
    if m_literal:
        val = m_literal.group(1).lower().strip()
        if val in ("hi", "hello", "ok", "cảm ơn", "cam on", "chào", "chao", "bạn là ai", "ban la ai", "help", "giúp tôi với", "giup toi voi"):
            return True
    elif m_number:
        return True
    return False


class SQLGeneratorAgent(BaseAgent):
    name = "sql_generator"
    role = "Sinh câu lệnh SQL từ câu hỏi (gọi LLM)"

    def __init__(self, memory=None):
        self.memory = memory

    def act(self, state: AgentState) -> None:
        if not getattr(state, "should_query_database", True):
            state.sql = ""
            state.add_step(self.name, "skipped", "Bỏ qua sinh SQL do không cần truy vấn DB", 0)
            return

        mem_ctx = self.memory.as_context() if self.memory else ""
        prompt = build_prompt(state.question, state.raw_schema, mem_ctx)
        generated_sql = clean_sql(llm.complete(prompt))
        
        # Kiểm tra an toàn: ngăn chặn sinh câu SQL dạng echo/chào hỏi vô nghĩa
        if is_echo_query(generated_sql):
            state.sql = ""
            state.final_error = "LLM sinh câu truy vấn SQL giả lập (chào hỏi/echo) thay vì truy vấn database."
            state.add_step(self.name, "error", "SQL generator từ chối sinh SQL giả lập", 0)
            raise RuntimeError(state.final_error)
            
        state.sql = generated_sql
        state.mark_task("Sinh câu truy vấn", "done")
        state.mark_task("Kiểm tra an toàn", "running")
        state.add_step(self.name, "done", state.sql, 0)
