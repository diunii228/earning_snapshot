from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, TypedDict

logger = logging.getLogger(__name__)


class ResearchState(TypedDict):
    """State cho general research agent workflow (kiểu dict)."""

    # Core
    topic: str
    urls: List[str]
    keywords: List[str]

    # Web content
    articles: List[Dict]
    raw_content: str

    # LLM outputs
    analysis: str
    findings: List[str]
    summary: str
    validation: Dict[str, Any]

    # Control / meta
    errors: List[str]
    status: str
    max_urls: int


class BaseResearchAgent(ABC):
    """
    Base class/contract cho general research agent.

    Module `base` giờ chỉ chứa type & interface, không chứa implementation cụ thể.
    """

    @abstractmethod
    def expand_urls(self, state: ResearchState) -> ResearchState:
        """Node 1: Expand URLs and extract relevant links."""

    @abstractmethod
    def fetch_content(self, state: ResearchState) -> ResearchState:
        """Node 2: Fetch content from all URLs."""

    @abstractmethod
    def analyze_content(self, state: ResearchState) -> ResearchState:
        """Node 3: Analyze content with LLM."""

    @abstractmethod
    def summarize_findings(self, state: ResearchState) -> ResearchState:
        """Node 4: Summarize all findings."""

    @abstractmethod
    def validate_results(self, state: ResearchState) -> ResearchState:
        """Node 5: Validate extracted information."""


# Backwards compatibility re-export:
# Cho phép import cũ: from graph.research_agent.base import ResearchAgent
try:
    from graph.research_agent.agent import ResearchAgent  # type: ignore
except Exception:  # pragma: no cover
    ResearchAgent = None
