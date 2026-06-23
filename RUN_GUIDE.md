# HƯỚNG DẪN CẤU HÌNH VÀ CHẠY CHƯƠNG TRÌNH

Tài liệu này hướng dẫn cách cấu hình khóa Gemini API Key, cài đặt thư viện và chạy chương trình SQL Assistant.

## 1. Cấu hình file `.env`

Chương trình đọc Gemini API Key từ file `.env` nằm ở thư mục gốc của dự án (`01_Source_Code`).

### Các bước tạo file `.env`:
1. Tại thư mục gốc `01_Source_Code`, tạo một file mới tên là `.env` (lưu ý không để đuôi `.txt` hay khoảng trắng thừa).
2. Nhập nội dung mẫu dưới đây:

```env
GEMINI_API_KEY=AIzaSyDskV2FTf3x6WqDVJrGNXBWluCzJrJKbJM
GEMINI_MODEL=gemini-3.5-flash
SQL_ASSISTANT_DB=database.db
SQL_MAX_RETRIES=2
SQL_TIMEOUT_SECONDS=15
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=2
MAX_QUESTION_LENGTH=2000
PORT=5002
FLASK_DEBUG=0
SQL_ASSISTANT_ORIGINS=http://localhost:5000,http://127.0.0.1:5002
```

> [!IMPORTANT]
> - Hãy thay thế giá trị `GEMINI_API_KEY` bằng API key thực tế của bạn.
> - Đảm bảo tên biến viết hoa chính xác là `GEMINI_API_KEY`.

---

## 2. Hướng dẫn chạy chương trình

### Cách 1: Chạy bằng file Script (Khuyến nghị trên Windows)
Nhấp đúp chuột vào file `run.bat` hoặc chạy trong PowerShell:
```powershell
.\run.bat
```
Script sẽ tự động:
1. Tạo môi trường ảo `.venv` nếu chưa có.
2. Kích hoạt môi trường ảo.
3. Cài đặt các thư viện từ `requirements.txt`.
4. Khởi chạy Flask Server (`python run.py`).

### Cách 2: Chạy bằng lệnh thủ công
Mở **Windows PowerShell** tại thư mục `01_Source_Code` và thực hiện các lệnh sau:

```powershell
# 1. Tạo môi trường ảo (nếu chưa có)
python -m venv .venv

# 3. Cài đặt thư viện bắt buộc (đã bao gồm python-dotenv)
.venv\Scripts\pip install -r requirements.txt

# 4. Chạy server
.venv\Scripts\python run.py
```

---

## 3. Cách kiểm tra API Key đã được tải thành công hay chưa

### Bước 1: Xem Console Log khi khởi động
Khi bạn chạy chương trình, nếu API key hợp lệ được tìm thấy và nạp từ `.env`, bạn sẽ thấy dòng sau xuất hiện ở Console:
```text
Gemini API key loaded: YES
```

### Bước 2: Kiểm tra qua API Health Check
Mở trình duyệt web hoặc dùng công cụ kiểm tra (như Postman/curl) truy cập đường dẫn:
`http://127.0.0.1:5002/api/health`

Kết quả trả về định dạng JSON sẽ như sau:
```json
{
  "architecture": "Agentic AI + Plan-and-Execute + Self-Correction",
  "database": "database.db",
  "database_found": true,
  "llm_configured": true,
  "model": "gemini-3.5-flash",
  "status": "ok"
}
```
* **`llm_configured`**: Nếu là `true`, có nghĩa là chương trình đã nhận diện và nạp thành công Gemini API Key của bạn từ file `.env`. Nếu là `false`, hãy kiểm tra lại file `.env` và tên biến.

---

## 4. Chạy kiểm thử (Unit Test)

Bạn có thể chạy toàn bộ 200 ca kiểm thử tự động của hệ thống để xác thực mọi chức năng hoạt động đúng:
```powershell
# Chạy pytest từ venv
.venv\Scripts\pytest
```
*Tất cả 200 tests sẽ tự động mock cuộc gọi API và đều được pass mà không cần kết nối mạng thực tế.*
