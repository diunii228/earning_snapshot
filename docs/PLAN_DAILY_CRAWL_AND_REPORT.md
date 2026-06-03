# Plan: Crawl hằng ngày → Lưu DB → Gen report từ DB

## 1. Tổng quan kịch bản

- **Crawl/search hằng ngày**: Chạy agent (expand links → fetch articles → extract KPIs → validate) cho **tất cả** ngân hàng mỗi ngày.
- **Lưu DB (PostgreSQL)**: Kết quả crawl được lưu vào DB. Mỗi lần chạy: **chỉ cập nhật** bản ghi khi **có dữ liệu mới** cho bank + kỳ báo cáo đó (vì thông tin từng bank public dần, không cùng lúc).
- **Gen report từ DB**: Báo cáo so sánh được sinh từ dữ liệu **đã lưu trong DB** (không gọi crawl lúc gen report). Logic agent (extract, validate, report) **giữ nguyên**.

---

## 2. Kiến trúc hai luồng

```
┌─────────────────────────────────────────────────────────────────┐
│  LUỒNG 1: Daily Crawl (chạy hằng ngày, e.g. cron/scheduler)     │
├─────────────────────────────────────────────────────────────────┤
│  For each bank (parallel):                                       │
│    → research_bank_async(urls, bank_name, reporting_period)      │
│    → Nếu có extracted_kpis (status success):                     │
│        → UPSERT vào DB (bank_name + reporting_period)             │
│    → Nếu failed: không ghi đè dữ liệu cũ, có thể ghi attempt     │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL                                                      │
│  - research_runs (mỗi lần chạy crawl)                            │
│  - bank_kpi_snapshots (KPI theo bank + kỳ, chỉ update khi có data)│
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  LUỒNG 2: Gen Report (on-demand hoặc theo lịch)                   │
├─────────────────────────────────────────────────────────────────┤
│  - Đọc từ DB: snapshot mới nhất theo bank + reporting_period      │
│  - Subject bank + danh sách peer (cùng format như hiện tại)       │
│  - BankingReporterAgent.generate_full_report(peers, subject_data)│
│  - Ghi file Markdown (hoặc lưu report vào DB tùy chọn)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Schema PostgreSQL

### 3.1. Bảng `research_runs`

Ghi lại mỗi lần chạy crawl (để audit / debug).

| Cột | Kiểu | Mô tả |
|-----|------|--------|
| `id` | UUID / BIGSERIAL | PK |
| `started_at` | TIMESTAMPTZ | Thời điểm bắt đầu |
| `finished_at` | TIMESTAMPTZ | Thời điểm kết thúc (nullable khi đang chạy) |
| `status` | VARCHAR | `running` / `success` / `partial` / `failed` |
| `reporting_period` | VARCHAR | Kỳ báo cáo (e.g. `2025`, `Q1 2025`, `Quý 1 - năm 2025`) |
| `reporting_year` | SMALLINT | Năm báo cáo (tự parse từ reporting_period, migration 002) |
| `reporting_quarter` | SMALLINT | Quý 1–4; NULL = cả năm (migration 002) |
| `config_snapshot` | JSONB | Snapshot config banks/urls (optional) |
| `summary` | JSONB | Số bank success/failed (optional) |

### 3.2. Bảng `bank_kpi_snapshots`

Một bản ghi = dữ liệu KPI của **một ngân hàng** cho **một kỳ báo cáo**. Chỉ cập nhật khi lần crawl có dữ liệu.

| Cột | Kiểu | Mô tả |
|-----|------|--------|
| `id` | BIGSERIAL | PK |
| `bank_name` | VARCHAR NOT NULL | Tên ngân hàng |
| `ticker` | VARCHAR | Mã (TCB, VPB, ...) |
| `reporting_period` | VARCHAR NOT NULL | e.g. `2025`, `Q1 2025`, `Quý 1 - năm 2025` |
| `reporting_year` | SMALLINT | Năm báo cáo (migration 002) |
| `reporting_quarter` | SMALLINT | Quý 1–4; NULL = cả năm (migration 002) |
| `extracted_kpis` | JSONB NOT NULL | Output extract (cấu trúc như hiện tại) |
| `validation_results` | JSONB | Kết quả validate |
| `article_links` | JSONB / TEXT[] | Danh sách URL nguồn |
| `run_id` | FK → research_runs.id | Lần chạy tạo/update bản ghi này |
| `fetched_at` | TIMESTAMPTZ | Thời điểm crawl thành công |
| `created_at` | TIMESTAMPTZ | Lần đầu ghi |
| `updated_at` | TIMESTAMPTZ | Lần cập nhật gần nhất |

**Ràng buộc duy nhất**: `UNIQUE(bank_name, reporting_period)`.

**Upsert logic**:
- Mỗi lần crawl xong 1 bank: nếu `status == "success"` và có `extracted_kpis` → `INSERT ... ON CONFLICT (bank_name, reporting_period) DO UPDATE SET extracted_kpis = ..., updated_at = ..., run_id = ...`.
- Nếu crawl failed → **không** UPDATE bản ghi cũ (giữ nguyên dữ liệu đã có).

### 3.3. (Tùy chọn) Bảng `bank_configs`

Lưu cấu hình URL theo bank để không hardcode trong code.

| Cột | Kiểu | Mô tả |
|-----|------|--------|
| `id` | BIGSERIAL | PK |
| `bank_name` | VARCHAR UNIQUE | |
| `ticker` | VARCHAR | |
| `source_urls` | JSONB / TEXT[] | Danh sách URL nguồn |
| `is_subject` | BOOLEAN | Bank chủ thể (Techcombank) |
| `updated_at` | TIMESTAMPTZ | |

Có thể bỏ qua và tiếp tục đọc config từ file/env nếu bạn muốn đơn giản.

### 3.4. Bảng `bank_kpi_values` (migration 002)

Tách từng chỉ tiêu KPI từ `extracted_kpis` (JSONB) thành từng dòng, dễ query/filter theo category hoặc tên KPI.

| Cột | Kiểu | Mô tả |
|-----|------|--------|
| `id` | BIGSERIAL | PK |
| `snapshot_id` | FK → bank_kpi_snapshots.id | Snapshot chứa KPI này |
| `category` | VARCHAR | Nhóm (profitability, balance_sheet, ...) |
| `kpi_name` | VARCHAR | Tên chỉ tiêu (pbt, roe, ...) |
| `value_num` | DOUBLE PRECISION | Giá trị số (nếu có) |
| `value_text` | TEXT | Giá trị dạng chữ (nếu không phải số) |
| `unit` | VARCHAR | Đơn vị (%, tỷ VND, ...) |
| `source_url` | TEXT | URL nguồn |
| `source_quote` | TEXT | Trích dẫn |
| `reasoning` | TEXT | Giải thích (optional) |

**Ràng buộc**: `UNIQUE(snapshot_id, category, kpi_name)`. Khi upsert snapshot, code xóa các dòng cũ của snapshot rồi insert lại từ `extracted_kpis`.

---

## 4. Logic “chỉ update khi có thông tin”

- Mỗi lần chạy daily job: **luôn** gọi agent cho **tất cả** bank (cùng danh sách config như hiện tại).
- Với từng bank:
  - Nếu agent trả về `status == "success"` và `extracted_kpis` không rỗng → **upsert** vào `bank_kpi_snapshots` (ghi đè bản ghi cũ cho cặp `bank_name` + `reporting_period`).
  - Nếu `status == "failed"` hoặc không có dữ liệu → **không** thay đổi bản ghi trong DB (dữ liệu cũ vẫn dùng cho report).
- Lần chạy sau: tương tự — bank nào hôm nay có số liệu mới thì mới update; bank chưa public thì giữ nguyên bản cũ.

---

## 5. Gen report từ DB

- Input: `reporting_period`, `subject_bank_name` (e.g. Techcombank).
- Query DB: lấy tất cả snapshot thỏa `reporting_period = ?` (subject + peers).
- Map sang format giống hiện tại: `{"bank_name": ..., "ticker": ..., "extracted_kpis": ..., "status": "success"}`.
- Gọi `BankingReporterAgent().generate_full_report(valid_peers, subject_data)` — **không đổi** signature/behavior.
- Ghi file Markdown (hoặc lưu vào bảng `reports` nếu cần).

---

## 6. Cấu trúc thư mục / module gợi ý

```
agent-competitor/
├── db/
│   ├── __init__.py
│   ├── models.py          # SQLAlchemy hoặc raw SQL schema (table names, columns)
│   ├── connection.py      # get_engine(), get_session(), async nếu dùng asyncpg
│   └── repository.py      # BankKpiSnapshotRepository: upsert_snapshot(), get_latest_by_period()
├── jobs/
│   ├── __init__.py
│   ├── daily_crawl.py     # Entry: chạy crawl all banks, upsert DB
│   └── report_from_db.py  # Entry: đọc DB, gen report
├── graph/                 # Giữ nguyên (base_agent, research_agent)
├── schemas/
├── main.py                # Có thể đổi thành CLI: crawl | report
└── docs/
    └── PLAN_DAILY_CRAWL_AND_REPORT.md  # Plan này
