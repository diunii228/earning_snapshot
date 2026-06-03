-- Migration 003: Lưu các cấu phần (components) trích xuất từ BCTC PDF
-- Mục tiêu:
-- - Lưu raw fields để audit / recompute KPI (CASA, NIM, growth, total credit...)
-- - Cho phép "web fill trước, PDF overwrite sau" theo rule ưu tiên PDF
--
-- Chạy: python -m db.run_migration

CREATE TABLE IF NOT EXISTS bank_fs_components (
    id                  BIGSERIAL PRIMARY KEY,
    bank_name           VARCHAR(128) NOT NULL,
    ticker              VARCHAR(16),
    reporting_period    VARCHAR(64) NOT NULL,
    reporting_year      SMALLINT,
    reporting_quarter   SMALLINT,

    component_key       VARCHAR(128) NOT NULL,

    value_current       DOUBLE PRECISION,
    value_previous      DOUBLE PRECISION,
    unit                VARCHAR(64),

    period_current_label   TEXT,
    period_previous_label  TEXT,

    source_url          TEXT,
    source_quote        TEXT,
    source_type         VARCHAR(64),
    reasoning           TEXT,
    pdf_path            TEXT,

    run_id              BIGINT REFERENCES research_runs(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(bank_name, reporting_period, component_key)
);

COMMENT ON TABLE bank_fs_components IS 'Raw components (BCTC/web) để tính & validate KPI; ưu tiên PDF overwrite.';
CREATE INDEX IF NOT EXISTS idx_bank_fs_components_period ON bank_fs_components(reporting_period);
CREATE INDEX IF NOT EXISTS idx_bank_fs_components_bank_period ON bank_fs_components(bank_name, reporting_period);
CREATE INDEX IF NOT EXISTS idx_bank_fs_components_updated_at ON bank_fs_components(updated_at DESC);
