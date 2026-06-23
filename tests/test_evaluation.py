"""
Bộ ĐÁNH GIÁ (evaluation) chất lượng sinh SQL của kiến trúc agentic.

Mỗi ca kiểm thử gồm:
  - Câu hỏi ngôn ngữ tự nhiên (mô phỏng người dùng thật)
  - SQL tham chiếu — được tiêm vào như phản hồi LLM (mock)
  - Quy tắc kiểm tra: cột mong đợi, số dòng tối thiểu, kiểm tra số, thứ tự sắp xếp

Đánh giá 4 khía cạnh:
  1. An toàn   — SQL qua được ValidatorTool (chỉ SELECT, không từ khoá nguy hiểm)
  2. Cú pháp   — SQL chạy được trên DB thật qua ExecutorTool
  3. Hình dạng — đúng cột, đủ số dòng
  4. Tính đúng — kiểm tra giá trị tổng hợp / thứ tự sắp xếp

Ngoài ra kiểm thử toàn bộ pipeline agentic end-to-end (run_agentic) với
LLM mock — đo tỉ lệ pass mà không phụ thuộc mạng.

Chạy: pytest tests/test_evaluation.py -v
"""

import sys, os

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core import llm
from agent_core.tools import SchemaTool, ValidatorTool, ExecutorTool
from agent_core.orchestrator import run_agentic
from agent_core.agents.sql_generator import clean_sql, build_prompt


# ════════════════════════════════════════════════════════════════
#  Định nghĩa bộ benchmark
# ════════════════════════════════════════════════════════════════
BENCHMARK_CASES = [
    {
        "id": "top10_revenue",
        "question": "Top 10 pizzas by total revenue",
        "reference_sql": """
            SELECT p.name, SUM(o.total_price) AS total_revenue
            FROM orders o JOIN pizzas p ON o.pizza_id = p.pizza_id
            GROUP BY p.name ORDER BY total_revenue DESC LIMIT 10
        """,
        "expected_columns": {"name", "total_revenue"},
        "min_rows": 1, "numeric_col": "total_revenue", "sorted_desc": True,
    },
    {
        "id": "revenue_per_city",
        "question": "Total orders and revenue per city",
        "reference_sql": """
            SELECT c.city, COUNT(o.order_id) AS total_orders, SUM(o.total_price) AS total_revenue
            FROM orders o JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.city ORDER BY total_revenue DESC
        """,
        "expected_columns": {"city", "total_orders", "total_revenue"},
        "min_rows": 1, "numeric_col": "total_revenue", "sorted_desc": True,
    },
    {
        "id": "avg_delivery_by_branch",
        "question": "Average delivery time by store branch",
        "reference_sql": """
            SELECT s.branch_name, ROUND(AVG(o.delivery_minutes), 1) AS avg_delivery_min
            FROM orders o JOIN stores s ON o.store_id = s.store_id
            WHERE o.delivery_minutes IS NOT NULL
            GROUP BY s.branch_name ORDER BY avg_delivery_min ASC
        """,
        "expected_columns": {"branch_name", "avg_delivery_min"},
        "min_rows": 1, "numeric_col": "avg_delivery_min", "sorted_desc": False,
    },
    {
        "id": "revenue_by_payment",
        "question": "Revenue breakdown by payment method",
        "reference_sql": """
            SELECT payment_method, COUNT(*) AS order_count, SUM(total_price) AS total_revenue
            FROM orders GROUP BY payment_method ORDER BY total_revenue DESC
        """,
        "expected_columns": {"payment_method", "total_revenue"},
        "min_rows": 1, "numeric_col": "total_revenue", "sorted_desc": True,
    },
    {
        "id": "top5_customers",
        "question": "Top 5 customers by total spending",
        "reference_sql": """
            SELECT c.full_name, SUM(o.total_price) AS total_spending
            FROM orders o JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.customer_id, c.full_name ORDER BY total_spending DESC LIMIT 5
        """,
        "expected_columns": {"full_name", "total_spending"},
        "min_rows": 1, "max_rows": 5, "numeric_col": "total_spending", "sorted_desc": True,
    },
    {
        "id": "orders_by_member_level",
        "question": "Orders count by customer member level",
        "reference_sql": """
            SELECT c.member_level, COUNT(o.order_id) AS order_count
            FROM orders o JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.member_level ORDER BY order_count DESC
        """,
        "expected_columns": {"member_level", "order_count"},
        "min_rows": 1, "numeric_col": "order_count", "sorted_desc": True,
    },
    {
        "id": "avg_rating_by_pizza",
        "question": "Average rating per pizza type",
        "reference_sql": """
            SELECT p.name, ROUND(AVG(o.rating), 2) AS avg_rating
            FROM orders o JOIN pizzas p ON o.pizza_id = p.pizza_id
            WHERE o.rating IS NOT NULL GROUP BY p.name ORDER BY avg_rating DESC
        """,
        "expected_columns": {"name", "avg_rating"},
        "min_rows": 1, "numeric_col": "avg_rating", "sorted_desc": True,
    },
    {
        "id": "best_selling_category",
        "question": "Best selling pizza category",
        "reference_sql": """
            SELECT p.category, SUM(o.quantity) AS total_quantity, SUM(o.total_price) AS total_revenue
            FROM orders o JOIN pizzas p ON o.pizza_id = p.pizza_id
            GROUP BY p.category ORDER BY total_quantity DESC
        """,
        "expected_columns": {"category", "total_quantity"},
        "min_rows": 1, "numeric_col": "total_quantity", "sorted_desc": True,
    },
    {
        "id": "cancelled_orders",
        "question": "Total number of cancelled orders",
        "reference_sql": """
            SELECT COUNT(*) AS cancelled_count FROM orders WHERE order_status = 'Cancelled'
        """,
        "expected_columns": {"cancelled_count"},
        "min_rows": 1, "numeric_col": "cancelled_count", "sorted_desc": False,
    },
    {
        "id": "available_pizzas",
        "question": "List all available pizzas with price",
        "reference_sql": """
            SELECT name, size, price FROM pizzas WHERE available = 1 ORDER BY price DESC
        """,
        "expected_columns": {"name", "size", "price"},
        "min_rows": 1, "numeric_col": "price", "sorted_desc": True,
    },
]


