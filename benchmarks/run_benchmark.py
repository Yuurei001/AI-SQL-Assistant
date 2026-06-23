"""Benchmark offline, tái lập được cho báo cáo và package bàn giao."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR if BACKEND_DIR.exists() else ROOT))

from agent_core import llm
from agent_core.orchestrator import run_agentic
from agent_core.tools import ExecutorTool, SchemaTool, ValidatorTool

PACKAGED_DB_PATH = ROOT / "database" / "database.db"
DB_PATH = PACKAGED_DB_PATH if PACKAGED_DB_PATH.exists() else ROOT / "database.db"
OUTPUT = Path(__file__).with_name("results.json")

QUERIES = [
    "SELECT name, price FROM pizzas ORDER BY price DESC LIMIT 10",
    "SELECT category, COUNT(*) AS total FROM pizzas GROUP BY category",
    "SELECT c.city, COUNT(o.order_id) AS orders_count FROM orders o JOIN customers c ON o.customer_id=c.customer_id GROUP BY c.city",
    "SELECT payment_method, SUM(total_price) AS revenue FROM orders GROUP BY payment_method",
    "SELECT s.branch_name, AVG(o.delivery_minutes) AS avg_delivery FROM orders o JOIN stores s ON o.store_id=s.store_id WHERE o.delivery_minutes IS NOT NULL GROUP BY s.branch_name",
    "SELECT p.name, SUM(o.quantity) AS total_quantity FROM orders o JOIN pizzas p ON o.pizza_id=p.pizza_id GROUP BY p.name ORDER BY total_quantity DESC LIMIT 5",
    "SELECT member_level, COUNT(*) AS customers FROM customers GROUP BY member_level",
    "SELECT order_status, COUNT(*) AS orders_count FROM orders GROUP BY order_status",
    "SELECT COUNT(*) AS completed_orders FROM orders WHERE order_status='Completed'",
    "SELECT city, COUNT(*) AS customers FROM customers GROUP BY city ORDER BY customers DESC",
]


def milliseconds(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    schema = SchemaTool(str(DB_PATH)).schema_map()
    validator = ValidatorTool(str(DB_PATH), schema_map=schema)
    executor = ExecutorTool(str(DB_PATH), timeout_seconds=5)

    validation_times: list[float] = []
    execution_times: list[float] = []
    row_counts: list[int] = []
    for _ in range(20):
        for query in QUERIES:
            started = time.perf_counter()
            ok, error = validator.run(query)
            validation_times.append(milliseconds(started))
            if not ok:
                raise RuntimeError(error)

            started = time.perf_counter()
            frame, error = executor.run(query)
            execution_times.append(milliseconds(started))
            if error:
                raise RuntimeError(error)
            row_counts.append(len(frame))

    responses = iter(
        [
            "SELECT * FROM bang_sai",
            "SELECT name, price FROM pizzas ORDER BY price DESC LIMIT 5",
            '{"summary":"Đã phục hồi sau lỗi.","labels":{},"columns":{}}',
        ]
    )
    with patch.object(llm, "complete", side_effect=lambda prompt: next(responses)):
        correction = run_agentic(
            "Top 5 pizza theo giá",
            str(DB_PATH),
            conversation_id="benchmark",
            max_retries=2,
        )

    result = {
        "database": DB_PATH.name,
        "query_count": len(QUERIES),
        "iterations_per_query": 20,
        "validation_samples": len(validation_times),
        "execution_samples": len(execution_times),
        "validation_ms": {
            "mean": round(statistics.mean(validation_times), 3),
            "median": round(statistics.median(validation_times), 3),
            "p95": round(sorted(validation_times)[int(len(validation_times) * 0.95) - 1], 3),
        },
        "execution_ms": {
            "mean": round(statistics.mean(execution_times), 3),
            "median": round(statistics.median(execution_times), 3),
            "p95": round(sorted(execution_times)[int(len(execution_times) * 0.95) - 1], 3),
        },
        "average_rows": round(statistics.mean(row_counts), 2),
        "self_correction": {
            "success": correction["success"],
            "retries": correction["retries"],
            "final_sql": correction["sql"],
            "timeline_steps": len(correction["steps"]),
        },
        "notes": [
            "Benchmark chạy offline, không tính độ trễ mạng hoặc Gemini API.",
            "Self-correction dùng phản hồi LLM giả lập để kiểm tra logic điều phối.",
        ],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
