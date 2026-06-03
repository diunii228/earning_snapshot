"""
Manual CSV ingestion -> DB components (bank_fs_components) + recompute KPI snapshot.

Use case:
- Bạn có file `data_manual.csv` (flatten KPI rows) và muốn coi như nguồn BCTC.
- Pipeline sẽ:
  1) upsert các dòng CSV vào bank_fs_components (source_type=financial_statement_pdf)
  2) build 9-KPI snapshot từ components (jobs.fs_kpi_compute)
  3) upsert snapshot cho target_date để Daily Earning Summary có thể đọc ngay từ DB
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from db.repository import BankKpiSnapshotRepository
from config.banks import parse_reporting_period
from jobs.fs_kpi_compute import (
    build_daily_earning_kpis_from_components,
    compute_nim_ltm_from_history,
)

logger = logging.getLogger(__name__)

EXPECTED_HEADERS = {
    "bank_name",
    "ticker",
    "category",
    "kpi_name",
    "value_num",
    "value_num_previous",   # ← thêm dòng này
    "value_text",
    "unit",
    "source_url",
    "source_quote",
    "reasoning",
    "article_links",
}

def _norm_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _iter_csv_rows(path: Path) -> Iterable[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not text:
        return []
    # Some exports prepend an id line like "data-xxxx"
    if text[0].startswith("data-") and len(text) >= 2:
        text = text[1:]
    # Expect semicolon-separated header
    reader = csv.DictReader(text, delimiter=";", quotechar='"')
    return reader


def _iter_xlsx_rows(path: Path) -> Iterable[Dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)  # bỏ read_only
    ws = wb.active

    all_rows: List[List[Any]] = [list(row) for row in ws.iter_rows(values_only=True)]

    if not all_rows:
        return

    # Tìm header row
    header_idx = 0
    header: List[str] = []
    for idx, row in enumerate(all_rows[:10]):  # chỉ scan 10 rows đầu
        normalized = {_norm_header(cell) for cell in row if _norm_header(cell)}
        if {"bank_name", "kpi_name"}.issubset(normalized):
            header_idx = idx
            header = [_norm_header(c) for c in row]
            break

    if not header:
        header = [_norm_header(c) for c in all_rows[0]]
        header_idx = 0

    print(f"[DEBUG] header_idx={header_idx}, header={header}")

    # Yield data rows (sau header)
    for row_values in all_rows[header_idx + 1:]:
        d: Dict[str, Any] = {}
        for j, key in enumerate(header):
            if not key:
                continue
            d[key] = row_values[j] if j < len(row_values) else None

        if not d:
            continue
        if not any(str(v or "").strip() for v in d.values()):
            continue  # skip empty rows

        yield d


def _iter_rows_from_file(path: Path) -> Iterable[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        return _iter_xlsx_rows(path)
    return _iter_csv_rows(path)


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "-", "N/A", "null", "NULL"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _parse_article_links(raw: Any) -> List[str]:
    if raw in (None, "", "None", "null", "NULL"):
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    s = str(raw).strip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if x]
    except Exception:
        pass
    return [s] if s else []


def _first_pdf_path(links: List[str]) -> Optional[str]:
    for u in links:
        if not isinstance(u, str):
            continue
        if u.startswith("file://") and ".pdf" in u.lower():
            # store local path only
            return u.replace("file://", "")
    return None


def _map_component_key(kpi_name: str) -> str:
    k = (kpi_name or "").strip().lower()
    # Normalize common aliases from old pipeline
    if k in ("total_credit", "total_credits", "credit"):
        return "total_credit_reported"
    if k in ("total_lending", "total_loans", "lending"):
        return "total_credit_reported"
    if k in ("lending_growth_ytd", "lending_growth", "lending_growth_qoq", "lending_growth_yoy"):
        # mail/snapshot now uses credit growth
        return "credit_growth_ytd"
    return kpi_name.strip()


def _build_component_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    kpi_name = (row.get("kpi_name") or "").strip()
    if not kpi_name:
        return None

    value_num = _safe_float(row.get("value_num"))
    
    prev_raw = (
        row.get("value_num_previous")
        if row.get("value_num_previous") is not None
        else row.get("value_num_privious")
    )
    value_prev = _safe_float(prev_raw)

    # Nếu value_num rỗng nhưng value_prev có → dùng prev làm current
    if value_num is None and value_prev is not None:
        value_num = value_prev
        value_prev = None

    if value_num is None:
        return None

    prev_raw = (
        row.get("value_num_previous")
        if row.get("value_num_previous") is not None
        else row.get("value_num_privious")  # common typo in your sheet
    )
    value_prev = _safe_float(prev_raw)

    unit = (row.get("unit") or "").strip() or None
    source_url = (row.get("source_url") or "").strip() or None
    source_quote = (row.get("source_quote") or "").strip() or None
    reasoning = (row.get("reasoning") or "").strip() or None

    return {
        "component_key": _map_component_key(kpi_name),
        "value_current": value_num,
        "value_previous": value_prev,
        "unit": unit,
        "period_current_label": None,
        "period_previous_label": None,
        "source_url": source_url,
        "source_quote": source_quote,
        "source_type": "manual_override",
        "reasoning": reasoning or "Manual override (treated as BCTC-highest priority)",
    }


async def ingest_manual_csv(
    csv_path: str,
    reporting_period: str,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(str(path))

    repo = BankKpiSnapshotRepository()

    # Create a run for audit
    run_id = await repo.create_run(
        reporting_period=reporting_period,
        config_snapshot={"manual_csv": str(path.resolve())},
    )

    td = target_date or dt.date.today().isoformat()

    banks: Dict[str, Dict[str, Any]] = {}
    for r in _iter_rows_from_file(path):
        bank_name = str(r.get("bank_name") or "").strip()
        if not bank_name:
            continue
        ticker = str(r.get("ticker") or "").strip() or None
        banks.setdefault(bank_name, {"ticker": ticker, "rows": [], "links": []})
        banks[bank_name]["rows"].append(r)
        banks[bank_name]["links"].extend(_parse_article_links(r.get("article_links")))

    summary = {"banks": 0, "components_upserted": 0, "snapshots_upserted": 0}

    for bank_name, payload in banks.items():
        ticker = payload.get("ticker")
        rows = payload.get("rows") or []
        links = list(dict.fromkeys(payload.get("links") or []))
        pdf_path = _first_pdf_path(links)

        components: List[Dict[str, Any]] = []
        for r in rows:
            c = _build_component_row(r)
            if c:
                components.append(c)

        if not components:
            continue

        affected = await repo.upsert_fs_components(
            bank_name=bank_name,
            reporting_period=reporting_period,
            components=components,
            run_id=run_id,
            ticker=ticker,
            pdf_path=pdf_path,
        )
        summary["components_upserted"] += affected

        # Recompute final KPI snapshot from components DB
        comps_map = await repo.get_fs_components(bank_name, reporting_period)
        final_kpis = build_daily_earning_kpis_from_components(comps_map or {})
        year, quarter = parse_reporting_period(reporting_period)
        if year and quarter:
            try:
                history = await repo.get_fs_components_history(
                    bank_name=bank_name,
                    upto_year=year,
                    upto_quarter=quarter,
                    component_keys=[
                        "net_interest_income",
                        "earning_assets_sbv_deposits",
                        "earning_assets_interbank_assets",
                        "earning_assets_customer_loans",
                        "earning_assets_debt_securities_afs",
                        "earning_assets_debt_securities_htm",
                    ],
                    limit_quarters=5,
                )
                nim_ltm = compute_nim_ltm_from_history(history or [])
                if nim_ltm is not None:
                    final_kpis.setdefault("profitability_ratios", {})
                    final_kpis["profitability_ratios"]["nim"] = nim_ltm
            except Exception:
                pass

        if final_kpis:
            await repo.upsert_snapshot_merge(
                bank_name=bank_name,
                reporting_period=reporting_period,
                extracted_kpis=final_kpis,
                run_id=run_id,
                ticker=ticker,
                target_date=td,
                validation_results={"manual_csv": True},
                article_links=links,
            )
            summary["snapshots_upserted"] += 1

        summary["banks"] += 1

    await repo.finish_run(run_id, status="success", summary=summary)
    return {"run_id": run_id, "summary": summary}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Manual file (CSV/XLSX) -> DB components + recompute snapshot")
    parser.add_argument("--csv", required=True, help="Path to data_manual.csv or data_manual.xlsx")
    parser.add_argument("--period", required=True, help='Reporting period, e.g. "Q1 2026"')
    parser.add_argument("--date", default=None, help="Target date (YYYY-MM-DD) for snapshot")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = asyncio.run(ingest_manual_csv(args.csv, args.period, args.date))
    print(result)


if __name__ == "__main__":
    main()
