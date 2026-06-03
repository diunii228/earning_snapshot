"""
Daily Earning Summary Agent

Luồng mới:
- Đọc dữ liệu trực tiếp từ database
- Đọc file .md từ folder summary_md để tạo earning summary (thay vì LLM từ KPI)
- Không dùng PDF/Markdown/Gemini cho KPI table
- Gửi email Daily Earning Summary theo template HTML hiện tại
- Không đính kèm file
- Nếu có lỗi thì dừng và không gửi mail
"""
from langchain_core.messages import HumanMessage
from models.llm_factory import get_llm
import argparse
import asyncio
import html
import logging
import os
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.banks import REPORTING_PERIOD
from db.connection import close_pool
from db.repository import BankKpiSnapshotRepository
from utils.normalize import normalize_banking_kpis

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ── Email style constants ──────────────────────────────────────────────────────
EMAIL_STYLES = {
    "PRIMARY_COLOR": "#E31837",
    "FONT_FAMILY": "'Proxima Nova', 'Segoe UI', Arial, sans-serif",
}

CONFIG = {
    "RECIPIENT_EMAIL": "lydd2@techcombank.com.vn",
    "CC_EMAILS": "",
    "SENDER_NAME": "Banking Market Bot",
    "SENDER_EMAIL": os.environ.get("SENDER_EMAIL", ""),
    "SENDER_PASSWORD": os.environ.get("SENDER_PASSWORD", ""),
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "COMPANY_NAME": "TECHCOMBANK",
    "COMPANY_LOGO_URL": "/Users/ddlyy/Documents/NCKH/agent-competitor/Logo-TCB-H-1024x341.webp",
    # Folder chứa các file .md tóm tắt BCTC, ví dụ: summary_md/TCB_Q1_2026.md
    "SUMMARY_MD_DIR": os.environ.get("SUMMARY_MD_DIR", "summary_md"),
}


BANK_SPECS = [
    {"ticker": "TCB", "name": "Techcombank", "aliases": {"tcb", "techcombank"}, "homepage": "https://techcombank.com/nha-dau-tu/thong-tin-tai-chinh/bao-cao-tai-chinh-vas"},
    {"ticker": "VCB", "name": "Vietcombank", "aliases": {"vcb", "vietcombank"}, "homepage": "https://www.vietcombank.com.vn/vi-VN/Nha-dau-tu"},
    {"ticker": "CTG", "name": "Vietinbank", "aliases": {"ctg", "vietinbank"}, "homepage": "https://investor.vietinbank.vn/vi/download.aspx/-/categories/471001"},
    {"ticker": "BID", "name": "BIDV", "aliases": {"bid", "bidv"}, "homepage": "https://bidv.com.vn/vn/quan-he-nha-dau-tu/bao-cao-va-tai-lieu/"},
    {"ticker": "MBB", "name": "MBBank", "aliases": {"mbb", "mbbank", "mb"}, "homepage": "https://www.mbbank.com.vn/Investor/nha-dau-tu"},
    {"ticker": "VPB", "name": "VPBank", "aliases": {"vpb", "vpbank"}, "homepage": "https://www.vpbank.com.vn/quan-he-nha-dau-tu/bao-cao-tai-chinh"},
    {"ticker": "ACB", "name": "ACB", "aliases": {"acb"}, "homepage": "https://acb.com.vn/nha-dau-tu/bao-cao-tai-chinh"},
]


KPI_SPECS = [
    {"id": "pbt", "label": "PBT", "unit": "trillion VND", "kind": "money", "aliases": ["pbt", "profit_before_tax"]},
    {"id": "pbt_growth", "label": "PBT growth (YoY)", "unit": "%", "kind": "percent", "aliases": ["pbt_growth", "pbt_growth_yoy", "profit_before_tax_growth"]},
    {"id": "toi", "label": "TOI", "unit": "trillion VND", "kind": "money", "aliases": ["toi", "total_operating_income", "operating_income"]},
    {"id": "toi_growth", "label": "TOI growth (YoY)", "unit": "%", "kind": "percent", "aliases": ["toi_growth", "toi_growth_yoy", "total_operating_income_growth"]},
    {"id": "nii", "label": "NII", "unit": "trillion VND", "kind": "money", "aliases": ["net_interest_income", "nii"]},
    {"id": "nii_growth", "label": "NII growth (YoY)", "unit": "%", "kind": "percent", "aliases": ["nii_growth", "nii_growth_yoy", "net_interest_income_growth"]},
    {"id": "nim", "label": "NIM", "unit": "%", "kind": "percent", "aliases": ["nim", "net_interest_margin"]},
    {"id": "casa", "label": "CASA", "unit": "%", "kind": "percent", "aliases": ["casa_ratio", "casa"]},
    {"id": "casa_growth", "label": "CASA growth (YTD)", "unit": "%", "kind": "percent", "aliases": ["casa_growth_ytd"]},
    {"id": "total_deposit", "label": "Total Deposit", "unit": "trillion VND", "kind": "money", "aliases": ["total_deposits", "total_deposit"]},
    {"id": "deposit_growth", "label": "Deposit growth (YTD)", "unit": "%", "kind": "percent", "aliases": ["deposit_growth_ytd"]},
    {"id": "total_credit", "label": "Total Credit", "unit": "trillion VND", "kind": "money", "aliases": ["total_credit"]},
    {"id": "credit_growth", "label": "Credit growth (YTD)", "unit": "%", "kind": "percent", "aliases": ["credit_growth_ytd"]},
    {"id": "opex", "label": "Operating Expenses", "unit": "trillion VND", "kind": "money", "aliases": ["opex", "operating_expenses", "operation_expenses"]},
    {"id": "cir", "label": "Cost-to-Income Ratio", "unit": "%", "kind": "percent", "aliases": ["cost_to_income_ratio", "cir"]}
]


