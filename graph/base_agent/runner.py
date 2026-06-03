import logging
import asyncio
from typing import List, Optional

from schemas.state import BankingResearchState
from graph.base_agent.graph_builder import build_banking_research_graph
from utils.setting import LLMProvider

logger = logging.getLogger(__name__)
async def research_bank_async(
    urls: List[str],
    bank_name: str,
    reporting_period: str = "Latest available",
    provider: Optional[LLMProvider] = None,
    model_name: Optional[str] = None,
    target_date: str = None,
    date_window_days: int = 1,
    shared_urls: Optional[List[str]] = None, \
    **llm_kwargs
) -> BankingResearchState:
    """
    Asynchronous runner for banking research.
    Required for parallel processing of multiple banks.
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"RESEARCHING BANK (ASYNC): {bank_name}")
    logger.info(f"URLS: {urls}")
    # Log để check xem nhận được bao nhiêu link chéo
    logger.info(f"Shared URLs received: {len(shared_urls) if shared_urls else 0}") 
    logger.info(f"Period: {reporting_period}")
    logger.info(f"{'='*80}")
    
    initial_state = BankingResearchState(
        urls=urls,
        bank_name=bank_name,
        reporting_period=reporting_period,
        target_date=target_date,
        date_window_days=date_window_days,
        shared_urls=shared_urls or [],  
        article_links=[],
        raw_content="",
        extracted_kpis={},
        validation_results={},
        errors=[],
        status='pending'
    )
    
    graph = build_banking_research_graph(
        provider=provider,
        model_name=model_name,
        max_tokens=8192,
        **llm_kwargs
    )
    
    try:
        final_state = await graph.ainvoke(initial_state)
    
        return {
            "extracted_kpis": final_state.get("extracted_kpis"),
            "validation_results": final_state.get("validation_results"),
            "article_links": final_state.get("article_links"),
            "has_new_data": final_state.get("has_new_data", False), 
            "kpi_count": final_state.get("kpi_count", 0)
        }
        
    except Exception as e:
        logger.error(f"Error executing graph for {bank_name}: {e}")
        initial_state["errors"].append(str(e))
        initial_state["status"] = "failed"
        return initial_state

def research_bank(
    urls: List[str],
    bank_name: str,
    reporting_period: str = "Latest available",
    provider: Optional[LLMProvider] = None,
    model_name: Optional[str] = None,
    **llm_kwargs
) -> BankingResearchState:
    """
    Synchronous wrapper for research_bank_async.
    Use this if you are running a simple script without asyncio loop.
    """
    return asyncio.run(research_bank_async(
        urls=urls,
        bank_name=bank_name,
        reporting_period=reporting_period,
        provider=provider,
        model_name=model_name,
        **llm_kwargs
    ))
