"""
Luồng 2: Gen report từ DB — đọc snapshot theo kỳ, gọi BankingReporterAgent, ghi file.
"""
import datetime
import logging
import os
from typing import Optional

from config.banks import REPORTING_PERIOD, SUBJECT_BANK_CONFIG
from db.connection import close_pool, get_pool
from db.repository import BankKpiSnapshotRepository
from graph.base_agent.report_agent import BankingReporterAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

async def run_report_from_db(
    reporting_period: Optional[str] = None,
    subject_bank_name: Optional[str] = None,
    output_dir: str = "outputs",
) -> str:
    """
    Đọc snapshot từ DB theo reporting_period, lấy subject + peers, gen report.
    """
    reporting_period = reporting_period or REPORTING_PERIOD
    subject_bank_name = subject_bank_name or SUBJECT_BANK_CONFIG["name"]
    target_date = datetime.datetime.now().strftime("%Y-%m-%d")

    await get_pool()
    repo = BankKpiSnapshotRepository()
    
    snapshots = await repo.get_latest_snapshots_with_previous(reporting_period)
    await close_pool()

    if not snapshots:
        raise ValueError(f"Không có dữ liệu trong DB cho kỳ {reporting_period}.")

    # Lấy dữ liệu ngân hàng mục tiêu
    subject_snapshot = next(
        (s for s in snapshots if s["bank_name"] == subject_bank_name),
        None,
    )

    # NẾU KHÔNG CÓ DATA SUBJECT: Tạo một snapshot giả chỉ có tên để Agent biết 
    # là đang làm report cho ngân hàng nào, nhưng extracted_kpis sẽ rỗng.
    if not subject_snapshot:
        logger.warning(f"Không tìm thấy KPI cho {subject_bank_name}. Report sẽ không có phần Market Landscape.")
        subject_data = {
            "bank_name": subject_bank_name,
            "extracted_kpis": {} # Data rỗng để kích hoạt logic ẩn Market Landscape
        }
    else:
        subject_data = subject_snapshot

    representative_snapshot = next(
        (s for s in snapshots if s["bank_name"] == subject_bank_name),
        snapshots[0] if snapshots else None
    )

    db_date = representative_snapshot.get("target_date") 
    if isinstance(db_date, datetime.datetime):
        target_date = db_date.strftime("%Y-%m-%d")
    elif isinstance(db_date, datetime.date):
        target_date = db_date.strftime("%Y-%m-%d")
    elif isinstance(db_date, str):
        target_date = db_date[:10] # Lấy phần YYYY-MM-DD
    else:
        target_date = datetime.datetime.now().strftime("%Y-%m-%d") # Fallback nếu DB null

    subject_snapshot = next(
        (s for s in snapshots if s["bank_name"] == subject_bank_name),
        None,
    )

    # Lấy danh sách Peers
    valid_peers = [
        s for s in snapshots
        if s["bank_name"] != subject_bank_name and s.get("status") == "success"
    ]

    # Vẫn yêu cầu phải có ít nhất 1 Peer hoặc Subject có data để làm report
    if not valid_peers and not subject_snapshot:
         raise ValueError(f"Cả Subject và Peers đều không có dữ liệu cho kỳ {reporting_period}.")

    logger.info("Gen report: subject=%s, peers=%d", subject_bank_name, len(valid_peers))
    
    reporter = BankingReporterAgent()
    # Agent lúc này sẽ nhận được subject_data.extracted_kpis = {} 
    # và tự động ẩn phần Market Landscape theo logic đã viết ở trên.
    full_report_content = await reporter.generate_overall_strategy(
        valid_peers, 
        subject_data, 
        target_date=target_date
    )
    os.makedirs(output_dir, exist_ok=True)
    report_filename = f"Competitor_Analysis_Financial_Performance_Report_{reporting_period}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md"
    report_path = os.path.join(output_dir, report_filename)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report_content)

    logger.info("Report đã lưu: %s", report_path)
    return report_path