EXACT_KPI_MAP = {
    "pe": "p_e_ratio",
    "p_e": "p_e_ratio",
    "pb": "p_b_ratio",
    "p_b": "p_b_ratio",
    "npl": "npl_ratio",
    "casa": "casa_ratio",
    "toi": "total_operating_income",
    "operating_income": "total_operating_income",
    "profit_before_tax": "pbt",
    "profit_after_tax": "pat",
    "net_profit": "pat",
    "net_interest_margin": "nim",
    "cost_to_income_ratio": "cir",
    "operating_expenses": "opex",
    "operation_expenses": "opex",
    "casa_growth_ytd": "casa_growth_ytd",
    # growth aliases
    "profit_before_tax_growth": "pbt_growth",
    "pbt_growth_yoy": "pbt_growth",
    "total_operating_income_growth": "toi_growth",
    "toi_growth_yoy": "toi_growth",
    "net_interest_income_growth": "nii_growth",
    "nii_growth_yoy": "nii_growth",
}


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _normalize_kpi_key(raw_kpi_name: str) -> str:
    key = str(raw_kpi_name).lower().strip().replace(" ", "_").replace("-", "_")
    return EXACT_KPI_MAP.get(key, key)


def _bank_lookup() -> Dict[str, Dict[str, Any]]:
    lookup = {}
    for spec in BANK_SPECS:
        for alias in spec["aliases"]:
            lookup[alias] = spec
    return lookup


BANK_LOOKUP = _bank_lookup()


