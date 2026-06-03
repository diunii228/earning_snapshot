"""
CLI: crawl (daily) | report (từ DB).

  python main.py crawl              # Crawl tất cả bank, upsert vào DB khi có data
  python main.py crawl --date 2026-03-19   # Chạy crawl với target_date tùy chỉnh (dùng cho test hoặc chạy lại kỳ cũ)
  python main.py report             # Đọc DB, gen report so sánh
  python main.py run                # Chạy luôn cả crawl + report trong memory (giữ tương thích cũ)
  python main.py backfill --start "2026-02-02" --end "2026-02-20" --period "Q4 2025"
"""
import argparse
import asyncio
import logging
import time
import datetime
import json
import logging
import os
from typing import Dict, Tuple, List
from graph.base_agent.graph_builder import build_banking_research_graph, build_reporting_graph
from graph.base_agent.report_agent import BankingReporterAgent  
from utils.presenter import export_to_pdf_playwright  
from utils.token_tracker import token_tracker  
from config.banks import REPORTING_PERIOD, SUBJECT_BANK_CONFIG, PEER_BANKS_CONFIG, GENERAL_NEWS_URL, get_all_bank_configs
import os

api_key = os.environ.get("GOOGLE_API_KEY")
if api_key:
    # Chỉ in ra vài ký tự đầu và cuối để bảo mật, tránh vô tình lộ key lên Github
    print(f"🔑 [KIỂM TRA] Google API Key đang dùng: {api_key[:8]}........{api_key[-4:]}")
else:
    print("❌ [CẢNH BÁO] Không tìm thấy biến môi trường GOOGLE_API_KEY!")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ==============================================================================
# CẤU HÌNH CHUNG
# ==============================================================================

# CHỌN CHẾ ĐỘ CHẠY 
# 1: Chạy từ đầu (Extract web -> Lưu JSON -> Viết báo cáo tổng hợp -> Chi tiết từng bank)
# 2: Lấy từ JSON có sẵn -> Báo cáo: Mục lục + Tổng hợp (Strategy) -> Chi tiết từng Bank
# 3: Extract web -> Lưu JSON
# 4: Lấy từ JSON có sẵn -> Báo cáo: So sánh đối đầu (Dùng hàm generate_full_report)
# 5: Chạy từ đầu (Extract web -> Lưu JSON) -> Báo cáo: So sánh đối đầu (Dùng hàm generate_full_report)

def load_data_from_json(filepath: str) -> Tuple[Dict, List[Dict]]:
    if not os.path.exists(filepath):
        print(f"Lỗi: Không tìm thấy file '{filepath}'")
        return None, []

    print(f"Đang đọc dữ liệu từ: {filepath}...")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            data_map = {item['bank_name']: item for item in raw_data} if isinstance(raw_data, list) else raw_data
        print(f"Đã load thành công {len(data_map)} ngân hàng.")
    except Exception as e:
        print(f" Lỗi đọc file JSON: {e}")
        return None, []

    subject_name = SUBJECT_BANK_CONFIG['name']
    subject_data = data_map.get(subject_name)
    
    if not subject_data:
        for k, v in data_map.items():
            if k.lower() == subject_name.lower():
                subject_data = v
                break
    
    if not subject_data: 
        print(f"CRITICAL: Không tìm thấy dữ liệu của {subject_name} trong file.")
        return None, []

    valid_peers = [
        item for item in data_map.values() 
        if item['bank_name'] != subject_data['bank_name'] and item.get('status') == 'success'
    ]
    return subject_data, valid_peers

extract_workflow = build_banking_research_graph()

