from pydantic import BaseModel, Field
from dataclasses import dataclass
from typing import Annotated, Dict, List, TypedDict, Any, Optional

def merge_errors(existing: List[str], new: List[str]) -> List[str]:
    if not existing: existing = []
    if not new: return existing
    if not isinstance(new, list): new = [str(new)]
    
    flat_new = []
    for item in new:
        if isinstance(item, list):
            flat_new.extend([str(i) for i in item])
        else:
            flat_new.append(str(item))
    return existing + flat_new

@dataclass
class BankingResearchState(TypedDict):
    # ── Input & Cấu hình ──
    urls: List[str]
    shared_urls: Optional[List[str]]  # Phục vụ Cross-Pollination (Hồ chứa chung)
    bank_name: str
    target_date: Optional[str] 
    date_window_days: Optional[int]
    reporting_period: str 
    
    # ── Dữ liệu cào được ──
    article_links: List[str]
    articles_data: List[Dict[str, Any]]
    raw_content: str
    
    # ── Kết quả LLM ──
    extracted_kpis: Dict[str, Any]
    kpi_count: Optional[int] 
    has_new_data: Optional[bool]
    validation_results: Dict[str, Any]
    
    # ── Vòng lặp Tự sửa sai (Self-Correction) ──
    validation_feedback: Optional[List[Dict[str, Any]]] # Gửi lỗi ngược lại cho Extract
    retry_count: Optional[int]                          # Đếm số lần đã thử lại
    
    # ── Quản lý Trạng thái ──
    errors: Annotated[List[str], merge_errors]
    status: str

class ResearchOutput(BaseModel):
    topic: str = Field(description="Research topic")
    summary: str = Field(description="Summary of findings")
    key_points: list[str] = Field(description="Key points discovered")
    confidence: float = Field(ge=0, le=1, description="Confidence score")

class AnalysisOutput(BaseModel):
    question: str = Field(description="The question being analyzed")
    answer: str = Field(description="The analysis answer")
    reasoning: str = Field(description="Step-by-step reasoning")
    sources: list[str] = Field(default_factory=list, description="Sources used")

class DecisionOutput(BaseModel):
    decision: str = Field(description="The decision made")
    action: str = Field(description="Next action to take")
    should_continue: bool = Field(default=True, description="Whether to continue")
