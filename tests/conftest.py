"""
Shared fixtures for all test modules.

Strategy:
  - Patch streamlit, altair, google.generativeai at the top of sys.modules
    BEFORE any import of SQL_Assistant so that @st.cache_resource and
    st.set_page_config() never actually run.
  - Provide a temp SQLite database that mirrors the real schema.
"""

import sys
import sqlite3
import os
import random
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

# ── Mock heavy / UI dependencies before SQL_Assistant is imported ──────────────

def _columns_side_effect(spec, **kw):
    """Return a list of MagicMocks matching the requested column count."""
    n = len(spec) if isinstance(spec, (list, tuple)) else (spec if isinstance(spec, int) else 2)
    return [MagicMock() for _ in range(n)]

def _tabs_side_effect(*labels):
    return [MagicMock() for _ in labels]

def _selectbox_side_effect(label, options=None, index=0, **kw):
    """Trả về một lựa chọn THỰC trong options (không phải MagicMock).

    Cần thiết vì SQL_Assistant.py dùng giá trị selectbox làm key của
    dict ``st.session_state.databases``; nếu trả về MagicMock sẽ gây
    KeyError khi import module để chạy unit test.
    """
    if options is None:
        return ""
    opts = list(options)
    if not opts:
        return ""
    try:
        return opts[index]
    except (TypeError, IndexError):
        return opts[0]

_st = MagicMock()
_st.cache_resource        = lambda **kw: (lambda f: f)
_st.stop                  = lambda: None
_st.columns.side_effect   = _columns_side_effect
_st.tabs.side_effect      = _tabs_side_effect
_st.selectbox.side_effect = _selectbox_side_effect
_st.form_submit_button.return_value = False   # don't execute the pipeline block
_st.text_input.return_value = ""
_st.button.return_value     = False
_st.file_uploader.return_value = None
# session_state: attribute-style access, "history" not present initially
_st.session_state           = MagicMock()
_st.session_state.__contains__ = lambda self, key: False
sys.modules.setdefault("streamlit", _st)
sys.modules.setdefault("altair",          MagicMock())
_genai = MagicMock()
sys.modules.setdefault("google",          MagicMock())
sys.modules.setdefault("google.generativeai", _genai)


# ── Fixture: temp database ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    """Create an isolated pizza database for the test session."""
    db_file = str(tmp_path_factory.mktemp("db") / "test_pizza.db")
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE pizzas (
            pizza_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT,
            category  TEXT,
            size      TEXT,
            price     REAL,
            calories  INTEGER,
            available INTEGER
        );
        CREATE TABLE customers (
            customer_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name    TEXT,
            city         TEXT,
            member_level TEXT,
            signup_date  TEXT
        );
        CREATE TABLE stores (
            store_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_name TEXT,
            city        TEXT,
            manager     TEXT
        );
        CREATE TABLE orders (
            order_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id      INTEGER,
            pizza_id         INTEGER,
            store_id         INTEGER,
            quantity         INTEGER,
            total_price      REAL,
            payment_method   TEXT,
            order_status     TEXT,
            order_time       TEXT,
            delivery_minutes INTEGER,
            rating           INTEGER,
            FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY(pizza_id)    REFERENCES pizzas(pizza_id),
            FOREIGN KEY(store_id)    REFERENCES stores(store_id)
        );
    """)

    cities   = ["Hanoi", "HCM", "Da Nang", "Hai Phong", "Can Tho"]
    payments = ["Cash", "Card", "Momo", "ZaloPay"]
    statuses = ["Completed", "Completed", "Completed", "Cancelled", "Preparing"]
    levels   = ["Normal", "Silver", "Gold", "VIP"]

    pizza_defs = [
        ("Margherita", "Classic"), ("Pepperoni", "Meat"),
        ("BBQ Chicken", "Meat"),   ("Hawaiian", "Meat"),
        ("Veggie", "Vegetarian"),  ("Four Cheese", "Vegetarian"),
        ("Seafood", "Seafood"),    ("Meat Lovers", "Meat"),
        ("Spicy Beef", "Meat"),    ("Mushroom Deluxe", "Vegetarian"),
    ]
    sizes = {"S": 6, "M": 9, "L": 12}

    pizza_rows = []
    for name, cat in pizza_defs:
        for size, base in sizes.items():
            pizza_rows.append((name, cat, size, round(base + random.uniform(0, 3), 2),
                               random.randint(500, 1400), random.choice([1, 1, 1, 0])))
    cur.executemany(
        "INSERT INTO pizzas (name,category,size,price,calories,available) VALUES (?,?,?,?,?,?)",
        pizza_rows,
    )

    store_rows = [(f"Branch {i}", random.choice(cities), f"Manager {i}") for i in range(1, 8)]
    cur.executemany("INSERT INTO stores (branch_name,city,manager) VALUES (?,?,?)", store_rows)

    cust_rows = []
    for i in range(1, 101):
        dt = (datetime.now() - timedelta(days=random.randint(1, 500))).strftime("%Y-%m-%d")
        cust_rows.append((f"Customer {i}", random.choice(cities), random.choice(levels), dt))
    cur.executemany(
        "INSERT INTO customers (full_name,city,member_level,signup_date) VALUES (?,?,?,?)",
        cust_rows,
    )

    order_rows = []
    for _ in range(500):
        pid   = random.randint(1, len(pizza_rows))
        cur.execute("SELECT price FROM pizzas WHERE pizza_id=?", (pid,))
        price = cur.fetchone()[0]
        qty   = random.randint(1, 4)
        status = random.choice(statuses)
        order_time = (datetime.now() - timedelta(days=random.randint(0, 180),
                                                  hours=random.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")
        order_rows.append((
            random.randint(1, 100), pid, random.randint(1, 7), qty,
            round(price * qty, 2), random.choice(payments), status,
            order_time,
            random.randint(15, 60) if status == "Completed" else None,
            random.randint(1, 5)   if status == "Completed" else None,
        ))
    cur.executemany("""
        INSERT INTO orders
        (customer_id,pizza_id,store_id,quantity,total_price,
         payment_method,order_status,order_time,delivery_minutes,rating)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, order_rows)

    conn.commit()
    conn.close()
    return db_file


@pytest.fixture()
def db_conn(test_db_path):
    """Provide a ready sqlite3 connection to the test database."""
    conn = sqlite3.connect(test_db_path)
    yield conn
    conn.close()
