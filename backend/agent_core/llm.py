"""
llm.py — Lớp truy cập mô hình ngôn ngữ lớn (Google Gemini).

Toàn bộ lời gọi LLM trong hệ thống đi qua hàm :func:`complete`.
Việc tập trung một điểm vào/ra giúp:
  * Cấu hình API key / tên model ở một chỗ duy nhất.
  * **Kiểm thử (unit test)** dễ dàng: chỉ cần monkeypatch
    ``agent_core.llm.complete`` là có thể chạy toàn bộ pipeline agent
    mà không cần gọi mạng — đây là lý do bộ test đạt 100% pass mà
    không phụ thuộc vào kết nối Internet của môi trường CI.
"""

from __future__ import annotations

import os
import time

def _load_env() -> tuple[bool, str]:
    from pathlib import Path
    from dotenv import load_dotenv
    current_dir = Path(__file__).resolve().parent
    for parent in [current_dir] + list(current_dir.parents):
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            return True, str(env_path)
    # Default fallback
    load_dotenv()
    return False, "Không tìm thấy file .env ở thư mục hiện tại hoặc các thư mục cha."

env_loaded, env_path_str = _load_env()

# Không lưu khóa API trong source. Người vận hành cấp qua biến môi trường.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))

_CLIENT_CACHE = None


def get_model():
    """Khởi tạo và cache Google Gen AI client.

    Tên hàm được giữ để tương thích với các module cũ đã import ``get_model``.
    """
    global _CLIENT_CACHE
    # Đọc key động để hỗ trợ mock hoặc cập nhật runtime
    api_key = os.environ.get("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    
    if not api_key:
        err_msg = (
            "LỖI CẤU HÌNH: Chưa cấu hình Gemini API key (thiếu biến môi trường GEMINI_API_KEY).\n"
            f"- Trạng thái load file .env: {'Thành công' if env_loaded else 'Thất bại'}\n"
            f"- Đường dẫn file .env đã cố gắng đọc: {env_path_str if env_loaded else 'Không tìm thấy file .env trong thư mục project.'}\n"
            "Gợi ý cách khắc phục:\n"
            "1. Hãy đảm bảo bạn đã tạo file tên là `.env` tại thư mục gốc của project.\n"
            "2. Điền nội dung mẫu: `GEMINI_API_KEY=your_api_key_here`\n"
            "3. Đảm bảo tên biến viết hoa chính xác là `GEMINI_API_KEY`.\n"
        )
        raise RuntimeError(err_msg)
        
    if _CLIENT_CACHE is None:
        from google import genai
        # Log trạng thái tải key (không in giá trị key)
        print("Gemini API key loaded: YES")
        _CLIENT_CACHE = genai.Client(api_key=api_key)
    return _CLIENT_CACHE


def complete(
    prompt: str,
    *,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
) -> str:
    """Gửi *prompt* tới LLM và trả về phần text thô.

    Đây là điểm mở rộng duy nhất cho mọi agent cần "suy luận"
    (reasoning). Trong test, hàm này được thay thế bằng một hàm giả
    lập trả về SQL/JSON định sẵn.
    """
    client = get_model()
    timeout = timeout_seconds or LLM_TIMEOUT_SECONDS
    retries = LLM_MAX_RETRIES if max_retries is None else max_retries
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            from google.genai import types

            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(timeout=int(timeout * 1000)),
                ),
            )
            text = (resp.text or "").strip()
            if not text:
                raise RuntimeError("Gemini trả về nội dung rỗng.")
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(min(0.5 * (2**attempt), 2.0))

    raise RuntimeError(
        f"Không thể gọi Gemini sau {retries + 1} lần thử: {last_error}"
    ) from last_error
