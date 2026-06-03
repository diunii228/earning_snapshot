# Agent-Competitor Pipeline Guide

Tài liệu này mô tả cách chạy dự án theo 3 luồng ingestion (web / PDF BCTC / manual Excel) và cách merge theo độ ưu tiên.

## Tổng Quan

Mục tiêu: cập nhật KPI của 7 ngân hàng vào database và dùng database để tạo Daily Earning Summary email.

Độ ưu tiên dữ liệu (thấp -> cao):

- Web crawl: `source_type` mặc định (web)
- PDF BCTC: `source_type=financial_statement_pdf`
- Manual Excel: `source_type=manual_override`

Khi cùng 1 KPI đã tồn tại, nguồn ưu tiên cao hơn sẽ ghi đè nguồn thấp hơn.

## Database Tables (chính)

- `research_runs`: audit mỗi lần chạy job
- `bank_kpi_snapshots`: snapshot KPI theo `bank_name + reporting_period + target_date`
- `bank_kpi_values`: bảng “phẳng” tách từng KPI từ snapshot (dễ query)
- `bank_fs_components`: raw components phục vụ tính KPI (CASA/growth/credit/NIM LTM, ...)

## Các Lệnh Chạy

Tất cả command chạy trong repo:

`cd /Users/ddlyy/Documents/NCKH/agent-competitor`

### 0) Chạy migration (bắt buộc khi thay đổi schema)

`python -m db.run_migration`

### 1) Web crawl (ưu tiên thấp nhất)

Chỉ crawl web và upsert snapshot theo ngày:

`python main.py crawl-web --period "Q1 2026" --date 2026-05-04`

Ghi DB:
- `research_runs`
- `bank_kpi_snapshots` (merge theo priority per KPI)
- `bank_kpi_values`

### 2) PDF BCTC extract (ưu tiên cao hơn web)

Chỉ ingest PDF BCTC và upsert components + snapshot:

`python main.py ingest-pdf --period "Q1 2026" --date 2026-05-04`

Ghi DB:
- `bank_fs_components` (raw components)
- `bank_kpi_snapshots` (KPI compute từ components)

### 3) Manual Excel (ưu tiên cao nhất)

File manual có thể là `.xlsx` hoặc `.csv` theo format cột:

- `bank_name`, `ticker`, `kpi_name`, `value_num`, `unit`, `source_url`, ...
- optional: `value_num_previous` (hoặc typo `value_num_privious`) để hỗ trợ compute growth

Chạy ingest:

`python main.py manual-csv --csv /Users/ddlyy/Documents/NCKH/agent-competitor/data_manual.xlsx --period "Q1 2026" --date 2026-04-29`

Ghi DB:
- `bank_fs_components` với `source_type=manual_override`
- `bank_kpi_snapshots` (merge, manual override được ưu tiên cao nhất)

### 4) Merge (chạy theo thứ tự web -> pdf -> excel)

`python main.py merge --period "Q1 2026" --date 2026-05-04 --excel /Users/ddlyy/Documents/NCKH/agent-competitor/VCB_Earning_Snapshot_1Q26.xlsx`

Lưu ý:
- Merge ở đây là chạy 3 lệnh liên tiếp theo đúng thứ tự ưu tiên.
- Nếu bạn không truyền `--excel` thì sẽ chỉ chạy web + pdf.

## Rerun 1 Luồng (không phá luồng khác)

Vì snapshot đang upsert theo kiểu merge per KPI (`upsert_snapshot_merge`), nên bạn có thể rerun từng luồng:

- rerun web: không overwrite KPI từ PDF/manual nếu `source_type` của KPI đó có priority cao hơn
- rerun pdf: sẽ overwrite web, nhưng không overwrite manual override
- rerun manual: overwrite tất cả

## Daily Earning Summary Email

Email lấy hoàn toàn từ DB snapshot:

`python banking_summary_agent.py --period "Q1 2026"`

Earning Summary:
- chỉ hiển thị bank có KPI update so với ngày trước
- tối đa 3 dòng/bank dựa trên `reasoning` / `source_quote` trong DB

## Troubleshooting

- Nếu transaction SQL bị lỗi `25P02`: chạy `ROLLBACK;` rồi chạy lại từng câu.
- Nếu growth không lên: cần `value_previous` ở `bank_fs_components` hoặc nhập thẳng `*_growth_ytd`.
