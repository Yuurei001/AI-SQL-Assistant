"""Flask API cho AI SQL Assistant theo kiến trúc Agentic AI."""

from __future__ import annotations

import logging
import os
import re
from collections import deque
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv

# Tự động tìm và nạp file .env từ thư mục cha
def _load_env():
    current_dir = Path(__file__).resolve().parent
    for parent in [current_dir] + list(current_dir.parents):
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            return
    load_dotenv()

_load_env()

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from agent_core import llm
from agent_core.orchestrator import AgenticOrchestrator

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent if BASE_DIR.name.lower() == "backend" else BASE_DIR
PACKAGED_DB = PROJECT_DIR / "database" / "database.db"
DEFAULT_DB_FILE = PACKAGED_DB if PACKAGED_DB.exists() else BASE_DIR / "database.db"
PACKAGED_FRONTEND = PROJECT_DIR / "frontend"
TEMPLATE_DIR = (
    PACKAGED_FRONTEND / "templates"
    if (PACKAGED_FRONTEND / "templates").exists()
    else BASE_DIR / "templates"
)
STATIC_DIR = (
    PACKAGED_FRONTEND / "static"
    if (PACKAGED_FRONTEND / "static").exists()
    else BASE_DIR / "static"
)
DEFAULT_DB_PATH = os.environ.get(
    "SQL_ASSISTANT_DB",
    str(DEFAULT_DB_FILE),
)
MAX_RETRIES = int(os.environ.get("SQL_MAX_RETRIES", "2"))
TIMEOUT_SECONDS = int(os.environ.get("SQL_TIMEOUT_SECONDS", "15"))
MAX_QUESTION_LENGTH = int(os.environ.get("MAX_QUESTION_LENGTH", "2000"))
CONVERSATION_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

log = logging.getLogger("agent_core")


class QueryMetrics:
    """Bộ đếm nhẹ phục vụ dashboard, không lưu dữ liệu nhạy cảm."""

    def __init__(self, max_recent: int = 100):
        self._lock = RLock()
        self._total = 0
        self._successful = 0
        self._durations: deque[int] = deque(maxlen=max_recent)

    def record(self, success: bool, duration_ms: int) -> None:
        with self._lock:
            self._total += 1
            self._successful += int(success)
            self._durations.append(max(0, duration_ms))

    def snapshot(self) -> dict:
        with self._lock:
            average = (
                round(sum(self._durations) / len(self._durations))
                if self._durations
                else 0
            )
            rate = round(self._successful / self._total * 100, 1) if self._total else 0
            return {
                "total_queries": self._total,
                "successful_queries": self._successful,
                "success_rate": rate,
                "average_execution_ms": average,
            }


def _conversation_id(payload: dict | None = None) -> str:
    raw = (
        (payload or {}).get("conversation_id")
        or request.args.get("conversation_id")
        or request.headers.get("X-Conversation-ID")
        or "default"
    )
    value = str(raw).strip()
    return value if CONVERSATION_RE.fullmatch(value) else "default"


def create_app(
    *,
    db_path: str | None = None,
    orchestrator: AgenticOrchestrator | None = None,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(TEMPLATE_DIR),
        static_folder=str(STATIC_DIR),
    )
    app.config.update(
        DATABASE_PATH=db_path or DEFAULT_DB_PATH,
        MAX_RETRIES=MAX_RETRIES,
        TIMEOUT_SECONDS=TIMEOUT_SECONDS,
        MAX_QUESTION_LENGTH=MAX_QUESTION_LENGTH,
    )

    allowed_origins = [
        value.strip()
        for value in os.environ.get(
            "SQL_ASSISTANT_ORIGINS",
            "http://localhost:5000,http://127.0.0.1:5000",
        ).split(",")
        if value.strip()
    ]
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    agent_system = orchestrator or AgenticOrchestrator()
    metrics = QueryMetrics()
    app.extensions["agent_orchestrator"] = agent_system
    app.extensions["query_metrics"] = metrics

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def api_health():
        database = app.config["DATABASE_PATH"]
        db_ok = os.path.isfile(database)
        return jsonify(
            {
                "status": "ok" if db_ok else "degraded",
                "database": os.path.basename(database),
                "database_found": db_ok,
                "llm_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
                "model": os.environ.get("GEMINI_MODEL", llm.GEMINI_MODEL),
                "architecture": "Agentic AI + Plan-and-Execute + Self-Correction",
            }
        )

    @app.get("/api/schema")
    def api_schema():
        database = app.config["DATABASE_PATH"]
        if not os.path.isfile(database):
            return jsonify({"error": "Không tìm thấy cơ sở dữ liệu."}), 404
        try:
            tool = agent_system.tools.schema(database)
            return jsonify(
                {
                    "schema": tool.describe(),
                    "tables": tool.schema_map(),
                    "relationships": tool.relationships(),
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Không đọc được schema: %s", exc)
            return jsonify({"error": "Không thể đọc schema cơ sở dữ liệu."}), 500

    @app.get("/api/tools")
    def api_tools():
        return jsonify({"tools": agent_system.tools.catalog()})

    @app.get("/api/stats")
    def api_stats():
        return jsonify(metrics.snapshot())

    @app.get("/api/history")
    def api_history():
        conversation_id = _conversation_id()
        limit = min(max(request.args.get("limit", default=20, type=int), 1), 100)
        return jsonify(
            {
                "conversation_id": conversation_id,
                "turns": agent_system.history(conversation_id, limit=limit),
            }
        )

    @app.delete("/api/history")
    def api_clear_history():
        conversation_id = _conversation_id()
        agent_system.clear_history(conversation_id)
        return jsonify({"success": True, "conversation_id": conversation_id})

    @app.post("/api/query")
    def api_query():
        payload = request.get_json(silent=True) or {}
        question = str(payload.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Câu hỏi không được để trống."}), 400
        if len(question) > app.config["MAX_QUESTION_LENGTH"]:
            return jsonify({"error": "Câu hỏi vượt quá độ dài cho phép."}), 413

        database = app.config["DATABASE_PATH"]
        if not os.path.isfile(database):
            return jsonify({"error": "Không tìm thấy cơ sở dữ liệu."}), 404

        conversation_id = _conversation_id(payload)
        try:
            result = agent_system.handle(
                question=question,
                db_path=database,
                conversation_id=conversation_id,
                max_retries=app.config["MAX_RETRIES"],
                timeout_seconds=app.config["TIMEOUT_SECONDS"],
            )
            metrics.record(result["success"], result.get("execution_ms", 0))
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            log.exception("Yêu cầu thất bại ngoài dự kiến: %s", exc)
            metrics.record(False, 0)
            return jsonify(
                {
                    "success": False,
                    "conversation_id": conversation_id,
                    "error": "Hệ thống không thể hoàn tất yêu cầu. Vui lòng kiểm tra cấu hình và thử lại.",
                }
            ), 500

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
