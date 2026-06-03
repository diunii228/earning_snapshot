-- Migration 001: research_runs + bank_kpi_snapshots
-- Chạy: psql $DATABASE_URL -f db/migrations/001_initial_schema.sql

-- Bảng ghi mỗi lần chạy crawl (audit)
CREATE TABLE IF NOT EXISTS research_runs (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(32) NOT NULL DEFAULT 'running',
    reporting_period VARCHAR(64) NOT NULL,
    config_snapshot JSONB,
    summary         JSONB,
    CONSTRAINT chk_status CHECK (status IN ('running', 'success', 'partial', 'failed'))
);

COMMENT ON TABLE research_runs IS 'Mỗi lần chạy daily crawl job';
COMMENT ON COLUMN research_runs.summary IS 'Ví dụ: {"success": 3, "failed": 4, "total": 7}';

-- Bảng snapshot KPI theo bank + kỳ (chỉ update khi có data mới)
CREATE TABLE IF NOT EXISTS bank_kpi_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    bank_name           VARCHAR(128) NOT NULL,
    ticker              VARCHAR(16),
    reporting_period     VARCHAR(64) NOT NULL,
    extracted_kpis      JSONB NOT NULL DEFAULT '{}',
    validation_results  JSONB DEFAULT '{}',
    article_links       JSONB DEFAULT '[]',
    run_id              BIGINT REFERENCES research_runs(id) ON DELETE SET NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(bank_name, reporting_period)
);

COMMENT ON TABLE bank_kpi_snapshots IS 'KPI đã extract theo bank + kỳ, upsert khi crawl có data';
CREATE INDEX IF NOT EXISTS idx_bank_kpi_snapshots_period ON bank_kpi_snapshots(reporting_period);
CREATE INDEX IF NOT EXISTS idx_bank_kpi_snapshots_updated_at ON bank_kpi_snapshots(updated_at DESC);
