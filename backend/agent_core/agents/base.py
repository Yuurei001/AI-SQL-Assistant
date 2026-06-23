"""
base.py — Lớp cơ sở cho mọi agent.

Mỗi agent kế thừa :class:`BaseAgent`, khai báo ``name`` (mã) và
``role`` (mô tả vai trò), rồi hiện thực :meth:`act`. Lớp cơ sở lo phần
*đo thời gian* và *ghi nhật ký bước* (``state.add_step``) một cách
thống nhất, để mọi agent đều xuất hiện trên timeline của giao diện.
"""

from __future__ import annotations

import logging
import time

from ..state import AgentState

log = logging.getLogger("agent_core")


class BaseAgent:
    name: str = "agent"
    role: str = ""

    def act(self, state: AgentState) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def run(self, state: AgentState) -> AgentState:
        """Bao bọc :meth:`act` với đo thời gian + ghi step + bắt lỗi."""
        start = time.perf_counter()
        log.info("→ %s bắt đầu", self.name)
        try:
            self.act(state)
            dur = int((time.perf_counter() - start) * 1000)
            # Nếu agent chưa tự ghi step thì ghi mặc định 'done'.
            if not state.steps or state.steps[-1]["agent"] != self.name:
                state.add_step(self.name, "done", self.role, dur)
            else:
                state.steps[-1]["duration_ms"] = dur
            log.info("← %s xong (%dms)", self.name, dur)
        except Exception as exc:  # noqa: BLE001
            dur = int((time.perf_counter() - start) * 1000)
            state.add_step(self.name, "error", str(exc), dur)
            state.errors.append(f"[{self.name}] {exc}")
            log.exception("✗ %s lỗi: %s", self.name, exc)
        return state
