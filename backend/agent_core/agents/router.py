import json
import logging
import re
from .base import BaseAgent
from ..state import AgentState
from .. import llm

log = logging.getLogger("agent_core")

class ConversationRouterAgent(BaseAgent):
    name = "conversation_router"
    role = "Phân loại ý định của người dùng và định tuyến yêu cầu"

    def act(self, state: AgentState) -> None:
        prompt = f"""Bạn là bộ phân loại ý định cho hệ thống SQL Assistant.
Nhiệm vụ của bạn là xác định người dùng có thật sự muốn truy vấn cơ sở dữ liệu hay không.

Chỉ phân loại là "database_query" nếu câu hỏi yêu cầu lấy, lọc, đếm, thống kê, so sánh, tổng hợp hoặc phân tích dữ liệu có trong database.

Không phân loại là "database_query" đối với:
- Lời chào (hi, hello, chào, chào bạn, chào robot, chao...)
- Cảm ơn (cảm ơn, cảm ơn bạn, cám ơn, cám ơn bạn, thanks, thank you...)
- Hỏi bạn là ai (bạn là ai, tên là gì, bạn tên là gì, giới thiệu bản thân...)
- Hỏi khả năng/cách dùng hệ thống (bạn làm được gì, bạn biết làm gì, hướng dẫn sử dụng, giúp tôi với, hướng dẫn, trợ giúp, làm thế nào...)
- Câu trò chuyện/phản hồi ngắn thông thường (ok, tốt, được, thế à, ừ, vâng, thế thôi...)
- Câu chưa đủ thông tin / mập mờ (xem cái đó, xem hộ tôi, kiểm tra cái này, làm tiếp đi, chạy đi...)
- Câu không liên quan đến database (thời tiết hôm nay thế nào, thủ đô nước Pháp là gì...)

Hãy trả về phản hồi trực tiếp (direct_response) bằng tiếng Việt thật tự nhiên, thân thiện và hữu ích nếu intent không phải là "database_query".

Trả về JSON đúng định dạng sau, tuyệt đối không có văn bản thừa ngoài JSON:
{{
  "intent": "general_chat | database_query | ambiguous | out_of_scope",
  "should_query_database": false,
  "reason": "giải thích ngắn gọn",
  "direct_response": "nếu should_query_database là false, hãy trả lời trực tiếp ở đây. Nếu should_query_database là true, hãy để null."
}}

User input: "{state.question}"
Output JSON:"""
        
        try:
            raw_resp = llm.complete(prompt)
            # Dọn dẹp markdown code block nếu có
            cleaned_resp = raw_resp.strip()
            if cleaned_resp.startswith("```"):
                cleaned_resp = re.sub(r"^```(?:json)?\s*", "", cleaned_resp)
                cleaned_resp = re.sub(r"\s*```$", "", cleaned_resp)
            cleaned_resp = cleaned_resp.strip()
            
            data = json.loads(cleaned_resp)
            state.intent = data.get("intent", "database_query")
            state.should_query_database = bool(data.get("should_query_database", True))
            state.direct_response = data.get("direct_response")
            
            # An toàn bổ sung: nếu intent khác database_query thì should_query_database bắt buộc phải False
            if state.intent != "database_query":
                state.should_query_database = False
                
        except Exception as exc:
            log.warning("Router phân tích thất bại: %s. Fallback về database_query.", exc)
            state.intent = "database_query"
            state.should_query_database = True
            state.direct_response = None

        state.add_step(
            self.name, "done",
            f"Phân loại ý định: {state.intent}", 0
        )
