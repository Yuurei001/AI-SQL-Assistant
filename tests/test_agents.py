"""
test_agents.py — Kiểm thử kiến trúc đa tác tử (agent_core).

Toàn bộ lời gọi LLM được mock qua ``agent_core.llm.complete`` nên bộ
test chạy hoàn toàn ngoại tuyến (không cần mạng) — đây là lý do test
đạt 100% pass kể cả trong môi trường CI không có Internet.

Dùng fixture ``test_db_path`` (CSDL pizza tạm) từ conftest.py.
"""

import time
import sys, os

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core import llm
from agent_core.state import AgentState
from agent_core.tools import (
    SchemaTool, ExecutorTool, ValidatorTool, OptimizerTool, MemoryTool,
)
from agent_core.agents.planner import PlannerAgent
from agent_core.agents.schema_analyzer import SchemaAnalyzerAgent
from agent_core.agents.sql_generator import SQLGeneratorAgent, clean_sql, build_prompt
from agent_core.agents.sql_validator import SQLValidatorAgent
from agent_core.agents.sql_executor import SQLExecutorAgent
from agent_core.agents.self_correction import SelfCorrectionAgent, classify_error
from agent_core.agents.result_interpreter import ResultInterpreterAgent, make_chart_spec
from agent_core.agents.response_generator import ResponseGeneratorAgent
from agent_core.orchestrator import AgenticOrchestrator, run_agentic


# ─────────────────────────────────────────────────────────────
#  Tiện ích: mock LLM
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def patch_llm(monkeypatch):
    """Trả về hàm cài đặt phản hồi LLM theo kịch bản."""
    def setter(sql_responses, summary='{"summary":"ok","labels":{},"columns":{}}'):
        seq = list(sql_responses)
        state = {"i": 0}

        def fake(prompt):
            if "data analyst" in prompt:
                return summary
            if "phân loại ý định" in prompt or "intent classifier" in prompt or "phân loại" in prompt:
                return '{"intent": "database_query", "should_query_database": true, "direct_response": null}'
            r = seq[min(state["i"], len(seq) - 1)]
            state["i"] += 1
            return r

        monkeypatch.setattr(llm, "complete", fake)
    return setter


def make_state(db, question="câu hỏi"):
    return AgentState(question=question, db_path=db)


# ═════════════════════════════════════════════════════════════
#  NHÓM 1 — TOOLS
# ═════════════════════════════════════════════════════════════
class TestSchemaTool:
    def test_user_tables(self, test_db_path):
        tables = SchemaTool(test_db_path).user_tables()
        assert {"pizzas", "customers", "stores", "orders"} <= set(tables)

    def test_columns_of(self, test_db_path):
        cols = SchemaTool(test_db_path).columns_of("pizzas")
        assert "price" in cols and "name" in cols

    def test_schema_map(self, test_db_path):
        m = SchemaTool(test_db_path).schema_map()
        assert "orders" in m and "total_price" in m["orders"]

    def test_relationships(self, test_db_path):
        rels = SchemaTool(test_db_path).relationships()
        parents = {parent for _, _, parent, _ in rels}
        assert {"customers", "pizzas", "stores"} <= parents

    def test_describe_contains_tables(self, test_db_path):
        desc = SchemaTool(test_db_path).describe()
        assert "TABLE pizzas" in desc and "RELATIONSHIPS" in desc


