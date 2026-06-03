"""
Luồng 1: Crawl hằng ngày — chạy agent cho tất cả bank, chỉ cập nhật DB khi có data.
Lần đầu của mỗi reporting_period dùng window 15 ngày; các lần sau dùng window ±1 ngày.
"""
import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional

from config.banks import get_all_bank_configs, REPORTING_PERIOD, parse_reporting_period
from db.connection import close_pool, get_pool
from db.repository import BankKpiSnapshotRepository
from jobs.financial_statement_ingest import (
    extract_pdf_kpis_for_bank,
    merge_extracted_kpis_with_pdf_priority,
)
from jobs.fs_kpi_compute import (
    build_daily_earning_kpis_from_components,
    compute_nim_ltm_from_history,
)
from jobs.kpi_validation import validate_and_resolve_kpis
from graph.base_agent.runner import research_bank_async

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

from graph.base_agent.banking_agent import BankingResearchAgent

logger = logging.getLogger(__name__)
MAX_CONCURRENT_BANKS = 4

def _count_valid_kpis(extracted_kpis: Dict) -> int:
    """
    Đếm số KPI có value hợp lệ (không phải null/N/A/...).

    FIX #2: Chỉ đếm field có key="value" bên trong KPI object,
    KHÔNG đệ quy vào unit/source_quote/reasoning/confidence.
    Tránh inflate count gấp 5-8 lần so với thực tế.

    Cấu trúc expected:
    {
      "profitability": {
        "pbt": {"value": 6500, "unit": "billion VND", ...},  ← đếm 1 nếu value hợp lệ
        "pbt_growth_yoy": {"value": null, ...},               ← không đếm
      },
      ...
    }
    """
    NULL_VALUES = {None, "-", "N/A", "", "none", "null"}

    count = 0
    if not isinstance(extracted_kpis, dict):
        return count

    for section in extracted_kpis.values():
        if not isinstance(section, dict):
            continue
        for kpi_key, details in section.items():
            # Skip metadata fields tồn tại ở cấp section
            if kpi_key in ("bank_name", "reporting_period", "report_period",
                           "report_year", "target_date"):
                continue
            if not isinstance(details, dict):
                continue
            val = details.get("value")
            if val not in NULL_VALUES and str(val).lower() not in ("none", "null", "n/a"):
                count += 1

    return count

async def process_bank_and_upsert(
    config: Dict[str, Any],
    reporting_period: str,
    repo: BankKpiSnapshotRepository,
    run_id: int,
    target_date: str,
    date_window_days: int,
    semaphore: asyncio.Semaphore,
    shared_urls: Optional[List[str]] = None, 
    enable_pdf: bool = True,
) -> Dict[str, Any]:

    bank_name = config["name"]

    async with semaphore:
        start = time.perf_counter()
        logger.info("[START] Thu thập: %s cho ngày %s...", bank_name, target_date)

        try:
            result = await research_bank_async(
                urls=config["urls"],
                bank_name=bank_name,
                reporting_period=reporting_period,
                target_date=target_date,
                date_window_days=date_window_days,
                shared_urls=shared_urls or [], 
            )

            extracted = result.get("extracted_kpis") or {}
            article_links = result.get("article_links") or []

            if enable_pdf:
                pdf_payload = await extract_pdf_kpis_for_bank(config)
                pdf_extracted = pdf_payload.get("extracted_kpis") or {}
                fs_components = pdf_payload.get("fs_components") or []
                pdf_path_obj = pdf_payload.get("pdf_path")
                pdf_path_str = str(pdf_path_obj.resolve()) if hasattr(pdf_path_obj, "resolve") else (str(pdf_path_obj) if pdf_path_obj else None)

                if fs_components:
                    try:
                        await repo.upsert_fs_components(
                            bank_name=bank_name,
                            reporting_period=reporting_period,
                            components=fs_components,
                            run_id=run_id,
                            ticker=config.get("ticker"),
                            pdf_path=pdf_path_str,
                        )
                    except Exception as exc:
                        logger.warning("[PDF] %s: cannot upsert fs components: %s", bank_name, exc)

                # Build final KPI snapshot from DB components (ưu tiên manual_override/BCTC)
                try:
                    components_map = await repo.get_fs_components(bank_name, reporting_period)
                    computed_pdf_kpis = build_daily_earning_kpis_from_components(components_map or {})

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
                            computed_pdf_kpis.setdefault("profitability_ratios", {})
                            computed_pdf_kpis["profitability_ratios"]["nim"] = nim_ltm

                    if computed_pdf_kpis:
                        pdf_extracted = computed_pdf_kpis
                except Exception as exc:
                    logger.warning("[PDF] %s: cannot compute kpis from fs components: %s", bank_name, exc)

                if pdf_extracted:
                    logger.info("[PDF] %s: merge %d sections from BCTC with PDF priority.", bank_name, len(pdf_extracted))
                    extracted = merge_extracted_kpis_with_pdf_priority(extracted, pdf_extracted)
                    article_links = list(dict.fromkeys(article_links + (pdf_payload.get("article_links") or [])))

            validation_payload = validate_and_resolve_kpis(extracted)
            extracted = validation_payload.get("final_kpis") or {}
            post_validation_results = validation_payload.get("validation_results") or {}
            if post_validation_results.get("mismatch_count"):
                logger.warning(
                    "[VALIDATION] %s: removed %d KPI(s) due to mismatch.",
                    bank_name,
                    post_validation_results["mismatch_count"],
                )

            actual_kpi_count = _count_valid_kpis(extracted)
            has_new_data = actual_kpi_count > 0
            elapsed = time.perf_counter() - start

            if has_new_data:
                await repo.upsert_snapshot_merge(
                    bank_name=bank_name,
                    reporting_period=reporting_period,
                    extracted_kpis=extracted,
                    run_id=run_id,
                    ticker=config.get("ticker"),
                    target_date=target_date,
                    validation_results={
                        "web_validation": result.get("validation_results") or {},
                        "post_resolution": post_validation_results,
                    },
                    article_links=article_links,
                )
                logger.info(
                    "[DONE] %s: Đã cập nhật DB (%d KPIs) trong %.2fs",
                    bank_name, actual_kpi_count, elapsed,
                )
                status = "success"

            else:
                logger.info(
                    "[SKIP] %s: Không tìm thấy dữ liệu mới cho ngày %s "
                    "(period=%s, elapsed=%.2fs)",
                    bank_name, target_date, reporting_period, elapsed,
                )
                status = "no_data"

            return {
                "bank_name": bank_name,
                "status": status,
                "kpi_count": actual_kpi_count,
                "extracted_kpis": extracted,
                "article_links": article_links,
                "has_new_data": has_new_data,
            }

        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.exception("[ERROR] %s (%.2fs): %s", bank_name, elapsed, e)
            return {
                "bank_name": bank_name,
                "status": "error",
                "kpi_count": 0,
                "extracted_kpis": {},
                "error_msg": str(e),
                "has_new_data": False,
            }


