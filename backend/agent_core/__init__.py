"""
agent_core — Kiến trúc Agentic AI cho AI SQL Assistant.

Gói này hiện thực hệ đa tác tử (multi-agent) theo mô hình
**Plan-and-Execute** kèm **Feedback Loop / Self-Correction**:

    User
      │
      ▼
    Planner Agent ──► Schema Analyzer ──► SQL Generator
                                              │
                                              ▼
                                         SQL Validator ◄──┐
                                              │           │
                                              ▼           │ (sửa lỗi)
                                         SQL Executor     │
                                              │           │
                                       lỗi?  ─┴─► Self-Correction Agent
                                              │
                                              ▼
                                      Result Interpreter ──► Response Generator ──► User

Các tác tử (agents) là "bộ não" điều phối, còn các thao tác cụ thể
(đọc schema, chạy SQL, kiểm tra, tối ưu, ghi nhớ) được tách thành
các *Tool* để minh hoạ cơ chế **Tool Calling**.
"""

from .orchestrator import run_agentic, AgenticOrchestrator
from .state import AgentState

__all__ = ["run_agentic", "AgenticOrchestrator", "AgentState"]