async def process_bank_data(config: Dict, target_date: str=None) -> Dict:
    """Worker: research 1 bank, trả về dict (dùng cho luồng run)."""
    import time
    start_time = time.perf_counter()
    logger.info(f"[START] Deep Research: {config['name']}...")

    initial_state = {
        "bank_name": config['name'],
        "reporting_period": REPORTING_PERIOD,
        "ticker": config.get("ticker", ""),
        "target_date": target_date,
        "urls": config['urls'],
        "url": "", 
        "article_links": [],
        "articles_data": [],
        "raw_content": "",
        "extracted_kpis": {},
        "kpi_count": 0,
        "validation_results": {},
        "status": "init",
        "errors": []
    }

    try:
        final_state = await extract_workflow.ainvoke(initial_state)
        
        kpi_count = final_state.get('kpi_count', 0)
        status = "success" if final_state.get('status') in ["validated", "extracted"] else "failed"
        duration = time.perf_counter() - start_time
        
        logger.info(f"[DONE] {config['name']}: Trích xuất được {kpi_count} KPIs trong {duration:.2f}s")

        return {
            "bank_name": config["name"],
            "ticker": config["ticker"],
            "status": status,
            "kpi_count": kpi_count, 
            "extracted_kpis": final_state.get('extracted_kpis', {}),
            "source_urls": final_state.get('article_links', []),
            "errors": final_state.get("errors", [])
        }
    except Exception as e:
        logger.error(f"[ERROR] Lỗi chiến dịch Graph {config['name']}: {e}")
        return {
            "bank_name": config["name"],
            "ticker": config["ticker"],
            "status": "error",
            "extracted_kpis": {},
            "error_msg": str(e)
        }