class TestValidatorTool:
    def test_safe_select(self, test_db_path):
        ok, _ = ValidatorTool(test_db_path).is_safe("SELECT * FROM orders")
        assert ok

    def test_block_drop(self, test_db_path):
        ok, msg = ValidatorTool(test_db_path).is_safe("DROP TABLE orders")
        assert not ok and msg

    def test_block_delete(self, test_db_path):
        ok, _ = ValidatorTool(test_db_path).is_safe("DELETE FROM orders")
        assert not ok

    def test_unknown_table(self, test_db_path):
        v = ValidatorTool(test_db_path, schema_map=SchemaTool(test_db_path).schema_map())
        ok, msg = v.check_tables("SELECT * FROM khong_co_bang")
        assert not ok and "khong_co_bang" in msg

    def test_known_table_ok(self, test_db_path):
        v = ValidatorTool(test_db_path, schema_map=SchemaTool(test_db_path).schema_map())
        ok, _ = v.check_tables("SELECT * FROM pizzas")
        assert ok

    def test_syntax_error_detected(self, test_db_path):
        ok, _ = ValidatorTool(test_db_path).check_syntax("SELECT FROM WHERE")
        assert not ok

    def test_full_run_valid(self, test_db_path):
        v = ValidatorTool(test_db_path, schema_map=SchemaTool(test_db_path).schema_map())
        ok, msg = v.run("SELECT name FROM pizzas")
        assert ok and msg == ""


class TestExecutorTool:
    def test_run_success(self, test_db_path):
        df, err = ExecutorTool(test_db_path).run("SELECT * FROM pizzas LIMIT 3")
        assert err is None and isinstance(df, pd.DataFrame) and len(df) == 3

    def test_run_error(self, test_db_path):
        df, err = ExecutorTool(test_db_path).run("SELECT * FROM nope")
        assert df is None and err

    def test_timeout(self, test_db_path):
        tool = ExecutorTool(test_db_path, timeout_seconds=1)
        tool._run_query = lambda q: time.sleep(3)          # giả lập truy vấn chậm
        df, err = tool.run("SELECT 1")
        assert df is None and "timeout" in err.lower()


class TestOptimizerTool:
    def test_add_limit(self):
        sql, added = OptimizerTool(default_limit=500).add_limit("SELECT * FROM pizzas")
        assert added and "LIMIT 500" in sql

    def test_keep_existing_limit(self):
        sql, added = OptimizerTool().add_limit("SELECT * FROM pizzas LIMIT 5")
        assert not added

    def test_skip_scalar_aggregate(self):
        sql, added = OptimizerTool().add_limit("SELECT COUNT(*) FROM orders")
        assert not added

    def test_warning_select_star(self):
        warns = OptimizerTool().warnings("SELECT * FROM pizzas")
        assert any("SELECT *" in w for w in warns)


class TestMemoryTool:
    def test_remember_and_recent(self):
        m = MemoryTool()
        m.remember("Q1", "SELECT 1")
        m.remember("Q2", "SELECT 2")
        assert [t.question for t in m.recent(2)] == ["Q1", "Q2"]

    def test_as_context(self):
        m = MemoryTool()
        m.remember("Top pizza", "SELECT name FROM pizzas")
        assert "Top pizza" in m.as_context()

    def test_max_turns(self):
        m = MemoryTool(max_turns=2)
        for i in range(5):
            m.remember(f"Q{i}")
        assert len(m.recent(10)) == 2


# ═════════════════════════════════════════════════════════════
#  NHÓM 2 — AGENTS
# ═════════════════════════════════════════════════════════════
class TestPlannerAgent:
    def test_returns_plan(self, test_db_path):
        st = make_state(test_db_path)
        PlannerAgent().run(st)
        assert len(st.plan) >= 5

    def test_group_step_for_per_question(self, test_db_path):
        st = make_state(test_db_path, "doanh thu theo thành phố")
        PlannerAgent().run(st)
        assert any("GROUP BY" in p for p in st.plan)

    def test_rank_step_for_top(self, test_db_path):
        st = make_state(test_db_path, "top 5 pizza")
        PlannerAgent().run(st)
        assert any("ORDER BY" in p for p in st.plan)


class TestSchemaAnalyzer:
    def test_loads_schema(self, test_db_path):
        st = make_state(test_db_path, "danh sách pizza")
        SchemaAnalyzerAgent().run(st)
        assert "TABLE pizzas" in st.raw_schema
        assert st.relevant_tables


