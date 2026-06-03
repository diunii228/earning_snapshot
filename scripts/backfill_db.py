"""
Backfill: cập nhật reporting_year/reporting_quarter và ghi extracted_kpis vào bank_kpi_values
cho các snapshot cũ (sau khi chạy migration 002).

Chạy: python scripts/backfill_db.py
Hoặc: .venv/bin/python scripts/backfill_db.py
"""
import asyncio
import json
import logging
import os
import sys

# Thêm project root vào path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _flatten_extracted_kpis(extracted_kpis):
    """Giống db.repository._flatten_extracted_kpis."""
    rows = []
    for category, kpis in (extracted_kpis or {}).items():
        if not isinstance(kpis, dict):
            continue
        for kpi_name, raw in kpis.items():
            value_num = None
            value_text = None
            unit = None
            source_url = None
            source_quote = None
            reasoning = None
            if isinstance(raw, dict):
                val = raw.get("value")
                unit = raw.get("unit")
                if isinstance(unit, str) and len(unit) > 64:
                    unit = unit[:64]
                source_url = raw.get("source_url")
                source_quote = raw.get("source_quote")
                reasoning = raw.get("reasoning")
                if val is not None:
                    try:
                        value_num = float(val)
                    except (TypeError, ValueError):
                        value_text = str(val)[:65535] if val else None
            else:
                try:
                    value_num = float(raw)
                except (TypeError, ValueError):
                    value_text = str(raw)[:65535] if raw is not None else None
            rows.append({
                "category": (category or "")[:64],
                "kpi_name": (kpi_name or "")[:128],
                "value_num": value_num,
                "value_text": value_text,
                "unit": (unit or "")[:64] if unit else None,
                "source_url": source_url,
                "source_quote": source_quote,
                "reasoning": reasoning,
            })
    return rows


async def main():
    from config.banks import parse_reporting_period
    from db.connection import get_pool, close_pool
    from utils.setting import get_settings

    settings = get_settings()
    url = settings.database_url
    if not url:
        logger.error("Chưa cấu hình DATABASE_URL trong .env")
        raise SystemExit(1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    try:
        import asyncpg
    except ImportError:
        logger.error("Cần cài asyncpg: pip install asyncpg")
        raise SystemExit(1)

    conn = await asyncpg.connect(url)
    try:
        # 1) Snapshot thiếu reporting_year / reporting_quarter
        rows = await conn.fetch(
            """
            SELECT id, bank_name, reporting_period, reporting_year, reporting_quarter, extracted_kpis
            FROM bank_kpi_snapshots
            WHERE reporting_year IS NULL OR reporting_quarter IS NULL
            """
        )
        updated_period = 0
        for row in rows:
            year, quarter = parse_reporting_period(row["reporting_period"])
            await conn.execute(
                """
                UPDATE bank_kpi_snapshots
                SET reporting_year = $2, reporting_quarter = $3
                WHERE id = $1
                """,
                row["id"],
                year,
                quarter,
            )
            updated_period += 1
            logger.info("  snapshot id=%s %s -> year=%s quarter=%s", row["id"], row["reporting_period"], year, quarter)

        if updated_period:
            logger.info("Đã cập nhật reporting_year/quarter cho %s snapshot.", updated_period)
        else:
            logger.info("Không có snapshot nào thiếu reporting_year/quarter.")

        # 2) research_runs thiếu year/quarter
        runs = await conn.fetch(
            "SELECT id, reporting_period FROM research_runs WHERE reporting_year IS NULL AND reporting_quarter IS NULL"
        )
        for r in runs:
            year, quarter = parse_reporting_period(r["reporting_period"])
            await conn.execute(
                "UPDATE research_runs SET reporting_year = $2, reporting_quarter = $3 WHERE id = $1",
                r["id"], year, quarter,
            )
        if runs:
            logger.info("Đã cập nhật reporting_year/quarter cho %s research_run.", len(runs))

        # 3) Snapshot chưa có dòng trong bank_kpi_values
        snapshots = await conn.fetch(
            """
            SELECT s.id, s.extracted_kpis
            FROM bank_kpi_snapshots s
            WHERE NOT EXISTS (SELECT 1 FROM bank_kpi_values v WHERE v.snapshot_id = s.id)
            AND s.extracted_kpis IS NOT NULL AND s.extracted_kpis != '{}'::jsonb
            """
        )
        inserted = 0
        for row in snapshots:
            extracted = row["extracted_kpis"]
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted) if extracted else {}
                except Exception:
                    extracted = {}
            if not isinstance(extracted, dict):
                continue
            flat = _flatten_extracted_kpis(extracted)
            for r in flat:
                await conn.execute(
                    """
                    INSERT INTO bank_kpi_values (snapshot_id, category, kpi_name, value_num, value_text, unit, source_url, source_quote, reasoning)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (snapshot_id, category, kpi_name) DO UPDATE SET
                        value_num = EXCLUDED.value_num,
                        value_text = EXCLUDED.value_text,
                        unit = EXCLUDED.unit,
                        source_url = EXCLUDED.source_url,
                        source_quote = EXCLUDED.source_quote,
                        reasoning = EXCLUDED.reasoning
                    """,
                    row["id"],
                    r["category"],
                    r["kpi_name"],
                    r["value_num"],
                    r["value_text"],
                    r["unit"],
                    r["source_url"],
                    r["source_quote"],
                    r["reasoning"],
                )
                inserted += 1
            logger.info("  snapshot id=%s: thêm %s dòng KPI.", row["id"], len(flat))
        if inserted or snapshots:
            logger.info("Đã ghi bank_kpi_values cho %s snapshot, tổng %s dòng.", len(snapshots), inserted)
        else:
            logger.info("Không có snapshot nào cần backfill bank_kpi_values.")
    finally:
        await conn.close()

    logger.info("Backfill xong.")


if __name__ == "__main__":
    asyncio.run(main())
