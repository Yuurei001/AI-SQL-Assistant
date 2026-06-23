"""
Kiểm thử TÍCH HỢP — chạy trên CSDL SQLite thật (tạo trong conftest.py).

Khác với unit test (kiểm thử từng hàm cô lập), bộ này kiểm thử sự phối
hợp của các *Tool* trong kiến trúc agentic với cơ sở dữ liệu thực:
  - SchemaTool   (đọc cấu trúc)
  - ValidatorTool (an toàn + hợp lệ)
  - ExecutorTool  (thực thi có timeout)
và đường đi HTTP qua Flask (app.py) tới orchestrator.

Toàn bộ chạy ngoại tuyến (LLM được mock) nên không phụ thuộc mạng.
"""

import sys, os

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core import llm
from agent_core.tools import SchemaTool, ValidatorTool, ExecutorTool


# ════════════════════════════════════════════════════════════════
#  ExecutorTool — thực thi SQL trên DB thật
# ════════════════════════════════════════════════════════════════
class TestExecuteOnRealDb:

    def _run(self, db, sql):
        df, err = ExecutorTool(db).run(sql)
        assert err is None, err
        return df

    def test_select_all_pizzas(self, test_db_path):
        df = self._run(test_db_path, "SELECT * FROM pizzas")
        assert isinstance(df, pd.DataFrame) and len(df) == 30

    def test_select_returns_correct_columns(self, test_db_path):
        df = self._run(test_db_path, "SELECT pizza_id, name, price FROM pizzas")
        assert list(df.columns) == ["pizza_id", "name", "price"]

    def test_select_with_filter(self, test_db_path):
        df = self._run(test_db_path, "SELECT * FROM pizzas WHERE size = 'L'")
        assert all(df["size"] == "L")

    def test_select_count(self, test_db_path):
        df = self._run(test_db_path, "SELECT COUNT(*) AS n FROM orders")
        assert df.loc[0, "n"] == 500

    def test_select_aggregation(self, test_db_path):
        df = self._run(
            test_db_path,
            "SELECT payment_method, SUM(total_price) AS rev FROM orders GROUP BY payment_method",
        )
        assert {"payment_method", "rev"} <= set(df.columns) and len(df) <= 4

    def test_select_join(self, test_db_path):
        df = self._run(test_db_path, """
            SELECT o.order_id, p.name FROM orders o
            JOIN pizzas p ON o.pizza_id = p.pizza_id LIMIT 10
        """)
        assert {"order_id", "name"} <= set(df.columns) and len(df) == 10

    def test_select_empty_result(self, test_db_path):
        df = self._run(test_db_path, "SELECT * FROM orders WHERE rating = 99")
        assert isinstance(df, pd.DataFrame) and len(df) == 0

    def test_invalid_sql_returns_error(self, test_db_path):
        df, err = ExecutorTool(test_db_path).run("SELECT * FROM nonexistent_table")
        assert df is None and err

    def test_limit_respected(self, test_db_path):
        df = self._run(test_db_path, "SELECT * FROM orders LIMIT 7")
        assert len(df) == 7

    def test_order_by_descending(self, test_db_path):
        df = self._run(test_db_path,
                       "SELECT total_price FROM orders ORDER BY total_price DESC LIMIT 5")
        prices = df["total_price"].tolist()
        assert prices == sorted(prices, reverse=True)

    def test_subquery(self, test_db_path):
        df = self._run(test_db_path, """
            SELECT name, price FROM pizzas
            WHERE price > (SELECT AVG(price) FROM pizzas) ORDER BY price DESC
        """)
        avg = self._run(test_db_path, "SELECT AVG(price) AS a FROM pizzas").loc[0, "a"]
        assert all(df["price"] > avg)


# ════════════════════════════════════════════════════════════════
#  SchemaTool — đọc schema từ DB thật
# ════════════════════════════════════════════════════════════════
class TestSchemaOnRealDb:

    def test_describe_contains_all_tables(self, test_db_path):
        desc = SchemaTool(test_db_path).describe()
        for tbl in ("pizzas", "customers", "stores", "orders"):
            assert tbl in desc

    def test_describe_contains_pk_marker(self, test_db_path):
        assert "[PK]" in SchemaTool(test_db_path).describe()

    def test_schema_map_columns(self, test_db_path):
        m = SchemaTool(test_db_path).schema_map()
        assert {"pizza_id", "customer_id", "order_id", "store_id"} <= {
            c for cols in m.values() for c in cols
        }

    def test_relationships_detected(self, test_db_path):
        rels = SchemaTool(test_db_path).relationships()
        assert any(parent == "pizzas" for _, _, parent, _ in rels)


# ════════════════════════════════════════════════════════════════
#  ValidatorTool — kiểm tra hợp lệ trên DB thật
# ════════════════════════════════════════════════════════════════
class TestValidatorOnRealDb:

    def _v(self, db):
        return ValidatorTool(db, schema_map=SchemaTool(db).schema_map())

    def test_valid_query_passes(self, test_db_path):
        ok, _ = self._v(test_db_path).run("SELECT name FROM pizzas")
        assert ok

    def test_unknown_table_rejected(self, test_db_path):
        ok, _ = self._v(test_db_path).run("SELECT * FROM khong_co")
        assert not ok

    def test_dangerous_rejected(self, test_db_path):
        ok, _ = self._v(test_db_path).run("DROP TABLE orders")
        assert not ok


# ════════════════════════════════════════════════════════════════
#  Tích hợp HTTP — Flask app.py + orchestrator (LLM mock)
# ════════════════════════════════════════════════════════════════
class TestFlaskIntegration:

    @pytest.fixture()
    def client(self, test_db_path, monkeypatch):
        monkeypatch.setenv("SQL_ASSISTANT_DB", test_db_path)
        # Ép app dùng DB test
        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.DEFAULT_DB_PATH = test_db_path
        app_module.orchestrator = app_module.AgenticOrchestrator()
        return app_module.app.test_client()

    def test_health(self, client):
        data = client.get("/api/health").get_json()
        assert data["status"] == "ok"

    def test_schema_endpoint(self, client):
        data = client.get("/api/schema").get_json()
        assert "pizzas" in data["schema"]

    def test_query_endpoint_success(self, client, monkeypatch):
        monkeypatch.setattr(
            llm, "complete",
            lambda p: '{"summary":"ok","labels":{},"columns":{}}' if "data analyst" in p
            else "SELECT name, price FROM pizzas ORDER BY price DESC",
        )
        r = client.post("/api/query", json={"question": "pizza đắt nhất"}).get_json()
        assert r["success"] and r["total_rows"] > 0 and len(r["steps"]) >= 6

    def test_query_empty_question(self, client):
        r = client.post("/api/query", json={"question": "  "})
        assert r.status_code == 400
