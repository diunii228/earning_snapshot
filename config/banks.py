"""
CLI: crawl (daily) | report (từ DB).

  python main.py crawl              # Crawl tất cả bank, upsert vào DB khi có data
  python main.py crawl --date 2026-03-19   # Chạy crawl với target_date tùy chỉnh (dùng cho test hoặc chạy lại kỳ cũ)
  python main.py report             # Đọc DB, gen report so sánh
  python main.py run                # Chạy luôn cả crawl + report trong memory (giữ tương thích cũ)
  python main.py backfill --start "2026-02-02" --end "2026-02-20" --period "Q4 2025"
  CRAWL TỪ BCTC
  export BCTC_EXTRACTOR_ROOT="/Users/ddlyy/Downloads/New_Extract_2feb/base64_BCTC_Extraction"
  export BCTC_PDF_DIR="/Users/ddlyy/Downloads/New_Extract_2feb/base64_BCTC_Extraction/temp_batch_downloads"
  python main.py crawl --period "Q1 2026" 
  python main.py crawl --period "Q1 2026" 2>&1 | grep "\[PDF\]"
  cd /Users/ddlyy/Documents/NCKH/agent-competitor
python -m db.run_migration
python main.py manual-csv --csv /Users/ddlyy/Documents/NCKH/agent-competitor/data_manual.xlsx --period "Q1 2026" --date 2026-04-28


"""
import re
from typing import Dict, List, Optional, Tuple

REPORTING_PERIOD = "Q1 2026"

def parse_reporting_period(period_str: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Bóc tách Năm và Quý từ chuỗi reporting_period.
    VD: "Năm 2025" -> (2025, None)
    VD: "Quý 3 2024", "Q3/2024" -> (2024, 3)
    """
    if not period_str:
        return None, None
        
    year = None
    quarter = None
    
    year_match = re.search(r'\b(20\d{2})\b', period_str)
    if year_match:
        year = int(year_match.group(1))
        
    quarter_match = re.search(r'(?:quý|quy|q)\s*([1-4])\b', period_str.lower())
    if quarter_match:
        quarter = int(quarter_match.group(1))
        
    return year, quarter

GENERAL_NEWS_URL = "https://cafef.vn/tai-chinh-ngan-hang.chn"

SUBJECT_BANK_CONFIG : Dict = {
    "name": "Techcombank", 
    "ticker": "TCB",
    "urls": [
        "https://cafef.vn/techcombank.html",
        "https://finance.vietstock.vn/TCB/tin-tuc-su-kien.htm",
        "https://vneconomy.vn/tim-kiem.html?Text=techcombank",
    ],
}

PEER_BANKS_CONFIG: List[Dict] = [
    {
        "name": "Vietinbank", "ticker": "CTG",
        "urls": ["https://cafef.vn/vietinbank.html", "https://finance.vietstock.vn/CTG/tin-tuc-su-kien.htm",
                 "https://vneconomy.vn/tim-kiem.html?Text=vietinbank","https://www.vietinbank.vn/tin-tuc"],
    },
    {
        "name": "Vietcombank", "ticker": "VCB",
        "urls": [
            "https://cafef.vn/vietcombank.html",
            "https://finance.vietstock.vn/VCB/tin-tuc-su-kien.htm",
            "https://vneconomy.vn/tim-kiem.html?Text=vietcombank"
        ],
    },
    {
        "name": "BIDV", "ticker": "BIDV",
        "urls": ["https://cafef.vn/bidv.html", "https://finance.vietstock.vn/BID/tin-tuc-su-kien.htm",
                 "https://vneconomy.vn/tim-kiem.html?Text=bidv"],
    },
    # {
    #     "name": "Agribank", "ticker": "AGB",
    #     "urls": [
    #         "https://cafef.vn/agribank.html",
    #         "https://finance.vietstock.vn/Agribank/tin-tuc-su-kien.htm",
    #         "https://vneconomy.vn/tim-kiem.html?Text=agribank"
    #     ],
    # },
    {
        "name": "MBBank",
        "ticker": "MBB",
        "urls": [
            "https://cafef.vn/mbb.html",
            "https://finance.vietstock.vn/MBB/tin-tuc-su-kien.htm",
            "https://vneconomy.vn/tim-kiem.html?Text=mbbank"
            ],
    },
    {
        "name": "VPBank",
        "ticker": "VPB",
        "urls": [
            "https://cafef.vn/vpbank.html",
            "https://finance.vietstock.vn/VPB/tin-tuc-su-kien.htm",
            "https://vneconomy.vn/tim-kiem.html?Text=vpbank"
        ],
    },
    {
        "name": "ACB",
        "ticker": "ACB",
        "urls": [
            "https://cafef.vn/acb.html",
            "https://finance.vietstock.vn/ACB/tin-tuc-su-kien.htm",
            "https://vneconomy.vn/tim-kiem.html?Text=acb"
        ],
    },
    # {
    #     "name": "HDBank",
    #     "ticker": "HDB",
    #     "urls": [
    #         "https://cafef.vn/hdbank.html",
    #         "https://finance.vietstock.vn/HDB/tin-tuc-su-kien.htm",
    #         "https://vneconomy.vn/tim-kiem.html?Text=hdbank"
    #     ],
    # }
]

def get_all_bank_configs(include_general_url: bool = True) -> List[Dict]:
    """Trả về [SUBJECT_BANK_CONFIG] + PEER_BANKS_CONFIG, có thể thêm GENERAL_NEWS_URL vào mỗi config."""
    all_configs = [dict(SUBJECT_BANK_CONFIG), *[dict(c) for c in PEER_BANKS_CONFIG]]
    if include_general_url and GENERAL_NEWS_URL:
        for conf in all_configs:
            urls = list(conf.get("urls", []))
            if GENERAL_NEWS_URL not in urls:
                urls.append(GENERAL_NEWS_URL)
            conf["urls"] = urls
    return all_configs
