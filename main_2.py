import asyncio
import logging
import time
import datetime
import json
import os
from typing import Dict

from graph.base_agent.runner import research_bank_async  
from graph.base_agent.report_agent import BankingReporterAgent    

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

REPORTING_PERIOD = "2025"  

GENERAL_NEWS_URL = "https://cafef.vn/tai-chinh-ngan-hang.chn"

SUBJECT_BANK_CONFIG = {
    "name": "Techcombank",
    "ticker": "TCB",
    "urls": [
        "https://cafef.vn/techcombank.html",
        "https://vietstock.vn/TCB-ngan-hang-tmcp-ky-thuong-viet-nam.htm",
        "https://vneconomy.vn/search.htm?q=Techcombank"
    ]
}

PEER_BANKS_CONFIG = [
    {
        "name": "VPBank",
        "ticker": "VPB",
        "urls": [
            "https://cafef.vn/vpbank.html",
            "https://finance.vietstock.vn/VPB/tin-tuc-su-kien.htm",
            "https://www.vpbank.com.vn/"
        ]
    },
    {
        "name": "MBBank",
        "ticker": "MBB",
        "urls": [
            "https://cafef.vn/loi-nhuan-mb-vuot-34000-ty-chu-tich-luu-trung-thai-chia-se-ve-muc-tieu-kinh-doanh-nam-2026-tang-22-tong-tai-san-va-25-tin-dung-188260118091555093.chn",
            "https://cafef.vn/mbbank.html",
            "https://finance.vietstock.vn/MBB/tin-tuc-su-kien.htm",
            "https://www.mbbank.com.vn/home"
            ]
    },
    {
        "name": "ACB",
        "ticker": "ACB",
        "urls": [
            "https://cafef.vn/acb.html",
            "https://finance.vietstock.vn/ACB/tin-tuc-su-kien.htm"
        ]
    },
    {
        "name": "BIDV", "ticker": "BIDV",
        "urls": ["https://cafef.vn/bidv.html", "https://finance.vietstock.vn/BIDV/tin-tuc-su-kien.htm",
                 "https://www.bidv.com.vn/"]
    },
    {
        "name": "HDBank", "ticker": "HDB",
        "urls": ["https://cafef.vn/hdbank.html", "https://finance.vietstock.vn/HDB/tin-tuc-su-kien.htm"]
    },
    {
        "name": "Vietinbank", "ticker": "CTG",
        "urls": ["https://cafef.vn/vietinbank.html", "https://finance.vietstock.vn/CTG/tin-tuc-su-kien.htm",
                 "https://www.vietinbank.vn/"]
    },
    {
        "name": "Vietcombank", "ticker": "VCB",
        "urls": [
            "https://cafef.vn/vietcombank.html",
            "https://finance.vietstock.vn/VCB/tin-tuc-su-kien.htm",
            "https://www.vietcombank.com.vn/"
        ]
    }
]

# async def process_bank_data(config: Dict) -> Dict:
#     """
#     Worker function: Chạy quy trình research cho 1 ngân hàng.
#     Trả về dictionary chứa dữ liệu đã extract.
#     """
#     start_time = time.perf_counter()
#     logger.info(f"[START] Bắt đầu thu thập dữ liệu: {config['name']}...")

#     try:
#         result = await research_bank_async(
#             urls=config['urls'],
#             bank_name=config['name'],
#             reporting_period=REPORTING_PERIOD
#         )
        
#         extracted_data = result.get('extracted_kpis', {})
#         status = "success" if extracted_data else "failed"
#         duration = time.perf_counter() - start_time
        
#         logger.info(f"[DONE] {config['name']} hoàn thành trong {duration:.2f}s | Status: {status}")

#         return {
#             "bank_name": config['name'],
#             "ticker": config['ticker'],
#             "status": status,
#             "extracted_kpis": extracted_data,
#             "source_urls": result.get('article_links', [])
#         }
        
#     except Exception as e:
#         logger.error(f"[ERROR] Lỗi xử lý {config['name']}: {e}")
#         return {
#             "bank_name": config['name'],
#             "ticker": config['ticker'],
#             "status": "error",
#             "extracted_kpis": {},
#             "error_msg": str(e)
#         }
    
# async def main():
#     print("\n" + "="*80)
#     print(f"BẮT ĐẦU CHẠY RESEARCH & REPORTING (Chủ thể: {SUBJECT_BANK_CONFIG['name']})")
#     print("="*80 + "\n")
    
#     all_configs = [SUBJECT_BANK_CONFIG] + PEER_BANKS_CONFIG
    