# ---------- CLI ----------
async def run_legacy() -> None:
    """Chạy crawl + report trong memory (không dùng DB), giữ hành vi cũ."""
    print("\n" + "=" * 80)
    print(f"BẮT ĐẦU CHẠY RESEARCH & REPORTING (Chủ thể: {SUBJECT_BANK_CONFIG['name']})")
    print("=" * 80 + "\n")
    t_date = getattr(args, 'date', None) or datetime.date.today().isoformat()
    all_configs = get_all_bank_configs(include_general_url=True)
    tasks = [process_bank_data(conf, target_date=t_date) for conf in all_configs]
    results_list = await asyncio.gather(*tasks)
    data_map = {item["bank_name"]: item for item in results_list}

    subject_data = data_map.get(SUBJECT_BANK_CONFIG["name"])
    if not subject_data or subject_data["status"] != "success":
        logger.error("CRITICAL: Không lấy được dữ liệu của %s. Dừng.", SUBJECT_BANK_CONFIG["name"])
        return

    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)
    raw_file_path = f"{output_dir}/raw_data_{REPORTING_PERIOD}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(raw_file_path, "w", encoding="utf-8") as f:
        json.dump(data_map, f, indent=2, ensure_ascii=False)
    print(f"Đã lưu dữ liệu thô JSON: {raw_file_path}")

    print("\n" + "-" * 80)
    print("KHỞI TẠO REPORT AGENT (Tạo bảng + Viết phân tích)...")
    print("-" * 80)
    valid_peers = [
        item for item in results_list
        if item["bank_name"] != SUBJECT_BANK_CONFIG["name"] and item["status"] == "success"
    ]
    if not valid_peers:
        print("Không có đối thủ nào lấy được dữ liệu để so sánh.")
        return
    print(f"Reporter đang xử lý {len(valid_peers)} ngân hàng đối thủ...")
    reporter = BankingReporterAgent()
    full_report_content = await reporter.generate_full_report(valid_peers, subject_data)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    report_path_md = os.path.join(output_dir, f"Financial_Performance_Report_{timestamp}.md")
    with open(report_path_md, "w", encoding="utf-8") as f:
        f.write(full_report_content)
    report_path_pdf = report_path_md.replace(".md", ".pdf")
    print(f"Đang khởi tạo Playwright để xuất PDF...")
    try:
        await export_to_pdf_playwright(full_report_content, report_path_pdf)
        print(f"✨ HOÀN TẤT! Báo cáo PDF đã sẵn sàng: {report_path_pdf}")
    except Exception as e:
        logger.error(f"Lỗi khi xuất PDF: {e}")
    print(f"\nHOÀN TẤT! Báo cáo: {report_path_md}")
    print(f"PDF báo cáo: {report_path_pdf}")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Banking research: crawl (lưu DB) | report (từ DB) | run (legacy in-memory)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # crawl: daily crawl, upsert DB
    p_crawl = subparsers.add_parser("crawl", help="Crawl tất cả bank, chỉ cập nhật DB khi có data")
    p_crawl.add_argument("--period", default=REPORTING_PERIOD)
    p_crawl.add_argument("--date", help="Set ngày thủ công (YYYY-MM-DD)", default=None) 
    p_crawl.set_defaults(func=lambda ns: asyncio.run(_cmd_crawl(ns)))

    p_crawl.set_defaults(func=lambda ns: asyncio.run(_cmd_crawl(ns)))

    # report: từ DB
    p_report = subparsers.add_parser("report", help="Đọc DB, gen report so sánh")
    p_report.add_argument("--period", default=REPORTING_PERIOD, help=f"Kỳ báo cáo (default: {REPORTING_PERIOD})")
    p_report.add_argument("--output-dir", default="outputs", help="Thư mục ghi file report")
    p_report.set_defaults(func=lambda ns: asyncio.run(_cmd_report(ns)))

    p_run = subparsers.add_parser("run", help="Chạy menu chọn mode cũ (in-memory)")
    p_run.set_defaults(func=lambda ns: asyncio.run(run_legacy())) # Gọi run_legacy thay vì run_legacy()
    # 5. Lệnh Backfill (Cào dữ liệu lùi ngày)
    p_backfill = subparsers.add_parser("backfill", help="Crawl dữ liệu liên tục cho 1 dải ngày (Backfill)")
    p_backfill.add_argument("--start", required=True, help="Ngày bắt đầu định dạng YYYY-MM-DD")
    p_backfill.add_argument("--end", required=True, help="Ngày kết thúc định dạng YYYY-MM-DD")
    p_backfill.add_argument("--period", default=REPORTING_PERIOD, help=f"Kỳ báo cáo (Mặc định: {REPORTING_PERIOD})")
    p_backfill.set_defaults(func=lambda ns: asyncio.run(_cmd_backfill(ns)))

    p_web = subparsers.add_parser("crawl-web", help="Chỉ crawl web (priority thấp nhất)")
    p_web.add_argument("--period", default=REPORTING_PERIOD)
    p_web.add_argument("--date", help="Set ngày thủ công (YYYY-MM-DD)", default=None)
    p_web.set_defaults(func=lambda ns: asyncio.run(_cmd_crawl_web(ns)))

    p_pdf = subparsers.add_parser("ingest-pdf", help="Chỉ extract BCTC PDF (priority cao hơn web)")
    p_pdf.add_argument("--period", default=REPORTING_PERIOD)
    p_pdf.add_argument("--date", help="Target date (YYYY-MM-DD) for snapshot", default=None)
    p_pdf.set_defaults(func=lambda ns: asyncio.run(_cmd_ingest_pdf(ns)))

    p_merge = subparsers.add_parser("merge", help="Chạy merge theo thứ tự web<pdf<excel")
    p_merge.add_argument("--period", default=REPORTING_PERIOD)
    p_merge.add_argument("--date", help="Target date (YYYY-MM-DD)", default=None)
    p_merge.add_argument("--excel", help="Optional path to manual excel", default=None)
    p_merge.set_defaults(func=lambda ns: asyncio.run(_cmd_merge(ns)))

    p_manual = subparsers.add_parser(
        "manual-csv",
        help="Ingest data_manual (csv/xlsx) vào DB (manual override) + recompute snapshot",
    )
    p_manual.add_argument("--csv", required=True, help="Path to data_manual.csv or data_manual.xlsx")
    p_manual.add_argument("--period", default=REPORTING_PERIOD)
    p_manual.add_argument("--date", help="Target date (YYYY-MM-DD) for snapshot", default=None)
    p_manual.set_defaults(func=lambda ns: asyncio.run(_cmd_manual_csv(ns)))

    args = parser.parse_args()
    args.func(args)
    token_tracker.print_summary()

