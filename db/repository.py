"""
Repository: upsert snapshot (chỉ khi có data), get latest theo reporting_period.
Hỗ trợ reporting_year/reporting_quarter và ghi từng KPI vào bank_kpi_values.
"""
import json
import logging
from typing import Any, Dict, List, Optional
import datetime
from config.banks import parse_reporting_period
from db.connection import get_pool
from utils.normalize import normalize_banking_kpis

logger = logging.getLogger(__name__)


def _parse_jsonish(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value


def _iso_date_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _normalize_kpi_key(raw_kpi_name: str) -> str:
    k = str(raw_kpi_name).lower().strip().replace(" ", "_").replace("-", "_")
    exact_map = {
        "pe": "p_e_ratio", "p_e": "p_e_ratio",
        "pb": "p_b_ratio", "p_b": "p_b_ratio",
        "npl": "npl_ratio", "casa": "casa_ratio",
        "toi": "total_operating_income",
        "operating_income": "total_operating_income",
        "profit_before_tax": "pbt",
        "profit_after_tax": "pat",
        "net_profit": "pat",
        "net_interest_margin": "nim",
        "return_on_assets": "roa",
        "return_on_equity": "roe",
        "cost_to_income_ratio": "cir",
        "operation_expenses": "opex",
        "operating_expenses": "opex" 
    }
    return exact_map.get(k, k)

def _flatten_extracted_kpis(extracted_kpis: Dict[str, Any]) -> List[Dict[str, Any]]:
    VALID_KEYS = {
        "pbt",
        # Growth keys used by fs_kpi_compute / email layer
        "pbt_growth", "toi_growth", "nii_growth",
        # Legacy/alias forms (keep for backward compatibility)
        "pbt_growth_yoy", "pbt_growth_qoq",
        "pat", "net_interest_income", "non_interest_income", "total_operating_income", "eps",
        "total_assets", "total_assets_growth_yoy", "total_assets_growth_qoq", "total_assets_growth_qtd", "total_assets_growth_ytd", "equity", "charter_capital", "leverage_ratio",
        "total_credit", "credit_growth_yoy", "credit_growth_qoq", "credit_growth_ytd", "total_deposits", "deposit_growth_yoy", "deposit_growth_qoq", "deposit_growth_ytd", "loan_to_deposit_ratio", "mlt_ratio", "wholesale_funding_ratio",
        "roa", "roe", "nim", "cir", "cost_of_funds", "lending_yields","total_lendings","lending_growth_yoy","lending_growth_qoq","lending_growth_ytd",
        "npl_ratio", "group_2_ratio", "llr", "credit_cost", "coverage_ratio",
        "casa_ratio", "casa_growth_ytd", "net_interest_income_growth", "fee_income", "operating_expenses", "car", "p_e_ratio", "p_b_ratio", "opex"
    }

    clean_kpis_dict = normalize_banking_kpis(extracted_kpis)

    rows = []
    for category, kpis in (clean_kpis_dict or {}).items():
        if not isinstance(kpis, dict): continue
        for raw_kpi_name, raw in kpis.items():
            k = _normalize_kpi_key(raw_kpi_name)
                
            if k not in VALID_KEYS: 
                continue
            
            if isinstance(raw, dict):
                norm_val = raw.get("value")
                norm_unit = raw.get("unit")
                
                rows.append({
                    "category": category, 
                    "kpi_name": k,
                    "value_num": norm_val if isinstance(norm_val, (int, float)) else None,
                    "value_text": str(norm_val) if isinstance(norm_val, str) else None,
                    "unit": str(norm_unit)[:64] if norm_unit else None,
                    "source_url": ", ".join([str(u) for u in raw.get("source_url", [])]) if isinstance(raw.get("source_url"), list) else str(raw.get("source_url", "")),
                    "source_quote": str(raw.get("source_quote", "")),
                    "reasoning": str(raw.get("reasoning", "")),
                    "reporting_year": raw.get("reporting_year"),
                    "reporting_quarter": raw.get("reporting_quarter")
                })
    return rows


def _snapshot_kpi_map(extracted_kpis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _flatten_extracted_kpis(extracted_kpis or {})
    result = {}
    for row in rows:
        value = row["value_num"] if row["value_num"] is not None else row["value_text"]
        if value in (None, "", "-", "N/A", "null"):
            continue
        result[row["kpi_name"]] = {
            "category": row["category"],
            "value": value,
            "unit": row["unit"],
            "source_url": row["source_url"],
            "source_quote": row["source_quote"],
            "reasoning": row["reasoning"],
            "reporting_year": row.get("reporting_year"),
            "reporting_quarter": row.get("reporting_quarter"),
        }
    return result


def _values_differ(current: Any, previous: Any) -> bool:
    if current is None and previous is None:
        return False
    if type(current) in (int, float) and type(previous) in (int, float):
        return float(current) != float(previous)
    return str(current) != str(previous)


def _build_daily_changes(current_kpis: Dict[str, Any], previous_kpis: Dict[str, Any]) -> Dict[str, Any]:
    current_map = _snapshot_kpi_map(current_kpis)
    previous_map = _snapshot_kpi_map(previous_kpis)

    current_keys = set(current_map.keys())
    previous_keys = set(previous_map.keys())

    added = []
    removed = []
    changed = []

    for key in sorted(current_keys - previous_keys):
        item = current_map[key]
        added.append({
            "kpi_name": key,
            "category": item.get("category"),
            "new_value": item.get("value"),
            "unit": item.get("unit"),
        })

    for key in sorted(previous_keys - current_keys):
        item = previous_map[key]
        removed.append({
            "kpi_name": key,
            "category": item.get("category"),
            "old_value": item.get("value"),
            "unit": item.get("unit"),
        })

    for key in sorted(current_keys & previous_keys):
        current_item = current_map[key]
        previous_item = previous_map[key]
        if (
            _values_differ(current_item.get("value"), previous_item.get("value")) or
            _values_differ(current_item.get("unit"), previous_item.get("unit"))
        ):
            changed.append({
                "kpi_name": key,
                "category": current_item.get("category") or previous_item.get("category"),
                "old_value": previous_item.get("value"),
                "new_value": current_item.get("value"),
                "unit": current_item.get("unit") or previous_item.get("unit"),
            })

    return {
        "has_previous": bool(previous_kpis),
        "added": added,
        "removed": removed,
        "changed": changed,
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "total_change_count": len(added) + len(removed) + len(changed),
    }

class BankKpiSnapshotRepository:
    """Thao tác bảng research_runs và bank_kpi_snapshots."""

    async def upsert_fs_components(
        self,
        bank_name: str,
        reporting_period: str,
        components: List[Dict[str, Any]],
        run_id: Optional[int] = None,
        ticker: Optional[str] = None,
        reporting_year: Optional[int] = None,
        reporting_quarter: Optional[int] = None,
        pdf_path: Optional[str] = None,
    ) -> int:
        """
        Ghi raw components vào bảng bank_fs_components để audit / recompute KPI.

        Priority rule:
        - manual_override (từ data_manual.csv) cao nhất
        - financial_statement_pdf (BCTC PDF) thứ 2
        - web thấp nhất

        Higher-priority sources can overwrite lower-priority sources; lower-priority cannot.

        Trả về số record được insert/update.
        """
        if not components:
            return 0

        if reporting_year is None:
            reporting_year, reporting_quarter = parse_reporting_period(reporting_period)

        pool = await get_pool()
        affected = 0
        async with pool.acquire() as conn:
            for c in components:
                if not isinstance(c, dict):
                    continue
                component_key = str(c.get("component_key") or "").strip()
                if not component_key:
                    continue

                source_type = str(c.get("source_type") or "").strip() or None
                source_url = str(c.get("source_url") or "").strip() or None
                source_quote = str(c.get("source_quote") or "").strip() or None
                reasoning = str(c.get("reasoning") or "").strip() or None

                value_current = c.get("value_current")
                value_previous = c.get("value_previous")
                unit = str(c.get("unit") or "").strip() or None

                period_current_label = str(c.get("period_current_label") or "").strip() or None
                period_previous_label = str(c.get("period_previous_label") or "").strip() or None

                rowcount = await conn.execute(
                    """
                    INSERT INTO bank_fs_components (
                        bank_name, ticker, reporting_period, reporting_year, reporting_quarter,
                        component_key, value_current, value_previous, unit,
                        period_current_label, period_previous_label,
                        source_url, source_quote, source_type, reasoning, pdf_path,
                        run_id, created_at, updated_at
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NOW(),NOW())
                    ON CONFLICT (bank_name, reporting_period, component_key)
                    DO UPDATE SET
                        ticker = EXCLUDED.ticker,
                        reporting_year = EXCLUDED.reporting_year,
                        reporting_quarter = EXCLUDED.reporting_quarter,
                        value_current = EXCLUDED.value_current,
                        value_previous = EXCLUDED.value_previous,
                        unit = EXCLUDED.unit,
                        period_current_label = EXCLUDED.period_current_label,
                        period_previous_label = EXCLUDED.period_previous_label,
                        source_url = EXCLUDED.source_url,
                        source_quote = EXCLUDED.source_quote,
                        source_type = EXCLUDED.source_type,
                        reasoning = EXCLUDED.reasoning,
                        pdf_path = EXCLUDED.pdf_path,
                        run_id = EXCLUDED.run_id,
                        updated_at = NOW()
                    WHERE
                        (
                          CASE COALESCE(bank_fs_components.source_type,'')
                            WHEN 'manual_override' THEN 3
                            WHEN 'financial_statement_pdf' THEN 2
                            ELSE 1
                          END
                        ) <= (
                          CASE COALESCE(EXCLUDED.source_type,'')
                            WHEN 'manual_override' THEN 3
                            WHEN 'financial_statement_pdf' THEN 2
                            ELSE 1
                          END
                        )
                    """,
                    bank_name,
                    ticker,
                    reporting_period,
                    reporting_year,
                    reporting_quarter,
                    component_key,
                    value_current,
                    value_previous,
                    unit,
                    period_current_label,
                    period_previous_label,
                    source_url,
                    source_quote,
                    source_type,
                    reasoning,
                    pdf_path,
                    run_id,
                )
                # asyncpg returns strings like "INSERT 0 1"
                if isinstance(rowcount, str) and rowcount.endswith(" 1"):
                    affected += 1
        return affected

    async def get_fs_components(
        self,
        bank_name: str,
        reporting_period: str,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Lấy map component_key -> component_row từ bảng bank_fs_components.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    component_key,
                    value_current,
                    value_previous,
                    unit,
                    period_current_label,
                    period_previous_label,
                    source_url,
                    source_quote,
                    source_type,
                    reasoning,
                    pdf_path
                FROM bank_fs_components
                WHERE bank_name = $1 AND reporting_period = $2
                """,
                bank_name,
                reporting_period,
            )
        result: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            key = r.get("component_key")
            if key:
                result[str(key)] = dict(r)
        return result

    async def get_fs_components_history(
        self,
        bank_name: str,
        upto_year: int,
        upto_quarter: int,
        component_keys: List[str],
        limit_quarters: int,
    ) -> List[Dict[str, Any]]:
        """
        Lấy components cho các quý gần nhất (bao gồm quý hiện tại) tính ngược từ upto_year/upto_quarter.
        Output: list các quarter blocks theo thứ tự mới -> cũ:
          {"reporting_year": 2026, "reporting_quarter": 1, "components": {key: row}}
        """
        if not component_keys or limit_quarters <= 0:
            return []

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    reporting_year,
                    reporting_quarter,
                    component_key,
                    value_current,
                    value_previous,
                    unit,
                    period_current_label,
                    period_previous_label,
                    source_url,
                    source_quote,
                    source_type,
                    reasoning,
                    pdf_path
                FROM bank_fs_components
                WHERE bank_name = $1
                  AND reporting_year IS NOT NULL
                  AND reporting_quarter IS NOT NULL
                  AND (
                        reporting_year < $2
                        OR (reporting_year = $2 AND reporting_quarter <= $3)
                      )
                  AND component_key = ANY($4::text[])
                ORDER BY reporting_year DESC, reporting_quarter DESC
                """,
                bank_name,
                upto_year,
                upto_quarter,
                component_keys,
            )

        # Group rows by quarter key, keep newest quarters first
        quarter_blocks: List[Dict[str, Any]] = []
        idx_map: Dict[tuple, int] = {}
        for r in rows:
            qkey = (r.get("reporting_year"), r.get("reporting_quarter"))
            if qkey not in idx_map:
                if len(quarter_blocks) >= limit_quarters:
                    continue
                idx_map[qkey] = len(quarter_blocks)
                quarter_blocks.append(
                    {
                        "reporting_year": qkey[0],
                        "reporting_quarter": qkey[1],
                        "components": {},
                    }
                )
            block = quarter_blocks[idx_map[qkey]]
            block["components"][str(r.get("component_key"))] = dict(r)

        return quarter_blocks

    async def has_any_run_for_period(self, reporting_period: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM research_runs
                WHERE reporting_period = $1
                """,
                reporting_period,
            )
            return bool(count and count > 0)

    async def has_runs_in_date_range(
        self,
        reporting_period: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM research_runs
                WHERE reporting_period = $1
                  AND created_at::date BETWEEN $2 AND $3
                """,
                reporting_period,
                start_date,
                end_date,
            )
            return bool(count and count > 0)

    async def create_run(
        self,
        reporting_period: str,
        config_snapshot: Optional[Dict[str, Any]] = None,
        reporting_year: Optional[int] = None,
        reporting_quarter: Optional[int] = None,
    ) -> int:
        if reporting_year is None and reporting_quarter is None:
            reporting_year, reporting_quarter = parse_reporting_period(reporting_period)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO research_runs (reporting_period, reporting_year, reporting_quarter, config_snapshot, status)
                VALUES ($1, $2, $3, $4, 'running')
                RETURNING id
                """,
                reporting_period,
                reporting_year,
                reporting_quarter,
                json.dumps(config_snapshot) if config_snapshot else None,
            )
            return row["id"]

    async def finish_run(
        self,
        run_id: int,
        status: str = "success",
        summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Cập nhật research_runs: finished_at, status, summary."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE research_runs
                SET finished_at = NOW(), status = $2, summary = $3
                WHERE id = $1
                """,
                run_id,
                status,
                json.dumps(summary) if summary else None,
            )

    async def upsert_snapshot(
        self,
        bank_name: str,
        reporting_period: str,
        extracted_kpis: Dict[str, Any],
        run_id: Optional[int] = None,
        ticker: Optional[str] = None,
        validation_results: Optional[Dict[str, Any]] = None,
        article_links: Optional[List[str]] = None,
        reporting_year: Optional[int] = None,
        reporting_quarter: Optional[int] = None,
        target_date: Optional[str] = None,
    ) -> None:
        # Fix NameError bằng cách dùng datetime.date
        if isinstance(target_date, str):
            target_date = datetime.date.fromisoformat(target_date)
        
        if not extracted_kpis:
            logger.warning(f"upsert_snapshot {bank_name} bỏ qua vì extracted_kpis rỗng")
            return

        # Tìm Year/Quarter thực tế từ nội dung Agent trích xuất
        found_year = None
        found_quarter = None
        for cat_kpis in extracted_kpis.values():
            if not isinstance(cat_kpis, dict): continue
            for kpi_data in cat_kpis.values():
                if isinstance(kpi_data, dict) and kpi_data.get("reporting_year"):
                    found_year = kpi_data["reporting_year"]
                    found_quarter = kpi_data.get("reporting_quarter")
                    break
            if found_year: break

        # Nếu Agent trích xuất được số liệu 2025, dùng nó thay vì 2026 của hệ thống
        if found_year:
            reporting_year = found_year
            reporting_quarter = found_quarter
        
        if reporting_year is None:
            reporting_year, reporting_quarter = parse_reporting_period(reporting_period)

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO bank_kpi_snapshots (
                    bank_name, ticker, reporting_period, reporting_year, reporting_quarter,
                    target_date, extracted_kpis, validation_results, article_links,
                    run_id, fetched_at, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW(), NOW())
                ON CONFLICT (bank_name, reporting_period, target_date)
                DO UPDATE SET
                    reporting_year = EXCLUDED.reporting_year,
                    reporting_quarter = EXCLUDED.reporting_quarter,
                    extracted_kpis = EXCLUDED.extracted_kpis,
                    validation_results = COALESCE(EXCLUDED.validation_results, bank_kpi_snapshots.validation_results),
                    article_links = COALESCE(EXCLUDED.article_links, bank_kpi_snapshots.article_links),
                    run_id = EXCLUDED.run_id,
                    updated_at = NOW()
                RETURNING id
                """,
                bank_name, ticker, reporting_period, reporting_year, reporting_quarter,
                target_date, json.dumps(extracted_kpis, ensure_ascii=False),
                json.dumps(validation_results or {}, ensure_ascii=False),
                json.dumps(article_links or [], ensure_ascii=False),
                run_id,
            )
            snapshot_id = row["id"]
            
            await conn.execute("DELETE FROM bank_kpi_values WHERE snapshot_id = $1", snapshot_id)
            
            flat = _flatten_extracted_kpis(extracted_kpis)
            for r in flat:
                await conn.execute(
                    """
                    INSERT INTO bank_kpi_values (
                        snapshot_id, category, kpi_name, value_num, value_text, 
                        unit, source_url, source_quote, reasoning
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (snapshot_id, category, kpi_name) DO UPDATE SET
                        value_num = EXCLUDED.value_num,
                        value_text = EXCLUDED.value_text,
                        unit = EXCLUDED.unit,
                        source_url = EXCLUDED.source_url,
                        source_quote = EXCLUDED.source_quote,
                        reasoning = EXCLUDED.reasoning
                    """,
                    snapshot_id, r["category"], r["kpi_name"],
                    r["value_num"], r["value_text"], r["unit"],
                    r["source_url"], r["source_quote"], r["reasoning"],
                )
        
        logger.info(f"Upserted: {bank_name} | Data: {reporting_year} Q{reporting_quarter} | SnapID: {snapshot_id}")

    async def upsert_snapshot_merge(
        self,
        bank_name: str,
        reporting_period: str,
        extracted_kpis: Dict[str, Any],
        run_id: Optional[int] = None,
        ticker: Optional[str] = None,
        validation_results: Optional[Dict[str, Any]] = None,
        article_links: Optional[List[str]] = None,
        reporting_year: Optional[int] = None,
        reporting_quarter: Optional[int] = None,
        target_date: Optional[str] = None,
    ) -> None:
        """
        Upsert snapshot theo kiểu merge (không overwrite toàn bộ).

        Priority per KPI (source_type):
        - manual_override (cao nhất)
        - financial_statement_pdf
        - web / other (thấp nhất)
        """
        if isinstance(target_date, str):
            td = datetime.date.fromisoformat(target_date)
        else:
            td = target_date

        pool = await get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                """
                SELECT extracted_kpis
                FROM bank_kpi_snapshots
                WHERE bank_name = $1 AND reporting_period = $2 AND target_date = $3
                """,
                bank_name,
                reporting_period,
                td,
            )

        existing_obj = _parse_jsonish(existing, {}) if existing else {}

        def _prio(st: Any) -> int:
            s = str(st or "").strip().lower()
            if s == "manual_override":
                return 3
            if s == "financial_statement_pdf":
                return 2
            return 1

        merged: Dict[str, Any] = json.loads(json.dumps(existing_obj, ensure_ascii=False)) if isinstance(existing_obj, dict) else {}
        for section, kpis in (extracted_kpis or {}).items():
            if not isinstance(kpis, dict):
                continue
            merged.setdefault(section, {})
            for kpi_name, details in kpis.items():
                if not isinstance(details, dict):
                    continue
                incoming_type = details.get("source_type") or "web"
                existing_details = merged.get(section, {}).get(kpi_name)
                if not isinstance(existing_details, dict):
                    merged[section][kpi_name] = details
                    continue
                if _prio(incoming_type) >= _prio(existing_details.get("source_type") or "web"):
                    merged[section][kpi_name] = details

        await self.upsert_snapshot(
            bank_name=bank_name,
            reporting_period=reporting_period,
            extracted_kpis=merged,
            run_id=run_id,
            ticker=ticker,
            validation_results=validation_results,
            article_links=article_links,
            reporting_year=reporting_year,
            reporting_quarter=reporting_quarter,
            target_date=str(td) if td else None,
        )

    def _build_reports_from_value_rows(self, rows) -> List[Dict[str, Any]]:
        bank_data_map = {}
        for row in rows:
            bank = row["bank_name"]
            if bank not in bank_data_map:
                bank_data_map[bank] = {
                    "bank_name": bank,
                    "ticker": row["ticker"] or "",
                    "reporting_year": row.get("reporting_year"),
                    "reporting_quarter": row.get("reporting_quarter"),
                    "status": "success",
                    "extracted_kpis": {},
                    "source_urls": set() 
                }
            
            a_links = row.get("article_links")
            if a_links:
                try:
                    links = json.loads(a_links) if isinstance(a_links, str) else a_links
                    if isinstance(links, list): bank_data_map[bank]["source_urls"].update(links)
                except: pass

            cat, kpi = row["category"], row["kpi_name"]
            if cat and kpi:
                if cat not in bank_data_map[bank]["extracted_kpis"]:
                    bank_data_map[bank]["extracted_kpis"][cat] = {}
                
                val = row["value_num"] if row["value_num"] is not None else row["value_text"]
                bank_data_map[bank]["extracted_kpis"][cat][kpi] = {
                    "value": val,
                    "unit": row["unit"],
                    "source_url": row["source_url"],
                    "source_quote": row["source_quote"],
                    "reasoning": row["reasoning"],
                    "reporting_year": row.get("reporting_year"),
                    "reporting_quarter": row.get("reporting_quarter")
                }
                if row["source_url"]:
                    bank_data_map[bank]["source_urls"].add(row["source_url"])

        for b in bank_data_map:
            bank_data_map[b]["source_urls"] = list(bank_data_map[b]["source_urls"])
        return list(bank_data_map.values())

    async def get_latest_by_period(
        self,
        reporting_period: str,
    ) -> List[Dict[str, Any]]:
        """
        Lấy các KPI xuất hiện MỚI NHẤT (gần đây nhất) của từng ngân hàng.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (s.bank_name, v.category, v.kpi_name)
                    s.bank_name,
                    s.ticker,
                    v.category,
                    v.kpi_name,
                    v.value_num,
                    v.value_text,
                    v.unit,
                    v.source_url,
                    v.source_quote,
                    v.reasoning,
                    s.article_links
                FROM bank_kpi_snapshots s
                JOIN bank_kpi_values v ON s.id = v.snapshot_id
                WHERE s.reporting_period = $1
                  AND (v.value_num IS NOT NULL OR (v.value_text IS NOT NULL AND v.value_text != 'null'))
                ORDER BY s.bank_name, v.category, v.kpi_name, s.target_date DESC, s.id DESC
                """,
                reporting_period,
            )
        return self._build_reports_from_value_rows(rows)

    async def get_latest_snapshots_with_previous(
        self,
        reporting_period: str,
    ) -> List[Dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (curr.bank_name)
                    curr.id,
                    curr.bank_name,
                    curr.ticker,
                    curr.reporting_period,
                    curr.reporting_year,
                    curr.reporting_quarter,
                    curr.target_date,
                    curr.extracted_kpis,
                    curr.validation_results,
                    curr.article_links,
                    prev.id AS previous_snapshot_id,
                    prev.target_date AS previous_target_date,
                    prev.extracted_kpis AS previous_extracted_kpis
                FROM bank_kpi_snapshots curr
                LEFT JOIN LATERAL (
                    SELECT p.id, p.target_date, p.extracted_kpis
                    FROM bank_kpi_snapshots p
                    WHERE p.bank_name = curr.bank_name
                      AND p.reporting_period = curr.reporting_period
                      AND p.target_date < curr.target_date
                    ORDER BY p.target_date DESC, p.id DESC
                    LIMIT 1
                ) prev ON TRUE
                WHERE curr.reporting_period = $1
                ORDER BY curr.bank_name, curr.target_date DESC, curr.id DESC
                """,
                reporting_period,
            )

        snapshots = []
        for row in rows:
            extracted_kpis = _parse_jsonish(row["extracted_kpis"], {}) or {}
            previous_extracted_kpis = _parse_jsonish(row["previous_extracted_kpis"], {}) or {}
            article_links = _parse_jsonish(row["article_links"], []) or []
            snapshots.append({
                "id": row["id"],
                "bank_name": row["bank_name"],
                "ticker": row["ticker"] or "",
                "reporting_period": row["reporting_period"],
                "reporting_year": row["reporting_year"],
                "reporting_quarter": row["reporting_quarter"],
                "target_date": _iso_date_or_none(row["target_date"]),
                "extracted_kpis": extracted_kpis,
                "validation_results": _parse_jsonish(row["validation_results"], {}) or {},
                "article_links": article_links,
                "previous_snapshot_id": row["previous_snapshot_id"],
                "previous_target_date": _iso_date_or_none(row["previous_target_date"]),
                "previous_extracted_kpis": previous_extracted_kpis,
                "daily_changes": _build_daily_changes(extracted_kpis, previous_extracted_kpis),
                "status": "success" if extracted_kpis else "no_data",
            })
        return snapshots
    async def get_snapshot(
        self,
        bank_name: str,
        reporting_period: str,
        target_date: str,
    ) -> Optional[Dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, extracted_kpis, article_links, validation_results
                FROM bank_kpi_snapshots
                WHERE bank_name = $1
                AND reporting_period = $2
                AND target_date = $3
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                bank_name,
                reporting_period,
                datetime.date.fromisoformat(target_date),
            )
        if not row:
            return None
        return {
            "id": row["id"],
            "extracted_kpis": _parse_jsonish(row["extracted_kpis"], {}),
            "article_links": _parse_jsonish(row["article_links"], []),
            "validation_results": _parse_jsonish(row["validation_results"], {}),
        }
    async def get_latest_by_year_quarter(
        self,
        reporting_year: int,
        reporting_quarter: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lấy các KPI xuất hiện MỚI NHẤT theo năm (và tùy chọn quý).
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            if reporting_quarter is not None:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (s.bank_name, v.category, v.kpi_name)
                        s.bank_name,
                        s.ticker,
                        v.category,
                        v.kpi_name,
                        v.value_num,
                        v.value_text,
                        v.unit,
                        v.source_url,
                        v.source_quote,
                        v.reasoning,
                        s.article_links
                    FROM bank_kpi_snapshots s
                    JOIN bank_kpi_values v ON s.id = v.snapshot_id
                    WHERE s.reporting_year = $1 AND s.reporting_quarter = $2
                      AND v.source_url != ''
                      AND (v.value_num IS NOT NULL OR (v.value_text IS NOT NULL AND v.value_text != 'null'))
                    ORDER BY s.bank_name, v.category, v.kpi_name, s.target_date DESC, s.id DESC
                    """,
                    reporting_year,
                    reporting_quarter,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (s.bank_name, v.category, v.kpi_name)
                        s.bank_name,
                        s.ticker,
                        v.category,
                        v.kpi_name,
                        v.value_num,
                        v.value_text,
                        v.unit,
                        v.source_url,
                        v.source_quote,
                        v.reasoning,
                        s.article_links
                    FROM bank_kpi_snapshots s
                    JOIN bank_kpi_values v ON s.id = v.snapshot_id
                    WHERE s.reporting_year = $1 AND s.reporting_quarter IS NULL
                      AND v.source_url != ''
                      AND (v.value_num IS NOT NULL OR (v.value_text IS NOT NULL AND v.value_text != 'null'))
                    ORDER BY s.bank_name, v.category, v.kpi_name, s.target_date DESC, s.id DESC
                    """,
                    reporting_year,
                )
        return self._build_reports_from_value_rows(rows)
