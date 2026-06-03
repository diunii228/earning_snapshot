# ERD — Cơ sở dữ liệu

## Sơ đồ quan hệ (Mermaid)

```mermaid
erDiagram
    research_runs ||--o{ bank_kpi_snapshots : "run_id"
    bank_kpi_snapshots ||--|{ bank_kpi_values : "snapshot_id"

    research_runs {
        bigserial id PK
        timestamptz started_at
        timestamptz finished_at
        varchar status
        varchar reporting_period
        smallint reporting_year
        smallint reporting_quarter
        jsonb config_snapshot
        jsonb summary
    }

    bank_kpi_snapshots {
        bigserial id PK
        varchar bank_name
        varchar ticker
        varchar reporting_period
        smallint reporting_year
        smallint reporting_quarter
        jsonb extracted_kpis
        jsonb validation_results
        jsonb article_links
        bigint run_id FK
        timestamptz fetched_at
        timestamptz created_at
        timestamptz updated_at
    }

    bank_kpi_values {
        bigserial id PK
        bigint snapshot_id FK
        varchar category
        varchar kpi_name
        float value_num
        text value_text
        varchar unit
        text source_url
        text source_quote
        text reasoning
        timestamptz created_at
    }

```

## Giải thích nhanh

| Bảng | Mục đích |
|------|----------|
| **research_runs** | Mỗi lần chạy daily crawl (audit). `reporting_year` / `reporting_quarter` parse từ `reporting_period` (e.g. Q1 2025). |
| **bank_kpi_snapshots** | Một bản ghi = KPI một ngân hàng cho một kỳ. Upsert theo `(bank_name, reporting_period)`. Vẫn lưu `extracted_kpis` JSONB. |
| **bank_kpi_values** | Từng chỉ tiêu KPI tách riêng (category, kpi_name, value_num/value_text, unit, source...). Dùng để query/filter theo chỉ tiêu. |

Migration: `001_initial_schema.sql` (research_runs, bank_kpi_snapshots), `002_reporting_period_and_kpi_values.sql` (cột year/quarter, bảng bank_kpi_values).
