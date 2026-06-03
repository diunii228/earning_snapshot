# scripts/rerunpdf.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
Chạy PDF extract → upsert fs_components vào bank_fs_components.
Không động vào web crawl, không chạy lại toàn bộ main.py.

Usage:
    python scripts/rerunpdf.py              # dùng cache nếu PDF không đổi
    python scripts/rerunpdf.py --force      # force re-extract, bỏ qua cache
"""
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime

from jobs.financial_statement_ingest import extract_pdf_kpis_for_bank, MANIFEST_PATH
from utils.setting import get_settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BANKS = [
    {"name": "acb",         "ticker": "ACB"},
    {"name": "techcombank", "ticker": "TCB"},
    {"name": "vpbank",      "ticker": "VPB"},
    {"name": "mbbank",      "ticker": "MBB"},
    {"name": "vietcombank", "ticker": "VCB"},
    {"name": "bidv",        "ticker": "BIDV"},
    {"name": "vietinbank",     "ticker": "CTG"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  🗓️  PERIOD HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_quarter(dt: datetime) -> str:
    """Trả về chuỗi quarter chuẩn, ví dụ '2025-Q1'."""
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def _parse_reporting_year_quarter(period: str):
    """
    Parse reporting_period string → (year, quarter).

    Các format phổ biến:
        "2025-Q1"       → (2025, 1)
        "Q1/2025"       → (2025, 1)
        "31/03/2025"    → (2025, 1)
        "2025"          → (2025, None)
    Trả về (None, None) nếu không parse được.
    """
    import re

    if not period:
        return None, None

    # "2025-Q1" hoặc "2025-Q01"
    m = re.match(r"(\d{4})-Q(\d{1,2})", period)
    if m:
        return int(m.group(1)), int(m.group(2))

    # "Q1/2025"
    m = re.match(r"Q(\d{1,2})[/\-](\d{4})", period)
    if m:
        return int(m.group(2)), int(m.group(1))

    # "31/03/2025" hoặc "31-03-2025"
    m = re.match(r"\d{1,2}[/\-](\d{1,2})[/\-](\d{4})", period)
    if m:
        month = int(m.group(1))
        year  = int(m.group(2))
        return year, (month - 1) // 3 + 1

    # "2025" only
    m = re.match(r"^(\d{4})$", period)
    if m:
        return int(m.group(1)), None

    return None, None


# ─────────────────────────────────────────────────────────────────────────────
#  💾  UPSERT
# ─────────────────────────────────────────────────────────────────────────────

UPSERT_SQL = """
INSERT INTO bank_fs_components (
    bank_name, ticker, reporting_period,
    reporting_year, reporting_quarter,
    component_key,
    source_type, value_current, value_previous, unit,
    period_current_label, period_previous_label,
    source_url, source_quote, reasoning,
    pdf_path,
    updated_at
)
VALUES (
    $1,  $2,  $3,
    $4,  $5,
    $6,
    $7,  $8,  $9,  $10,
    $11, $12,
    $13, $14, $15,
    $16,
    $17
)
ON CONFLICT (bank_name, reporting_period, component_key)
DO UPDATE SET
    ticker                = EXCLUDED.ticker,
    reporting_year        = EXCLUDED.reporting_year,
    reporting_quarter     = EXCLUDED.reporting_quarter,
    source_type           = EXCLUDED.source_type,
    value_current         = EXCLUDED.value_current,
    value_previous        = EXCLUDED.value_previous,
    unit                  = EXCLUDED.unit,
    period_current_label  = EXCLUDED.period_current_label,
    period_previous_label = EXCLUDED.period_previous_label,
    source_url            = EXCLUDED.source_url,
    source_quote          = EXCLUDED.source_quote,
    reasoning             = EXCLUDED.reasoning,
    pdf_path              = EXCLUDED.pdf_path,
    updated_at            = EXCLUDED.updated_at
"""
# Không có WHERE — PDF là authoritative source, luôn overwrite.


async def upsert_components(
    conn,
    bank_name: str,
    ticker: str,
    reporting_period: str,
    reporting_year: int,
    reporting_quarter: int,
    components: list,
    pdf_path_str: str,
) -> int:
    count = 0
    for comp in components:
        val_current = comp.get("value_current")
        if val_current is None:
            continue

        source_type = comp.get("source_type") or "financial_statement_pdf"

        try:
            await conn.execute(
                UPSERT_SQL,
                # $1–$3: identity
                bank_name,
                ticker,
                reporting_period,
                # $4–$5: time decompose
                reporting_year,
                reporting_quarter,
                # $6: component key
                comp["component_key"],
                # $7–$10: values
                source_type,
                float(val_current),
                float(comp["value_previous"]) if comp.get("value_previous") is not None else None,
                comp.get("unit"),
                # $11–$12: period labels
                comp.get("period_current_label"),
                comp.get("period_previous_label"),
                # $13–$15: audit
                comp.get("source_url"),
                comp.get("source_quote"),
                comp.get("reasoning"),
                # $16: pdf path
                pdf_path_str,
                # $17: updated_at
                datetime.utcnow(),
            )
            count += 1
        except Exception as e:
            logger.error("  FAIL upsert %s.%s: %s", bank_name, comp["component_key"], e)

    return count


# ─────────────────────────────────────────────────────────────────────────────
#  🚀  MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main(force: bool = False):
    if force:
        MANIFEST_PATH.unlink(missing_ok=True)
        logger.info("🗑️  Cache cleared — forcing re-extraction for all banks.")

    settings = get_settings()
    url = settings.database_url.replace("postgres://", "postgresql://", 1)

    import asyncpg
    conn = await asyncpg.connect(url)

    try:
        for bank in BANKS:
            ticker = bank["ticker"]
            logger.info("\n%s [%s] Extracting PDF...", "=" * 40, ticker)

            result = await extract_pdf_kpis_for_bank(bank)
            components = result.get("fs_components", [])

            if not components:
                logger.warning("[%s] No components extracted — skip upsert.", ticker)
                continue

            # ── Resolve reporting_period ──────────────────────────────────────
            sample = next(
                (c for c in components if c.get("period_current_label")), None
            )
            reporting_period = (
                sample["period_current_label"]
                if sample
                else _get_quarter(datetime.utcnow())   # fallback chuẩn, không dùng %m
            )

            reporting_year, reporting_quarter = _parse_reporting_year_quarter(reporting_period)

            # ── Resolve pdf_path ──────────────────────────────────────────────
            pdf_path_raw = result.get("pdf_path")
            pdf_path_str = str(Path(pdf_path_raw).resolve()) if pdf_path_raw else None

            logger.info(
                "[%s] period=%s (year=%s, quarter=%s) | components=%d | pdf=%s",
                ticker,
                reporting_period,
                reporting_year,
                reporting_quarter,
                len(components),
                pdf_path_str,
            )

            count = await upsert_components(
                conn,
                bank_name=bank["name"],
                ticker=ticker,
                reporting_period=reporting_period,
                reporting_year=reporting_year,
                reporting_quarter=reporting_quarter,
                components=components,
                pdf_path_str=pdf_path_str,
            )
            logger.info("[%s] ✅ Upserted %d / %d rows.", ticker, count, len(components))

    finally:
        await conn.close()

    logger.info("\n✅ Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-run PDF extraction → upsert fs_components.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-extract all banks, ignore manifest cache.",
    )
    args = parser.parse_args()
    asyncio.run(main(force=args.force))