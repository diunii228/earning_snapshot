import os
import json
import base64
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
import pandas as pd
from datetime import datetime
import multiprocessing as mp
import google.generativeai as genai
from pydantic import BaseModel, Field

BANK_NAME_MAP = {
    "VIỆT NAM THỊNH VƯỢNG": "VPB",
    "KỸ THƯƠNG": "TCB",
    "NGOẠI THƯƠNG": "VCB",
    "CÔNG THƯƠNG": "CTG",
    "ĐẦU TƯ VÀ PHÁT TRIỂN": "BIDV",
    "QUÂN ĐỘI": "MBB",
    "Á CHÂU": "ACB",
    "SÀI GÒN THƯƠNG TÍN": "STB",
    "SÀI GÒN HÀ NỘI": "SHB",
    "QUỐC TẾ": "VIB",
    "PHÁT TRIỂN THÀNH PHỐ HỒ CHÍ MINH": "HDB",
    "LIÊN VIỆT": "LPB",
    "TIÊN PHONG": "TPB",
    "PHƯƠNG ĐÔNG": "OCB",
    "XUẤT NHẬP KHẨU": "EIB",
    "ĐÔNG NAM Á": "SSB",
    "HÀNG HẢI": "MSB",
    "KIÊN LONG": "KLB",
    "QUỐC DÂN": "NCB",
    
}

def get_short_bank_name(long_name: str) -> str:
    """
    Chuyển đổi tên dài thành mã ngân hàng (Ticker/Short name)
    Có xử lý ký tự đặc biệt và khoảng trắng thừa.
    """
    if not long_name or long_name == "Unknown Bank":
        return long_name
        
    clean_string = long_name.upper().replace("_", " ").replace("-", " ")
    
    clean_string = " ".join(clean_string.split())
    
    for keyword, short_name in BANK_NAME_MAP.items():
        if keyword in clean_string:
            return short_name
            
    fallback_name = clean_string
    remove_keywords = ["NGÂN HÀNG", "THƯƠNG MẠI", "CỔ PHẦN", "NH TMCP", "TMCP"]
    
    for kw in remove_keywords:
        fallback_name = fallback_name.replace(kw, "")
        
    return fallback_name.strip()

