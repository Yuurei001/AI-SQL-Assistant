"""
memory_tool.py — Memory Tool (bộ nhớ hội thoại).

Lưu lại lịch sử các lượt hỏi - đáp trong một phiên làm việc để các
agent (đặc biệt là SQL Generator) có thể tham chiếu ngữ cảnh trước đó,
ví dụ câu hỏi nối tiếp kiểu "còn theo thành phố thì sao?".

Đây là bộ nhớ ngắn hạn (short-term / working memory) ở mức tiến trình.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


@dataclass
class Turn:
    question: str
    sql: str = ""
    summary: str = ""


class MemoryTool:
    name = "memory"
    description = "Lưu và truy xuất lịch sử hội thoại trong phiên."

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._turns: list[Turn] = []
        self._lock = RLock()

    def remember(self, question: str, sql: str = "", summary: str = "") -> None:
        with self._lock:
            self._turns.append(Turn(question=question, sql=sql, summary=summary))
            if len(self._turns) > self.max_turns:
                self._turns = self._turns[-self.max_turns :]

    def recent(self, n: int = 3) -> list[Turn]:
        with self._lock:
            return list(self._turns[-n:])

    def as_context(self, n: int = 3) -> str:
        """Sinh đoạn ngữ cảnh để chèn vào prompt LLM."""
        turns = self.recent(n)
        if not turns:
            return ""
        lines = ["LỊCH SỬ HỘI THOẠI GẦN ĐÂY:"]
        for i, t in enumerate(turns, 1):
            lines.append(f"{i}. Hỏi: {t.question}")
            if t.sql:
                lines.append(f"   SQL: {t.sql}")
        return "\n".join(lines)

    def run(self, n: int = 3) -> str:
        return self.as_context(n)


class MemoryManager:
    """Cấp bộ nhớ độc lập cho từng cuộc hội thoại."""

    def __init__(self, max_turns: int = 10, max_conversations: int = 100):
        self.max_turns = max_turns
        self.max_conversations = max_conversations
        self._memories: dict[str, MemoryTool] = {}
        self._lock = RLock()

    def for_conversation(self, conversation_id: str) -> MemoryTool:
        key = (conversation_id or "default").strip()[:128]
        with self._lock:
            if key not in self._memories:
                if len(self._memories) >= self.max_conversations:
                    oldest = next(iter(self._memories))
                    self._memories.pop(oldest, None)
                self._memories[key] = MemoryTool(max_turns=self.max_turns)
            return self._memories[key]

    def history(self, conversation_id: str, limit: int = 20) -> list[Turn]:
        return self.for_conversation(conversation_id).recent(limit)

    def clear(self, conversation_id: str) -> None:
        key = (conversation_id or "default").strip()[:128]
        with self._lock:
            self._memories.pop(key, None)
