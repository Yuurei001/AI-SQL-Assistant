# AI SQL Assistant - Source Code

Đây là source code độc lập trong package bàn giao. Hệ thống chuyển câu hỏi
tiếng Việt thành truy vấn SQLite theo kiến trúc **Agentic AI +
Plan-and-Execute + Tool Calling + Feedback Loop + Self-Correction**.

## Luồng xử lý

`User -> Planner -> Schema Analyzer -> SQL Generator -> Validator -> Executor`

Nếu validate hoặc execute thất bại, `SelfCorrectionAgent` phân tích lỗi và đưa
SQL đã sửa trở lại Validator/Executor. Khi thành công, Result Interpreter và
Response Generator tạo phản hồi cuối. Mọi bước được ghi vào timeline và
`task_status`.

## Yêu cầu

- Windows 10/11 hoặc Linux 64-bit
- Python 3.11-3.13
- RAM tối thiểu 4 GB, khuyến nghị 8 GB
- Khoảng 1 GB dung lượng trống
- Gemini API key để sinh SQL bằng LLM

## Cài đặt nhanh

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Mở `http://localhost:5000`. Runtime tự đọc API key từ tệp `.env` cục bộ.

## Cấu hình

Các biến cấu hình quan trọng:

- `GEMINI_API_KEY`: khóa truy cập Gemini.
- `GEMINI_MODEL`: mặc định `gemini-2.5-flash`.
- `SQL_ASSISTANT_DB`: đường dẫn SQLite; mặc định tự nhận
  `database/database.db`.
- `SQL_MAX_RETRIES`: số vòng self-correction, mặc định `2`.
- `SQL_TIMEOUT_SECONDS`: timeout truy vấn, mặc định `15`.
- `LLM_TIMEOUT_SECONDS`: timeout mỗi lần gọi Gemini, mặc định `30`.

## Kiểm thử

```powershell
python -m pytest tests -q
```

Kết quả bàn giao đã xác minh: `200 passed`, không failed và không skipped.
Benchmark offline:

```powershell
python benchmarks/run_benchmark.py
```

## API chính

- `GET /api/health`
- `GET /api/schema`
- `GET /api/tools`
- `GET /api/stats`
- `GET /api/history?conversation_id=...`
- `DELETE /api/history?conversation_id=...`
- `POST /api/query`

Ví dụ payload:

```json
{
  "question": "Top 5 pizza có giá cao nhất",
  "conversation_id": "demo-01"
}
```

## Cấu trúc

- `backend/`: Flask API, agent, state, orchestrator và tool.
- `frontend/templates/`, `frontend/static/`: giao diện HTML/CSS/JS.
- `database/`: SQLite, schema và dữ liệu mẫu.
- `tests/`: unit, agent, integration, API và error handling.
- `benchmarks/`: benchmark offline có thể lặp lại.

## Tác giả / Author

- **Nguyễn Ngọc Doanh** - *Phát triển chính & Thiết kế kiến trúc Agentic AI*