```

---

## 7. Phụ thuộc

- **PostgreSQL**: đã chọn.
- **Python driver**: `psycopg2-binary` hoặc `asyncpg` (nếu giữ toàn bộ luồng async). Có thể thêm vào `pyproject.toml`:
  - `asyncpg` (async)
  - hoặc `psycopg[binary]` (sync, đơn giản hơn với cron).

---

## 8. Các bước triển khai (phase)

| Phase | Nội dung |
|-------|----------|
| **1** | Thêm dependency DB (asyncpg hoặc psycopg), cấu hình kết nối (env: `DATABASE_URL`). |
| **2** | Tạo schema PostgreSQL (migration hoặc script SQL): `research_runs`, `bank_kpi_snapshots`. |
| **3** | Implement `db/repository.py`: upsert snapshot (chỉ khi có data), get latest by `reporting_period`. |
| **4** | Implement `jobs/daily_crawl.py`: loop banks, gọi `research_bank_async`, upsert từng bank thành công vào DB. |
| **5** | Implement `jobs/report_from_db.py`: đọc snapshot từ DB, build list peers + subject, gọi `BankingReporterAgent.generate_full_report`, ghi file. |
| **6** | CLI hoặc entrypoint: `python -m jobs.daily_crawl` và `python -m jobs.report_from_db` (hoặc tích hợp vào `main.py` với subcommand). |
| **7** | (Tùy chọn) Scheduler: cron hoặc Celery/Airflow chạy daily_crawl mỗi ngày; report có thể chạy tay hoặc sau crawl. |

---

## 9. Tóm tắt

- **Crawl**: Chạy hằng ngày, **luôn** crawl hết tất cả bank; **chỉ cập nhật DB** khi có `extracted_kpis` cho bank + kỳ đó.
- **DB**: PostgreSQL với `research_runs` và `bank_kpi_snapshots`; upsert theo `(bank_name, reporting_period)`.
- **Report**: Đọc từ DB → format giống hiện tại → gọi `BankingReporterAgent` (logic agent không đổi).
- **Agent**: Giữ nguyên `BankingResearchAgent`, `BankingReporterAgent`, prompts và graph.

---

## 10. Đã triển khai (sau khi làm 7 phase)

- **Phase 1**: Dependency `asyncpg`, biến `database_url` trong `utils/setting.py`.
- **Phase 2**: Schema trong `db/migrations/001_initial_schema.sql`; **migration 002**: `reporting_year`/`reporting_quarter`, bảng `bank_kpi_values`.
- **Phase 3**: `db/connection.py`, `db/repository.py` (upsert_snapshot, get_latest_by_period, get_latest_by_year_quarter).
- **Phase 4**: `jobs/daily_crawl.py` — crawl tất cả bank, upsert khi có data.
- **Phase 5**: `jobs/report_from_db.py` — đọc DB (ưu tiên query theo year/quarter nếu parse được), gen report.
- **Phase 6**: CLI `main.py`: `crawl` | `report` | `run` (legacy).
- **Phase 7**: Hướng dẫn cron trong `docs/SCHEDULER_CRON.md`, script `scripts/run_crawl.sh`.
- **Backfill**: Script `scripts/backfill_db.py` — cập nhật reporting_year/quarter và ghi `bank_kpi_values` cho snapshot cũ (chạy một lần sau migration 002).

**Kỳ báo cáo (REPORTING_PERIOD)**: Hỗ trợ nhiều format trong `config/banks.py`: `2025`, `Q1 2025`, `Quý 1 - năm 2025`, ... Hàm `parse_reporting_period()` trả về (year, quarter) để lưu và query theo `reporting_year`/`reporting_quarter`.

**Lệnh thường dùng**:
```bash
# Tạo/cập nhật bảng (chạy tất cả file trong db/migrations/)
python -m db.run_migration

# Backfill snapshot cũ (sau khi chạy migration 002 lần đầu)
python scripts/backfill_db.py

# Crawl và lưu DB
python main.py crawl

# Gen report từ DB
python main.py report

# Chạy legacy (crawl + report in-memory, không DB)
python main.py run
```
