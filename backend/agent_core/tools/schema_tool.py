"""
schema_tool.py — Database Schema Tool.

Trách nhiệm: trích xuất cấu trúc cơ sở dữ liệu (bảng, cột, khoá chính,
khoá ngoại) để agent hiểu được "thế giới" mà nó đang truy vấn.
Việc tách thành tool giúp agent không cần biết chi tiết SQLite/PRAGMA.
"""

from __future__ import annotations

import sqlite3


class SchemaTool:
    name = "database_schema"
    description = "Đọc schema (bảng, cột, PK, FK) của cơ sở dữ liệu SQLite."

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ── API công khai ─────────────────────────────────────────
    def user_tables(self) -> list[str]:
        """Danh sách bảng do người dùng tạo (bỏ bảng nội bộ sqlite_*)."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def columns_of(self, table: str) -> list[str]:
        """Tên các cột của một bảng."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table});")
            return [c[1] for c in cur.fetchall()]
        finally:
            conn.close()

    def schema_map(self) -> dict[str, list[str]]:
        """Bản đồ {tên_bảng: [cột,...]} — dùng cho kiểm tra tĩnh."""
        return {t: self.columns_of(t) for t in self.user_tables()}

    def relationships(self) -> list[tuple[str, str, str, str]]:
        """Danh sách khoá ngoại: (bảng_con, cột_con, bảng_cha, cột_cha)."""
        rels: list[tuple[str, str, str, str]] = []
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            for t in self.user_tables():
                cur.execute(f"PRAGMA foreign_key_list({t});")
                for fk in cur.fetchall():
                    # fk = (id, seq, table, from, to, on_update, on_delete, match)
                    rels.append((t, fk[3], fk[2], fk[4]))
        finally:
            conn.close()
        return rels

    def describe(self) -> str:
        """Mô tả schema dạng văn bản để đưa vào prompt cho LLM."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            tables = self.user_tables()
            if not tables:
                return "(no tables)"
            lines: list[str] = []
            for tname in tables:
                cur.execute(f"PRAGMA table_info({tname});")
                lines.append(f"TABLE {tname}")
                for col in cur.fetchall():
                    pk = " [PK]" if col[5] else ""
                    nn = " NN" if col[3] else ""
                    lines.append(f"  ├─ {col[1]} {col[2]}{pk}{nn}")
                lines.append("")
            # Quan hệ giữa các bảng
            rels = self.relationships()
            if rels:
                lines.append("RELATIONSHIPS")
                for child, cfrom, parent, cto in rels:
                    lines.append(f"  {child}.{cfrom} → {parent}.{cto}")
            return "\n".join(lines)
        finally:
            conn.close()

    # cho phép gọi tool theo kiểu thống nhất run(...)
    def run(self) -> str:
        return self.describe()