def _df(db, sql):
    df, err = ExecutorTool(db).run(sql)
    assert err is None, err
    return df


# ════════════════════════════════════════════════════════════════
#  Đánh giá theo từng khía cạnh (tham số hoá theo benchmark)
# ════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("case", BENCHMARK_CASES, ids=[c["id"] for c in BENCHMARK_CASES])
class TestEvaluation:

    def test_sql_is_safe(self, case, test_db_path):
        ok, reason = ValidatorTool(test_db_path).is_safe(case["reference_sql"].strip())
        assert ok, f"Safety failed: {reason}"

    def test_sql_executes(self, case, test_db_path):
        assert isinstance(_df(test_db_path, case["reference_sql"]), pd.DataFrame)

    def test_expected_columns_present(self, case, test_db_path):
        df = _df(test_db_path, case["reference_sql"])
        missing = case["expected_columns"] - set(df.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_min_rows(self, case, test_db_path):
        assert len(_df(test_db_path, case["reference_sql"])) >= case["min_rows"]

    def test_max_rows(self, case, test_db_path):
        max_rows = case.get("max_rows", 500)
        assert len(_df(test_db_path, case["reference_sql"])) <= max_rows

    def test_numeric_column_non_negative(self, case, test_db_path):
        df = _df(test_db_path, case["reference_sql"])
        col = case["numeric_col"]
        if col not in df.columns or df.empty:
            pytest.skip(f"{col} not present/empty")
        assert (df[col].dropna() >= 0).all()

    def test_sort_order(self, case, test_db_path):
        df = _df(test_db_path, case["reference_sql"])
        col = case["numeric_col"]
        assert col in df.columns
        if len(df) < 2:
            assert len(df) == 1
            return
        vals = df[col].dropna().tolist()
        assert vals == sorted(vals, reverse=case["sorted_desc"])


# ════════════════════════════════════════════════════════════════
#  Pipeline agentic end-to-end (LLM mock = SQL tham chiếu)
# ════════════════════════════════════════════════════════════════
class TestAgenticPipeline:

    def _mock(self, monkeypatch, sql):
        monkeypatch.setattr(
            llm, "complete",
            lambda p: '{"summary":"ok","labels":{},"columns":{}}' if "data analyst" in p else sql,
        )

    @pytest.mark.parametrize("case", BENCHMARK_CASES[:5], ids=[c["id"] for c in BENCHMARK_CASES[:5]])
    def test_pipeline_success(self, case, test_db_path, monkeypatch):
        self._mock(monkeypatch, case["reference_sql"].strip())
        out = run_agentic(case["question"], test_db_path)
        assert out["success"], out.get("error")
        assert out["total_rows"] >= case["min_rows"]
        assert len(out["steps"]) >= 6

    def test_pipeline_strips_markdown_fences(self, test_db_path, monkeypatch):
        self._mock(monkeypatch, "```sql\nSELECT COUNT(*) AS n FROM pizzas\n```")
        out = run_agentic("Count all pizzas", test_db_path)
        assert "```" not in out["sql"] and out["success"]

    def test_pipeline_blocks_unsafe_output(self, test_db_path, monkeypatch):
        self._mock(monkeypatch, "DROP TABLE orders")
        out = run_agentic("delete everything", test_db_path, max_retries=0)
        assert out["success"] is False     # validator chặn, graceful fallback

    def test_clean_sql_helper(self):
        assert clean_sql("```sql\nSELECT 1\n```") == "SELECT 1"

    def test_build_prompt_includes_schema(self, test_db_path):
        schema = SchemaTool(test_db_path).describe()
        prompt = build_prompt("hỏi", schema)
        assert "TABLE pizzas" in prompt and "QUESTION" in prompt


# ════════════════════════════════════════════════════════════════
#  Bảng điểm tổng hợp cuối phiên
# ════════════════════════════════════════════════════════════════
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    skipped = len(terminalreporter.stats.get("skipped", []))
    total = passed + failed + skipped
    terminalreporter.write_sep("=", "Evaluation Summary")
    terminalreporter.write_line(f"Total checks : {total}")
    terminalreporter.write_line(f"Passed       : {passed}")
    terminalreporter.write_line(f"Failed       : {failed}")
    terminalreporter.write_line(f"Skipped      : {skipped}")
    if passed + failed > 0:
        terminalreporter.write_line(f"Score        : {round(passed/(passed+failed)*100, 1)}%")
