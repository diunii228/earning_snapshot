from typing import Optional

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from graph.research_agent.agent import ResearchAgent
from graph.research_agent.base import ResearchState
from utils.setting import LLMProvider


def build_research_graph(
    provider: Optional[LLMProvider] = None,
    model_name: Optional[str] = None,
    **llm_kwargs
) -> CompiledStateGraph:
    """
    Build the research agent workflow graph.
    
    Workflow:
        expand_urls -> fetch_content -> analyze -> summarize -> validate -> END
    
    Args:
        provider: LLM provider to use
        model_name: Specific model name
        **llm_kwargs: Additional LLM configuration
        
    Returns:
        Compiled LangGraph workflow
    """
    agent = ResearchAgent(
        provider=provider,
        model_name=model_name,
        **llm_kwargs
    )
    
    workflow = StateGraph(ResearchState)
    
    # Add nodes
    workflow.add_node("expand_urls", agent.expand_urls)
    workflow.add_node("fetch_content", agent.fetch_content)
    workflow.add_node("analyze", agent.analyze_content)
    workflow.add_node("summarize", agent.summarize_findings)
    workflow.add_node("validate", agent.validate_results)
    
    # Define edges
    workflow.set_entry_point("expand_urls")
    workflow.add_edge("expand_urls", "fetch_content")
    workflow.add_edge("fetch_content", "analyze")
    workflow.add_edge("analyze", "summarize")
    workflow.add_edge("summarize", "validate")
    workflow.add_edge("validate", END)
    
    return workflow.compile()


def research(
    topic: str,
    urls: list[str],
    keywords: list[str] = None,
    max_urls: int = 10,
    provider: Optional[LLMProvider] = None,
    **llm_kwargs
) -> ResearchState:
    """
    Run research on a topic.
    
    Args:
        topic: Research topic/question
        urls: Starting URLs to research
        keywords: Keywords to filter relevant content
        max_urls: Maximum URLs to process
        provider: LLM provider
        **llm_kwargs: Additional LLM options
        
    Returns:
        Final research state with findings
        
    Example:
        >>> result = research(
        ...     topic="AI trends 2024",
        ...     urls=["https://example.com/ai-news"],
        ...     keywords=["artificial intelligence", "machine learning"]
        ... )
        >>> print(result["summary"])
    """
    initial_state = ResearchState(
        topic=topic,
        urls=urls,
        keywords=keywords or [],
        articles=[],
        raw_content="",
        analysis="",
        findings=[],
        summary="",
        validation={},
        errors=[],
        status="pending",
        max_urls=max_urls,
    )
    
    graph = build_research_graph(provider=provider, **llm_kwargs)
    return graph.invoke(initial_state)
