"""
orchestrator.py — Bộ điều phối đa tác tử (Plan-and-Execute + Feedback Loop).

Điều phối luồng:

    Planner → Schema Analyzer → SQL Generator
        → [ Validator → Executor ]  ◄─┐
                 │ lỗi?               │  Self-Correction (tối đa N lần)
                 └────────────────────┘
        → Result Interpreter → Response Generator

Tích hợp sẵn: **Timeout Handler** (trong ExecutorTool), **Retry
Mechanism** + **Self-Correction** (vòng lặp dưới đây), **Graceful
Fallback** (trả thông báo thân thiện thay vì crash) và **Logging**
(ghi ra ``logs/agent.log``).
"""

from __future__ import annotations

import logging
import os
import time

from .state import AgentState
from .tool_manager import ToolManager
from .tools import MemoryManager, MemoryTool
from .agents import (
    PlannerAgent,
    SchemaAnalyzerAgent,
    SQLGeneratorAgent,
    SQLValidatorAgent,
    SQLExecutorAgent,
    SelfCorrectionAgent,
    ResultInterpreterAgent,
    ResponseGeneratorAgent,
    ConversationRouterAgent,
)

# ── Cấu hình logging một lần ──────────────────────────────────
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
log = logging.getLogger("agent_core")
if not log.handlers:
    log.setLevel(logging.INFO)
    _fh = logging.FileHandler(os.path.join(_LOG_DIR, "agent.log"), encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(_fh)


class AgenticOrchestrator:
    """Điều phối toàn bộ vòng đời một yêu cầu truy vấn."""

    def __init__(
        self,
        memory: MemoryTool | None = None,
        memory_manager: MemoryManager | None = None,
        tools: ToolManager | None = None,
    ):
        self.tools = tools or ToolManager(memory_manager=memory_manager)
        self._legacy_memory = memory
        self.memory = memory or self.tools.memory("default")

    def handle(
        self,
        question: str,
        db_path: str,
        conversation_id: str = "default",
        max_retries: int = 2,
        timeout_seconds: int = 15,
    ) -> dict:
        started = time.perf_counter()
        log.info("=== Yêu cầu mới: %r (db=%s) ===", question, db_path)
        state = AgentState(
            question=question,
            db_path=db_path,
            conversation_id=conversation_id,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
        memory = self._legacy_memory or self.tools.memory(conversation_id)

        # 1) Phân loại ý định (Conversation Router)
        ConversationRouterAgent().run(state)

        # 2) Lập kế hoạch (Planner)
        PlannerAgent().run(state)

        # 3) Định tuyến: chỉ chạy SQL pipeline khi có ý định truy vấn DB
        if state.should_query_database:
            SchemaAnalyzerAgent(tools=self.tools).run(state)
            SQLGeneratorAgent(memory=memory).run(state)

            validator = SQLValidatorAgent(tools=self.tools)
            executor = SQLExecutorAgent(tools=self.tools)
            corrector = SelfCorrectionAgent()

            # 4) Vòng lặp Validate → Execute với Self-Correction (Feedback Loop)
            for attempt in range(max_retries + 1):
                if not state.sql:
                    break
                validator.run(state)
                if not validator.last_ok:
                    if attempt < max_retries:
                        corrector.run(state)
                        continue
                    state.final_error = f"SQL không hợp lệ: {validator.last_message}"
                    break

                executor.run(state)
                if executor.last_error is None:
                    state.success = True
                    break

                # Thực thi lỗi → tự sửa nếu còn lượt
                if attempt < max_retries:
                    corrector.run(state)
                    continue
                state.final_error = f"Thực thi thất bại: {executor.last_error}"
                break

            # 5) Diễn giải (chỉ khi có dữ liệu) — Graceful fallback nếu thất bại
            if state.success:
                ResultInterpreterAgent().run(state)
            else:
                log.warning("Thất bại sau %d lần thử: %s", state.retries, state.final_error)
                state.add_step("self_correction", "error", state.final_error, 0)
        else:
            state.success = True
            state.final_error = ""

        # 6) Tổng hợp phản hồi
        resp_agent = ResponseGeneratorAgent()
        state.execution_ms = int((time.perf_counter() - started) * 1000)
        resp_agent.run(state)
        payload = resp_agent.build_payload(state)

        # Ghi nhớ lượt hội thoại để dùng cho câu hỏi tiếp theo
        if state.success and state.should_query_database:
            memory.remember(question, state.sql, state.summary)

        log.info("=== Kết thúc: success=%s, retries=%d ===", state.success, state.retries)
        return payload

    def history(self, conversation_id: str, limit: int = 20) -> list[dict]:
        memory = self._legacy_memory or self.tools.memory(conversation_id)
        return [
            {"question": turn.question, "sql": turn.sql, "summary": turn.summary}
            for turn in memory.recent(limit)
        ]

    def clear_history(self, conversation_id: str) -> None:
        if self._legacy_memory is None:
            self.tools.memory_manager.clear(conversation_id)


def run_agentic(
    question: str,
    db_path: str,
    conversation_id: str = "default",
    max_retries: int = 2,
    timeout_seconds: int = 15,
    memory: MemoryTool | None = None,
) -> dict:
    """Tiện ích chạy một yêu cầu (tạo orchestrator dùng-một-lần)."""
    return AgenticOrchestrator(memory=memory).handle(
        question,
        db_path,
        conversation_id=conversation_id,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
    )
