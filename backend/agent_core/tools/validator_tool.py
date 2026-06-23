"""
validator_tool.py — SQL Validator Tool.

Kiểm tra một câu SQL trước khi thực thi, gồm ba mức:
  1. **An toàn**: chỉ cho phép SELECT, chặn các từ khoá nguy hiểm
     (DROP/DELETE/UPDATE/...). (Chuyển từ ``is_safe_query`` của bản cũ.)
  2. **Tĩnh theo schema**: bảng/cột tham chiếu phải tồn tại thật.
  3. **Cú pháp**: thử biên dịch câu lệnh bằng ``EXPLAIN`` (dry-run) để
     SQLite tự bắt lỗi cú pháp mà không cần chạy thật.
"""

from __future__ import annotations

import re
import sqlite3

DANGEROUS_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT",
    "ALTER", "TRUNCATE", "CREATE", "REPLACE", "EXEC",
}


class ValidatorTool:
    name = "sql_validator"
    description = "Kiểm tra an toàn, tính hợp lệ theo schema và cú pháp của SQL."

    def __init__(self, db_path: str, schema_map: dict[str, list[str]] | None = None):
        self.db_path = db_path
        self.schema_map = schema_map or {}

    # ── 1. An toàn ────────────────────────────────────────────
    @staticmethod
    def is_safe(query: str) -> tuple[bool, str]:
        norm = (query or "").strip().upper()
        if not norm.startswith("SELECT"):
            return False, "Chỉ cho phép câu lệnh SELECT."
        found = DANGEROUS_KEYWORDS & set(re.findall(r"\b[A-Z]+\b", norm))
        if found:
            return False, f"Phát hiện từ khoá bị chặn: {', '.join(sorted(found))}"
        return True, ""

    # ── 2. Tĩnh theo schema ───────────────────────────────────
    def check_tables(self, query: str) -> tuple[bool, str]:
        """Phát hiện tên bảng lạ xuất hiện sau FROM/JOIN."""
        if not self.schema_map:
            return True, ""
        known = {t.lower() for t in self.schema_map}
        refs = re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)",
                          query, flags=re.IGNORECASE)
        for tbl in refs:
            if tbl.lower() not in known:
                return False, f"Bảng không tồn tại: '{tbl}'"
        return True, ""

    # ── 3. Cú pháp (dry-run) ──────────────────────────────────
    def check_syntax(self, query: str) -> tuple[bool, str]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("EXPLAIN " + query)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            conn.close()

    # ── API tổng hợp ──────────────────────────────────────────
    def run(self, query: str) -> tuple[bool, str]:
        ok, msg = self.is_safe(query)
        if not ok:
            return False, msg
        ok, msg = self.check_tables(query)
        if not ok:
            return False, msg
        ok, msg = self.check_syntax(query)
        if not ok:
            return False, f"Lỗi cú pháp: {msg}"
        return True, ""
