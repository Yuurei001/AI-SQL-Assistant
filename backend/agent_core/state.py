"""
state.py — Trạng thái dùng chung (shared memory) chảy qua các agent.

:class:`AgentState` là "bộ nhớ làm việc" (working memory) được truyền
tuần tự qua từng agent trong orchestrator. Mỗi agent đọc các trường nó
cần và ghi kết quả của mình vào, đồng thời ghi lại một dòng vào
``steps`` để giao diện và báo cáo có thể hiển thị **trạng thái Agent**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


@dataclass
class AgentState:
    # ── Đầu vào ────────────────────────────────────────────────
    question: str
    db_path: str
    conversation_id: str = "default"
    max_retries: int = 2
    timeout_seconds: int = 15

    # ── Intent và Định tuyến ───────────────────────────────────
    intent: str = "database_query"
    should_query_database: bool = True
    direct_response: Optional[str] = None

    # ── Sản phẩm trung gian của các agent ─────────────────────
    raw_schema: str = ""
    relevant_tables: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    sql: str = ""
    df: Optional[pd.DataFrame] = None
    columns: list[str] = field(default_factory=list)

    # ── Diễn giải kết quả ─────────────────────────────────────
    summary: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    columns_info: dict[str, str] = field(default_factory=dict)
    chart: Optional[dict[str, Any]] = None

    # ── Theo dõi lỗi & vòng lặp tự sửa ────────────────────────
    errors: list[str] = field(default_factory=list)
    retry_events: list[dict[str, Any]] = field(default_factory=list)
    retries: int = 0
    success: bool = False
    final_error: str = ""
    execution_ms: int = 0
    halted: bool = False

    # ── Nhật ký các bước agent (cho UI / báo cáo) ─────────────
    steps: list[dict[str, Any]] = field(default_factory=list)
    task_status: list[dict[str, Any]] = field(default_factory=list)

    def add_step(
        self,
        agent: str,
        status: str = "done",
        detail: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Ghi lại một mốc thực thi của agent.

        status ∈ {"done", "running", "error", "skipped", "retry"}.
        """
        self.steps.append(
            {
                "agent": agent,
                "status": status,
                "detail": detail,
                "duration_ms": duration_ms,
            }
        )

    def initialize_tasks(self) -> None:
        """Khởi tạo trạng thái cho task list do Planner tạo."""
        self.task_status = [
            {"index": index, "task": task, "status": "pending"}
            for index, task in enumerate(self.plan, start=1)
        ]

    def mark_task(self, keyword: str, status: str) -> None:
        """Đánh dấu task đầu tiên chứa *keyword* bằng trạng thái mới."""
        needle = keyword.casefold()
        for task in self.task_status:
            if needle in task["task"].casefold():
                task["status"] = status
                return
