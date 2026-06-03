"""
Compute final KPI snapshot from raw financial-statement components stored in DB.

Mục tiêu:
- Snapshot KPI (9 KPI) được dựng lại từ bảng bank_fs_components
- Giảm phụ thuộc vào output extract trực tiếp (extract chỉ chịu trách nhiệm "lấy raw fields")

Changelog:
- Thêm casa_growth_ytd (từ casa_ratio_d current/previous)
- Thêm cir (|opex| / toi × 100)
- Relaxed NIM LTM: cho phép một số earning asset components bằng 0 thay vì None
- Thêm pbt_growth, toi_growth, nii_growth (YoY: kỳ này / cùng kỳ năm trước − 1)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from jobs.fs_kpi_shared import safe_float as _safe_float
logger = logging.getLogger(__name__)

def _kpi_from_component(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "value": row.get("value_current"),
        "unit": row.get("unit"),
        "source_url": row.get("source_url"),
        "source_type": row.get("source_type"),
        "source_quote": row.get("source_quote"),
        "reasoning": row.get("reasoning") or "Derived from bank_fs_components",
        "previous_value": row.get("value_previous"),
        "period_current_label": row.get("period_current_label"),
        "period_previous_label": row.get("period_previous_label"),
        "validation_status": "reported_only",
    }


def _compute_growth_from_total(
    total_row: Dict[str, Any], label: str, growth_label: str = "YTD"
) -> Optional[Dict[str, Any]]:
    """
    Generic growth = (current / previous − 1) × 100.
    growth_label: "YTD" cho balance-sheet items, "YoY" cho P&L items.

    Keep wording consistent with jobs/financial_statement_ingest.py::_compute_growth.
    """
    current = _safe_float(total_row.get("value_current"))
    previous = _safe_float(total_row.get("value_previous"))
    if current is None or previous in (None, 0):
        return None
    growth = (current / previous - 1) * 100
    source_url = total_row.get("source_url")
    source_type = total_row.get("source_type")
    return {
        "value": round(growth, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": source_type,
        "source_quote": (
            f"Computed from {label}: current={current:,.0f}, previous={previous:,.0f}"
        ),
        "reasoning": (
            f"{label} growth ({growth_label}) = (current / previous − 1) × 100 "
            f"= ({current:,.0f} / {previous:,.0f} − 1) × 100 = {growth:.4f}%"
        ),
        "components": {"current": current, "previous": previous},
        "validation_status": "computed_from_components",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  📈  P&L YoY GROWTH HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _compute_yoy_growth_from_component(
    components: Dict[str, Dict[str, Any]],
    component_key: str,
    label: str,
) -> Optional[Dict[str, Any]]:
    """
    Tính YoY growth cho P&L KPI (pbt, total_operating_income, net_interest_income).

    growth (%) = (value_current / value_previous − 1) × 100

    Trong đó:
    - value_current  = kết quả kỳ này (Q1 20xx)
    - value_previous = kết quả cùng kỳ năm trước (Q1 20xx-1) — cột bên phải trong P&L

    Trả về None nếu:
    - Component không tồn tại trong DB
    - value_current hoặc value_previous là None
    - value_previous = 0 (likely unfilled sentinel từ extractor)
    """
    row = components.get(component_key)
    if not isinstance(row, dict):
        logger.debug(
            "[fs_kpi_compute] %s_growth YoY: thiếu component '%s'",
            label.lower(), component_key,
        )
        return None

    result = _compute_growth_from_total(row, label, growth_label="YoY")
    if result is None:
        logger.debug(
            "[fs_kpi_compute] %s_growth YoY: không compute được "
            "(value_current=%s, value_previous=%s)",
            label.lower(),
            row.get("value_current"),
            row.get("value_previous"),
        )
    return result


def _compute_casa_ratio(components: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    CASA ratio (%) = (a + b + c) / d × 100
    Keep reasoning/components keys consistent with jobs/financial_statement_ingest.py::_compute_casa_ratio.
    """
    a_row = components.get("casa_ratio_a") or {}
    b_row = components.get("casa_ratio_b") or {}
    c_row = components.get("casa_ratio_c") or {}
    d_row = components.get("casa_ratio_d") or {}

    val_a = _safe_float(a_row.get("value_current"))
    val_b = _safe_float(b_row.get("value_current"))
    val_c = _safe_float(c_row.get("value_current"))
    val_d = _safe_float(d_row.get("value_current"))

    missing_required: List[str] = []
    if val_a is None:
        missing_required.append("casa_ratio_a (tiền gửi không kỳ hạn)")
    if val_d is None:
        missing_required.append("casa_ratio_d (tổng tiền gửi khách hàng)")
    if missing_required:
        logger.debug(
            "[fs_kpi_compute] casa_ratio: thiếu required components: %s",
            ", ".join(missing_required),
        )
        return None
    if val_d == 0:
        logger.debug("[fs_kpi_compute] casa_ratio: denominator (casa_ratio_d) = 0")
        return None

    missing_optional: List[str] = []
    if val_b is None:
        missing_optional.append("casa_ratio_b (tiền gửi ký quỹ) → used 0")
        val_b = 0.0
    if val_c is None:
        missing_optional.append("casa_ratio_c (tiền gửi mục đích riêng) → used 0")
        val_c = 0.0

    numerator = val_a + val_b + val_c
    casa_ratio = (numerator / val_d) * 100

    formula_parts = [
        f"a (không kỳ hạn)  = {val_a:,.0f}",
        f"b (ký quỹ)         = {val_b:,.0f}",
        f"c (mục đích riêng) = {val_c:,.0f}",
        f"d (tổng tiền gửi)  = {val_d:,.0f}",
        (
            f"CASA = (a + b + c) / d × 100 "
            f"= ({val_a:,.0f} + {val_b:,.0f} + {val_c:,.0f}) / {val_d:,.0f} × 100 "
            f"= {casa_ratio:.4f}%"
        ),
    ]
    if missing_optional:
        formula_parts.append(
            "Note — optional components defaulted to 0: " + "; ".join(missing_optional)
        )

    source_url = a_row.get("source_url") or d_row.get("source_url")
    source_type = a_row.get("source_type") or d_row.get("source_type")

    return {
        "value": round(casa_ratio, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": source_type,
        "source_quote": (
            f"Computed from extracted components: a={val_a}, b={val_b}, c={val_c}, d={val_d}"
        ),
        "reasoning": " | ".join(formula_parts),
        "components": {
            "a_demand_deposits": val_a,
            "b_margin_deposits": val_b,
            "c_earmarked_deposits": val_c,
            "d_total_deposits": val_d,
            "numerator": numerator,
        },
        "validation_status": "computed_from_components",
    }


def _compute_casa_growth_ytd(
    components: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    CASA growth YTD = (sum_cur / sum_prev − 1) × 100

    sum_cur  = a_cur  + b_cur  + c_cur
    sum_prev = a_prev + b_prev + c_prev

    Keep logic consistent with jobs/financial_statement_ingest.py::_compute_casa_growth_ytd.
    """
    def _get(key: str, field: str) -> Optional[float]:
        return _safe_float((components.get(key) or {}).get(field))

    a_cur = _get("casa_ratio_a", "value_current")
    a_prev = _get("casa_ratio_a", "value_previous")
    if any(v is None for v in (a_cur, a_prev)):
        logger.debug(
            "[fs_kpi_compute] casa_growth_ytd: thiếu a (a_cur=%s, a_prev=%s)",
            a_cur,
            a_prev,
        )
        return None

    b_cur = _get("casa_ratio_b", "value_current") or 0.0
    c_cur = _get("casa_ratio_c", "value_current") or 0.0
    b_prev = _get("casa_ratio_b", "value_previous") or 0.0
    c_prev = _get("casa_ratio_c", "value_previous") or 0.0

    sum_cur = a_cur + b_cur + c_cur
    sum_prev = a_prev + b_prev + c_prev
    if sum_prev == 0:
        logger.debug("[fs_kpi_compute] casa_growth_ytd: sum_prev = 0, bỏ qua")
        return None

    growth = (sum_cur / sum_prev - 1) * 100

    a_row = components.get("casa_ratio_a") or {}
    source_url = a_row.get("source_url")
    source_type = a_row.get("source_type")

    return {
        "value": round(growth, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": source_type,
        "source_quote": (
            "CASA growth YTD = (sum_cur / sum_prev − 1) × 100 "
            f"= ({sum_cur:,.0f} / {sum_prev:,.0f} − 1) × 100"
        ),
        "reasoning": (
            f"sum_cur  = {a_cur:,.0f} + {b_cur:,.0f} + {c_cur:,.0f} = {sum_cur:,.0f}\n"
            f"sum_prev = {a_prev:,.0f} + {b_prev:,.0f} + {c_prev:,.0f} = {sum_prev:,.0f}\n"
            f"CASA growth YTD = ({sum_cur:,.0f} / {sum_prev:,.0f} − 1) × 100 = {growth:.4f}%"
        ),
        "components": {
            "a_cur": a_cur,
            "b_cur": b_cur,
            "c_cur": c_cur,
            "a_prev": a_prev,
            "b_prev": b_prev,
            "c_prev": c_prev,
            "sum_cur": round(sum_cur, 4),
            "sum_prev": round(sum_prev, 4),
        },
        "validation_status": "computed_from_components",
    }


def _compute_cir(
    components: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    CIR (%) = |OPEX| / TOI × 100
    OPEX thường âm trong BCTC → lấy giá trị tuyệt đối.
    """
    opex_row = components.get("opex")
    toi_row  = components.get("total_operating_income")

    if not isinstance(opex_row, dict):
        logger.debug("[fs_kpi_compute] cir: thiếu opex")
        return None
    if not isinstance(toi_row, dict):
        logger.debug("[fs_kpi_compute] cir: thiếu total_operating_income")
        return None

    opex_val = _safe_float(opex_row.get("value_current"))
    toi_val  = _safe_float(toi_row.get("value_current"))

    if opex_val is None:
        logger.debug("[fs_kpi_compute] cir: opex value_current là None")
        return None
    if toi_val in (None, 0):
        logger.debug("[fs_kpi_compute] cir: toi value_current là %s", toi_val)
        return None

    opex_abs = abs(opex_val)
    cir = opex_abs / toi_val * 100

    source_url  = opex_row.get("source_url") or toi_row.get("source_url")
    source_type = opex_row.get("source_type") or toi_row.get("source_type")

    return {
        "value": round(cir, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": source_type,
        "source_quote": (
            f"Computed: CIR = |OPEX| / TOI × 100 "
            f"= |{opex_val:,.0f}| / {toi_val:,.0f} × 100"
        ),
        "reasoning": (
            f"CIR = |OPEX| / TOI × 100 "
            f"= |{opex_val:,.0f}| / {toi_val:,.0f} × 100 = {cir:.4f}%"
        ),
        "components": {
            "opex_raw": opex_val,
            "opex_abs": opex_abs,
            "toi": toi_val,
        },
        "validation_status": "computed_from_components",
    }


def _resolve_total_credit(
    components: Dict[str, Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Returns:
    - total_credit_kpi_detail for snapshot
    - a "total_row" dict with value_current/value_previous for computing growth
    """
    reported = components.get("total_credit_reported")
    if reported and _safe_float(reported.get("value_current")) is not None:
        kpi = _kpi_from_component(reported)
        # Ensure wording consistent with PDF ingest.
        kpi["reasoning"] = "Reported directly in financial statement (Total credit / Tổng dư nợ tín dụng)."
        kpi["validation_status"] = "reported_only"
        return kpi, reported

    parts = [
        ("credit_customer_loans", "customer_loans"),
        ("credit_domestic_bonds_trading", "domestic_bonds_trading"),
        ("credit_domestic_bonds_afs", "domestic_bonds_afs"),
        ("credit_domestic_bonds_htm", "domestic_bonds_htm"),
    ]
    current_sum = 0.0
    previous_sum = 0.0
    any_current = False
    all_previous_present = True
    unit = None
    src_url = None
    src_type = None
    used = {}

    for key, label in parts:
        row = components.get(key) or {}
        cur = _safe_float(row.get("value_current"))
        prev = _safe_float(row.get("value_previous"))
        if cur is None:
            continue
        any_current = True
        current_sum += cur
        if prev is None:
            all_previous_present = False
        else:
            previous_sum += prev
        used[label] = {"current": cur, "previous": prev}
        unit = unit or row.get("unit")
        src_url = src_url or row.get("source_url")
        src_type = src_type or row.get("source_type")

    if not any_current:
        return None, None

    total_row = {
        "value_current": current_sum,
        "value_previous": previous_sum if all_previous_present else None,
        "unit": unit,
        "source_url": src_url,
        "source_type": src_type,
        "period_current_label": (components.get("credit_customer_loans") or {}).get("period_current_label"),
        "period_previous_label": (components.get("credit_customer_loans") or {}).get("period_previous_label"),
    }
    kpi = {
        "value": round(current_sum, 4),
        "unit": unit,
        "source_url": src_url,
        "source_type": src_type,
        "source_quote": "Computed from balance-sheet components (saved in components table).",
        "reasoning": (
            "Computed Total Credit = customer_loans + domestic bonds (trading/AFS/HTM)"
            f" = {current_sum:,.0f}"
            + (
                f" | previous_total_credit={total_row['value_previous']:,.0f}"
                if total_row["value_previous"] is not None
                else ""
            )
        ),
        "previous_value": total_row["value_previous"],
        "components": used,
        "validation_status": "computed_from_components",
    }
    return kpi, total_row


def build_daily_earning_kpis_from_components(
    components: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Output structure matches extracted_kpis schema used by snapshot/email:

    profitability:
        pbt, total_operating_income, net_interest_income, opex
        pbt_growth, toi_growth, nii_growth        ← YoY growth mới thêm
    profitability_ratios:
        nim, cir
    other_metrics:
        casa_ratio, casa_growth_ytd
    lending_deposit:
        total_deposits, deposit_growth_ytd, total_credit, credit_growth_ytd
    """
    out: Dict[str, Any] = {
        "profitability": {},
        "profitability_ratios": {},
        "other_metrics": {},
        "lending_deposit": {},
    }

    # ── Direct P&L KPIs ──────────────────────────────────────────────────────
    if components.get("pbt"):
        out["profitability"]["pbt"] = _kpi_from_component(components["pbt"])
    if components.get("total_operating_income"):
        out["profitability"]["total_operating_income"] = _kpi_from_component(
            components["total_operating_income"]
        )
    if components.get("net_interest_income"):
        out["profitability"]["net_interest_income"] = _kpi_from_component(
            components["net_interest_income"]
        )
    if components.get("opex"):
        # Expose OPEX in snapshot so email can display it (still used for CIR compute).
        out["profitability"]["opex"] = _kpi_from_component(components["opex"])

    # ── P&L YoY growth: pbt_growth, toi_growth, nii_growth ──────────────────
    # growth (%) = (value_current / value_previous − 1) × 100
    # value_previous = cùng kỳ năm trước (cột bên phải trong P&L BCTC)
    # Ưu tiên dùng reported growth nếu đã được extract, fallback compute từ components.
    _pl_growth_specs = [
        ("pbt",                   "pbt_growth",  "PBT"),
        ("total_operating_income","toi_growth",  "TOI"),
        ("net_interest_income",   "nii_growth",  "NII"),
    ]
    for _comp_key, _growth_key, _label in _pl_growth_specs:
        if components.get(_growth_key):
            # Đã được extract/compute trước và lưu vào DB → dùng trực tiếp
            out["profitability"][_growth_key] = _kpi_from_component(components[_growth_key])
            logger.debug(
                "[fs_kpi_compute] %s loaded from DB component.", _growth_key
            )
        else:
            # Compute từ value_current / value_previous của KPI gốc
            growth = _compute_yoy_growth_from_component(components, _comp_key, _label)
            if growth is not None:
                out["profitability"][_growth_key] = growth
                logger.info(
                    "[fs_kpi_compute] ✅ %s (YoY) computed: %.4f%% "
                    "(current=%.0f, previous=%.0f)",
                    _growth_key,
                    growth["value"],
                    growth["components"]["current"],
                    growth["components"]["previous"],
                )
            else:
                logger.warning(
                    "[fs_kpi_compute] ⚠️  %s (YoY) could not be computed — "
                    "check that value_previous is stored for '%s' in bank_fs_components "
                    "(extractor must return cùng kỳ năm trước column).",
                    _growth_key, _comp_key,
                )

    # ── NIM ──────────────────────────────────────────────────────────────────
    if components.get("nim"):
        out["profitability_ratios"]["nim"] = _kpi_from_component(components["nim"])

    # ── CIR ──────────────────────────────────────────────────────────────────
    if components.get("cir"):
        out["profitability_ratios"]["cir"] = _kpi_from_component(components["cir"])
    else:
        cir = _compute_cir(components)
        if cir is not None:
            out["profitability_ratios"]["cir"] = cir
            logger.info(
                "[fs_kpi_compute] ✅ CIR computed: %.4f%% (opex=%.0f, toi=%.0f)",
                cir["value"],
                cir["components"]["opex_abs"],
                cir["components"]["toi"],
            )
        else:
            logger.warning(
                "[fs_kpi_compute] ⚠️  CIR could not be computed — "
                "check opex and total_operating_income in bank_fs_components."
            )

    # ── CASA ratio ───────────────────────────────────────────────────────────
    if components.get("casa_ratio"):
        out["other_metrics"]["casa_ratio"] = _kpi_from_component(components["casa_ratio"])
    else:
        casa = _compute_casa_ratio(components)
        if casa is not None:
            out["other_metrics"]["casa_ratio"] = casa
            logger.info(
                "[fs_kpi_compute] ✅ CASA ratio computed: %.4f%%", casa["value"]
            )
        else:
            logger.warning(
                "[fs_kpi_compute] ⚠️  CASA ratio could not be computed — "
                "check casa_ratio_a/d in bank_fs_components."
            )

    # ── CASA growth YTD ──────────────────────────────────────────────────────
    if components.get("casa_growth_ytd"):
        out["other_metrics"]["casa_growth_ytd"] = _kpi_from_component(
            components["casa_growth_ytd"]
        )
    else:
        casa_growth = _compute_casa_growth_ytd(components)
        if casa_growth is not None:
            out["other_metrics"]["casa_growth_ytd"] = casa_growth
            logger.info(
                "[fs_kpi_compute] ✅ CASA growth (YTD) computed: %.4f%%",
                casa_growth["value"],
            )
        else:
            logger.warning(
                "[fs_kpi_compute] ⚠️  CASA growth (YTD) could not be computed — "
                "check casa_ratio_d value_previous in bank_fs_components."
            )

    # ── Deposits + growth ────────────────────────────────────────────────────
    total_deposits_row = components.get("total_deposits")
    if total_deposits_row:
        out["lending_deposit"]["total_deposits"] = _kpi_from_component(total_deposits_row)
        if components.get("deposit_growth_ytd"):
            out["lending_deposit"]["deposit_growth_ytd"] = _kpi_from_component(
                components["deposit_growth_ytd"]
            )
        else:
            growth = _compute_growth_from_total(
                total_deposits_row, "Total Deposits", growth_label="YTD"
            )
            if growth is not None:
                out["lending_deposit"]["deposit_growth_ytd"] = growth
                logger.info(
                    "[fs_kpi_compute] ✅ Deposit growth (YTD) computed: %.4f%%",
                    growth["value"],
                )
            else:
                logger.warning(
                    "[fs_kpi_compute] ⚠️  Deposit growth (YTD) could not be computed — "
                    "check total_deposits value_previous in bank_fs_components."
                )

    # ── Credit + growth ──────────────────────────────────────────────────────
    total_credit_kpi, total_credit_row = _resolve_total_credit(components)
    if total_credit_kpi is not None:
        out["lending_deposit"]["total_credit"] = total_credit_kpi
        if components.get("credit_growth_ytd"):
            out["lending_deposit"]["credit_growth_ytd"] = _kpi_from_component(
                components["credit_growth_ytd"]
            )
        elif total_credit_row:
            growth = _compute_growth_from_total(
                total_credit_row, "Total Credit", growth_label="YTD"
            )
            if growth is not None:
                out["lending_deposit"]["credit_growth_ytd"] = growth
                logger.info(
                    "[fs_kpi_compute] ✅ Credit growth (YTD) computed: %.4f%%",
                    growth["value"],
                )
            else:
                logger.warning(
                    "[fs_kpi_compute] ⚠️  Credit growth (YTD) could not be computed — "
                    "check total_credit value_previous in bank_fs_components."
                )

    # Cleanup empty sections
    return {k: v for k, v in out.items() if isinstance(v, dict) and v}


# ─────────────────────────────────────────────────────────────────────────────
#  📈  NIM LTM  (relaxed: missing earning asset component → treat as 0)
# ─────────────────────────────────────────────────────────────────────────────

_EARNING_ASSET_OPTIONAL = {
    "earning_assets_sbv_deposits",
    "earning_assets_interbank_assets",
    "earning_assets_debt_securities_htm",
}

_EARNING_ASSET_REQUIRED = {
    "earning_assets_customer_loans",
    "earning_assets_debt_securities_afs",
}


def compute_nim_ltm_from_history(
    history_quarters: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    NIM (LTM) = Sum(NII last 4Q) / Avg(Total Earning Assets last 5Q) × 100

    Relaxed: optional earning asset components (sbv_deposits, interbank, htm)
    → None treated as 0 instead of aborting.
    """
    if not history_quarters or len(history_quarters) < 5:
        logger.debug(
            "[fs_kpi_compute] NIM LTM: không đủ lịch sử (%d/5 quý)",
            len(history_quarters) if history_quarters else 0,
        )
        return None

    last4 = history_quarters[:4]
    last5 = history_quarters[:5]

    earning_keys = list(_EARNING_ASSET_REQUIRED) + list(_EARNING_ASSET_OPTIONAL)

    # ── NII: 4 quý gần nhất ──────────────────────────────────────────────────
    nii_vals = []
    for i, q in enumerate(last4):
        comps = q.get("components") or {}
        row = comps.get("net_interest_income")
        val = _safe_float((row or {}).get("value_current"))
        if val is None:
            logger.debug(
                "[fs_kpi_compute] NIM LTM: thiếu net_interest_income tại quý %d", i
            )
            return None
        nii_vals.append(val)

    # ── Earning assets: 5 quý gần nhất ───────────────────────────────────────
    totals = []
    for i, q in enumerate(last5):
        comps = q.get("components") or {}
        quarter_total = 0.0
        missing_required = []

        for k in earning_keys:
            row = comps.get(k)
            v = _safe_float((row or {}).get("value_current"))

            if v is None:
                if k in _EARNING_ASSET_REQUIRED:
                    missing_required.append(k)
                else:
                    logger.debug(
                        "[fs_kpi_compute] NIM LTM quý %d: %s = None → dùng 0 (optional component)",
                        i, k,
                    )
                    v = 0.0
            quarter_total += v

        if missing_required:
            logger.debug(
                "[fs_kpi_compute] NIM LTM: thiếu required components tại quý %d: %s",
                i, missing_required,
            )
            return None

        totals.append(quarter_total)

    sum_nii    = sum(nii_vals)
    avg_assets = sum(totals) / 5.0
    if avg_assets == 0:
        logger.debug("[fs_kpi_compute] NIM LTM: avg_earning_assets = 0, bỏ qua.")
        return None

    nim = (sum_nii / avg_assets) * 100

    newest_comps = (history_quarters[0] or {}).get("components") or {}
    src_row      = newest_comps.get("net_interest_income") or {}
    source_url   = src_row.get("source_url")
    source_type  = src_row.get("source_type")

    reasoning = (
        f"NIM (LTM) = Sum(NII last 4Q) / Avg(Total earning assets last 5Q) × 100 "
        f"= {sum_nii:,.0f} / {avg_assets:,.0f} × 100 = {nim:.4f}%"
    )

    return {
        "value": round(nim, 4),
        "unit": "%",
        "source_url": source_url,
        "source_type": source_type or "financial_statement_pdf",
        "source_quote": (
            "Computed NIM (LTM) from bank_fs_components history "
            "(NII + earning assets, optional components default to 0)."
        ),
        "reasoning": reasoning,
        "components": {
            "nii_last4q":                  [round(x, 4) for x in nii_vals],
            "earning_assets_last5q_total": [round(x, 4) for x in totals],
            "sum_nii_last4q":              round(sum_nii, 4),
            "avg_earning_assets_last5q":   round(avg_assets, 4),
        },
        "validation_status": "computed_from_components",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  🔗  BRIDGE: fs_components → bank_kpi_snapshots
# ─────────────────────────────────────────────────────────────────────────────

NIM_COMPONENT_KEYS = [
    "net_interest_income",
    "earning_assets_customer_loans",
    "earning_assets_debt_securities_afs",
    "earning_assets_sbv_deposits",
    "earning_assets_interbank_assets",
    "earning_assets_debt_securities_htm",
]

async def sync_fs_components_to_snapshot(
    repo,
    bank_name: str,
    reporting_period: str,
    reporting_year: int,
    reporting_quarter: int,
    run_id: Optional[int] = None,
    ticker: Optional[str] = None,
) -> bool:
    """
    Đọc bank_fs_components → tính KPI → ghi vào bank_kpi_snapshots.
    Gọi sau khi upsert_fs_components() hoàn tất.
    Trả về True nếu upsert thành công, False nếu không có data.
    """
    components = await repo.get_fs_components(bank_name, reporting_period)
    if not components:
        logger.warning(
            "[fs_sync] %s %s: không có fs_components, bỏ qua",
            bank_name, reporting_period,
        )
        return False

    extracted_kpis = build_daily_earning_kpis_from_components(components)

    # NIM LTM cần 5 quý lịch sử
    history = await repo.get_fs_components_history(
        bank_name=bank_name,
        upto_year=reporting_year,
        upto_quarter=reporting_quarter,
        component_keys=NIM_COMPONENT_KEYS,
        limit_quarters=5,
    )
    nim_ltm = compute_nim_ltm_from_history(history)
    if nim_ltm:
        extracted_kpis.setdefault("profitability_ratios", {})["nim"] = nim_ltm
        logger.info("[fs_sync] %s: NIM LTM = %.4f%%", bank_name, nim_ltm["value"])

    await repo.upsert_snapshot(
        bank_name=bank_name,
        reporting_period=reporting_period,
        extracted_kpis=extracted_kpis,
        run_id=run_id,
        ticker=ticker,
        reporting_year=reporting_year,
        reporting_quarter=reporting_quarter,
    )

    logger.info(
        "[fs_sync] %s %s: sync xong %d categories, KPIs: %s",
        bank_name,
        reporting_period,
        len(extracted_kpis),
        {sec: list(kpis.keys()) for sec, kpis in extracted_kpis.items()},
    )
    return True
