"""
Luồng 1: Crawl hằng ngày — chạy agent cho tất cả bank, chỉ cập nhật DB khi có data.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List

from config.banks import get_all_bank_configs, REPORTING_PERIOD
from db.connection import close_pool, get_pool
from db.repository import BankKpiSnapshotRepository
from graph.base_agent.runner import research_bank_async

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

async def process_bank_and_upsert(
    config: Dict[str, Any],
    reporting_period: str,
    repo: BankKpiSnapshotRepository,
    run_id: int,
    target_date: str,
) -> Dict[str, Any]:

    start = time.perf_counter()
    bank_name = config["name"]
    logger.info("[START] Thu thập: %s cho ngày %s...", bank_name, target_date)

    try:
        result = await research_bank_async(
            urls=config["urls"],
            bank_name=bank_name,
            reporting_period=reporting_period,
            target_date=target_date,
        )

        extracted = result.get("extracted_kpis") or {}

        def count_valid_values(data):
            if isinstance(data, dict) and 'value' in data:
                val = data['value']
                if val not in [None, "-", "N/A", "", "none", "null"] and str(val).lower() != "null":
                    return 1
                return 0
            
            count = 0
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in ['bank_name', 'reporting_period', 'report_period', 'report_year', 'target_date']:
                        continue
                    if isinstance(v, (dict, list)):
                        count += count_valid_values(v)
                    else:
                        if v not in [None, "-", "N/A", "", "none", "null"] and str(v).lower() != "null":
                            count += 1
            elif isinstance(data, list):
                for item in data:
                    count += count_valid_values(item)
                    
            return count

        # Tự tính toán kpi_count ngay tại đây, không cần xin LangGraph nữa!
        actual_kpi_count = count_valid_values(extracted)

        # Ghi đè lại biến has_new_data dựa trên số đếm thực tế
        has_new_data = actual_kpi_count > 0

        elapsed = time.perf_counter() - start

        if has_new_data:
            await repo.upsert_snapshot(
                bank_name=bank_name,
                reporting_period=reporting_period,
                extracted_kpis=extracted,
                run_id=run_id,
                ticker=config.get("ticker"),
                target_date=target_date,
                validation_results=result.get("validation_results"),
                article_links=result.get("article_links") or [],
            )

            logger.info(
                "[DONE] %s: Đã cập nhật DB (%s KPIs) trong %.2fs",
                bank_name,
                actual_kpi_count,
                elapsed,
            )

            status = "success"

        else:
            logger.info("has_new_data=False")
            logger.info("report_period=%s", reporting_period)
            logger.info("target_date=%s", target_date)
            logger.info(
                "[SKIP] %s: Không tìm thấy dữ liệu mới cho ngày %s.",
                bank_name,
                target_date,
            )

            status = "no_data"

        return {
            "bank_name": bank_name,
            "status": status,
            "extracted_kpis": extracted,
            "has_new_data": has_new_data,
        }

    except Exception as e:
        logger.exception("[ERROR] %s: %s", bank_name, e)
        return {
            "bank_name": bank_name,
            "status": "error",
            "extracted_kpis": {},
            "error_msg": str(e),
        }
    
async def run_daily_crawl(
    reporting_period: str | None = None,
    config_snapshot: Dict[str, Any] | None = None,
    target_date: str | None = None, 
) -> Dict[str, Any]:
    """
    Entry: crawl tất cả bank, ghi run vào research_runs, upsert snapshot khi có data.
    Cho phép tự set target_date (định dạng YYYY-MM-DD).
    """
    import datetime
    
    current_date = str(target_date) if target_date else datetime.date.today().strftime("%Y-%m-%d")
    reporting_period = reporting_period or REPORTING_PERIOD
    
    all_configs = get_all_bank_configs(include_general_url=True)
    repo = BankKpiSnapshotRepository()

    # Đảm bảo pool đã tạo
    await get_pool()

    snapshot = config_snapshot or {"banks": [c["name"] for c in all_configs]}
    snapshot["target_date"] = current_date 

    run_id = await repo.create_run(
        reporting_period=reporting_period,
        config_snapshot=snapshot,
    )
    
    logger.info(
        "Research START: run_id=%s | target_date=%s | period=%s | banks=%d", 
        run_id, current_date, reporting_period, len(all_configs)
    )

    tasks = [
        process_bank_and_upsert(
            config=c, 
            reporting_period=reporting_period, 
            repo=repo, 
            run_id=run_id,
            target_date=current_date 
        )
        for c in all_configs
    ]
    
    results: List[Dict[str, Any]] = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.get("status") == "success")
    failed_count = len(results) - success_count
    status = "success" if failed_count == 0 else ("partial" if success_count else "failed")
    summary = {"success": success_count, "failed": failed_count, "total": len(results)}

    await repo.finish_run(run_id=run_id, status=status, summary=summary)
    await close_pool()

    logger.info("Daily crawl xong: run_id=%s | date=%s | %s", run_id, current_date, summary)
    return {"run_id": run_id, "status": status, "summary": summary, "results": results}
