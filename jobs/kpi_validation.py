"""
Post-extraction KPI validation and resolution.

Luồng:
- nhận merged_kpis sau khi đã merge web + PDF
- validate KPI có thể tính lại
- loại khỏi final snapshot nếu mismatch rõ ràng
- giữ validation summary để audit
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple
# Xóa _safe_float định nghĩa trong file
from jobs.fs_kpi_shared import safe_float as _safe_float

def _iter_kpis(extracted_kpis: Dict[str, Any]):
    for section_name, section in (extracted_kpis or {}).items():
        if not isinstance(section, dict):
            continue
        for kpi_name, details in section.items():
            if isinstance(details, dict):
                yield section_name, kpi_name, details


def _find_entry(extracted_kpis: Dict[str, Any], aliases: List[str]) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    for section_name, kpi_name, details in _iter_kpis(extracted_kpis):
        if kpi_name in aliases:
            return section_name, kpi_name, details
    return None, None, None


def _set_status(entry: Dict[str, Any], status: str, note: str = "", computed_value: Any = None) -> None:
    entry["validation_status"] = status
    if note:
        entry["validation_note"] = note
    if computed_value is not None:
        entry["computed_value"] = computed_value


def _remove_kpi(extracted_kpis: Dict[str, Any], section_name: str, kpi_name: str) -> None:
    if not section_name or not kpi_name:
        return
    section = extracted_kpis.get(section_name)
    if not isinstance(section, dict):
        return
    section.pop(kpi_name, None)

def _validate_growth_from_base(
    extracted_kpis: Dict[str, Any],
    summary: List[Dict[str, Any]],
    label: str,
    growth_aliases: List[str],
    base_aliases: List[str],
) -> None:
    growth_section, growth_key, growth_entry = _find_entry(extracted_kpis, growth_aliases)
    base_section, base_key, base_entry = _find_entry(extracted_kpis, base_aliases)

    if not growth_entry:
        summary.append({"kpi": label, "status": "missing", "note": "Reported growth KPI not found"})
        return

    growth_val = _safe_float(growth_entry.get("value"))
    base_val = _safe_float(base_entry.get("value")) if base_entry else None
    previous_val = _safe_float(base_entry.get("previous_value")) if base_entry else None

    if growth_val is None:
        _set_status(growth_entry, "invalid", "Reported growth KPI is not numeric")
        summary.append({"kpi": label, "status": "invalid", "note": "Reported growth KPI is not numeric"})
        _remove_kpi(extracted_kpis, growth_section, growth_key)
        return

    if base_val is None or previous_val in (None, 0):
        _set_status(growth_entry, "unverified", "Missing current/previous base value for recomputation")
        summary.append({"kpi": label, "status": "unverified", "note": "Missing current/previous base value"})
        return

    computed = ((base_val - previous_val) / abs(previous_val)) * 100
    tolerance = 0.2
    if abs(growth_val - computed) <= tolerance:
        _set_status(growth_entry, "validated", "Reported growth matches recomputed growth within tolerance", round(computed, 4))
        summary.append({"kpi": label, "status": "validated", "reported": growth_val, "computed": computed})
        return

    _set_status(growth_entry, "mismatch", "Reported growth does not match recomputed growth", round(computed, 4))
    summary.append({"kpi": label, "status": "mismatch", "reported": growth_val, "computed": computed})
    _remove_kpi(extracted_kpis, growth_section, growth_key)


def _validate_ratio_from_components(
    extracted_kpis: Dict[str, Any],
    summary: List[Dict[str, Any]],
    label: str,
    ratio_aliases: List[str],
    numerator_aliases: List[str],
    denominator_aliases: List[str],
    tolerance: float,
) -> None:
    ratio_section, ratio_key, ratio_entry = _find_entry(extracted_kpis, ratio_aliases)
    numerator_section, numerator_key, numerator_entry = _find_entry(extracted_kpis, numerator_aliases)
    denominator_section, denominator_key, denominator_entry = _find_entry(extracted_kpis, denominator_aliases)

    if not ratio_entry:
        summary.append({"kpi": label, "status": "missing", "note": "Reported ratio KPI not found"})
        return

    ratio_val = _safe_float(ratio_entry.get("value"))
    numerator_val = _safe_float(numerator_entry.get("value")) if numerator_entry else None
    denominator_val = _safe_float(denominator_entry.get("value")) if denominator_entry else None

    if ratio_val is None:
        _set_status(ratio_entry, "invalid", "Reported ratio KPI is not numeric")
        summary.append({"kpi": label, "status": "invalid", "note": "Reported ratio KPI is not numeric"})
        _remove_kpi(extracted_kpis, ratio_section, ratio_key)
        return

    if numerator_val is None or denominator_val in (None, 0):
        _set_status(ratio_entry, "unverified", "Missing numerator/denominator for recomputation")
        summary.append({"kpi": label, "status": "unverified", "note": "Missing numerator/denominator"})
        return

    computed = (numerator_val / denominator_val) * 100
    if abs(ratio_val - computed) <= tolerance:
        _set_status(ratio_entry, "validated", "Reported ratio matches recomputed ratio within tolerance", round(computed, 4))
        summary.append({"kpi": label, "status": "validated", "reported": ratio_val, "computed": computed})
        return

    _set_status(ratio_entry, "mismatch", "Reported ratio does not match recomputed ratio", round(computed, 4))
    summary.append({"kpi": label, "status": "mismatch", "reported": ratio_val, "computed": computed})
    _remove_kpi(extracted_kpis, ratio_section, ratio_key)


def validate_and_resolve_kpis(merged_kpis: Dict[str, Any]) -> Dict[str, Any]:
    final_kpis = copy.deepcopy(merged_kpis or {})
    summary: List[Dict[str, Any]] = []

    _validate_growth_from_base(
        final_kpis,
        summary,
        label="Deposit growth",
        growth_aliases=["deposit_growth_yoy", "deposit_growth_ytd", "deposit_growth_qoq"],
        base_aliases=["total_deposits"],
    )
    _validate_growth_from_base(
        final_kpis,
        summary,
        label="Lending growth",
        growth_aliases=["credit_growth_yoy", "credit_growth_ytd", "credit_growth_qoq"],
        base_aliases=["total_credit"],
    )
    _validate_ratio_from_components(
        final_kpis,
        summary,
        label="CASA",
        ratio_aliases=["casa_ratio"],
        numerator_aliases=[
            "non_term_deposits",
            "demand_deposits",
            "current_account_deposits",
            "demand_and_casa_deposits",
        ],
        denominator_aliases=["total_deposits"],
        tolerance=0.3,
    )
    _validate_ratio_from_components(
        final_kpis,
        summary,
        label="NIM",
        ratio_aliases=["nim"],
        numerator_aliases=["net_interest_income", "nii"],
        denominator_aliases=[
            "average_earning_assets",
            "interest_earning_assets_average",
            "earning_assets_average",
            "avg_interest_earning_assets",
        ],
        tolerance=0.2,
    )

    validated = sum(1 for item in summary if item["status"] == "validated")
    unverified = sum(1 for item in summary if item["status"] == "unverified")
    mismatches = sum(1 for item in summary if item["status"] == "mismatch")
    invalid = sum(1 for item in summary if item["status"] == "invalid")

    return {
        "final_kpis": final_kpis,
        "validation_results": {
            "kpi_validation": summary,
            "validated_count": validated,
            "unverified_count": unverified,
            "mismatch_count": mismatches,
            "invalid_count": invalid,
        },
    }
