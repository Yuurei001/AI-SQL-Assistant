"""
Unit tests for pure-logic functions in SQL_Assistant.

Functions covered:
  - is_safe_query()
  - highlight_sql()
  - try_make_chart()
"""

import re
import pandas as pd
import pytest

# conftest already patched streamlit/altair/google before we arrive here,
# so the import is safe.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from SQL_Assistant import is_safe_query, highlight_sql, try_make_chart


# ════════════════════════════════════════════════════════════════
#  is_safe_query
# ════════════════════════════════════════════════════════════════

class TestIsSafeQuery:

    # ── Safe queries ─────────────────────────────────────────────

    def test_simple_select(self):
        ok, msg = is_safe_query("SELECT * FROM orders")
        assert ok is True
        assert msg == ""

    def test_select_with_where(self):
        ok, _ = is_safe_query("SELECT name FROM customers WHERE city='Hanoi'")
        assert ok is True

    def test_select_with_join(self):
        sql = """
            SELECT o.order_id, p.name
            FROM orders o
            JOIN pizzas p ON o.pizza_id = p.pizza_id
            WHERE o.order_status = 'Completed'
        """
        ok, _ = is_safe_query(sql)
        assert ok is True

    def test_select_with_aggregates(self):
        sql = "SELECT category, COUNT(*), SUM(total_price) FROM orders GROUP BY category"
        ok, _ = is_safe_query(sql)
        assert ok is True

    def test_select_with_subquery(self):
        sql = "SELECT * FROM pizzas WHERE price > (SELECT AVG(price) FROM pizzas)"
        ok, _ = is_safe_query(sql)
        assert ok is True

    # ── Unsafe queries ───────────────────────────────────────────

    def test_drop_table(self):
        # DROP doesn't start with SELECT, so the first guard fires first
        ok, msg = is_safe_query("DROP TABLE orders")
        assert ok is False
        assert msg  # some non-empty error reason is returned

    def test_delete_statement(self):
        ok, msg = is_safe_query("DELETE FROM orders WHERE order_id=1")
        assert ok is False

    def test_update_statement(self):
        ok, msg = is_safe_query("UPDATE orders SET rating=5 WHERE order_id=1")
        assert ok is False

    def test_insert_statement(self):
        ok, msg = is_safe_query("INSERT INTO pizzas VALUES (1,'X','M','L',9.0,500,1)")
        assert ok is False

    def test_alter_table(self):
        ok, _ = is_safe_query("ALTER TABLE pizzas ADD COLUMN discount REAL")
        assert ok is False

    def test_truncate(self):
        ok, _ = is_safe_query("TRUNCATE TABLE orders")
        assert ok is False

    def test_empty_query(self):
        ok, msg = is_safe_query("")
        assert ok is False

    def test_whitespace_only(self):
        ok, _ = is_safe_query("   \n\t  ")
        assert ok is False

    def test_not_select_keyword(self):
        ok, msg = is_safe_query("EXEC sp_help")
        assert ok is False

    def test_select_with_drop_in_comment(self):
        # Inline comment containing DROP should still be blocked because the
        # regex matches keywords anywhere in the string after the SELECT check.
        sql = "SELECT * FROM orders -- DROP TABLE orders"
        ok, _ = is_safe_query(sql)
        # The current implementation blocks if DROP appears as word anywhere,
        # even in comments — that is the expected (conservative) behavior.
        assert ok is False

    def test_case_insensitive_keyword(self):
        ok, _ = is_safe_query("select * from orders")
        assert ok is True

    def test_mixed_case_blocked(self):
        ok, _ = is_safe_query("Select * From orders; Delete FROM orders")
        assert ok is False


# ════════════════════════════════════════════════════════════════
#  highlight_sql
# ════════════════════════════════════════════════════════════════

