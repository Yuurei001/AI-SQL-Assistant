import pytest
from agent_core import llm
from agent_core.orchestrator import run_agentic

def test_general_chat_routing(test_db_path, monkeypatch):
    # Mock LLM for routing
    monkeypatch.setattr(
        llm,
        "complete",
        lambda prompt: (
            '{"intent": "general_chat", "should_query_database": false, '
            '"reason": "Chào hỏi", "direct_response": "Xin chào! Mình là trợ lý SQL."}'
        )
    )
    
    out = run_agentic("hi", test_db_path)
    assert out["success"] is True
    assert out["summary"] == "Xin chào! Mình là trợ lý SQL."
    assert out["sql"] == ""
    assert out["data"] == []
    assert out["chart"] is None
    assert "Đã phân loại ý định người dùng" in out["plan"]
    assert "Hoàn tất phản hồi" in out["plan"]
    
    # Check steps
    steps = [s["agent"] for s in out["steps"]]
    assert "conversation_router" in steps
    assert "planner" in steps
    assert "response_generator" in steps
    # SQL agents must be skipped
    assert "sql_generator" not in steps
    assert "sql_executor" not in steps

def test_ambiguous_routing(test_db_path, monkeypatch):
    monkeypatch.setattr(
        llm,
        "complete",
        lambda prompt: (
            '{"intent": "ambiguous", "should_query_database": false, '
            '"reason": "Mập mờ", "direct_response": "Bạn muốn xem thông tin gì?"}'
        )
    )
    
    out = run_agentic("xem cái đó", test_db_path)
    assert out["success"] is True
    assert out["summary"] == "Bạn muốn xem thông tin gì?"
    assert out["sql"] == ""

def test_sql_generator_echo_prevention(test_db_path, monkeypatch):
    # If the router says database_query, but the generator tries to echo the greeting as SELECT 'hi'
    def fake_complete(prompt):
        if "phân loại" in prompt:
            return '{"intent": "database_query", "should_query_database": true, "direct_response": null}'
        if "data analyst" in prompt:
            return '{"summary":"ok","labels":{},"columns":{}}'
        return "SELECT 'hi';" # Trivial echo query
        
    monkeypatch.setattr(llm, "complete", fake_complete)
    
    out = run_agentic("hi", test_db_path)
    assert out["success"] is False
    assert "LLM sinh câu truy vấn SQL giả lập" in out["error"]
    assert out["sql"] == ""