#     print(f"🔗 Đang thêm link '{GENERAL_NEWS_URL}' vào {len(all_configs)} ngân hàng...")
#     for conf in all_configs:
#         if GENERAL_NEWS_URL not in conf["urls"]:
#             conf["urls"].append(GENERAL_NEWS_URL)

#     tasks = [process_bank_data(conf) for conf in all_configs]
#     results_list = await asyncio.gather(*tasks)
    
#     data_map = {item['bank_name']: item for item in results_list}
    
#     subject_data = data_map.get(SUBJECT_BANK_CONFIG['name'])
#     if not subject_data or subject_data['status'] != 'success':
#         logger.error(f"CRITICAL ERROR: Không lấy được dữ liệu của {SUBJECT_BANK_CONFIG['name']}. Dừng chương trình.")
#         return

#     output_dir = "outputs"
#     os.makedirs(output_dir, exist_ok=True) 
#     raw_file_path = f"{output_dir}/raw_data_{REPORTING_PERIOD}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json"
    
#     with open(raw_file_path, "w", encoding="utf-8") as f:
#         json.dump(data_map, f, indent=2, ensure_ascii=False)    
#     print(f"Đã lưu dữ liệu thô JSON vào: {raw_file_path}")

#     print("\n" + "-"*80)
#     print("KHỞI TẠO REPORT AGENT (Tạo bảng + Viết phân tích)...")
#     print("-" * 80)
    
#     valid_peers = [
#         item for item in results_list 
#         if item['bank_name'] != SUBJECT_BANK_CONFIG['name'] and item['status'] == 'success'
#     ]

#     if not valid_peers:
#         print("Không có đối thủ nào lấy được dữ liệu để so sánh.")
#         return
#     print("\n" + "-"*80)
#     print("📝 KHỞI TẠO REPORT AGENT...")
#     print("-" * 80)
    
#     reporter = BankingReporterAgent()
    
#     final_full_report = f"# COMPARATIVE ANALYSIS REPORT: {SUBJECT_BANK_CONFIG['name']} vs PEERS\n\n"
#     final_full_report += f"**Reporting Period:** {REPORTING_PERIOD}\n\n"

#     print("Phase 1: Analyzing Individual Banks...")
    
#     for peer in valid_peers:
#         print(f"   - Analyzing {peer['bank_name']}...")
#         highlight = await reporter.generate_individual_highlight(peer)
#         final_full_report += highlight + "\n\n" 
#     print("Phase 2: Generating Market Strategy & Comparison...")
    
#     strategy_section = await reporter.generate_overall_strategy(valid_peers, subject_data)
    
#     final_full_report += "\n" + "="*50 + "\n\n" 
#     final_full_report += strategy_section

#     timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
#     final_path = f"outputs/Final_Full_Report_{REPORTING_PERIOD}_{timestamp}.md"
    
#     with open(final_path, "w", encoding="utf-8") as f:
#         f.write(final_full_report)
        
#     print(f"\nHOÀN TẤT! Báo cáo tổng hợp tại: {final_path}")

