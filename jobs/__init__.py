"""
jobs package

Không import các module nặng (db/asyncpg, LLM clients, ...) ở import-time để tránh
crash khi chỉ cần dùng một job nhỏ (ví dụ manual ingest utilities).
"""

from __future__ import annotations

from typing import Any

__all__ = ["run_daily_crawl", "run_report_from_db"]


def __getattr__(name: str) -> Any:
    if name == "run_daily_crawl":
        from jobs.daily_crawl_v1 import run_daily_crawl

        return run_daily_crawl
    if name == "run_report_from_db":
        from jobs.report_from_db import run_report_from_db

        return run_report_from_db
    raise AttributeError(name)
