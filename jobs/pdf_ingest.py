"""
PDF-only ingestion job.

- Discover latest BCTC PDF per bank
- Extract raw components + upsert into bank_fs_components (priority: financial_statement_pdf)
- Recompute final KPIs from components and upsert snapshot for target_date
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from config.banks import REPORTING_PERIOD, get_all_bank_configs, parse_reporting_period
from db.connection import close_pool, get_pool
from db.repository import BankKpiSnapshotRepository
from jobs.financial_statement_ingest import extract_pdf_kpis_for_bank
from jobs.fs_kpi_compute import build_daily_earning_kpis_from_components, compute_nim_ltm_from_history

logger = logging.getLogger(__name__)


async def run_pdf_ingest(
    reporting_period: Optional[str] = None,
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    reporting_period = reporting_period or REPORTING_PERIOD
    current_date = str(target_date) if target_date else datetime.date.today().strftime("%Y-%m-%d")
    all_configs = get_all_bank_configs(include_general_url=True)
    repo = BankKpiSnapshotRepository()

    await get_pool()
    run_id = await repo.create_run(
        reporting_period=reporting_period,
        config_snapshot={"mode": "pdf_ingest", "target_date": current_date},
    )

    success = 0
    skipped = 0
    errors = 0
    try:
        for cfg in all_configs:
            bank_name = cfg["name"]
            try:
                pdf_payload = await extract_pdf_kpis_for_bank(cfg)
                fs_components = pdf_payload.get("fs_components") or []
                pdf_path_obj = pdf_payload.get("pdf_path")
                pdf_path_str = (
                    str(pdf_path_obj.resolve())
                    if hasattr(pdf_path_obj, "resolve")
                    else (str(pdf_path_obj) if pdf_path_obj else None)
                )
                if not fs_components:
                    logger.info(
                        "[PDF] %s skipped: reason=%s pdf=%s",
                        bank_name,
                        pdf_payload.get("skip_reason"),
                        pdf_path_str,
                    )
                    skipped += 1
                    continue

                await repo.upsert_fs_components(
                    bank_name=bank_name,
                    reporting_period=reporting_period,
                    components=fs_components,
                    run_id=run_id,
                    ticker=cfg.get("ticker"),
                    pdf_path=pdf_path_str,
                )

                comps_map = await repo.get_fs_components(bank_name, reporting_period)
                final_kpis = build_daily_earning_kpis_from_components(comps_map or {})

                year, quarter = parse_reporting_period(reporting_period)
                if year and quarter:
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

                if final_kpis:
                    await repo.upsert_snapshot_merge(
                        bank_name=bank_name,
                        reporting_period=reporting_period,
                        extracted_kpis=final_kpis,
                        run_id=run_id,
                        ticker=cfg.get("ticker"),
                        target_date=current_date,
                        validation_results={"pdf_ingest": True},
                        article_links=pdf_payload.get("article_links") or [],
                    )
                success += 1
            except Exception as exc:
                logger.exception("[PDF] %s error: %s", bank_name, exc)
                errors += 1
        status = "success" if errors == 0 else ("partial" if success else "failed")
        summary = {"success": success, "skipped": skipped, "error": errors, "total": len(all_configs)}
        await repo.finish_run(run_id, status=status, summary=summary)
        return {"run_id": run_id, "status": status, "summary": summary}
    finally:
        try:
            await close_pool()
        except Exception:
            pass
