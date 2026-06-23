"""
planner.py — Planner Agent.

Tác tử lập kế hoạch: nhận câu hỏi ngôn ngữ tự nhiên và phân rã thành
một **danh sách công việc (task list)** theo mô hình *Plan-and-Execute*.
Kế hoạch này định hướng cho các agent phía sau và được hiển thị cho
người dùng để giải thích "hệ thống định làm gì".

Planner hoạt động theo luật (rule-based) trên đặc trưng câu hỏi nên
không phụ thuộc LLM — đảm bảo ổn định và dễ kiểm thử.
"""

from __future__ import annotations

import re

from .base import BaseAgent
from ..state import AgentState


class PlannerAgent(BaseAgent):
    name = "planner"
    role = "Phân rã câu hỏi thành kế hoạch các bước thực thi"

    def act(self, state: AgentState) -> None:
        if getattr(state, "should_query_database", True):
            q = state.question.lower()
            plan: list[str] = [
                "Phân tích schema để xác định bảng/cột liên quan",
                "Sinh câu truy vấn SQL từ câu hỏi",
                "Kiểm tra an toàn và tính hợp lệ của SQL",
                "Thực thi SQL trên cơ sở dữ liệu (có timeout)",
            ]

            # Suy luận đặc trưng câu hỏi để bổ sung bước (reasoning).
            if re.search(r"\b(theo|by|mỗi|từng|per|group)\b", q):
                plan.insert(2, "Áp dụng nhóm/tổng hợp (GROUP BY) theo tiêu chí")
            if re.search(r"\b(top|nhiều nhất|cao nhất|lớn nhất|xếp hạng|rank)\b", q):
                plan.insert(2, "Sắp xếp và giới hạn kết quả (ORDER BY + LIMIT)")
            if re.search(r"\b(trung bình|average|avg|tổng|sum|đếm|count)\b", q):
                plan.insert(2, "Tính toán chỉ số tổng hợp (AVG/SUM/COUNT)")

            plan += [
                "Tự sửa lỗi và thử lại nếu truy vấn thất bại",
                "Diễn giải kết quả sang ngôn ngữ tự nhiên",
                "Tổng hợp phản hồi cuối cùng cho người dùng",
            ]
        else:
            plan = [
                "Đã phân loại ý định người dùng",
                "Hoàn tất phản hồi"
            ]

        state.plan = plan
        state.initialize_tasks()
        
        if getattr(state, "should_query_database", True):
            state.mark_task("Phân tích schema", "running")
        else:
            state.mark_task("Đã phân loại ý định", "done")
            
        state.add_step(
            self.name, "done",
            f"Lập kế hoạch {len(plan)} bước", 0,
        )
