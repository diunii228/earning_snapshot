from langgraph.graph import StateGraph, END, START
from schemas.state import BankingResearchState
from graph.base_agent.banking_agent import BankingResearchAgent
from graph.base_agent.report_agent import BankingReporterAgent 
from utils.setting import LLMProvider
from utils.normalize import normalize_banking_kpis 
from typing import TypedDict, List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

def build_banking_research_graph(
    provider: Optional[LLMProvider] = None,
    model_name: Optional[str] = None,
    max_tokens=8192,
    **llm_kwargs
) -> StateGraph:
    agent = BankingResearchAgent(
        provider=provider,
        model_name=model_name,
        temperature=0,
        **llm_kwargs,
        max_tokens=max_tokens
    )
    workflow = StateGraph(BankingResearchState)
    
    workflow.add_node("expand_links", agent.expand_category_links)
    workflow.add_node("fetch_articles", agent.fetch_articles_content)
    workflow.add_node("extract_kpis", agent.extract_banking_kpis)
    
    async def normalize_node(state: BankingResearchState):
        if state.get("extracted_kpis") and state.get("status") not in ["failed", "error"]:
            logger.info(f"Graph Node: Normalizing KPIs for {state.get('bank_name')}...")
            state["extracted_kpis"] = normalize_banking_kpis(state["extracted_kpis"])
        return state

    workflow.add_node("normalize_kpis", normalize_node)
    workflow.add_node("validate_kpis", agent.validate_banking_kpis)

    def should_continue_after_links(state: BankingResearchState) -> str:
        if state.get("status") == "failed" or not state.get("article_links"):
            logger.warning(
                f"[expand_links → END] status={state.get('status')!r}, "
                f"article_links={len(state.get('article_links', []))}"
            )
            return END
        return "fetch_articles"

    def should_continue_after_fetch(state: BankingResearchState) -> str:
        if state.get("status") == "failed" or not state.get("raw_content"):
            logger.warning(
                f"[fetch_articles → END] status={state.get('status')!r}, "
                f"has_content={bool(state.get('raw_content'))}"
            )
            return END
        return "extract_kpis"

    def should_continue_after_extract(state: BankingResearchState) -> str:
        if state.get("status") == "failed" or state.get("kpi_count", 0) == 0:
            logger.warning(
                f"[extract_kpis → END] status={state.get('status')!r}, "
                f"kpi_count={state.get('kpi_count', 0)}"
            )
            return END
        return "normalize_kpis"

    def should_continue_after_validate(state: BankingResearchState) -> str:
        status = state.get("status")
        retry_count = state.get("retry_count", 0)

        if status == "needs_correction":
            if retry_count < 2:
                logger.info(f" VÒNG LẶP SỬA SAI (Lần {retry_count + 1}): Trả về Extract Agent để khắc phục!")
                return "extract_kpis" 
            else:
                logger.warning("Đã thử sửa sai 2 lần nhưng vẫn thất bại. Chấp nhận kết quả hiện tại và Dừng.")
                return END
                
        return END

    workflow.add_edge(START, "expand_links")
    
    workflow.add_conditional_edges("expand_links", should_continue_after_links)
    
    workflow.add_conditional_edges("fetch_articles", should_continue_after_fetch)
    
    workflow.add_conditional_edges("extract_kpis", should_continue_after_extract)
    
    workflow.add_conditional_edges("normalize_kpis", should_continue_after_validate)
    
    workflow.add_edge("validate_kpis", END)
    
    return workflow.compile()

class ReportState(TypedDict):
    subject_data: Dict
    peers_list: List[Dict]
    final_report: str
    errors: List[str]

def build_reporting_graph(model_name: Optional[str] = None) -> StateGraph:
    """
    Khởi tạo LangGraph cho quá trình tổng hợp báo cáo.
    Luồng này gồm 1 Node duy nhất bọc toàn bộ logic phức tạp của BankingReporterAgent.
    """
    logger.info("Khởi tạo Reporting Graph...")
    
    reporter = BankingReporterAgent(model_name=model_name)
    
    workflow = StateGraph(ReportState)
    
    async def write_report_node(state: ReportState):
        sub_data = state.get('subject_data', {})
        if isinstance(sub_data, list):
            sub_data = sub_data[0] if sub_data else {}

        bank_name = sub_data.get('bank_name', 'Unknown Bank')
        logger.info(f"Report Node: Đang tổng hợp báo cáo cho {bank_name}...")
        
        try:
            p_list = state.get("peers_list", [])
            if not isinstance(p_list, list):
                p_list = [p_list] if p_list else []

            report_md = await reporter.generate_overall_strategy(
                peers_list=p_list,
                subject_data=sub_data
            )
            return {"final_report": str(report_md)}
        except Exception as e:
            error_msg = str(e) 
            logger.error(f"Lỗi: {error_msg}")
            return {"errors": [error_msg], "final_report": ""}

    workflow.add_node("report_writer", write_report_node)
    
    workflow.add_edge(START, "report_writer")
    workflow.add_edge("report_writer", END)
    
    return workflow.compile()