class TestSQLGenerator:
    def test_generates_and_cleans(self, test_db_path, patch_llm):
        patch_llm(["```sql\nSELECT name FROM pizzas\n```"])
        st = make_state(test_db_path)
        st.raw_schema = "TABLE pizzas"
        SQLGeneratorAgent().run(st)
        assert st.sql == "SELECT name FROM pizzas"


class TestSQLValidatorAgent:
    def test_valid(self, test_db_path):
        st = make_state(test_db_path)
        st.sql = "SELECT name FROM pizzas"
        a = SQLValidatorAgent(); a.run(st)
        assert a.last_ok

    def test_invalid_unknown_table(self, test_db_path):
        st = make_state(test_db_path)
        st.sql = "SELECT * FROM khong_ton_tai"
        a = SQLValidatorAgent(); a.run(st)
        assert not a.last_ok


class TestSQLExecutorAgent:
    def test_executes_and_limits(self, test_db_path):
        st = make_state(test_db_path)
        st.sql = "SELECT * FROM pizzas"
        a = SQLExecutorAgent(); a.run(st)
        assert a.last_error is None and st.df is not None
        assert "LIMIT" in st.sql.upper()

    def test_error_sets_df_none(self, test_db_path):
        st = make_state(test_db_path)
        st.sql = "SELECT * FROM nope"
        a = SQLExecutorAgent(); a.run(st)
        assert a.last_error and st.df is None


class TestSelfCorrection:
    def test_classify_timeout(self):
        assert "chậm" in classify_error("Query timeout exceeded")

    def test_classify_no_table(self):
        assert classify_error("no such table: x")

    def test_classify_no_column(self):
        assert "cột" in classify_error("no such column: y")

    def test_regenerates_and_counts(self, test_db_path, patch_llm):
        patch_llm(["SELECT name FROM pizzas"])
        st = make_state(test_db_path)
        st.sql = "SELECT * FROM bad"
        st.errors.append("no such table: bad")
        SelfCorrectionAgent().run(st)
        assert st.retries == 1 and st.sql == "SELECT name FROM pizzas"


class TestResultInterpreter:
    def test_chart_spec(self):
        df = pd.DataFrame({"name": ["A", "B", "C"], "rev": [10, 20, 30]})
        assert make_chart_spec(df) is not None

    def test_no_chart_single_col(self):
        assert make_chart_spec(pd.DataFrame({"rev": [1, 2, 3]})) is None

    def test_summary_from_llm(self, test_db_path, patch_llm):
        patch_llm([], summary='{"summary":"Đây là tóm tắt","labels":{},"columns":{}}')
        st = make_state(test_db_path)
        st.df = pd.DataFrame({"name": ["A"], "rev": [10]})
        st.sql = "SELECT name, rev FROM t"
        ResultInterpreterAgent().run(st)
        assert "tóm tắt" in st.summary


class TestResponseGenerator:
    def test_payload_shape(self, test_db_path):
        st = make_state(test_db_path)
        st.df = pd.DataFrame({"name": ["A"], "price": [9.5]})
        st.success = True
        st.sql = "SELECT name, price FROM pizzas"
        a = ResponseGeneratorAgent(); a.run(st)
        p = a.build_payload(st)
        for key in ("success", "sql", "data", "steps", "plan", "total_rows"):
            assert key in p
        assert p["total_rows"] == 1