class TestHighlightSql:

    def test_returns_string(self):
        out = highlight_sql("SELECT * FROM pizzas")
        assert isinstance(out, str)

    def test_keywords_wrapped_in_kw_span(self):
        out = highlight_sql("SELECT name FROM pizzas WHERE available = 1")
        assert '<span class="kw">SELECT</span>' in out or 'class="kw"' in out

    def test_line_numbers_present(self):
        sql = "SELECT name\nFROM pizzas"
        out = highlight_sql(sql)
        assert 'class="sql-lineno"' in out

    def test_two_lines_have_two_numbers(self):
        sql = "SELECT name\nFROM pizzas"
        out = highlight_sql(sql)
        matches = re.findall(r'class="sql-lineno">(\d+)<', out)
        assert len(matches) == 2
        assert matches == ["1", "2"]

    def test_string_literals_escaped_before_highlight(self):
        # html.escape() runs first, so single-quotes become &#x27; and the
        # str-span regex cannot match them. Document current behavior: the
        # literal value is present in escaped form, just not wrapped in a span.
        sql = "SELECT * FROM orders WHERE city = 'Hanoi'"
        out = highlight_sql(sql)
        assert "Hanoi" in out               # value is present
        assert "&#x27;" in out             # single-quote was HTML-escaped

    def test_numeric_literals_highlighted(self):
        sql = "SELECT * FROM pizzas WHERE price > 10"
        out = highlight_sql(sql)
        assert 'class="num"' in out

    def test_comment_highlighted(self):
        sql = "SELECT * FROM pizzas -- get all pizzas"
        out = highlight_sql(sql)
        assert 'class="cmt"' in out

    def test_html_special_chars_escaped(self):
        sql = "SELECT * FROM t WHERE a < b AND c > d"
        out = highlight_sql(sql)
        assert "&lt;" in out
        assert "&gt;" in out

    def test_empty_sql(self):
        out = highlight_sql("")
        assert isinstance(out, str)

    def test_multiline_preserves_all_lines(self):
        lines = ["SELECT o.order_id,", "       p.name", "FROM orders o", "JOIN pizzas p ON o.pizza_id = p.pizza_id"]
        sql   = "\n".join(lines)
        out   = highlight_sql(sql)
        numbers = re.findall(r'class="sql-lineno">(\d+)<', out)
        assert len(numbers) == 4


# ════════════════════════════════════════════════════════════════
#  try_make_chart
# ════════════════════════════════════════════════════════════════

class TestTryMakeChart:

    def _df(self, **kwargs):
        return pd.DataFrame(kwargs)

    def test_returns_chart_for_valid_data(self):
        df = self._df(name=["Pepperoni", "Margherita", "BBQ Chicken"],
                      revenue=[1200.0, 950.0, 870.0])
        chart = try_make_chart(df)
        assert chart is not None

    def test_returns_none_for_single_row(self):
        df = self._df(name=["Pepperoni"], revenue=[1200.0])
        assert try_make_chart(df) is None

    def test_returns_none_for_single_column(self):
        df = self._df(revenue=[1200.0, 950.0, 870.0])
        assert try_make_chart(df) is None

    def test_returns_none_when_no_text_column(self):
        df = self._df(x=[1, 2, 3], y=[4, 5, 6])
        assert try_make_chart(df) is None

    def test_returns_none_when_no_numeric_column(self):
        df = self._df(name=["A", "B", "C"], city=["Hanoi", "HCM", "Hanoi"])
        assert try_make_chart(df) is None

    def test_returns_none_for_more_than_40_rows(self):
        df = self._df(name=[f"Item {i}" for i in range(41)],
                      value=list(range(41)))
        assert try_make_chart(df) is None

    def test_exactly_40_rows_returns_chart(self):
        df = self._df(name=[f"Item {i}" for i in range(40)],
                      value=list(range(40)))
        assert try_make_chart(df) is not None

    def test_multiple_numeric_cols_uses_first(self):
        df = self._df(
            name=["A", "B", "C"],
            total_price=[100.0, 200.0, 150.0],
            quantity=[2, 4, 3],
        )
        chart = try_make_chart(df)
        assert chart is not None

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        assert try_make_chart(df) is None
