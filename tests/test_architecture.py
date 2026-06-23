"""Kiểm thử các hợp đồng kiến trúc Agentic AI và API bàn giao."""

from pathlib import Path

from agent_core import llm
from agent_core.orchestrator import AgenticOrchestrator
from agent_core.tool_manager import ToolManager
from agent_core.tools import MemoryManager
from app import create_app


def test_source_does_not_embed_gemini_key():
    source = Path(llm.__file__).read_text(encoding="utf-8")
    assert "AQ." not in source
    assert 'os.environ.get("GEMINI_API_KEY", "")' in source


def test_tool_manager_exposes_required_tools():
    names = {tool["name"] for tool in ToolManager().catalog()}
    assert {
        "database_schema",
        "sql_validator",
        "sql_executor",
        "query_optimizer",
        "memory",
    } <= names


def test_memory_isolated_by_conversation():
    manager = MemoryManager()
    manager.for_conversation("a").remember("Q-a", "SELECT 1")
    manager.for_conversation("b").remember("Q-b", "SELECT 2")
    assert manager.history("a")[0].question == "Q-a"
    assert manager.history("b")[0].question == "Q-b"


def test_memory_clear_only_target_conversation():
    manager = MemoryManager()
    manager.for_conversation("a").remember("Q-a")
    manager.for_conversation("b").remember("Q-b")
    manager.clear("a")
    assert manager.history("a") == []
    assert len(manager.history("b")) == 1


def test_orchestrator_payload_has_agentic_telemetry(
    test_db_path,
    monkeypatch,
):
    monkeypatch.setattr(
        llm,
        "complete",
        lambda prompt: (
            '{"summary":"ok","labels":{},"columns":{}}'
            if "data analyst" in prompt
            else "SELECT name FROM pizzas"
        ),
    )
    result = AgenticOrchestrator().handle(
        "Danh sách pizza",
        test_db_path,
        conversation_id="telemetry",
    )
    assert result["success"]
    assert result["conversation_id"] == "telemetry"
    assert result["task_status"]
    assert result["execution_ms"] >= 0


def test_api_health_reports_architecture(test_db_path):
    client = create_app(db_path=test_db_path).test_client()
    payload = client.get("/api/health").get_json()
    assert payload["database_found"] is True
    assert "Agentic AI" in payload["architecture"]


def test_api_tools_returns_catalog(test_db_path):
    client = create_app(db_path=test_db_path).test_client()
    payload = client.get("/api/tools").get_json()
    assert len(payload["tools"]) >= 5


def test_api_rejects_invalid_question(test_db_path):
    client = create_app(db_path=test_db_path).test_client()
    response = client.post("/api/query", json={"question": "  "})
    assert response.status_code == 400


def test_api_history_round_trip(test_db_path, monkeypatch):
    monkeypatch.setattr(
        llm,
        "complete",
        lambda prompt: (
            '{"summary":"ok","labels":{},"columns":{}}'
            if "data analyst" in prompt
            else "SELECT name FROM pizzas"
        ),
    )
    client = create_app(db_path=test_db_path).test_client()
    response = client.post(
        "/api/query",
        json={"question": "Pizza", "conversation_id": "history-test"},
    )
    assert response.status_code == 200
    history = client.get(
        "/api/history?conversation_id=history-test",
    ).get_json()
    assert history["turns"][0]["question"] == "Pizza"


def test_api_stats_updates_after_query(test_db_path, monkeypatch):
    monkeypatch.setattr(
        llm,
        "complete",
        lambda prompt: (
            '{"summary":"ok","labels":{},"columns":{}}'
            if "data analyst" in prompt
            else "SELECT COUNT(*) AS total FROM pizzas"
        ),
    )
    client = create_app(db_path=test_db_path).test_client()
    client.post("/api/query", json={"question": "Đếm pizza"})
    stats = client.get("/api/stats").get_json()
    assert stats["total_queries"] == 1
    assert stats["successful_queries"] == 1