def _canonical_bank_spec(bank_name: str = "", ticker: str = "") -> Optional[Dict[str, Any]]:
    candidates = [str(ticker or "").strip().lower(), str(bank_name or "").strip().lower()]
    for candidate in candidates:
        if candidate in BANK_LOOKUP:
            return BANK_LOOKUP[candidate]
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "-", "N/A", "null"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _flatten_kpis(extracted_kpis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized = normalize_banking_kpis(extracted_kpis or {}) or {}
    flat: Dict[str, Dict[str, Any]] = {}
    for category, section in normalized.items():
        if not isinstance(section, dict):
            continue
        for raw_name, details in section.items():
            if not isinstance(details, dict):
                continue
            canonical = _normalize_kpi_key(raw_name)
            value = details.get("value")
            if value in (None, "", "-", "N/A", "null"):
                continue
            source_url = details.get("source_url", "")
            if isinstance(source_url, list):
                source_url = next((str(u).strip() for u in source_url if str(u).strip()), "")
            flat[canonical] = {
                "category": category,
                "value": value,
                "unit": details.get("unit", ""),
                "source_url": str(source_url or "").strip(),
                "source_quote": str(details.get("source_quote", "") or "").strip(),
                "source_type": str(details.get("source_type", "") or "").strip(),
                "reasoning": str(details.get("reasoning", "") or "").strip(),
            }
    return flat


def _insight_text(entry: Dict[str, Any], max_len: int = 160) -> str:
    text = (entry.get("reasoning") or "").strip()
    if not text:
        text = (entry.get("source_quote") or "").strip()
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _render_exec_lines(lines: List[str], font: str, muted: str) -> str:
    return "".join(
        f'<p style="margin:6px 0 0 28px;font-size:12px;line-height:20px;'
        f'color:{muted};font-family:{font};">{_e(line)}</p>'
        for line in lines
    )


def _find_kpi(flat_map: Dict[str, Dict[str, Any]], spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for alias in spec["aliases"]:
        if alias in flat_map:
            return flat_map[alias]
    return None


def _format_money_trillion(value: Any, unit: str) -> Optional[str]:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    unit_lower = str(unit or "").lower()
    if "trillion" in unit_lower:
        trillion_value = numeric
    elif "billion" in unit_lower:
        trillion_value = numeric / 1000
    elif "million" in unit_lower:
        trillion_value = numeric / 1_000_000
    elif unit_lower in ("vnd", "dong", "đ", ""):
        trillion_value = numeric / 1_000_000_000_000
    else:
        trillion_value = numeric / 1000
    return f"{trillion_value:,.1f}".rstrip("0").rstrip(".")


def _format_percent(value: Any) -> Optional[str]:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    text = f"{numeric:,.1f}".rstrip("0").rstrip(".")
    return f"{text}"


def _format_cell_value(kpi_spec: Dict[str, Any], entry: Optional[Dict[str, Any]]) -> Optional[str]:
    if not entry:
        return None
    if kpi_spec["kind"] == "money":
        return _format_money_trillion(entry.get("value"), entry.get("unit", ""))
    if kpi_spec["kind"] == "percent":
        formatted = _format_percent(entry.get("value"))
        return formatted
    value = entry.get("value")
    return None if value in (None, "", "-", "N/A", "null") else str(value)


class SourceIndexer:
    def __init__(self):
        self._url_to_idx: Dict[str, int] = {}

    def tag(self, url: str) -> str:
        url = str(url or "").strip()
        if not url:
            return ""
        if url not in self._url_to_idx:
            self._url_to_idx[url] = len(self._url_to_idx) + 1
        idx = self._url_to_idx[url]
        return f'<a href="{html.escape(url)}" target="_blank" style="color:inherit;text-decoration:none;">[{idx}]</a>'

    def render_links_html(self, muted: str) -> str:
        if not self._url_to_idx:
            return ""
        rows = []
        for url, idx in sorted(self._url_to_idx.items(), key=lambda item: item[1]):
            rows.append(
                f'<p style="margin:0 0 6px 0;font-size:11px;line-height:18px;color:{muted};font-family:{EMAIL_STYLES["FONT_FAMILY"]};">'
                f'[{idx}] <a href="{html.escape(url)}" target="_blank" style="color:{muted};text-decoration:underline;">{html.escape(url)}</a>'
                f'</p>'
            )
        return "".join(rows)


def _is_bctc_source(url: str, source_type: str = "") -> bool:
    source_type = str(source_type or "").strip().lower()
    if source_type in ("financial_statement_pdf", "manual_override"):
        return True
    url = str(url or "").strip().lower()
    return url.startswith("file://") or ".pdf" in url


def _source_kind(url: str, source_type: str = "") -> str:
    return "FS" if _is_bctc_source(url, source_type) else "WEB"


def _normalize_reference_url(url: str, bank_spec: Dict[str, Any], source_type: str = "") -> str:
    clean = str(url or "").strip()
    if not clean:
        return str(bank_spec.get("homepage", "") or "")
    if _is_bctc_source(clean, source_type):
        return str(bank_spec.get("homepage", "") or clean)
    return clean


def _render_value_markup(value_text: str, source_url: str, source_tag: str, source_type: str = "") -> str:
    source_kind = _source_kind(source_url, source_type)
    if source_kind == "WEB":
        star = "*" if source_tag else "*"
        content = f"{_e(value_text)}"
        if source_tag:
            content += f" {source_tag}{star}"
        else:
            content += star
        return f"<i>{content}</i>"

    content = _e(value_text)
    if source_tag:
        content += f" {source_tag}"
    return content


def _first_non_empty_url(*url_lists: List[str]) -> str:
    for url_list in url_lists:
        if not url_list:
            continue
        for item in url_list:
            if str(item or "").strip():
                return str(item).strip()
    return ""


def _bank_homepage_if_bctc(bank_spec: Dict[str, Any], flat_map: Dict[str, Dict[str, Any]], fallback_url: str) -> str:
    try:
        if any(
            str(v.get("source_type", "") or "").strip().lower() in ("financial_statement_pdf", "manual_override")
            for v in (flat_map or {}).values()
            if isinstance(v, dict)
        ):
            return str(bank_spec.get("homepage", "") or fallback_url)
    except Exception:
        pass
    return fallback_url


def _bank_heading_html(bank_ticker: str, reporting_period: str, url: str, ink: str) -> str:
    label = f"[{bank_ticker}] {reporting_period} earning highlights"
    if url:
        return f'<a href="{html.escape(url)}" target="_blank" style="color:{ink};text-decoration:underline;">{label}</a>'
    return _e(label)


def _strong(text: str) -> str:
    return f"<strong>{_e(text)}</strong>"


# ── summary_md helpers ─────────────────────────────────────────────────────────

def _find_summary_md_file(ticker: str, reporting_period: str, summary_md_dir: str) -> Optional[Path]:
    """
    Tìm file .md trong folder summary_md theo ticker và period.
    Ưu tiên match cả ticker lẫn period, fallback chỉ ticker.
    Ví dụ: summary_md/TCB_Q1_2026.md hoặc summary_md/tcb_q1_2026.md
    """
    base = Path(summary_md_dir)
    if not base.exists():
        return None

    # Chuẩn hoá period thành slug để match tên file: "Q1 2026" -> "Q1_2026"
    period_slug = re.sub(r"[\s\-/]+", "_", reporting_period.strip()).upper()
    ticker_upper = ticker.upper()

    # Thứ tự ưu tiên tìm kiếm
    candidates = [
        base / f"{ticker_upper}_{period_slug}.md",
        base / f"{ticker_upper}_{period_slug}.MD",
        base / f"{ticker_upper.lower()}_{period_slug.lower()}.md",
    ]
    for path in candidates:
        if path.exists():
            return path

    # Fallback: bất kỳ file nào bắt đầu bằng ticker (ưu tiên mới nhất)
    matches = sorted(base.glob(f"{ticker_upper}*.md"), reverse=True)
    if not matches:
        matches = sorted(base.glob(f"{ticker_upper.lower()}*.md"), reverse=True)
    return matches[0] if matches else None


def _read_summary_md(path: Path) -> str:
    """Đọc nội dung file md, trả về string rỗng nếu lỗi."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        log.warning("Cannot read summary md %s: %s", path, exc)
        return ""


def _md_to_plain_paragraphs(md_text: str) -> List[str]:
    """
    Chuyển markdown đơn giản thành list các đoạn văn thuần, loại bỏ:
    - Heading (#, ##, ###)
    - Bullet/numbered list markers (-, *, 1.)
    - Bold/italic markers (**text**, *text*, __text__)
    - Blank lines thừa
    Trả về list tối đa 5 đoạn không rỗng.
    """
    lines = md_text.splitlines()
    paragraphs: List[str] = []
    current: List[str] = []

    for raw_line in lines:
        # Bỏ heading
        line = re.sub(r"^#{1,6}\s+", "", raw_line.strip())
        # Bỏ bullet / numbered list markers
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        # Bỏ bold/italic
        line = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", line)
        line = re.sub(r"_{1,2}(.*?)_{1,2}", r"\1", line)
        # Bỏ inline code
        line = re.sub(r"`+([^`]*)`+", r"\1", line)
        # Bỏ link markdown [text](url)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)

        line = line.strip()
        if line:
            current.append(line)
        else:
            if current:
                paragraphs.append(" ".join(current))
                current = []

    if current:
        paragraphs.append(" ".join(current))

    # Lọc bỏ đoạn quá ngắn (< 30 ký tự, thường là tiêu đề còn sót)
    paragraphs = [p for p in paragraphs if len(p) >= 30]
    return paragraphs[:5]


async def _summarize_md_with_llm(
    bank_name: str,
    ticker: str,
    md_text: str,
) -> str:
    """
    Dùng LLM để tóm tắt nội dung file .md BCTC thành 3-5 câu executive summary.
    Trả về HTML string hoặc "" nếu lỗi.
    """
    # Giới hạn input để tránh vượt context
    truncated = md_text[:4000] if len(md_text) > 4000 else md_text

    prompt = f"""Bạn là chuyên gia phân tích tài chính ngân hàng. Dưới đây là bản tóm tắt báo cáo tài chính (BCTC) của {bank_name} ({ticker}).

Hãy viết 1 đoạn executive summary ngắn gọn dựa trên nội dung này.

Yêu cầu:
- NGẮN GỌN NHẤT CÓ THỂ, đúng 2-3 câu, không bullet point, không tiêu đề.
- Nêu rõ các KPI chính (PBT, TOI/NII, NIM, CASA, tăng trưởng tín dụng/huy động) tăng hay giảm và so sánh với kỳ trước/đầu năm nếu có.
- Nêu ngắn gọn nguyên nhân tăng/giảm nếu BCTC đề cập, nếu không có thông tin thì không được bịa.
- Giọng văn trung lập, chuyên nghiệp, phong cách analyst report.
- Viết bằng tiếng Anh.

NỘI DUNG BCTC:
{truncated}

Executive summary:"""

    try:
        llm = get_llm(temperature=0.1, top_p=0.3, max_tokens=300)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        summary_text = ""
        if isinstance(response.content, str):
            summary_text = response.content.strip()
        elif isinstance(response.content, list):
            summary_text = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in response.content
            ).strip()
        return summary_text
    except Exception as exc:
        log.warning("[%s] LLM summarize error: %s", ticker, exc)
        return ""


def _render_summary_block(summary_text: str, ink: str) -> str:
    """Render executive summary thành HTML block."""
    if not summary_text:
        return ""
    accent = EMAIL_STYLES["PRIMARY_COLOR"]
    font = EMAIL_STYLES["FONT_FAMILY"]
    return (
        f'<div style="margin:0 0 12px 0;padding:10px 14px;'
        f'background:#fdf2f4;border-left:3px solid {accent};'
        f'border-radius:3px;font-size:12px;line-height:19px;'
        f'color:#374151;font-family:{font};font-style:italic;">'
        f'{html.escape(summary_text)}'
        f'</div>'
    )


def _derive_bank_rows(
    snapshots: List[Dict[str, Any]],
    cumulative_rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {
        spec["ticker"]: {
            "ticker": spec["ticker"],
            "bank_name": spec["name"],
            "snapshot": None,
            "current_flat": {},
            "previous_flat": {},
            "latest_flat": {},
            "source_urls": [],
            "new_kpis": set(),
            "upgraded_kpis": set(),
            "is_new_bank": False,
        }
        for spec in BANK_SPECS
    }

    for snapshot in snapshots:
        spec = _canonical_bank_spec(snapshot.get("bank_name", ""), snapshot.get("ticker", ""))
        if not spec or spec["ticker"] not in rows:
            continue
        current_flat = _flatten_kpis(snapshot.get("extracted_kpis", {}) or {})
        previous_flat = _flatten_kpis(snapshot.get("previous_extracted_kpis", {}) or {})
        row = rows[spec["ticker"]]
        row["snapshot"] = snapshot
        row["current_flat"] = current_flat
        row["previous_flat"] = previous_flat
        row["source_urls"] = list(snapshot.get("article_links", []) or [])
        row["is_new_bank"] = bool(current_flat) and not snapshot.get("previous_snapshot_id")

        new_kpis = set()
        upgraded_kpis = set()
        for kpi_spec in KPI_SPECS:
            current_entry = _find_kpi(current_flat, kpi_spec)
            previous_entry = _find_kpi(previous_flat, kpi_spec)
            if current_entry and not previous_entry:
                new_kpis.add(kpi_spec["id"])
            elif current_entry and previous_entry:
                current_kind = _source_kind(
                    current_entry.get("source_url", ""),
                    current_entry.get("source_type", ""),
                )
                previous_kind = _source_kind(
                    previous_entry.get("source_url", ""),
                    previous_entry.get("source_type", ""),
                )
                if previous_kind == "WEB" and current_kind == "FS":
                    upgraded_kpis.add(kpi_spec["id"])
        if row["is_new_bank"]:
            for kpi_spec in KPI_SPECS:
                if _find_kpi(current_flat, kpi_spec):
                    new_kpis.add(kpi_spec["id"])
        row["new_kpis"] = new_kpis
        row["upgraded_kpis"] = upgraded_kpis

    for item in cumulative_rows:
        spec = _canonical_bank_spec(item.get("bank_name", ""), item.get("ticker", ""))
        if not spec or spec["ticker"] not in rows:
            continue
        row = rows[spec["ticker"]]
        row["latest_flat"] = _flatten_kpis(item.get("extracted_kpis", {}) or {})
        row["source_urls"] = list(item.get("source_urls", []) or row["source_urls"])

    return rows


def _is_first_period_run(bank_rows: Dict[str, Dict[str, Any]]) -> bool:
    return not any(
        row["snapshot"] and row["snapshot"].get("previous_snapshot_id")
        for row in bank_rows.values()
    )


# ── Core: build earning summary HTML từ summary_md ────────────────────────────

async def build_earning_summary_html(
    bank_rows: Dict[str, Dict[str, Any]],
    reporting_period: str,
    source_indexer: SourceIndexer,
    line: str,
    soft: str,
    ink: str,
    muted: str,
    summary_md_dir: str = "",
) -> str:
    font = EMAIL_STYLES["FONT_FAMILY"]
    is_first_run = _is_first_period_run(bank_rows)

    blocks: List[str] = []
    for spec in BANK_SPECS:
        ticker = spec["ticker"]
        row = bank_rows.get(ticker) or {}
        current_flat = row.get("current_flat") or {}
        latest_flat = row.get("latest_flat") or {}

        has_update = bool(row.get("new_kpis") or row.get("upgraded_kpis"))
        if not is_first_run and not has_update:
            continue

        flat_for_link = current_flat or latest_flat
        link_url = _bank_homepage_if_bctc(spec, flat_for_link, spec.get("homepage", ""))
        heading = _bank_heading_html(ticker, reporting_period, link_url, ink)

        exec_lines: List[str] = []
        for key in (
            "pbt",
            "total_operating_income",
            "net_interest_income",
            "total_credit",
            "credit_growth_ytd",
            "total_deposits",
            "deposit_growth_ytd",
            "nim",
            "casa_ratio",
        ):
            entry = current_flat.get(key)
            if isinstance(entry, dict):
                text = _insight_text(entry)
                if text:
                    exec_lines.append(text)
            if len(exec_lines) >= 3:
                break

        if not exec_lines:
            continue

        blocks.append(
            f'<div style="margin-bottom:22px;">'
            f'<p style="margin:0 0 8px 0;font-size:15px;line-height:22px;font-weight:bold;'
            f'color:{ink};font-family:{font};">{heading}:</p>'
            f'{_render_exec_lines(exec_lines, font, muted)}'
            f'</div>'
        )

    if not blocks:
        note = "Scanned the latest database snapshots and found no additional KPI update."
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {line};background-color:{soft};">'
            f'<tr><td style="padding:18px 20px;">'
            f'<p style="margin:0;font-size:14px;line-height:22px;color:{ink};font-family:{font};">{note}</p>'
            f'</td></tr></table>'
        )

    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {line};background-color:#ffffff;">'
        f'<tr><td style="padding:20px 22px;">{"".join(blocks)}</td></tr></table>'
    )


def build_kpi_table_html(
    bank_rows: Dict[str, Dict[str, Any]],
    source_indexer: SourceIndexer,
    line: str,
    soft: str,
    ink: str,
    muted: str,
    is_first_run: bool,
) -> str:
    font = EMAIL_STYLES["FONT_FAMILY"]
    header_cells = [
        f'<td style="padding:10px 12px;background-color:{soft};border-bottom:1px solid {line};font-size:11px;font-weight:bold;color:{muted};text-transform:uppercase;font-family:{font};">KPI</td>',
        f'<td style="padding:10px 12px;background-color:{soft};border-bottom:1px solid {line};font-size:11px;font-weight:bold;color:{muted};text-transform:uppercase;font-family:{font};">Unit</td>',
    ]
    for spec in BANK_SPECS:
        bank_row = bank_rows[spec["ticker"]]
        header_bg = "#fff4df" if bank_row["is_new_bank"] else soft
        header_cells.append(
            f'<td style="padding:10px 12px;background-color:{header_bg};border-bottom:1px solid {line};font-size:11px;font-weight:bold;color:{muted};text-transform:uppercase;text-align:right;font-family:{font};">{spec["ticker"]}</td>'
        )

    body_rows: List[str] = []
    for kpi_spec in KPI_SPECS:
        row_cells = [
            f'<td style="padding:10px 12px;border-bottom:1px solid {line};font-size:12px;font-weight:bold;color:{ink};font-family:{font};">{_e(kpi_spec["label"])}</td>',
            f'<td style="padding:10px 12px;border-bottom:1px solid {line};font-size:12px;color:{muted};font-family:{font};">{_e(kpi_spec["unit"])}</td>',
        ]
        for bank_spec in BANK_SPECS:
            bank_row = bank_rows[bank_spec["ticker"]]
            entry = _find_kpi(bank_row["latest_flat"], kpi_spec)
            value_text = _format_cell_value(kpi_spec, entry)
            source_url = entry.get("source_url", "") if entry else ""
            source_type = entry.get("source_type", "") if entry else ""
            normalized_source_url = _normalize_reference_url(source_url, bank_spec, source_type)
            source_tag = source_indexer.tag(normalized_source_url) if entry else ""
            display = "&mdash;"
            if value_text:
                display = _render_value_markup(value_text, source_url, source_tag, source_type)

            is_new_cell = False
            if is_first_run:
                is_new_cell = bank_row["is_new_bank"] or kpi_spec["id"] in bank_row["new_kpis"]
            else:
                is_new_cell = kpi_spec["id"] in bank_row["new_kpis"] or kpi_spec["id"] in bank_row["upgraded_kpis"]
            cell_bg = "background-color:#fff4df;" if is_new_cell and value_text else ""
            row_cells.append(
                f'<td style="padding:10px 12px;border-bottom:1px solid {line};font-size:12px;color:{ink};text-align:right;font-family:{font};{cell_bg}">{display}</td>'
            )
        body_rows.append(f'<tr>{"".join(row_cells)}</tr>')

    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {line};">'
        f'<tr>{"".join(header_cells)}</tr>'
        f'{"".join(body_rows)}'
        f'</table>'
    )


async def build_email_html(
    reporting_period: str,
    bank_rows: Dict[str, Dict[str, Any]],
    latest_target_date: str,
    summary_md_dir: str = "",
) -> str:
    accent = EMAIL_STYLES["PRIMARY_COLOR"]
    font = EMAIL_STYLES["FONT_FAMILY"]
    ink = "#1f2937"
    muted = "#6b7280"
    line = "#e5e7eb"
    soft = "#f8fafc"
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    header_title = "Daily Earning Summary"
    source_indexer = SourceIndexer()
    is_first_run = _is_first_period_run(bank_rows)

    def spacer(height: int) -> str:
        return f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td height="{height}" style="font-size:1px;line-height:1px;">&nbsp;</td></tr></table>'

    def section_label(text: str) -> str:
        return (
            f'<p style="margin:0 0 14px 0;font-size:11px;font-weight:bold;letter-spacing:1.2px;'
            f'text-transform:uppercase;color:{accent};font-family:{font};">{_e(text)}</p>'
        )

    summary_html = await build_earning_summary_html(
        bank_rows, reporting_period, source_indexer, line, soft, ink, muted,
        summary_md_dir=summary_md_dir or CONFIG.get("SUMMARY_MD_DIR", "summary_md"),
    )
    kpi_table_html = build_kpi_table_html(bank_rows, source_indexer, line, soft, ink, muted, is_first_run)
    notes_html = (
        f'<p style="margin:0 0 4px 0;font-size:11px;line-height:18px;color:{muted};font-family:{font};">'
        f'Default figures are sourced from published financial statements.</p>'
        f'<p style="margin:0;font-size:11px;line-height:18px;color:{muted};font-family:{font};">'
        f'<i>Italic figures marked with *</i> are scraped from web sources pending financial statement confirmation.</p>'
    )

    logo_section = (
        f'<img src="{CONFIG["COMPANY_LOGO_URL"]}" height="26" alt="{CONFIG["COMPANY_NAME"]}" style="height:26px;display:block;border:0;">'
        if CONFIG["COMPANY_LOGO_URL"]
        else f'<span style="font-size:12px;font-weight:bold;color:{ink};letter-spacing:1.4px;font-family:{font};">{CONFIG["COMPANY_NAME"]}</span>'
    )

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{header_title}</title>
<style type="text/css">
  body,table,td,p,a,span{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
  table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;}}
  img{{-ms-interpolation-mode:bicubic;border:0;outline:none;text-decoration:none;display:block;}}
</style>
</head>
<body style="margin:0;padding:0;background-color:#ffffff;font-family:{font};">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background-color:#ffffff;">
  <tr>
    <td align="center" style="padding:0 16px;">
      <table width="96%" cellpadding="0" cellspacing="0" border="0" style="width:96%;background-color:#ffffff;">
        <tr>
          <td style="padding:0;border-top:4px solid {accent};border-bottom:1px solid {line};background-color:#ffffff;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;">
              <tr>
                <td style="padding:24px 28px 10px 28px;vertical-align:middle;">{logo_section}</td>
                <td style="padding:24px 28px 10px 28px;text-align:right;vertical-align:middle;font-size:10px;line-height:14px;color:{muted};font-family:{font};text-transform:uppercase;">AI Report</td>
              </tr>
              <tr>
                <td colspan="2" style="padding:0 28px 24px 28px;">
                  <p style="margin:0 0 14px 0;font-size:28px;line-height:36px;font-weight:bold;color:{ink};font-family:{font};">{header_title}</p>
                  <table cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="padding:0 20px 0 0;vertical-align:top;">
                        <p style="margin:0 0 4px 0;font-size:10px;line-height:14px;color:{muted};text-transform:uppercase;font-family:{font};">Period</p>
                        <p style="margin:0;font-size:13px;line-height:18px;font-weight:bold;color:{ink};font-family:{font};">{_e(reporting_period)}</p>
                      </td>
                      <td style="padding:0 20px;border-left:1px solid {line};vertical-align:top;">
                        <p style="margin:0 0 4px 0;font-size:10px;line-height:14px;color:{muted};text-transform:uppercase;font-family:{font};">Snapshot Date</p>
                        <p style="margin:0;font-size:13px;line-height:18px;font-weight:bold;color:{ink};font-family:{font};">{_e(latest_target_date or "—")}</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:28px;background-color:#ffffff;">
            {section_label("Earning Summary")}
            {summary_html}
            {spacer(24)}
            {section_label("Earning Snapshot")}
            {kpi_table_html}
            {spacer(12)}
            {notes_html}
            {spacer(24)}
            {source_indexer.render_links_html(muted)}
          </td>
        </tr>

        <tr>
          <td style="padding:18px 28px;border-top:1px solid {line};background-color:#ffffff;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;">
              <tr>
                <td style="font-size:11px;line-height:16px;color:{muted};font-family:{font};">{CONFIG["COMPANY_NAME"]} | Daily Earning Summary | Database source</td>
                <td style="font-size:11px;line-height:16px;color:{muted};font-family:{font};text-align:right;">Do not reply</td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _smtp_send(msg: MIMEMultipart) -> None:
    import smtplib

    with smtplib.SMTP(CONFIG["SMTP_HOST"], CONFIG["SMTP_PORT"]) as server:
        server.ehlo()
        server.starttls()
        server.login(CONFIG["SENDER_EMAIL"], CONFIG["SENDER_PASSWORD"])
        recipients = [CONFIG["RECIPIENT_EMAIL"]]
        if CONFIG["CC_EMAILS"]:
            recipients += [email.strip() for email in CONFIG["CC_EMAILS"].split(",") if email.strip()]
        server.sendmail(CONFIG["SENDER_EMAIL"], recipients, msg.as_string())


def send_summary_email(html_body: str, reporting_period: str) -> None:
    subject = f"Daily Earning Summary — {reporting_period} — {datetime.now().strftime('%d/%m/%Y')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f'{CONFIG["SENDER_NAME"]} <{CONFIG["SENDER_EMAIL"]}>'
    msg["To"] = CONFIG["RECIPIENT_EMAIL"]
    if CONFIG["CC_EMAILS"]:
        msg["Cc"] = CONFIG["CC_EMAILS"]
    msg.attach(MIMEText(html_body, "html"))

    _smtp_send(msg)
    log.info("📨 Email sent to: %s", CONFIG["RECIPIENT_EMAIL"])


async def build_daily_earning_payload(reporting_period: str, summary_md_dir: str = "") -> Dict[str, Any]:
    repo = BankKpiSnapshotRepository()
    snapshots = await repo.get_latest_snapshots_with_previous(reporting_period)
    cumulative_rows = await repo.get_latest_by_period(reporting_period)

    if not snapshots and not cumulative_rows:
        raise ValueError(f"Không có dữ liệu trong database cho kỳ {reporting_period}.")

    bank_rows = _derive_bank_rows(snapshots, cumulative_rows)

    latest_dates = []
    for row in bank_rows.values():
        snapshot = row.get("snapshot")
        if snapshot and snapshot.get("target_date"):
            latest_dates.append(snapshot["target_date"])
    latest_target_date = max(latest_dates) if latest_dates else datetime.now().strftime("%Y-%m-%d")

    html_body = await build_email_html(
        reporting_period, bank_rows, latest_target_date,
        summary_md_dir=summary_md_dir,
    )
    return {
        "reporting_period": reporting_period,
        "latest_target_date": latest_target_date,
        "html_body": html_body,
    }


async def run_daily_earning_summary_agent(reporting_period: str, summary_md_dir: str = "") -> None:
    if not CONFIG["SENDER_EMAIL"] or not CONFIG["SENDER_PASSWORD"]:
        raise ValueError("Thiếu SENDER_EMAIL hoặc SENDER_PASSWORD để gửi SMTP.")

    payload = await build_daily_earning_payload(reporting_period, summary_md_dir=summary_md_dir)
    send_summary_email(payload["html_body"], payload["reporting_period"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Daily Earning Summary email from database snapshots.")
    parser.add_argument("--period", default=REPORTING_PERIOD, help="Reporting period, ví dụ: Q1 2026")
    parser.add_argument("--to", default="", help="Override RECIPIENT_EMAIL")
    parser.add_argument("--cc", default="", help="Override CC_EMAILS")
    parser.add_argument(
        "--summary-md-dir", default="",
        help="Folder chứa file .md tóm tắt BCTC (default: summary_md hoặc SUMMARY_MD_DIR env var)"
    )
    parser.add_argument("--input", default="", help="Ignored. This agent now reads directly from database.")
    parser.add_argument("--dir", default="", help="Ignored. This agent now reads directly from database.")
    return parser.parse_args()


async def _amain() -> int:
    args = parse_args()
    if args.to.strip():
        CONFIG["RECIPIENT_EMAIL"] = args.to.strip()
    if args.cc.strip():
        CONFIG["CC_EMAILS"] = args.cc.strip()
    if args.input.strip() or args.dir.strip():
        log.warning("⚠️ --input/--dir are ignored. banking_summary_agent.py now reads directly from database.")

    summary_md_dir = getattr(args, "summary_md_dir", "").strip() or CONFIG.get("SUMMARY_MD_DIR", "summary_md")

    try:
        log.info("🚀 Starting Daily Earning Summary Agent...")
        log.info("📂 summary_md dir: %s", summary_md_dir)
        await run_daily_earning_summary_agent(args.period, summary_md_dir=summary_md_dir)
        log.info("✅ Daily Earning Summary complete.")
        return 0
    except Exception as exc:
        log.error("❌ Error: %s", exc)
        return 1
    finally:
        await close_pool()


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