async def _cmd_crawl(args: argparse.Namespace) -> None:
    from jobs.daily_crawl import run_daily_crawl
    logger.info(f"🚀 BẮT ĐẦU CHIẾN DỊCH CRAWL (Kỳ: {args.period}, Ngày: {args.date})")
    result = await run_daily_crawl(
            reporting_period=args.period, 
            target_date=args.date
        )
    print("Kết quả:", result.get("summary"))


async def _cmd_crawl_web(args: argparse.Namespace) -> None:
    from jobs.daily_crawl import run_daily_crawl

    result = await run_daily_crawl(
        reporting_period=args.period,
        target_date=args.date,
        enable_pdf=False,
    )
    print("Kết quả crawl-web:", result.get("summary"))


async def _cmd_ingest_pdf(args: argparse.Namespace) -> None:
    from jobs.pdf_ingest import run_pdf_ingest

    result = await run_pdf_ingest(reporting_period=args.period, target_date=args.date)
    print("Kết quả ingest-pdf:", result.get("summary"))


async def _cmd_merge(args: argparse.Namespace) -> None:
    # 1) web
    await _cmd_crawl_web(args)
    # 2) pdf
    await _cmd_ingest_pdf(args)
    # 3) excel (optional)
    if args.excel:
        ns = argparse.Namespace(csv=args.excel, period=args.period, date=args.date)
        await _cmd_manual_csv(ns)

async def _cmd_report(args: argparse.Namespace) -> None:
    from jobs.report_from_db import run_report_from_db
    md_path = await run_report_from_db(
        reporting_period=args.period,
        output_dir=args.output_dir,
    )
    print("Báo cáo Markdown đã lưu:", md_path)

    if md_path and os.path.exists(md_path):
        pdf_path = md_path.replace(".md", ".pdf")
        print(f"Đang chuyển đổi sang PDF: {pdf_path}...")
        
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                report_content = f.read()
            
            await export_to_pdf_playwright(report_content, pdf_path)
            print("✨ Báo cáo PDF đã lưu:", pdf_path)
        except Exception as e:
            logger.error(f"Lỗi khi xuất PDF từ DB: {e}")

async def _cmd_backfill(args: argparse.Namespace) -> None:
    """Module tự động cào dữ liệu cho một dải ngày liên tiếp (Backfill)"""
    from jobs.daily_crawl import run_daily_crawl
    from datetime import datetime, timedelta
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d")
    end_date = datetime.strptime(args.end, "%Y-%m-%d")
    period = args.period

    if start_date > end_date:
        print("❌ Lỗi: Ngày bắt đầu không được lớn hơn ngày kết thúc!")
        return

    print("\n" + "="*80)
    print(f"🚀 KHỞI ĐỘNG CHIẾN DỊCH BACKFILL DỮ LIỆU")
    print(f"📅 Từ ngày: {args.start} --> Đến ngày: {args.end}")
    print(f"📊 Kỳ báo cáo: {period}")
    print("="*80 + "\n")

    current_date = start_date
    while current_date <= end_date:
        target_date_str = current_date.strftime("%Y-%m-%d")
        
        print(f"\n▶️ ĐANG XỬ LÝ NGÀY: {target_date_str}")
        try:
            # Gọi thẳng hàm cào dữ liệu của hệ thống
            result = await run_daily_crawl(
                reporting_period=period, 
                target_date=target_date_str
            )
            print(f"✅ Hoàn tất ngày {target_date_str}. Kết quả: {result.get('summary')}")
        except Exception as e:
            logger.error(f"❌ Lỗi nghiêm trọng khi cào ngày {target_date_str}: {e}")

        # Tăng lên 1 ngày
        current_date += timedelta(days=1)
        
        # NGHỈ GIỮA HIỆP (Rất quan trọng để không bị block IP/API)
        if current_date <= end_date:
            print("⏳ Đang nghỉ 10 giây để tránh bị rate-limit trước khi cào ngày tiếp theo...")
            await asyncio.sleep(10)

    print("\n🎉 HOÀN TẤT CHIẾN DỊCH BACKFILL DỮ LIỆU THÀNH CÔNG!")


