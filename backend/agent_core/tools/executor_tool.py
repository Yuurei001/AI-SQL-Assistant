"""
executor_tool.py — SQL Executor Tool (có kiểm soát Timeout).

Trách nhiệm: thực thi câu lệnh SELECT trên cơ sở dữ liệu và trả về
DataFrame. Việc thực thi được chạy trong một luồng riêng và **giới hạn
thời gian** (timeout): nếu truy vấn chạy quá lâu, tool trả về lỗi
timeout thay vì treo cả tiến trình — đây là một phần của cơ chế
*Timeout Handler / Graceful Fallback*.
"""

from __future__ import annotations

import sqlite3
import time
from threading import Lock, Thread

import pandas as pd


class TimeoutError_(Exception):
    """Truy vấn vượt quá thời gian cho phép."""


class ExecutorTool:
    name = "sql_executor"
    description = "Thực thi câu SELECT với giới hạn thời gian (timeout)."

    def __init__(self, db_path: str, timeout_seconds: int = 15):
        self.db_path = db_path
        self.timeout_seconds = timeout_seconds
        self._connection: sqlite3.Connection | None = None
        self._connection_lock = Lock()

    def _run_query(self, query: str) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        deadline = time.monotonic() + self.timeout_seconds
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() >= deadline else 0,
            1000,
        )
        with self._connection_lock:
            self._connection = conn
        try:
            return pd.read_sql_query(query, conn)
        finally:
            conn.set_progress_handler(None, 0)
            with self._connection_lock:
                self._connection = None
            conn.close()

    def _interrupt(self) -> None:
        with self._connection_lock:
            connection = self._connection
        if connection is not None:
            connection.interrupt()

    def run(self, query: str) -> tuple[pd.DataFrame | None, str | None]:
        """Trả về ``(df, None)`` nếu thành công, ``(None, error)`` nếu lỗi.

        Lỗi có thể là lỗi cú pháp/thực thi SQLite hoặc timeout. Tool
        **không bao giờ ném exception ra ngoài** — luôn trả về thông tin
        lỗi để Self-Correction Agent xử lý.
        """
        holder: list[tuple[str, object]] = []

        def worker():
            try:
                df = self._run_query(query)
                holder.append(("ok", df))
            except Exception as exc:  # noqa: BLE001 - cố ý bắt mọi lỗi SQL
                holder.append(("err", str(exc)))

        thread = Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        if thread.is_alive():
            self._interrupt()
            thread.join(timeout=1)
            return None, (
                f"Truy vấn vượt quá {self.timeout_seconds}s (timeout). "
                "SQLite đã nhận tín hiệu hủy; hãy tối ưu truy vấn để thử lại."
            )
        if not holder:
            return None, "Không nhận được kết quả thực thi."
        status, payload = holder[0]
        if status == "ok":
            return payload, None  # type: ignore[return-value]
        return None, str(payload)
