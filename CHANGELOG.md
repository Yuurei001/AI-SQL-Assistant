# Changelog

## 2026-06-09 - Agentic AI graduation package

### Architecture

- Chuyển pipeline NL2SQL tuyến tính thành Plan-and-Execute với tám agent.
- Thêm `AgentState`, task status, timeline, telemetry và retry events.
- Thêm feedback loop và `SelfCorrectionAgent`.
- Thêm `ToolManager`, `MemoryManager` cô lập theo conversation.
- Thêm SQLite progress handler và `connection.interrupt()` cho timeout.

### Security and reliability

- Xóa API key khỏi source, chỉ đọc từ `GEMINI_API_KEY`.
- Nâng từ SDK Gemini cũ sang SDK chính thức `google-genai`.
- Giới hạn loại truy vấn, chiều dài câu hỏi, conversation ID và CORS origin.
- Không trả traceback nội bộ về client.

### Web UI

- Thiết kế lại medical AI dashboard responsive.
- Thêm dark/light mode, sidebar, lịch sử hội thoại và schema explorer.
- Thêm SQL viewer, agent timeline, task plan, retry events và bảng kết quả.
- Thêm loading, toast, empty, no-row và error state.
- Sửa scroll, overflow và layout mobile.

### Quality and documentation

- Mở rộng lên 200 test, đạt 100% pass.
- Thêm benchmark offline và 10 sơ đồ Mermaid mới.
- Viết lại báo cáo 96 trang, slide bảo vệ và bộ tài liệu bàn giao.
