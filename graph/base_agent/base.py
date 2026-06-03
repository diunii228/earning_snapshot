from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from schemas.state import BankingResearchState


logger = logging.getLogger(__name__)


class BaseBankingAgent(ABC):
    """
    Base class cho tất cả banking research agents.

    Lớp này chỉ định nghĩa interface/contract, không chứa implementation cụ thể.
    Các agent cụ thể (ví dụ: BankingResearchAgent) sẽ kế thừa và implement.
    """

    @abstractmethod
    async def expand_category_links(
        self,
        state: BankingResearchState,
        max_links: int = 15,
    ) -> BankingResearchState:
        """Mở rộng và chọn lọc link nguồn theo ngân hàng/kỳ báo cáo."""

    @abstractmethod
    async def fetch_articles_content(
        self,
        state: BankingResearchState,
    ) -> BankingResearchState:
        """Lấy nội dung chi tiết từ các bài báo đã chọn."""

    @abstractmethod
    async def extract_banking_kpis(
        self,
        state: BankingResearchState,
    ) -> BankingResearchState:
        """Trích xuất KPI ngân hàng từ nội dung đã crawl."""

    @abstractmethod
    async def validate_banking_kpis(
        self,
        state: BankingResearchState,
    ) -> BankingResearchState:
        """Validate bộ KPI đã trích xuất."""