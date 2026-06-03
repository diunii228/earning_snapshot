import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from models import get_llm
from utils.setting import LLMProvider
from graph.research_agent.prompts import (
    RESEARCH_SYSTEM_PROMPT,
    get_analysis_prompt,
    get_summarize_prompt,
    get_validate_prompt,
)
from graph.research_agent.utils import (
    fetch_url_content,
    extract_links,
    format_sources,
    parse_json_response,
)
from graph.research_agent.base import BaseResearchAgent, ResearchState


logger = logging.getLogger(__name__)


class ResearchAgent(BaseResearchAgent):
    """General-purpose research agent for web content analysis."""

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        **llm_kwargs: Any,
    ):
        self.llm = get_llm(
            provider=provider,
            model_name=model_name,
            temperature=temperature,
            **llm_kwargs,
        )
        self.provider = provider.value if provider else "default"
        logger.info("Initialized ResearchAgent with provider: %s", self.provider)

    def expand_urls(self, state: ResearchState) -> ResearchState:
        """Node 1: Expand URLs and extract relevant links."""
        logger.info("\nExpanding URLs for topic: %s", state["topic"])

        all_links: List[str] = []
        for url in state.get("urls", []):
            links = extract_links(
                url,
                keywords=state.get("keywords", []),
                max_links=state.get("max_urls", 10),
            )
            all_links.extend(links)

        unique_links = list(dict.fromkeys(all_links))[: state.get("max_urls", 10)]

        state["urls"] = unique_links
        state["status"] = "urls_expanded"
        logger.info("Found %d relevant URLs", len(unique_links))

        return state

    def fetch_content(self, state: ResearchState) -> ResearchState:
        """Node 2: Fetch content from all URLs."""
        logger.info("\nFetching content from URLs...")

        articles: List[Dict[str, Any]] = []
        for url in state.get("urls", []):
            result = fetch_url_content(url)
            if result["success"]:
                articles.append(result)
                logger.info("  Fetched: %s...", result["title"][:50])
            else:
                state["errors"].append(f"Failed to fetch: {url}")

        state["articles"] = articles
        state["raw_content"] = format_sources(articles)
        state["status"] = "content_fetched"

        logger.info("Successfully fetched %d articles", len(articles))
        return state

    def analyze_content(self, state: ResearchState) -> ResearchState:
        """Node 3: Analyze content with LLM."""
        logger.info("\nAnalyzing content for: %s", state["topic"])

        if not state.get("raw_content"):
            state["errors"].append("No content to analyze")
            state["status"] = "failed"
            return state

        prompt = get_analysis_prompt(
            topic=state["topic"],
            content=state["raw_content"][:30000],
        )

        try:
            messages = [
                SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]

            response = self.llm.invoke(messages)
            state["analysis"] = response.content
            state["findings"].append(response.content)
            state["status"] = "analyzed"

            logger.info("Analysis complete")

        except Exception as e:
            state["errors"].append(f"Analysis failed: {e}")
            state["status"] = "failed"
            logger.error("Analysis failed: %s", e)

        return state

    def summarize_findings(self, state: ResearchState) -> ResearchState:
        """Node 4: Summarize all findings."""
        logger.info("\nSummarizing findings...")

        if not state.get("findings"):
            state["errors"].append("No findings to summarize")
            return state

        findings_text = "\n\n---\n\n".join(state["findings"])
        prompt = get_summarize_prompt(
            topic=state["topic"],
            findings=findings_text,
        )

        try:
            messages = [
                SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]

            response = self.llm.invoke(messages)
            state["summary"] = response.content
            state["status"] = "summarized"

            logger.info("Summary complete")

        except Exception as e:
            state["errors"].append(f"Summarization failed: {e}")
            logger.error("Summarization failed: %s", e)

        return state

    def validate_results(self, state: ResearchState) -> ResearchState:
        """Node 5: Validate extracted information."""
        logger.info("\nValidating results...")

        prompt = get_validate_prompt(
            topic=state["topic"],
            data=state.get("analysis", state.get("summary", "")),
        )

        try:
            messages = [
                SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]

            response = self.llm.invoke(messages)
            validation = parse_json_response(response.content)

            state["validation"] = validation or {"raw_response": response.content}
            state["status"] = "validated"

            logger.info("Validation complete")

        except Exception as e:
            state["errors"].append(f"Validation failed: {e}")
            logger.error("Validation failed: %s", e)

        return state

