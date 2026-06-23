"""Registry tạo và cung cấp các tool cho hệ thống Agentic AI."""

from __future__ import annotations

from .tools import (
    ExecutorTool,
    MemoryManager,
    MemoryTool,
    OptimizerTool,
    SchemaTool,
    ValidatorTool,
)


class ToolManager:
    """Một điểm quản lý Tool Calling thay vì để agent tự khởi tạo tùy ý."""

    def __init__(self, memory_manager: MemoryManager | None = None):
        self.memory_manager = memory_manager or MemoryManager()

    def schema(self, db_path: str) -> SchemaTool:
        return SchemaTool(db_path)

    def validator(
        self,
        db_path: str,
        schema_map: dict[str, list[str]] | None = None,
    ) -> ValidatorTool:
        return ValidatorTool(db_path, schema_map=schema_map)

    def executor(self, db_path: str, timeout_seconds: int) -> ExecutorTool:
        return ExecutorTool(db_path, timeout_seconds=timeout_seconds)

    def optimizer(self, default_limit: int = 500) -> OptimizerTool:
        return OptimizerTool(default_limit=default_limit)

    def memory(self, conversation_id: str) -> MemoryTool:
        return self.memory_manager.for_conversation(conversation_id)

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"name": SchemaTool.name, "description": SchemaTool.description},
            {"name": ValidatorTool.name, "description": ValidatorTool.description},
            {"name": ExecutorTool.name, "description": ExecutorTool.description},
            {"name": OptimizerTool.name, "description": OptimizerTool.description},
            {
                "name": "memory",
                "description": "Lưu ngữ cảnh độc lập theo từng cuộc hội thoại.",
            },
        ]