async def _run_daily_crawl_for_single_date(
    reporting_period: str,
    all_configs: List[Dict[str, Any]],
    repo: BankKpiSnapshotRepository,
    current_date: str,
    date_window_days: int,
    config_snapshot: Optional[Dict[str, Any]] = None,
    enable_pdf: bool = True,
) -> Dict[str, Any]:
    snapshot = dict(config_snapshot or {"banks": [c["name"] for c in all_configs]})
    snapshot["target_date"] = current_date
    snapshot["date_window_days"] = date_window_days

    run_id = await repo.create_run(
        reporting_period=reporting_period,
        config_snapshot=snapshot,
    )

    logger.info(
        "Research START: run_id=%s | target_date=%s | period=%s | window=±%sd | banks=%d | concurrency=%d",
        run_id, current_date, reporting_period, date_window_days, len(all_configs), MAX_CONCURRENT_BANKS,
    )

    logger.info("=== BẮT ĐẦU PHA 1: SĂN LINK DÙNG CHUNG ===")
    global_url_pool = set()
    agent_for_search = BankingResearchAgent()

    async def fetch_links_for_bank(config: dict) -> list:
        state = {
            "bank_name": config["name"],
            "reporting_period": reporting_period,
            "target_date": current_date,
            "urls": config.get("urls", []),
        }
        try:
            res_state = await agent_for_search.expand_category_links(state, max_links=20)
            return res_state.get("article_links", [])
        except Exception as e:
            logger.error(f"Lỗi săn link Pha 1 cho {config['name']}: {e}")
            return []

    link_tasks = [fetch_links_for_bank(c) for c in all_configs]
    link_results = await asyncio.gather(*link_tasks)
    for links in link_results:
        global_url_pool.update(links)

    raw_shared_urls = list(global_url_pool)
    logger.info(f"=== KẾT THÚC PHA 1: Tóm được {len(raw_shared_urls)} link độc nhất ===")

    logger.info(f"=== PHA 1.5: KIỂM DUYỆT WINDOW ±{date_window_days} NGÀY QUANH {current_date} CHO RỔ CHUNG ===")
    target_dt = datetime.datetime.strptime(current_date, "%Y-%m-%d").date()

    import aiohttp

    async def check_url_date(url):
        async with aiohttp.ClientSession() as session:
            res = await agent_for_search._fetch_url(session, url, retries=1)
            if res and res.get("pub_date"):
                try:
                    pub_dt = datetime.datetime.strptime(res["pub_date"], "%Y-%m-%d").date()
                    if abs((pub_dt - target_dt).days) <= date_window_days:
                        return url
                except ValueError:
                    pass
        return None

    date_check_tasks = [check_url_date(u) for u in raw_shared_urls]
    valid_links_results = await asyncio.gather(*date_check_tasks)
    validated_shared_urls = [url for url in valid_links_results if url is not None]

    logger.info(f"👉 Sau khi lọc theo window ±{date_window_days} ngày quanh {current_date}, Rổ chung còn lại: {len(validated_shared_urls)} link.")

    logger.info("=== BẮT ĐẦU PHA 2: BÓC TÁCH KPI TỪNG BANK ===")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BANKS)

    tasks = [
        process_bank_and_upsert(
            config=c,
            reporting_period=reporting_period,
            repo=repo,
            run_id=run_id,
            target_date=current_date,
            date_window_days=date_window_days,
            semaphore=semaphore,
            shared_urls=validated_shared_urls,
            enable_pdf=enable_pdf,
        )
        for c in all_configs
    ]

    results: List[Dict[str, Any]] = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.get("status") == "success")
    no_data_count = sum(1 for r in results if r.get("status") == "no_data")
    error_count = sum(1 for r in results if r.get("status") == "error")
    total_kpis = sum(r.get("kpi_count", 0) for r in results)

    overall_status = (
        "success" if error_count == 0
        else ("partial" if success_count > 0 else "failed")
    )
    summary = {
        "success": success_count,
        "no_data": no_data_count,
        "error": error_count,
        "total": len(results),
        "total_kpis_extracted": total_kpis,
    }

    await repo.finish_run(run_id=run_id, status=overall_status, summary=summary)

    logger.info(
        "Daily crawl xong: run_id=%s | date=%s | %s",
        run_id, current_date, summary,
    )
    return {
        "run_id": run_id,
        "target_date": current_date,
        "date_window_days": date_window_days,
        "status": overall_status,
        "summary": summary,
        "results": results,
    }

