-- Migration 002: Thời gian theo quý/năm + tách KPI thành bảng riêng (không chỉ JSONB)
-- Chạy: python -m db.run_migration (cần cập nhật run_migration đọc cả 002) hoặc psql -f ...

-- 1) Thêm cột thời gian có cấu trúc (quý 1–4, năm)
ALTER TABLE research_runs
  ADD COLUMN IF NOT EXISTS reporting_year  SMALLINT,
  ADD COLUMN IF NOT EXISTS reporting_quarter SMALLINT;

ALTER TABLE bank_kpi_snapshots
  ADD COLUMN IF NOT EXISTS reporting_year  SMALLINT,
  ADD COLUMN IF NOT EXISTS reporting_quarter SMALLINT;

COMMENT ON COLUMN research_runs.reporting_year IS 'Năm báo cáo, ví dụ 2025';
COMMENT ON COLUMN research_runs.reporting_quarter IS 'Quý 1-4, NULL = cả năm';
COMMENT ON COLUMN bank_kpi_snapshots.reporting_year IS 'Năm báo cáo';
COMMENT ON COLUMN bank_kpi_snapshots.reporting_quarter IS 'Quý 1-4, NULL = cả năm';

-- 2) Bảng KPI từng chỉ tiêu (tách từ extracted_kpis JSON)
CREATE TABLE IF NOT EXISTS bank_kpi_values (
    id           BIGSERIAL PRIMARY KEY,
    snapshot_id  BIGINT NOT NULL REFERENCES bank_kpi_snapshots(id) ON DELETE CASCADE,
    category     VARCHAR(64) NOT NULL,
    kpi_name     VARCHAR(128) NOT NULL,
    value_num    DOUBLE PRECISION,
    value_text   TEXT,
    unit         VARCHAR(64),
    source_url   TEXT,
    source_quote TEXT,
    reasoning    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(snapshot_id, category, kpi_name)
);

COMMENT ON TABLE bank_kpi_values IS 'Từng chỉ tiêu KPI (tách từ JSON), dễ query, filter theo category/kpi';
CREATE INDEX IF NOT EXISTS idx_bank_kpi_values_snapshot ON bank_kpi_values(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_bank_kpi_values_category ON bank_kpi_values(category);
CREATE INDEX IF NOT EXISTS idx_bank_kpi_values_kpi_name ON bank_kpi_values(kpi_name);