class FinancialItem(BaseModel):
    """Một dòng trong bảng tài chính"""
    item_type: str = Field(
        description="Loại mục: section_title, main_item, sub_item, sub_sub_item"
    )
    content: str = Field(
        description="Nội dung khoản mục"
    )
    note_reference: str = Field(
        default="",
        description="Mã thuyết minh, để trống nếu không có"
    )
    value_current: float = Field(
        default=0.0,
        description="Giá trị kì hiện tại, để 0 nếu không có"
    )
    value_previous: float = Field(
        default=0.0,
        description="Giá trị kì trước, để 0 nếu không có"
    )
    indentation_level: int = Field(
        default=0,
        description="Mức độ thụt lề (0=không thụt, 1=có dấu -, 2=thụt sâu hơn)"
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for DataFrame"""
        return {
            "Type": self.item_type,
            "Content": self.content,
            "Note": self.note_reference,
            "Current": self.value_current,
            "Previous": self.value_previous,
            "Indent": self.indentation_level
        }


class ReportPage(BaseModel):
    """Kết quả trích xuất từ một trang"""
    page_number: int = Field(description="Số trang PDF")
    section_title: Optional[str] = Field(
        default="",
        description="Tiêu đề section chính"
    )
    items: List[FinancialItem] = Field(
        description="Danh sách các khoản mục trong trang"
    )
    confidence: float = Field(
        default=0.0,
        description="Độ tin cậy của việc trích xuất (0-1)"
    )

class FinancialExtraction(BaseModel):
    """Kết quả trích xuất báo cáo tài chính"""
    document_title: str = Field(description="Tiêu đề báo cáo")
    report_type: str = Field(description="Loại báo cáo: balance_sheet, income_statement, cash_flow, custom")
    reporting_date: str = Field(description="Ngày báo cáo")
    entity_name: str = Field(description="Tên tổ chức/ngân hàng")
    
    # THÊM 2 TRƯỜNG NÀY ĐỂ LƯU TÊN CỘT
    period_current: str = Field(default="Current", description="Tên cột kỳ hiện tại (VD: 31/12/2023)")
    period_previous: str = Field(default="Previous", description="Tên cột kỳ trước (VD: 01/01/2023)")
    
    pages: List[ReportPage] = Field(description="Danh sách các trang đã trích xuất")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Thông tin bổ sung")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_title": self.document_title,
            "report_type": self.report_type,
            "reporting_date": self.reporting_date,
            "entity_name": self.entity_name,
            "period_current": self.period_current,
            "period_previous": self.period_previous,
            "pages": [
                {
                    "page_number": page.page_number,
                    "section_title": page.section_title,
                    "confidence": page.confidence,
                    "items": [item.to_dict() for item in page.items]
                }
                for page in self.pages
            ],
            "metadata": self.metadata
        }
    
    def to_dataframe(self, request_label: str = None) -> pd.DataFrame:
        """Convert to pandas DataFrame với tên cột động"""
        rows = []
        for page in self.pages:
            for item in page.items:
                item_dict = item.to_dict()
                
                # Rút giá trị ra khỏi key mặc định
                curr_val = item_dict.pop("Current")
                prev_val = item_dict.pop("Previous")
                
                # Gán lại bằng key động lấy từ LLM
                row = {
                    "Page": page.page_number,
                    "Section": page.section_title,
                    **item_dict,
                    self.period_current: curr_val,
                    self.period_previous: prev_val
                }
                rows.append(row)
        
        df = pd.DataFrame(rows)
        
        if request_label and not df.empty:
            df.insert(0, "Mã Yêu Cầu", request_label)
            
        return df
        
    
    def get_summary(self) -> Dict[str, Any]:
        total_items = sum(len(page.items) for page in self.pages)
        avg_confidence = sum(page.confidence for page in self.pages) / max(len(self.pages), 1)
        
        return {
            "total_pages": len(self.pages),
            "total_items": total_items,
            "avg_confidence": avg_confidence,
            "sections": list(set(page.section_title for page in self.pages if page.section_title)),
            "report_type": self.report_type,
            "entity": self.entity_name,
            "periods": f"{self.period_current} vs {self.period_previous}"
        }
# ==================== CONFIG CLASS ====================

class Config:
    """Configuration settings"""
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    MAX_WORKERS: int = min(4, mp.cpu_count())
    BATCH_SIZE: int = 5  
    ENABLE_CACHING: bool = True
    ENABLE_PARALLEL: bool = True
    
    BASE_DIR: Path = Path.cwd()
    TEMP_DIR: Path = BASE_DIR / "temp"
    RESULTS_DIR: Path = TEMP_DIR / "results"
    
    @classmethod
    def setup_directories(cls):
        """Tạo các thư mục cần thiết"""
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        cls.RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ==================== PDF HANDLER ====================

class PDFHandler:
    """Xử lý PDF trực tiếp - Không cần render image"""
    
    @staticmethod
    def pdf_to_base64(pdf_path: Path) -> str:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            return base64.b64encode(pdf_bytes).decode('utf-8')
    
    @staticmethod
    def get_pdf_info(pdf_path: Path) -> Dict[str, Any]:
        """
        Lấy thông tin PDF (size, pages estimate)
        
        Args:
            pdf_path: Path to PDF
            
        Returns:
            Dict với file_size_mb và estimated_pages
        """
        file_size = pdf_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        estimated_pages = int(file_size / 150000)
        
        return {
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size_mb, 2),
            "estimated_pages": estimated_pages
        }


# ==================== CACHE SYSTEM ====================

import hashlib
import pickle

class ExtractionCache:    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Config.TEMP_DIR / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache = {}
    
    def _get_cache_key(
        self,
        pdf_path: Path,
        page_range: Optional[tuple],
        report_type: str,
        request_hint: str = "",
    ) -> str:
        """Tạo cache key từ PDF path + page range + report type + request hint."""
        key_str = f"{pdf_path}_{page_range}_{report_type}_{request_hint}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
    def get(
        self,
        pdf_path: Path,
        page_range: Optional[tuple],
        report_type: str,
        request_hint: str = "",
    ) -> Optional[List[ReportPage]]:
        """Lấy kết quả từ cache"""
        if not Config.ENABLE_CACHING:
            return None
        
        cache_key = self._get_cache_key(pdf_path, page_range, report_type, request_hint)
        
        if cache_key in self._memory_cache:
            print(f"Cache hit (memory): {pdf_path.name}")
            return self._memory_cache[cache_key]
        
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    result = pickle.load(f)
                    self._memory_cache[cache_key] = result
                    print(f"Cache hit (disk): {pdf_path.name}")
                    return result
            except:
                pass
        
        return None
    
    def set(
        self,
        pdf_path: Path,
        page_range: Optional[tuple],
        report_type: str,
        result: List[ReportPage],
        request_hint: str = "",
    ):
        if not Config.ENABLE_CACHING:
            return
        
        cache_key = self._get_cache_key(pdf_path, page_range, report_type, request_hint)
        
        self._memory_cache[cache_key] = result
        
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(result, f)
        except Exception as e:
            print(f"Không thể lưu cache: {e}")
    
    def clear(self):
        """Xóa cache"""
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                cache_file.unlink()
            except:
                pass

# ==================== GEMINI EXTRACTOR ====================

class GeminiExtractor:
    """Handler cho Gemini Vision API - Direct PDF Base64"""
    
    def __init__(self, api_key: str = None, model_name: str = None):
        """Khởi tạo Gemini client"""
        self.api_key = api_key or Config.GEMINI_API_KEY
        self.model_name = model_name or Config.GEMINI_MODEL
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required.")
        genai.configure(api_key=self.api_key)
        
        self.model = genai.GenerativeModel(self.model_name)
        
        Config.setup_directories()
        
        print(f"Đã khởi tạo Gemini model: {self.model_name}")
    
    def _call_gemini_with_pdf(
        self, 
        prompt: str, 
        pdf_base64: str,
        temperature: float = 0.1
    ) -> str:
        """
        Gọi Gemini API với PDF base64
        
        Args:
            prompt: Prompt text
            pdf_base64: Base64 encoded PDF
            temperature: Temperature setting
            
        Returns:
            Response text
        """
        pdf_part = {
            "mime_type": "application/pdf",
            "data": pdf_base64
        }
        
        response = self.model.generate_content(
            [prompt, pdf_part],
            generation_config=genai.GenerationConfig(
                temperature=temperature,
            )
        )
        
        return response.text.strip()
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON từ response"""
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        return json.loads(response_text)


# ==================== REPORT TYPE DETECTOR ====================

class ReportTypeDetector(GeminiExtractor):
    
    def detect_report_type(
        self,
        pdf_path: Path,
        sample_pages: int = 10
    ) -> Dict[str, Any]:
        """
        Tự động phát hiện loại báo cáo
        
        Args:
            pdf_path: Đường dẫn file PDF
            sample_pages: Số trang để scan (Note: Gemini sẽ xử lý toàn bộ PDF)
            
        Returns:
            Dict với report_type, confidence
        """
        print("\n" + "="*80)
        print("PHÁT HIỆN LOẠI BÁO CÁO")
        print("="*80)
        
        pdf_base64 = PDFHandler.pdf_to_base64(pdf_path)
        pdf_info = PDFHandler.get_pdf_info(pdf_path)
        
        print(f"PDF: {pdf_info['file_size_mb']} MB, ~{pdf_info['estimated_pages']} trang")
        
        detection_prompt = f"""
Bạn là chuyên gia phân tích báo cáo tài chính.

**NHIỆM VỤ**: Phân tích PDF và xác định loại báo cáo tài chính chính trong file.

**LƯU Ý**: File PDF có thể có nhiều trang. Hãy scan qua {sample_pages} trang đầu để xác định loại báo cáo chính.

**CÁC LOẠI BÁO CÁO CHÍNH**:

1. **balance_sheet** (Bảng cân đối kế toán):
   - Tiêu đề: "BẢNG CÂN ĐỐI KẾ TOÁN", "BÁO CÁO TÌNH HÌNH TÀI CHÍNH"
   - Cấu trúc: TÀI SẢN, NỢ PHẢI TRẢ, VỐN CHỦ SỞ HỮU
   - Hai cột so sánh 2 thời điểm

2. **income_statement** (Báo cáo kết quả kinh doanh):
   - Tiêu đề: "BÁO CÁO KẾT QUẢ KINH DOANH", "INCOME STATEMENT"
   - Cấu trúc: Thu nhập, Chi phí, Lợi nhuận
   - Có thể so sánh 2 kỳ

3. **cash_flow** (Báo cáo lưu chuyển tiền tệ):
   - Tiêu đề: "BÁO CÁO LƯU CHUYỂN TIỀN TỆ", "CASH FLOW STATEMENT"
   - Cấu trúc: Hoạt động kinh doanh, Đầu tư, Tài chính

4. **notes** (Thuyết minh báo cáo tài chính):
   - Tiêu đề: "THUYẾT MINH BÁO CÁO TÀI CHÍNH"
   - Chi tiết giải thích các khoản mục

5. **mixed** (Nhiều loại báo cáo):
   - File chứa nhiều loại báo cáo khác nhau

6. **other**:
   - Các loại khác: Trang bìa, Mục lục, v.v.

**OUTPUT JSON**:
{{
  "report_type": "balance_sheet|income_statement|cash_flow|notes|mixed|other",
  "confidence": 0.0-1.0,
  "main_sections": ["section1", "section2"],
  "page_analysis": {{
    "balance_sheet_pages": [1, 2, 3],
    "income_statement_pages": [4, 5],
    "other_pages": [6, 7]
  }},
  "reason": "Lý do kết luận"
}}
"""
        
        try:
            print(f"Đang phân tích PDF...")
            
            response = self._call_gemini_with_pdf(detection_prompt, pdf_base64)
            result = self._parse_json_response(response)
            
            report_type = result.get("report_type", "other")
            confidence = result.get("confidence", 0.0)
            
            print("\n" + "="*80)
            print("KẾT QUẢ PHÁT HIỆN")
            print("="*80)
            print(f"Loại báo cáo chính: {report_type}")
            print(f"Độ tin cậy: {confidence:.2%}")
            print(f"Lý do: {result.get('reason', 'N/A')}")
            
            return {
                "report_type": report_type,
                "confidence": confidence,
                "page_analysis": result.get("page_analysis", {}),
                "main_sections": result.get("main_sections", [])
            }
            
        except Exception as e:
            print(f"Lỗi phát hiện báo cáo: {e}")
            return {
                "report_type": "unknown",
                "confidence": 0.0,
                "page_analysis": {},
                "main_sections": []
            }


# ==================== BALANCE SHEET EXTRACTOR ====================

class BalanceSheetExtractor(GeminiExtractor):
    """Extractor cho Bảng cân đối kế toán"""
    
    def _create_extraction_prompt(self, page_range: Optional[tuple] = None) -> str:
        """Tạo prompt cho Balance Sheet"""
        
        page_info = ""
        if page_range:
            page_info = f"Chỉ trích xuất từ trang {page_range[0] + 1} đến trang {page_range[1]}."
        
        return f"""
Bạn là chuyên gia phân tích báo cáo tài chính ngân hàng.

**NHIỆM VỤ**: 
1. Xác định TÊN ĐẦY ĐỦ của Ngân hàng/Công ty từ nội dung PDF (trang bìa hoặc tiêu đề trang).
2. Trích xuất CHÍNH XÁC Bảng cân đối kế toán từ PDF.

{page_info}

**CẤU TRÚC BẢNG**:
- Cột 1: Nội dung (Content)
- Cột 2: Thuyết minh (Note reference)
- Cột 3: Giá trị kỳ hiện tại (triệu đồng)
- Cột 4: Giá trị kỳ trước (triệu đồng)

**QUY TẮC**:

1. **PHÂN LOẠI**:
   - section_title: TÀI SẢN, NỢ PHẢI TRẢ, VỐN CHỦ SỞ HỮU
   - main_item: Khoản mục chính (không dấu -)
   - sub_item: Khoản mục con (có dấu -)

2. **XỬ LÝ SỐ**:
   - Loại bỏ dấu chấm: "1.050.492" → 1050492
   - Số âm: "(264.549)" → -264549
   - Ô trống → 0.0

3. **INDENTATION**:
   - 0: section_title hoặc main_item
   - 1: sub_item (1 dấu -)
   - 2: sub_item thụt sâu hơn

4. **PHÂN TRANG**:
   - Trích xuất TỪNG TRANG riêng biệt
   - Mỗi page object trong mảng pages tương ứng với 1 trang PDF

**OUTPUT JSON**:
{{
  "entity_name": "Tên ngân hàng viết hoa",
  "period_current": "Tên cột thời gian hiện tại (VD: 31/12/2023)",
  "period_previous": "Tên cột thời gian kỳ trước (VD: 01/01/2023)",
  "pages": [
    {{
      "page_number": 1,
      "section_title": "TÀI SẢN",
      "confidence": 0.95,
      "items": [
        {{
          "item_type": "section_title",
          "content": "TÀI SẢN",
          "note_reference": "",
          "value_current": 0.0,
          "value_previous": 0.0,
          "indentation_level": 0
        }},
        {{
          "item_type": "main_item",
          "content": "Tiền mặt và vàng bạc",
          "note_reference": "5",
          "value_current": 1050492,
          "value_previous": 850234,
          "indentation_level": 0
        }}
      ]
    }}
  ]
}}

**LƯU Ý**: Trả về mảng pages với mỗi phần tử là một trang riêng biệt.
"""
    
    async def extract_report(
        self, pdf_path: Path, page_range: Optional[tuple] = None, cache: ExtractionCache = None
    ) -> tuple:
        if cache:
            cached_result = cache.get(pdf_path, page_range, "balance_sheet")
            if cached_result:
                return cached_result
        
        prompt = self._create_extraction_prompt(page_range)
        try:
            pdf_base64 = PDFHandler.pdf_to_base64(pdf_path)
            response = self._call_gemini_with_pdf(prompt, pdf_base64)
            result = self._parse_json_response(response)
            
            ai_entity_name = result.get("entity_name", "")
            final_short_name = get_short_bank_name(ai_entity_name)
            
            period_current = result.get("period_current", "Current")
            period_previous = result.get("period_previous", "Previous")
            
            pages_data = []
            for page_dict in result.get("pages", []):
                items = []
                for item in page_dict.get("items", []):
                    try:
                        val_curr = str(item.get("value_current", 0)).replace('.', '').replace(',', '.')
                        val_prev = str(item.get("value_previous", 0)).replace('.', '').replace(',', '.')
                        items.append(FinancialItem(
                            item_type=item.get("item_type", "main_item"),
                            content=item.get("content", ""),
                            note_reference=item.get("note_reference", ""),
                            value_current=float(val_curr) if val_curr else 0.0,
                            value_previous=float(val_prev) if val_prev else 0.0,
                            indentation_level=int(item.get("indentation_level", 0))
                        ))
                    except:
                        items.append(FinancialItem(item_type="error", content=item.get("content", "")))

                pages_data.append(ReportPage(
                    page_number=page_dict.get("page_number", 0),
                    section_title=page_dict.get("section_title", ""),
                    items=items,
                    confidence=float(page_dict.get("confidence", 0.0))
                ))
            
            return pages_data, final_short_name, period_current, period_previous
            
        except Exception as e:
            print(f"Lỗi trích xuất AI: {e}")
            return [], "Unknown Bank", "Current", "Previous"
    

# ==================== INCOME STATEMENT EXTRACTOR ====================

class IncomeStatementExtractor(GeminiExtractor):
    """Extractor cho Báo cáo kết quả kinh doanh"""
    
    def _create_extraction_prompt(self, page_range: Optional[tuple] = None) -> str:
        """Tạo prompt cho Income Statement"""
        
        page_info = ""
        if page_range:
            page_info = f"Chỉ trích xuất từ trang {page_range[0] + 1} đến trang {page_range[1]}."
        
        return f"""
Bạn là chuyên gia phân tích báo cáo tài chính.

**NHIỆM VỤ**: 
1. Xác định TÊN ĐẦY ĐỦ của Ngân hàng/Công ty từ nội dung PDF (trang bìa hoặc tiêu đề trang).
2. Trích xuất Báo cáo kết quả kinh doanh từ PDF.

{page_info}

**CẤU TRÚC**:
- Thu nhập lãi và các khoản thu nhập tương tự
- Chi phí lãi và các chi phí tương tự
- Thu nhập từ hoạt động dịch vụ
- Chi phí hoạt động
- Lợi nhuận/(Lỗ) thuần

**QUY TẮC TƯƠNG TỰ Balance Sheet**

**OUTPUT JSON** (format giống Balance Sheet):
{{
  "entity_name": "Tên ngân hàng viết hoa",
  "period_current": "Tên cột thời gian hiện tại (VD: 31/12/2023)",
  "period_previous": "Tên cột thời gian kỳ trước (VD: 01/01/2023)",
  "pages": [
    {{
      "page_number": 1,
      "section_title": "TÀI SẢN",
      "confidence": 0.95,
      "items": [
        {{
          "item_type": "section_title",
          "content": "TÀI SẢN",
          "note_reference": "",
          "value_current": 0.0,
          "value_previous": 0.0,
          "indentation_level": 0
        }},
        {{
          "item_type": "main_item",
          "content": "Tiền mặt và vàng bạc",
          "note_reference": "5",
          "value_current": 1050492,
          "value_previous": 850234,
          "indentation_level": 0
        }}
      ]
    }}
  ]
}}
"""
    
    async def extract_report(
        self, pdf_path: Path, page_range: Optional[tuple] = None, cache: ExtractionCache = None
    ) -> tuple:
        if cache:
            cached_result = cache.get(pdf_path, page_range, "balance_sheet")
            if cached_result:
                return cached_result
        
        prompt = self._create_extraction_prompt(page_range)
        try:
            pdf_base64 = PDFHandler.pdf_to_base64(pdf_path)
            response = self._call_gemini_with_pdf(prompt, pdf_base64)
            result = self._parse_json_response(response)
            
            ai_entity_name = result.get("entity_name", "")
            final_short_name = get_short_bank_name(ai_entity_name)
            
            period_current = result.get("period_current", "Current")
            period_previous = result.get("period_previous", "Previous")
            
            pages_data = []
            for page_dict in result.get("pages", []):
                items = []
                for item in page_dict.get("items", []):
                    try:
                        val_curr = str(item.get("value_current", 0)).replace('.', '').replace(',', '.')
                        val_prev = str(item.get("value_previous", 0)).replace('.', '').replace(',', '.')
                        items.append(FinancialItem(
                            item_type=item.get("item_type", "main_item"),
                            content=item.get("content", ""),
                            note_reference=item.get("note_reference", ""),
                            value_current=float(val_curr) if val_curr else 0.0,
                            value_previous=float(val_prev) if val_prev else 0.0,
                            indentation_level=int(item.get("indentation_level", 0))
                        ))
                    except:
                        items.append(FinancialItem(item_type="error", content=item.get("content", "")))

                pages_data.append(ReportPage(
                    page_number=page_dict.get("page_number", 0),
                    section_title=page_dict.get("section_title", ""),
                    items=items,
                    confidence=float(page_dict.get("confidence", 0.0))
                ))
            
            return pages_data, final_short_name, period_current, period_previous
            
        except Exception as e:
            print(f"Lỗi trích xuất AI: {e}")
            return [], "Unknown Bank", "Current", "Previous"
    


# ==================== CUSTOM EXTRACTOR ====================
class CustomExtractor(GeminiExtractor):
    """Agent-based extractor cho yêu cầu tùy chỉnh"""
    
    def extract_report(
        self,
        pdf_path: Path,
        custom_request: str,
        page_range: Optional[tuple] = None,
        cache: ExtractionCache = None
    ) -> tuple: # Đã đổi type hint thành tuple vì trả về 4 biến
        """Trích xuất theo yêu cầu custom"""
        
        # Kiểm tra cache trước (Cập nhật trả về 4 biến nếu có cache)
        if cache:
            cached_result = cache.get(pdf_path, page_range, "custom", custom_request)
            if cached_result:
                print(f"✓ Lấy từ cache: {pdf_path.name}")
                # Lưu ý: Nếu dùng cache cũ chưa có tên cột, ta gán mặc định
                return cached_result, "Unknown Bank", "Current", "Previous"

        page_info = ""
        if page_range:
            page_info = f"Chỉ trích xuất từ trang {page_range[0] + 1} đến trang {page_range[1]}."
        
        prompt = f"""
Bạn là chuyên gia phân tích báo cáo tài chính.

**YÊU CẦU CỦA USER**: {custom_request}

{page_info}

**NHIỆM VỤ**: 
1. Xác định TÊN ĐẦY ĐỦ của Ngân hàng/Công ty từ nội dung PDF (trang bìa hoặc tiêu đề trang).
2. Trích xuất dữ liệu từ PDF theo yêu cầu.
3. Đọc chính xác TÊN CỘT THỜI GIAN thực tế trên báo cáo (ví dụ: "31/12/2023", "01/01/2023", "Năm nay", "Năm trước") để điền vào `period_current` và `period_previous`. Nếu không tìm thấy, để mặc định là "Current" và "Previous".

**QUY TẮC**:
- Trích xuất CHÍNH XÁC những gì được yêu cầu
- Giữ nguyên định dạng số (loại bỏ dấu chấm phân cách)
- Nếu không có dữ liệu → 0.0
- Phân trang rõ ràng

**OUTPUT JSON**:
{{
  "entity_name": "Tên ngân hàng viết hoa",
  "period_current": "Tên cột thời gian hiện tại (VD: 31/12/2023)",
  "period_previous": "Tên cột thời gian kỳ trước (VD: 01/01/2023)",
  "pages": [
    {{
      "page_number": 1,
      "section_title": "Tên section tìm thấy",
      "confidence": 0.95,
      "items": [
        {{
          "item_type": "main_item",
          "content": "Nội dung",
          "note_reference": "",
          "value_current": 0.0,
          "value_previous": 0.0,
          "indentation_level": 0
        }}
      ]
    }}
  ]
}}
"""
        
        try:
            print(f"Đang trích xuất custom từ {pdf_path.name}...")
            print(f"   Yêu cầu: {custom_request}")
            
            pdf_base64 = PDFHandler.pdf_to_base64(pdf_path)
            response = self._call_gemini_with_pdf(prompt, pdf_base64)
            result = self._parse_json_response(response)
            
            ai_entity_name = result.get("entity_name", "Unknown Bank")
            final_short_name = get_short_bank_name(ai_entity_name)
            
            period_current = result.get("period_current", "Current")
            period_previous = result.get("period_previous", "Previous")
            
            debug_path = Config.RESULTS_DIR / f"debug_custom_{pdf_path.stem}.json"
            with open(debug_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            pages_data = []
            for page_dict in result.get("pages", []):
                page_data = ReportPage(
                    page_number=page_dict.get("page_number", 0),
                    section_title=page_dict.get("section_title", ""),
                    items=[
                        FinancialItem(
                            item_type=item.get("item_type", "main_item"),
                            content=item.get("content", ""),
                            note_reference=item.get("note_reference", ""),
                            value_current=float(item.get("value_current", 0.0)) if item.get("value_current") else 0.0,
                            value_previous=float(item.get("value_previous", 0.0)) if item.get("value_previous") else 0.0,
                            indentation_level=int(item.get("indentation_level", 0))
                        )
                        for item in page_dict.get("items", [])
                    ],
                    confidence=float(page_dict.get("confidence", 0.0))
                )
                pages_data.append(page_data)
            
            print(f"Đã trích xuất {len(pages_data)} trang cho {final_short_name} (Kỳ: {period_current} vs {period_previous})")

            if cache:
                cache.set(pdf_path, page_range, "custom", pages_data, custom_request)
            
            # Trả về đủ 4 biến để FinancialExtractor hứng
            return pages_data, final_short_name, period_current, period_previous
            
        except Exception as e:
            print(f"Lỗi trích xuất: {e}")
            # Trả về 4 biến phòng hờ khi bị lỗi
            return [], "Unknown Bank", "Current", "Previous"

# ==================== MAIN FINANCIAL EXTRACTOR ====================

class FinancialExtractor:
    """Main extractor - Direct PDF Base64"""
    
    def __init__(self, api_key: str = None, model_name: str = None):
        """Khởi tạo"""
        self.api_key = api_key or Config.GEMINI_API_KEY
        self.model_name = model_name or Config.GEMINI_MODEL
        
        # Initialize sub-extractors
        self.detector = ReportTypeDetector(api_key, model_name)
        self.balance_sheet_extractor = BalanceSheetExtractor(api_key, model_name)
        self.income_statement_extractor = IncomeStatementExtractor(api_key, model_name)
        self.custom_extractor = CustomExtractor(api_key, model_name)
        
        # Initialize cache
        self.cache = ExtractionCache()
        
        print("Đã khởi tạo Financial Extractor (Direct PDF Base64)")

    def _refine_hierarchy(self, pages: List[ReportPage]) -> List[ReportPage]:
        """
        Xử lý lại phân cấp khi gặp các mục 'Bằng VND', 'Bằng ngoại tệ'
        """
        refined_pages = []
        for page in pages:
            new_items = []
            # Lấy tiêu đề section làm cha dự phòng
            current_section_title = page.section_title or "Chi tiết"
            
            for item in page.items:
                content_upper = item.content.upper()
                is_currency_split = "BẰNG VND" in content_upper or "BẰNG NGOẠI TỆ" in content_upper
                
                # Nếu main_item là dòng tiền tệ
                if item.item_type == "main_item" and is_currency_split:
                    # Tạo dòng cha mới lấy từ tên Section nếu dòng trước đó chưa phải là cha này
                    if not new_items or new_items[-1].content != current_section_title:
                        new_items.append(FinancialItem(
                            item_type="main_item",
                            content=current_section_title,
                            indentation_level=0
                        ))
                    
                    # Đẩy dòng "Bằng VND..." xuống làm con (level 1)
                    item.item_type = "sub_item"
                    item.indentation_level = 1
                    new_items.append(item)
                
                # Nếu dòng hiện tại là con của dòng tiền tệ vừa xử lý
                elif item.item_type == "sub_item" and new_items and \
                     ("BẰNG VND" in new_items[-1].content.upper() or "BẰNG NGOẠI TỆ" in new_items[-1].content.upper()):
                    item.indentation_level = 2 # Đẩy sâu vào level 2
                    new_items.append(item)
                
                else:
                    new_items.append(item)
            
            # Cập nhật lại items cho page
            page.items = new_items
            refined_pages.append(page)
            
        return refined_pages
    
    def extract_report(
        self,
        pdf_path: Path,
        report_type: Literal["auto", "balance_sheet", "income_statement", "cash_flow", "custom"] = "auto",
        custom_request: str = None,
        page_range: Optional[tuple] = None,
        use_cache: bool = True,
        clear_cache: bool = False,
        filter_empty_pages: bool = True,
        min_confidence: float = 0.4,
        min_items: int = 1
    ) -> FinancialExtraction:
        """
        Main extraction method
        """
        if clear_cache:
            self.cache.clear()
        
        print("\n" + "="*80)
        print("BẮT ĐẦU TRÍCH XUẤT BÁO CÁO TÀI CHÍNH")
        print("Mode: DIRECT PDF BASE64 (No rendering)")
        print("="*80)
        print(f"File: {pdf_path}")
        
        pdf_info = PDFHandler.get_pdf_info(pdf_path)
        print(f"Size: {pdf_info['file_size_mb']} MB")
        print(f"Estimated pages: {pdf_info['estimated_pages']}")
        print(f"Cache: {use_cache}")
        
        # Check file size limit (50 MB per Gemini docs)
        if pdf_info['file_size_mb'] > 50:
            print(f"WARNING: File > 50MB, may hit Gemini limits")
        
        # Auto-detect nếu cần
        if report_type == "auto":
            detection = self.detector.detect_report_type(pdf_path)
            report_type = detection["report_type"]
            
            if report_type == "unknown":
                print("Không thể tự động phát hiện loại báo cáo")
                print("Vui lòng chỉ định report_type thủ công")
                return FinancialExtraction(
                    document_title="",
                    report_type="unknown",
                    reporting_date="",
                    entity_name="",
                    pages=[]
                )
        
        print(f"\nLoại báo cáo: {report_type}")
        
        # Select appropriate extractor
        cache_to_use = self.cache if use_cache else None
        
        # ---------------------------------------------------------
        # ĐÃ SỬA LỖI: Hứng đúng 4 biến trả về và xóa đoạn gọi dư thừa
        # ---------------------------------------------------------
        if report_type == "balance_sheet":
            extracted_pages, final_short_name, p_curr, p_prev = self.balance_sheet_extractor.extract_report(
                pdf_path, page_range, cache_to_use
            )
        elif report_type == "income_statement":
            extracted_pages, final_short_name, p_curr, p_prev = self.income_statement_extractor.extract_report(
                pdf_path, page_range, cache_to_use
            )
        elif report_type == "custom":
            if not custom_request:
                raise ValueError("custom_request is required when report_type='custom'")
            extracted_pages, final_short_name, p_curr, p_prev = self.custom_extractor.extract_report(
                pdf_path, custom_request, page_range, cache_to_use
            )
        else:
            extracted_pages, final_short_name, p_curr, p_prev = self.balance_sheet_extractor.extract_report(
                pdf_path, page_range, cache_to_use
            )
        if extracted_pages:
            extracted_pages = self._refine_hierarchy(extracted_pages)
            
        if filter_empty_pages:
            original_count = len(extracted_pages)
            
            filtered_pages = []
            for page in extracted_pages:
                has_enough_items = len(page.items) >= min_items
                has_enough_confidence = page.confidence >= min_confidence
                has_section = bool(page.section_title.strip())
                
                if has_enough_items and (has_enough_confidence or has_section):
                    filtered_pages.append(page)
                else:
                    print(f"⊗ Bỏ qua trang {page.page_number}: "
                          f"items={len(page.items)}, "
                          f"confidence={page.confidence:.2f}")
            
            extracted_pages = filtered_pages
            print(f"\nFiltering: {original_count} trang → {len(filtered_pages)} trang có nội dung")
        
        final_bank_name = final_short_name
        if not final_bank_name or final_bank_name == "Tên ngân hàng viết hoa":
            final_bank_name = self._extract_entity_name(extracted_pages)
        
        if final_bank_name == "Unknown Bank":
            final_bank_name = pdf_path.stem.replace("_", " ").title()

        # ---------------------------------------------------------
        # ĐÃ SỬA LỖI: Truyền p_curr và p_prev vào object FinancialExtraction
        # ---------------------------------------------------------
        result = FinancialExtraction(
            document_title=self._extract_document_title(extracted_pages),
            report_type=report_type,
            reporting_date=self._extract_reporting_date(extracted_pages),
            entity_name=final_short_name if final_short_name != "Unknown Bank" else self._extract_entity_name(extracted_pages),
            period_current=p_curr,  # <-- Tên cột năm nay
            period_previous=p_prev, # <-- Tên cột năm trước
            pages=extracted_pages,
            metadata={
                "pdf_path": str(pdf_path),
                "extraction_date": datetime.now().isoformat(),
                "total_pages_processed": len(extracted_pages),
                "mode": "direct_pdf_base64",
                "pdf_size_mb": pdf_info['file_size_mb'],
                "filtering_enabled": filter_empty_pages,
                "min_confidence": min_confidence,
                "min_items": min_items
            }
        )
        
        print("\n" + "="*80)
        print("HOÀN THÀNH TRÍCH XUẤT")
        print("="*80)
        
        summary = result.get_summary()
        print(f"Tổng số trang: {summary['total_pages']}")
        print(f"Tổng số items: {summary['total_items']}")
        print(f"Độ tin cậy TB: {summary['avg_confidence']:.2%}")
        
        return result
    
    def _extract_document_title(self, pages: List[ReportPage]) -> str:
        """Trích xuất document title"""
        return "BÁO CÁO TÀI CHÍNH"
    
    def _extract_reporting_date(self, pages: List[ReportPage]) -> str:
        """Trích xuất reporting date"""
        return "31/12/2025"
    
    def _extract_entity_name(self, pages: List[ReportPage], pdf_path: Optional[Path] = None) -> str:
        search_keywords = ["NGÂN HÀNG", "NH TMCP", "BANK", "TỔ CHỨC TÍN DỤNG"]
        found_full_name = ""

        if pages:
            for page in pages[:2]:
                for item in page.items[:15]:
                    if any(kw in item.content.upper() for kw in search_keywords):
                        found_full_name = item.content.strip()
                        break
                if found_full_name: break

        if not found_full_name and pdf_path:
            found_full_name = pdf_path.stem.upper()
        
        if found_full_name:
            return get_short_bank_name(found_full_name)
            
        return "Unknown Bank"