async def _cmd_manual_csv(args: argparse.Namespace) -> None:
    from jobs.manual_csv_ingest import ingest_manual_csv

    result = await ingest_manual_csv(
        csv_path=args.csv,
        reporting_period=args.period,
        target_date=args.date,
    )
    print("Manual CSV ingest:", result.get("summary"))

# async def run_legacy():
#     """Hàm cầu nối để chạy menu chọn mode như phiên bản cũ"""
#     print("\n" + "="*80)
#     print(" BANKING RESEARCH AGENT - CHẾ ĐỘ CHẠY NHANH (IN-MEMORY)")
#     print("="*80)
#     print("1. Chạy từ đầu (Extract web -> Lưu JSON -> Viết báo cáo tổng hợp)")
#     print("2. Lấy từ JSON có sẵn -> Báo cáo Strategy (Cần cập nhật JSON_FILE_PATH)")
#     print("3. Chỉ Extract web -> Lưu JSON (Không tạo báo cáo)")
#     print("4. Lấy từ JSON có sẵn -> Báo cáo So sánh đối đầu")
#     print("5. Chạy từ đầu (Extract -> Báo cáo So sánh đối đầu)")
    
#     choice = input("\n> Chọn chế độ (1-5): ").strip()

#     if choice == "1":
#         await mode_1_full_extract_and_report()
#     elif choice == "2":
#         await mode_2_json_strategy_first()
#     elif choice == "3":
#         await mode_3_json_only()
#     elif choice == "4":
#         await mode_4_json_comparison_only()
#     elif choice == "5":
#         await mode_5_full_extract_and_compare()
#     else:
#         print("Lựa chọn không hợp lệ. Thoát.")


if __name__ == "__main__":
    main()

# async def _cmd_crawl(args: argparse.Namespace) -> None:
#     from jobs.daily_crawl import run_daily_crawl
#     result = await run_daily_crawl(
#             reporting_period=args.period, 
#             target_date=args.date
#         )
#     print("Kết quả:", result.get("summary"))

# async def _cmd_report(args: argparse.Namespace) -> None:
#     from jobs.report_from_db import run_report_from_db
#     md_path = await run_report_from_db(
#         reporting_period=args.period,
#         output_dir=args.output_dir,
#     )
#     print("Báo cáo Markdown đã lưu:", md_path)

#     if md_path and os.path.exists(md_path):
#         pdf_path = md_path.replace(".md", ".pdf")
#         print(f"Đang chuyển đổi sang PDF: {pdf_path}...")
        
#         try:
#             with open(md_path, "r", encoding="utf-8") as f:
#                 report_content = f.read()
            
#             from utils.presenter import export_to_pdf_playwright
#             await export_to_pdf_playwright(report_content, pdf_path)
#             print("✨ Báo cáo PDF đã lưu:", pdf_path)
#         except Exception as e:
#             logger.error(f"Lỗi khi xuất PDF từ DB: {e}")

# # ==========================================
# # HÀM TEST LOCAL (Bị thiếu nãy giờ đây)
# # ==========================================
# async def _cmd_test_local(args: argparse.Namespace) -> None:
#     """Module test nhanh Extraction và Report từ file TXT nội bộ"""
#     file_path = args.file
#     bank_name = args.bank
#     period = args.period
    
#     if not os.path.exists(file_path):
#         logger.error(f"❌ Lỗi: Không tìm thấy file '{file_path}'")
#         return

#     with open(file_path, "r", encoding="utf-8") as f:
#         raw_content = f.read()

#     print("\n" + "="*80)
#     print(f"🧪 ĐANG TEST LOCAL CHO: {bank_name.upper()} | KỲ: {period}")
#     print(f"📂 File nguồn: {file_path} ({len(raw_content)} ký tự)")
#     print("="*80)

#     # Import Agent
#     from graph.base_agent.banking_agent import BankingResearchAgent 
#     from graph.base_agent.report_agent import BankingReporterAgent
    
#     agent = BankingResearchAgent()
    
