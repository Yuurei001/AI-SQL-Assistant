"""
optimizer_tool.py — Query Optimizer Tool.

Thực hiện các tinh chỉnh nhẹ, an toàn trên câu SQL trước khi thực thi:
  * Thêm ``LIMIT`` mặc định nếu truy vấn không giới hạn số dòng
    (tránh kéo về hàng vạn bản ghi gây chậm / treo).
  * Sinh các *cảnh báo* (warnings) mang tính gợi ý: thiếu điều kiện
    JOIN (nguy cơ tích Descartes), dùng ``SELECT *`` trên bảng lớn...
Các cảnh báo này được dùng để giải thích "reasoning" của agent.
"""

from __future__ import annotations

import re


class OptimizerTool:
    name = "query_optimizer"
    description = "Thêm LIMIT an toàn và sinh cảnh báo tối ưu cho câu SQL."

    def __init__(self, default_limit: int = 500):
        self.default_limit = default_limit

    def add_limit(self, query: str) -> tuple[str, bool]:
        """Trả về ``(sql_mới, đã_thêm_limit?)``.

        Không thêm LIMIT cho truy vấn tổng hợp 1 dòng (chỉ có hàm gộp,
        không GROUP BY) vì kết quả vốn đã nhỏ.
        """
        q = query.rstrip().rstrip(";")
        if re.search(r"\bLIMIT\b", q, flags=re.IGNORECASE):
            return query, False
        upper = q.upper()
        is_aggregate_scalar = (
            re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", upper)
            and "GROUP BY" not in upper
        )
        if is_aggregate_scalar:
            return query, False
        return f"{q} LIMIT {self.default_limit}", True

    def warnings(self, query: str) -> list[str]:
        warns: list[str] = []
        upper = query.upper()
        if re.search(r"\bSELECT\s+\*", upper):
            warns.append("Dùng SELECT * — nên chọn cột cụ thể để giảm dữ liệu.")
        joins = len(re.findall(r"\bJOIN\b", upper))
        ons = len(re.findall(r"\bON\b", upper))
        if joins > ons:
            warns.append("Có JOIN nhưng thiếu điều kiện ON — nguy cơ tích Descartes.")
        return warns

    def run(self, query: str) -> tuple[str, list[str]]:
        optimized, added = self.add_limit(query)
        warns = self.warnings(query)
        if added:
            warns.append(f"Đã thêm LIMIT {self.default_limit} để giới hạn kết quả.")
        return optimized, warns