# #=============== REPORT TỪ FILE EXTRACTION CÓ SẴN ===============
async def main():
    print("\n" + "="*80)
    print(f"CHẠY REPORT TỪ DỮ LIỆU CÓ SẴN (Skip Extract)")
    print("="*80 + "\n")

    JSON_FILE_PATH = "/Users/ddlyy/agent-competitor/outputs/raw_data_2025_20260210_1432.json" 

    if not os.path.exists(JSON_FILE_PATH):
        print(f"Lỗi: Không tìm thấy file '{JSON_FILE_PATH}'")
        return

    print(f"Đang đọc dữ liệu từ: {JSON_FILE_PATH}...")
    try:
        with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            if isinstance(raw_data, list):
                data_map = {item['bank_name']: item for item in raw_data}
            else:
                data_map = raw_data
                
        print(f"Đã load thành công {len(data_map)} ngân hàng.")
    except Exception as e:
        print(f" Lỗi đọc file JSON: {e}")
        return

    subject_name = SUBJECT_BANK_CONFIG['name']
    subject_data = data_map.get(subject_name)
    
    if not subject_data:
        for k, v in data_map.items():
            if k.lower() == subject_name.lower():
                subject_data = v
                break
    
    if not subject_data: 
        print(f"CRITICAL: Không tìm thấy dữ liệu của {subject_name} trong file.")
        return

    all_items = list(data_map.values())
    valid_peers = [
        item for item in all_items 
        if item['bank_name'] != subject_data['bank_name'] and item.get('status') == 'success'
    ]

    if not valid_peers:
        print("Không tìm thấy đối thủ nào hợp lệ.")
        return

    print(f"Tìm thấy {len(valid_peers)} đối thủ hợp lệ: {[p['bank_name'] for p in valid_peers]}")

    print("\n" + "-"*80)
    print("KHỞI TẠO REPORT AGENT...")
    print("-" * 80)
    
    reporter = BankingReporterAgent()
    
    final_full_report = f"# COMPARATIVE ANALYSIS REPORT:\n"
    final_full_report += f"# {subject_name} vs PEERS\n\n"
    final_full_report += f"**Reporting Period:** {REPORTING_PERIOD}\n"
    final_full_report += f"**Generated Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    def make_id(text):
        return text.strip().lower().replace(" ", "-")

    toc = "## Table of Contents\n\n"
    
    toc += "- [1. Market Landscape & Strategic Actions](#market-strategy)\n"
    
    sub_id = make_id(subject_data['bank_name'])
    toc += f"- [2. {subject_data['bank_name']} (Subject Bank)](#{sub_id})\n"
    
    for i, peer in enumerate(valid_peers, 3):
        p_name = peer['bank_name']
        p_id = make_id(p_name)
        toc += f"- [{i}. {p_name}](#{p_id})\n"
    
    toc += "\n---\n\n"
    
    final_full_report += toc

    print("Phase 1: Generating Market Landscape & Strategic Actions...")
    strategy_section = await reporter.generate_overall_strategy(valid_peers, subject_data)
    
    final_full_report += strategy_section 
    final_full_report += "\n\n" + "="*60 + "\n\n"

    print("Phase 2: Analyzing Individual Banks...")

    print(f"Writing highlight for Subject: {subject_data['bank_name']}...")
    highlight_subject = await reporter.generate_individual_highlight(subject_data)
    final_full_report += highlight_subject + "\n\n---\n\n"

    for peer in valid_peers:
        print(f"Writing highlight for Peer: {peer['bank_name']}...")
        highlight_peer = await reporter.generate_individual_highlight(peer)
        final_full_report += highlight_peer + "\n\n---\n\n"

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    final_path = f"outputs/Final_Report_{REPORTING_PERIOD}_{timestamp}.md"
    
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(final_full_report)
        
    print(f"\nHOÀN TẤT! Báo cáo tổng hợp đã được lưu tại: {final_path}")

#======================= research trước tổng hợp sau================
    # print("\n" + "-"*80)
    # print("KHỞI TẠO REPORT AGENT...")
    # print("-" * 80)
    
    # reporter = BankingReporterAgent()
    
    # final_full_report = f"# COMPARATIVE ANALYSIS REPORT: {SUBJECT_BANK_CONFIG['name']} vs PEERS\n\n"
    # final_full_report += f"**Reporting Period:** {REPORTING_PERIOD}\n"
    # final_full_report += f"**Data Source:** Local File ({os.path.basename(JSON_FILE_PATH)})\n\n"

    # print("Phase 1: Analyzing Individual Banks...")

    # for peer in valid_peers:
    #     print(f"   - Writing highlight for: {peer['bank_name']}...")
    #     highlight = await reporter.generate_individual_highlight(peer)
    #     final_full_report += highlight + "\n\n" 

    # print("Phase 2: Generating Market Strategy & Comparison...")
    
    # strategy_section = await reporter.generate_overall_strategy(valid_peers, subject_data)
    
    # final_full_report += "\n" + "="*50 + "\n\n" 
    # final_full_report += strategy_section

    # timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    # output_filename = f"outputs/Final_Report_From_Local_{timestamp}.md"
    
    # with open(output_filename, "w", encoding="utf-8") as f:
    #     f.write(final_full_report)
        
    # print(f"\nHOÀN TẤT! Báo cáo đã lưu tại: {output_filename}")

##=============== Report TCB vs Peers ===============
#     print(f"Reporter đang xử lý {len(valid_peers)} ngân hàng đối thủ...")

#     reporter = BankingReporterAgent()
    
#     full_report_content = await reporter.generate_full_report(valid_peers, subject_data)

#     timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
#     report_filename = f"Report_{SUBJECT_BANK_CONFIG['ticker']}_vs_Peers_{timestamp}.md"
#     report_path = os.path.join(output_dir, report_filename)
    
#     with open(report_path, "w", encoding="utf-8") as f:
#         f.write(full_report_content)
        
#     print(f"\nHOÀN TẤT! Báo cáo đã được lưu tại:\n {report_path}")
#     print("="*80)

if __name__ == "__main__":
    asyncio.run(main())