async def run_daily_crawl(
    reporting_period: Optional[str] = None,
    config_snapshot: Optional[Dict[str, Any]] = None,
    target_date: Optional[str] = None,
    enable_pdf: bool = True,
) -> Dict[str, Any]:
    """
    KIẾN TRÚC 2 PHA (CROSS-POLLINATION):
    Pha 1: Tất cả bank đi săn link -> Gom vào Rổ chung.
    Pha 2: Các bank bóc KPI dựa trên link riêng + link từ Rổ chung.
    """
    current_date = str(target_date) if target_date else datetime.date.today().strftime("%Y-%m-%d")
    reporting_period = reporting_period or REPORTING_PERIOD

    all_configs = get_all_bank_configs(include_general_url=True)
    repo = BankKpiSnapshotRepository()

    await get_pool()
    is_first_period_run = not await repo.has_any_run_for_period(reporting_period)
    date_window_days = 15 if is_first_period_run else 1

    if is_first_period_run:
        logger.info(
            "Lần đầu chạy reporting_period=%s -> dùng window ±%s ngày quanh %s.",
            reporting_period,
            date_window_days,
            current_date,
        )
    else:
        logger.info(
            "Đã có run trước cho reporting_period=%s -> dùng window ±%s ngày quanh %s.",
            reporting_period,
            date_window_days,
            current_date,
        )

    daily_runs = []
    try:
        daily_runs.append(
            await _run_daily_crawl_for_single_date(
                reporting_period=reporting_period,
                all_configs=all_configs,
                repo=repo,
                current_date=current_date,
                date_window_days=date_window_days,
                config_snapshot=config_snapshot,
                enable_pdf=enable_pdf,
            )
        )
    finally:
        try:
            await close_pool()
        except Exception as e:
            logger.warning("close_pool() warning (pool may already be closed): %s", e)

    success_days = sum(1 for run in daily_runs if run.get("status") == "success")
    partial_days = sum(1 for run in daily_runs if run.get("status") == "partial")
    failed_days = sum(1 for run in daily_runs if run.get("status") == "failed")
    total_kpis = sum(run.get("summary", {}).get("total_kpis_extracted", 0) for run in daily_runs)

    overall_status = (
        "failed" if daily_runs and all(run.get("status") == "failed" for run in daily_runs)
        else ("partial" if partial_days or failed_days else "success")
    )

    return {
        "status": overall_status,
        "summary": {
            "days_run": len(daily_runs),
            "success_days": success_days,
            "partial_days": partial_days,
            "failed_days": failed_days,
            "date_window_days": date_window_days,
            "total_kpis_extracted": total_kpis,
        },
        "run_ids": [run["run_id"] for run in daily_runs],
        "daily_runs": daily_runs,
    }
