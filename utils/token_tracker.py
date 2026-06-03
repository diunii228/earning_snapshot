# utils/token_tracker.py
import logging

logger = logging.getLogger(__name__)

class GlobalTokenTracker:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.api_calls = 0

    def add_from_response(self, response):
        """Hàm này sẽ bóc tách metadata từ LangChain response và cộng dồn vào tổng"""
        self.api_calls += 1
        
        # LangChain bản mới (usage_metadata)
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = response.usage_metadata
            self.input_tokens += usage.get('input_tokens', 0)
            self.output_tokens += usage.get('output_tokens', 0)
            self.total_tokens += usage.get('total_tokens', 0)
            return

        # LangChain bản cũ (response_metadata)
        if hasattr(response, 'response_metadata'):
            meta = response.response_metadata.get("token_usage", {})
            if hasattr(meta, 'prompt_token_count'): # Dạng Object
                self.input_tokens += getattr(meta, 'prompt_token_count', 0)
                self.output_tokens += getattr(meta, 'candidates_token_count', 0)
                self.total_tokens += getattr(meta, 'total_token_count', 0)
            elif isinstance(meta, dict): # Dạng Dict
                self.input_tokens += meta.get('prompt_token_count', 0)
                self.output_tokens += meta.get('candidates_token_count', 0)
                self.total_tokens += meta.get('total_token_count', 0)

    def print_summary(self):
        """In ra báo cáo tổng kết đẹp mắt"""
        summary = (
            f"\n" + "="*50 +
            f"\n🔥 BÁO CÁO TIÊU THỤ TOKEN (Google Gemini) 🔥"
            f"\n- Số lần gọi API: {self.api_calls}"
            f"\n- Input Tokens : {self.input_tokens:,}"
            f"\n- Output Tokens: {self.output_tokens:,}"
            f"\n- TỔNG TOKENS  : {self.total_tokens:,}"
            f"\n" + "="*50
        )
        logger.info(summary)
        print(summary)

token_tracker = GlobalTokenTracker()