# ═════════════════════════════════════════════════════════════
#  NHÓM 3 — SINH SQL (qua validator)
# ═════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sql", [
    "SELECT name FROM pizzas",
    "SELECT category, COUNT(*) FROM pizzas GROUP BY category",
    "SELECT category, COUNT(*) c FROM pizzas GROUP BY category HAVING c > 1",
    "SELECT o.order_id, p.name FROM orders o JOIN pizzas p ON o.pizza_id = p.pizza_id",
    "SELECT name, price FROM pizzas ORDER BY price DESC",
])
def test_generated_sql_passes_pipeline(test_db_path, patch_llm, sql):
    """SELECT / GROUP BY / HAVING / JOIN / ORDER BY đều qua được validate+execute."""
    patch_llm([sql])
    st = make_state(test_db_path)
    SchemaAnalyzerAgent().run(st)
    SQLGeneratorAgent().run(st)
    v = SQLValidatorAgent(); v.run(st)
    assert v.last_ok, st.errors
    e = SQLExecutorAgent(); e.run(st)
    assert e.last_error is None and st.df is not None


# ═════════════════════════════════════════════════════════════
#  NHÓM 4 — XỬ LÝ LỖI
# ═════════════════════════════════════════════════════════════
class TestErrorHandling:
    def test_wrong_table_fails_validation(self, test_db_path, patch_llm):
        patch_llm(["SELECT * FROM khong_co"])
        st = make_state(test_db_path)
        SchemaAnalyzerAgent().run(st)
        SQLGeneratorAgent().run(st)
        v = SQLValidatorAgent(); v.run(st)
        assert not v.last_ok

    def test_wrong_column_fails_execution(self, test_db_path):
        st = make_state(test_db_path)
        st.sql = "SELECT khong_co_cot FROM pizzas"
        e = SQLExecutorAgent(); e.run(st)
        assert e.last_error and "column" in e.last_error.lower()

    def test_syntax_error(self, test_db_path):
        st = make_state(test_db_path)
        st.sql = "SELECT FROM WHERE"
        v = SQLValidatorAgent(); v.run(st)
        assert not v.last_ok

    def test_timeout_then_fallback(self, test_db_path, patch_llm, monkeypatch):
        patch_llm(["SELECT 1", "SELECT 1", "SELECT 1"])
        # Ép mọi lần thực thi đều timeout
        monkeypatch.setattr(
            "agent_core.tools.executor_tool.ExecutorTool.run",
            lambda self, q: (None, "Query timeout (timeout)"),
        )
        out = run_agentic("câu hỏi chậm", test_db_path, max_retries=1, timeout_seconds=1)
        assert out["success"] is False
        assert out["error"]                       # graceful fallback, không crash

    def test_retry_counted(self, test_db_path, patch_llm):
        patch_llm(["SELECT * FROM bad_table", "SELECT name FROM pizzas"])
        out = run_agentic("hỏi", test_db_path, max_retries=2)
        assert out["success"] is True and out["retries"] >= 1


# ═════════════════════════════════════════════════════════════
#  NHÓM 5 — TÍCH HỢP ORCHESTRATOR
# ═════════════════════════════════════════════════════════════
class TestOrchestrator:
    def test_end_to_end_success(self, test_db_path, patch_llm):
        patch_llm(["SELECT name, price FROM pizzas ORDER BY price DESC"])
        out = run_agentic("pizza đắt nhất", test_db_path)
        assert out["success"] and out["total_rows"] > 0
        assert len(out["steps"]) >= 6

    def test_self_correction_recovers(self, test_db_path, patch_llm):
        patch_llm(["SELECT * FROM sai_bang", "SELECT name FROM pizzas"])
        out = run_agentic("hỏi", test_db_path, max_retries=2)
        assert out["success"] and out["retries"] >= 1
        assert any(s["agent"] == "self_correction" for s in out["steps"])

    def test_total_failure_graceful(self, test_db_path, patch_llm):
        patch_llm(["SELECT * FROM sai1", "SELECT * FROM sai2", "SELECT * FROM sai3"])
        out = run_agentic("hỏi", test_db_path, max_retries=2)
        assert out["success"] is False and out["error"]

    def test_memory_persists_across_turns(self, test_db_path, patch_llm):
        patch_llm(["SELECT name FROM pizzas"])
        orch = AgenticOrchestrator()
        orch.handle("câu đầu", test_db_path)
        assert len(orch.memory.recent(5)) == 1