#     mock_state = {
#         "bank_name": bank_name,
#         "reporting_period": period,
#         "target_date": datetime.datetime.now().strftime("%Y-%m-%d"),
#         "raw_content": raw_content,
#         "extracted_kpis": {},
#         "errors": [],
#         "status": "fetched"
#     }

#     print("\n[1/2] 🧠 Đang chạy Extraction Agent (Bóc tách số liệu)...")
#     result_state = await agent.extract_banking_kpis(mock_state)
    
#     extracted_data = result_state.get("extracted_kpis", {})
    
#     os.makedirs("outputs", exist_ok=True)
#     test_json_path = f"outputs/test_local_{bank_name}_{period.replace(' ', '')}.json"
#     with open(test_json_path, "w", encoding="utf-8") as f:
#         json.dump(extracted_data, f, indent=2, ensure_ascii=False)
        
#     print(f"✅ Đã bóc tách xong! Có {result_state.get('kpi_count', 0)} KPI được tìm thấy.")
#     print(f"💾 Dữ liệu JSON đã lưu tại: {test_json_path}")

#     if not extracted_data:
#         print("⚠️ Extraction Agent không tìm thấy KPI nào. Dừng test Report.")
#         if result_state.get("errors"):
#             print("Lỗi:", result_state["errors"])
#         return

#     print("\n[2/2] ✍️ Đang chạy Report Agent (Viết nhận xét)...")
#     reporter = BankingReporterAgent()
    
#     mock_subject_data = {
#         "bank_name": bank_name,
#         "extracted_kpis": extracted_data,
#         "status": "success"
#     }
    
#     highlight_content = await reporter.generate_individual_highlight(mock_subject_data)
    
#     print("\n" + "-"*80)
#     print("🎯 KẾT QUẢ VIẾT BÁO CÁO (HIGHLIGHT):")
#     print("-"*80)
#     print(highlight_content)
#     print("-"*80 + "\n")

# # ==========================================
# # KHỐI MAIN: ĐĂNG KÝ CLI
# # ==========================================
# def main() -> None:
#     parser = argparse.ArgumentParser(
#         description="Banking research: crawl (lưu DB) | report (từ DB) | run (legacy in-memory) | test-local",
#     )
#     subparsers = parser.add_subparsers(dest="command", required=True)

#     p_crawl = subparsers.add_parser("crawl", help="Crawl tất cả bank, chỉ cập nhật DB khi có data")
#     p_crawl.add_argument("--period", default=REPORTING_PERIOD)
#     p_crawl.add_argument("--date", help="Set ngày thủ công (YYYY-MM-DD)", default=None) 
#     p_crawl.set_defaults(func=lambda ns: asyncio.run(_cmd_crawl(ns)))

#     p_report = subparsers.add_parser("report", help="Đọc DB, gen report so sánh")
#     p_report.add_argument("--period", default=REPORTING_PERIOD, help=f"Kỳ báo cáo (default: {REPORTING_PERIOD})")
#     p_report.add_argument("--output-dir", default="outputs", help="Thư mục ghi file report")
#     p_report.set_defaults(func=lambda ns: asyncio.run(_cmd_report(ns)))

#     p_run = subparsers.add_parser("run", help="Chạy menu chọn mode cũ (in-memory)")
#     p_run.set_defaults(func=lambda ns: asyncio.run(run_legacy()))

#     p_test = subparsers.add_parser("test-local", help="Test Extraction & Report bằng file TXT nội bộ")
#     p_test.add_argument("--file", required=True, help="Đường dẫn tới file .txt chứa bài báo")
#     p_test.add_argument("--bank", required=True, help="Tên ngân hàng muốn test (VD: Techcombank)")
#     p_test.add_argument("--period", default=REPORTING_PERIOD, help=f"Kỳ báo cáo (Mặc định: {REPORTING_PERIOD})")
#     p_test.set_defaults(func=lambda ns: asyncio.run(_cmd_test_local(ns)))

#     args = parser.parse_args()
#     args.func(args)
#     token_tracker.print_summary()

# if __name__ == "__main__":
#     main()
