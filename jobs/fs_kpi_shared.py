"""
Shared pure helpers — không import gì ngoài stdlib.
Import bởi: financial_statement_ingest, fs_kpi_compute, kpi_validation.
"""
from __future__ import annotations
from typing import Any, Optional


def safe_float(value: Any) -> Optional[float]:
    """Canonical _safe_float dùng chung toàn bộ jobs/."""
    if value in (None, "", "-", "N/A", "null"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def compute_casa_ratio_value(
    a: Optional[float],
    b: Optional[float],
    c: Optional[float],
    d: Optional[float],
) -> Optional[float]:
    """
    Trả về CASA ratio (%) hoặc None nếu thiếu dữ liệu bắt buộc.
    Không build KPI dict — caller tự wrap.
    """
    if a is None or d in (None, 0):
        return None
    return ((a + (b or 0.0) + (c or 0.0)) / d) * 100


def compute_growth_pct(
    current: Optional[float],
    previous: Optional[float],
) -> Optional[float]:
    """(current / previous − 1) × 100. None nếu previous là None hoặc 0."""
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100