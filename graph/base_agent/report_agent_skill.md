# BankingReporterAgent — Skill Catalog
> **Mục đích tài liệu này**: Cho phép AI agent hoặc developer tra cứu nhanh — _cần chạy skill nào, truyền gì, nhận lại gì, khi nào KHÔNG nên dùng_ — mà không cần đọc source code.

---

## Mục lục
- [BankingReporterAgent — Skill Catalog](#bankingreporteragent--skill-catalog)
  - [Mục lục](#mục-lục)
  - [1. Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
    - [Vai trò từng file](#vai-trò-từng-file)
    - [Cấu hình LLM mặc định](#cấu-hình-llm-mặc-định)
  - [2. Input / Output Contract](#2-input--output-contract)
    - [Input chính của `generate_overall_strategy`](#input-chính-của-generate_overall_strategy)
    - [Output](#output)
  - [3. Luồng xử lý nội bộ](#3-luồng-xử-lý-nội-bộ)
  - [4. Ví dụ gọi end-to-end](#4-ví-dụ-gọi-end-to-end)
    - [Python (async)](#python-async)
    - [Python (tích hợp sau BankingResearchAgent)](#python-tích-hợp-sau-bankingresearchagent)
  - [5. Skill: generate\_overall\_strategy](#5-skill-generate_overall_strategy)
    - [Signature](#signature)
    - [Hành vi chi tiết](#hành-vi-chi-tiết)
    - [Output mẫu (cấu trúc phần)](#output-mẫu-cấu-trúc-phần)
    - [Khi KHÔNG nên gọi skill này](#khi-không-nên-gọi-skill-này)
  - [6. Skill: generate\_individual\_highlight](#6-skill-generate_individual_highlight)
    - [Signature](#signature-1)
    - [Input](#input)
    - [Output](#output-1)
    - [Prompt sử dụng](#prompt-sử-dụng)
    - [Lưu ý](#lưu-ý)
  - [7. Skill: \_create\_master\_comparison\_table](#7-skill-_create_master_comparison_table)
    - [Signature](#signature-2)
    - [Cách hoạt động](#cách-hoạt-động)
    - [Cấu trúc tìm kiếm KPI (`get_clean_value`)](#cấu-trúc-tìm-kiếm-kpi-get_clean_value)
    - [Output mẫu](#output-mẫu)
  - [8. Skill: \_generate\_toc](#8-skill-_generate_toc)
    - [Signature](#signature-3)
    - [Cấu trúc TOC sinh ra](#cấu-trúc-toc-sinh-ra)
    - [Anchor ID rules](#anchor-id-rules)
  - [9. Skill: \_map\_global\_indices\_to\_data](#9-skill-_map_global_indices_to_data)
    - [Signature](#signature-4)
    - [Hành vi](#hành-vi)
    - [Mapping toàn cục](#mapping-toàn-cục)
    - [Ví dụ](#ví-dụ)
  - [10. Skill: \_process\_ai\_content\_links](#10-skill-_process_ai_content_links)
    - [Signature](#signature-5)
    - [Các bước xử lý](#các-bước-xử-lý)
    - [Output HTML anchor](#output-html-anchor)
  - [11. Report Output Schema đầy đủ](#11-report-output-schema-đầy-đủ)
    - [PAGE\_BREAK token](#page_break-token)
  - [12. KPI Groups \& Name Map](#12-kpi-groups--name-map)
    - [structured\_kpi\_groups (6 nhóm)](#structured_kpi_groups-6-nhóm)
    - [kpi\_name\_map (key → display label trong bảng)](#kpi_name_map-key--display-label-trong-bảng)
  - [13. Điều kiện bỏ qua Market Landscape](#13-điều-kiện-bỏ-qua-market-landscape)
    - [Logic kiểm tra](#logic-kiểm-tra)
    - [Bảng quyết định](#bảng-quyết-định)
    - [Tác động đến đánh số La Mã](#tác-động-đến-đánh-số-la-mã)
  - [14. Retry / Timeout / Giới hạn kỹ thuật](#14-retry--timeout--giới-hạn-kỹ-thuật)
    - [Hành vi khi LLM Strategy lỗi](#hành-vi-khi-llm-strategy-lỗi)
  - [15. Quick Mapping: Yêu cầu → Skill](#15-quick-mapping-yêu-cầu--skill)

---

## 1. Tổng quan kiến trúc

```
graph/base_agent/
├── reporting_agent.py   # BankingReporterAgent (entry-point chính + các skill)
├── prompts.py           # OVERALL_MARKET_STRATEGY_PROMPT, INDIVIDUAL_HIGHLIGHTS_PROMPT
models/
└── llm_factory.py       # get_llm() — khởi tạo LLM instance
utils/
└── token_tracker.py     # token_tracker.add_from_response() — theo dõi token usage
```

### Vai trò từng file

| File | Vai trò |
|------|---------|
| `reporting_agent.py` | Implement toàn bộ logic sinh báo cáo HTML |
| `prompts.py` | Prompt LLM cho phân tích chiến lược và highlight từng ngân hàng |
| `llm_factory.py` | Factory tạo LLM instance (Gemini / GPT / Claude) |
| `token_tracker.py` | Ghi nhận token đã dùng từ response LLM |

### Cấu hình LLM mặc định

```python
get_llm(
    model_name=model_name,  # None → dùng default model
    temperature=0.1,        # Thấp → AI tuân thủ tuyệt đối giọng điệu trung lập
    top_p=0.3,
    max_tokens=8000,
    request_timeout=300     # 5 phút timeout cho LLM call
)
```

---

## 2. Input / Output Contract

### Input chính của `generate_overall_strategy`

```python
await agent.generate_overall_strategy(
    peers_list=[
        {
            "bank_name": "TCB",
            "extracted_kpis": { ... }   # Dict KPI theo schema 6 category
        },
        ...
    ],
    subject_data={
        "bank_name": "VCB",
        "extracted_kpis": { ... }       # Nếu rỗng → bỏ qua Market Landscape
    },
    target_date="2024-03-31"            # Optional, dạng "YYYY-MM-DD"
)
```

| Tham số | Kiểu | Bắt buộc | Mô tả |
|---------|------|----------|-------|
| `peers_list` | `List[Dict]` | ✅ | Danh sách ngân hàng so sánh, mỗi phần tử có `bank_name` + `extracted_kpis` |
| `subject_data` | `Dict` | ✅ | Ngân hàng chủ thể phân tích (highlighted màu đỏ trong bảng) |
| `target_date` | `str` | ❌ | Ngày báo cáo dạng `YYYY-MM-DD`. Nếu None → dùng ngày hiện tại |

### Output

Trả về **chuỗi HTML đầy đủ** của báo cáo, bao gồm:
- Header tiêu đề + ngày báo cáo
- Table of Contents (TOC)
- Master Comparison Table
- Section Market Landscape & Strategy *(nếu subject có data)*
- Detailed Highlights từng ngân hàng
- References section

---

## 3. Luồng xử lý nội bộ

```
generate_overall_strategy()
        │
        ├─► _map_global_indices_to_data(subject_kpis)
        │       └─ Gán source_reference_id [1], [2]... cho mỗi KPI
        │
        ├─► _map_global_indices_to_data(peer_kpis) × N peers
        │
        ├─► _create_master_comparison_table(subject, peers)
        │       └─ Tạo Markdown table theo 6 KPI group
        │
        ├─► [Kiểm tra subject có data không?]
        │       │
        │       ├─ CÓ data → LLM.ainvoke(OVERALL_MARKET_STRATEGY_PROMPT)
        │       │               └─ _process_ai_content_links(response)
        │       │
        │       └─ KHÔNG data → strategy_section = "" (bỏ qua hoàn toàn)
        │
        ├─► asyncio.gather([generate_individual_highlight(bank) for all banks])
        │       └─ LLM.ainvoke(INDIVIDUAL_HIGHLIGHTS_PROMPT) × (1 subject + N peers)
        │
        ├─► _generate_toc(subject_name, peers_list)
        │
        └─► Assemble HTML report parts → return "\n\n".join(report_parts)
```

**Lưu ý quan trọng**:
- `global_url_to_id` và `global_id_to_url` được **reset** ở đầu mỗi lần gọi `generate_overall_strategy`.
- Các individual highlight chạy **song song** (`asyncio.gather`) — không tuần tự.
- Bộ đếm `current_section_idx` đánh số La Mã động — nếu không có strategy thì Highlights là **Section I**.

---

## 4. Ví dụ gọi end-to-end

### Python (async)

```python
import asyncio
from graph.base_agent.reporting_agent import BankingReporterAgent

agent = BankingReporterAgent()

subject = {
    "bank_name": "VCB",
    "extracted_kpis": {
        "profitability": {
            "pbt": {"value": 12500.0, "unit": "billion VND", "source_url": "https://cafef.vn/vcb-q1.html"}
        }
    }
}

peers = [
    {
        "bank_name": "TCB",
        "extracted_kpis": {
            "profitability": {
                "pbt": {"value": 6800.0, "unit": "billion VND", "source_url": "https://cafef.vn/tcb-q1.html"}
            }
        }
    }
]

html_report = asyncio.run(
    agent.generate_overall_strategy(
        peers_list=peers,
        subject_data=subject,
        target_date="2024-03-31"
    )
)

with open("report.html", "w", encoding="utf-8") as f:
    f.write(html_report)
```

### Python (tích hợp sau BankingResearchAgent)

```python
import asyncio
from graph.base_agent.runner import research_bank_async
from graph.base_agent.reporting_agent import BankingReporterAgent

async def full_pipeline(banks, period):
    # B1: Research song song tất cả ngân hàng
    tasks = [
        research_bank_async(urls=b["urls"], bank_name=b["name"], reporting_period=period)
        for b in banks
    ]
    results = await asyncio.gather(*tasks)

    # B2: Tạo báo cáo
    subject_data = {"bank_name": results[0]["bank_name"], "extracted_kpis": results[0]["extracted_kpis"]}
    peers_list   = [{"bank_name": r["bank_name"], "extracted_kpis": r["extracted_kpis"]} for r in results[1:]]

    reporter = BankingReporterAgent()
    return await reporter.generate_overall_strategy(peers_list, subject_data, target_date="2024-03-31")
```

---

## 5. Skill: generate_overall_strategy

**Entry-point chính** — orchestrate toàn bộ quy trình sinh báo cáo.

### Signature

```python
async def generate_overall_strategy(
    self,
    peers_list: List[Dict],
    subject_data: Dict,
    target_date: Optional[str] = None
) -> str
```

### Hành vi chi tiết

| Bước | Hành động | Điều kiện |
|------|-----------|-----------|
| 1 | Reset `global_url_to_id`, `global_id_to_url` | Luôn thực hiện |
| 2 | Parse `target_date` → định dạng `"Month DD, YYYY"` | Nếu `target_date` hợp lệ YYYY-MM-DD |
| 3 | `_map_global_indices_to_data` cho subject và từng peer | Luôn thực hiện |
| 4 | `_create_master_comparison_table` | Luôn thực hiện |
| 5 | Gọi LLM → `OVERALL_MARKET_STRATEGY_PROMPT` | CHỈ khi `extracted_kpis` của subject **không rỗng** |
| 6 | `asyncio.gather` các `generate_individual_highlight` | Luôn thực hiện cho tất cả banks |
| 7 | Lắp ráp HTML parts với đánh số La Mã động | Luôn thực hiện |

### Output mẫu (cấu trúc phần)

```
[H1] COMPETITORS ANALYSIS REPORT
[p]  Report Date: March 31, 2024 | Data Extraction Date: 2024-03-31
[TOC]
[PAGE_BREAK]
[Master Comparison Table]
[PAGE_BREAK]
[I. MARKET LANDSCAPE & STRATEGIC POSITIONING]   ← chỉ có khi subject có data
[PAGE_BREAK]
[II. DETAILED OPERATIONAL HIGHLIGHTS]
  └─ VCB (Subject)
  └─ TCB
  └─ ...
[PAGE_BREAK]
[REFERENCES]
```

### Khi KHÔNG nên gọi skill này

- Khi chỉ cần bảng so sánh đơn giản (dùng `_create_master_comparison_table` trực tiếp).
- Khi chỉ cần highlight 1 ngân hàng (dùng `generate_individual_highlight` trực tiếp).
- Khi `peers_list` rỗng và `subject_data` cũng không có KPI (output sẽ là báo cáo trống).

---

## 6. Skill: generate_individual_highlight

Sinh phần **"Detailed Highlight"** cho một ngân hàng cụ thể dưới dạng HTML/Markdown.

### Signature

```python
async def generate_individual_highlight(self, bank_data: Dict) -> str
```

### Input

```python
bank_data = {
    "bank_name": "VCB",
    "extracted_kpis": { ... }   # Dict KPI đã qua _map_global_indices_to_data
}
```

### Output

Chuỗi HTML fragment, ví dụ:

```html
<a name='vcb'></a>
### VCB
[Nội dung phân tích từ LLM với inline citation [1], [2]...]
```

### Prompt sử dụng

`INDIVIDUAL_HIGHLIGHTS_PROMPT` — format với:
- `{target_bank_name}`: tên ngân hàng
- `{target_bank_data}`: JSON string của `extracted_kpis`

### Lưu ý

- Anchor ID được tạo bằng `_get_anchor_id(name)`: lowercase, thay space bằng `-`.
- Các citation `[N]` trong content được convert thành thẻ `<a href>` bởi `_process_ai_content_links`.
- Hàm này **không** reset `global_id_to_url` — dùng state chung từ `generate_overall_strategy`.

---

## 7. Skill: _create_master_comparison_table

Tạo **Markdown table** so sánh KPI giữa subject bank và các peer banks.

### Signature

```python
def _create_master_comparison_table(
    self,
    subject_data: Dict,
    peers_list: List[Dict]
) -> str
```

### Cách hoạt động

1. Duyệt qua 6 KPI group theo `structured_kpi_groups`.
2. Với mỗi KPI key, tìm `value` và `unit` từ `extracted_kpis` (tìm flat trước, sau đó nested).
3. Chỉ render row nếu **ít nhất 1 bank** (subject hoặc peer) có data hợp lệ cho KPI đó.
4. Format số: `≥ 1000` → `"{:,.0f}"` | `< 1000` → `"{:,.1f}"`.
5. Subject bank được **highlight đỏ** bằng `<span style='color: #c60000'>`.

### Cấu trúc tìm kiếm KPI (`get_clean_value`)

```python
# 1. Tìm trực tiếp ở top-level extracted_kpis
extracted[target_key] → details

# 2. Nếu không có → tìm trong các section con
for section in extracted.values():
    if target_key in section:
        details = section[target_key]
```

### Output mẫu

```markdown
### **Master Comparison Table**

| **Metric** | **Unit** | <span style='color: #c60000'>VCB (Subject)</span> | **TCB** |
|---|---|---|---|
| Profit Before Tax (PBT) | billion VND | 12,500 | 6,800 |
| PBT Growth (YoY) | % | 15.2 | 8.7 |
...
```

---

## 8. Skill: _generate_toc

Tạo **Table of Contents** HTML với anchor links đến từng section của báo cáo.

### Signature

```python
def _generate_toc(self, subject_name: str, peers_list: List[Dict]) -> str
```

### Cấu trúc TOC sinh ra

```
1. Master Comparison Table         → #master-comparison-table
2. Market Landscape & Strategy     → #market-landscape-strategy
3. Detailed Operational Highlights → #detailed-highlights
   ├─ [Subject Bank] (Subject Bank) → #{anchor_id}   ← in đậm
   ├─ Peer Bank 1                  → #{anchor_id}
   └─ Peer Bank N                  → #{anchor_id}
4. References                      → #references_section
```

### Anchor ID rules

```python
anchor_id = name.strip().lower().replace(" ", "-")
# "VCB" → "vcb"
# "MB Bank" → "mb-bank"
# "VP Bank" → "vp-bank"
```

---

## 9. Skill: _map_global_indices_to_data

Gán **source reference ID** (`[1]`, `[2]`...) cho từng KPI dựa trên `source_url`.

### Signature

```python
def _map_global_indices_to_data(self, kpi_data: Dict) -> Dict
```

### Hành vi

- Deep copy `kpi_data` — **không mutate** input gốc.
- Với mỗi KPI có `source_url`:
  - Nếu là `str`: tách theo `,` → xử lý từng URL.
  - Nếu là `list`: duyệt từng phần tử.
  - URL phải bắt đầu bằng `http` mới được xử lý.
- Ghi `source_reference_id = "[1][2]..."` vào KPI details.
- **Xoá** trường `source_url` khỏi dict sau khi xử lý.

### Mapping toàn cục

```python
# URL → ID (tăng dần, không reset giữa các bank trong cùng 1 report)
self.global_url_to_id = {"https://cafef.vn/vcb.html": 1, "https://vneconomy.vn/tcb.html": 2, ...}
self.global_id_to_url = {1: "https://cafef.vn/vcb.html", 2: "https://vneconomy.vn/tcb.html", ...}
```

### Ví dụ

```python
# Input KPI
{"pbt": {"value": 12500, "unit": "billion VND", "source_url": "https://cafef.vn/vcb.html"}}

# Output KPI
{"pbt": {"value": 12500, "unit": "billion VND", "source_reference_id": "[1]"}}
```

---

## 10. Skill: _process_ai_content_links

Chuyển đổi citation dạng `[1]`, `[1] [2]` trong text LLM thành **thẻ HTML anchor** clickable.

### Signature

```python
def _process_ai_content_links(self, content: Any) -> str
```

### Các bước xử lý

| Bước | Regex / Hành động | Mục đích |
|------|-------------------|---------|
| 1 | `content[0].get('text')` nếu là list | Unpack LangChain response |
| 2 | `re.sub(r'\(https?://...\)', "")` | Xoá URL thô AI lỡ sinh ra |
| 3 | `[1, 2]` → `[1] [2]` | Tách cụm 2 số |
| 4 | `[1, 2, 3]` → `[1] [2] [3]` | Tách cụm 3 số |
| 5 | `[N]` → `<a href="URL" target="_blank">[N]</a>` | Thay thế bằng HTML link |

### Output HTML anchor

```html
<a href="https://cafef.vn/vcb.html" target="_blank"
   style="font-weight: bold; text-decoration: none; color: #1a365d;">[1]</a>
```

Nếu `idx` không tìm thấy trong `global_id_to_url` → fallback href là `#N`.

---

## 11. Report Output Schema đầy đủ

Báo cáo cuối cùng là **chuỗi HTML** gồm các phần sau (theo thứ tự):

```
Part 1: Title Header
  <h1 style='text-align: center; font-size: 28px; text-transform: uppercase;'>
    COMPETITORS ANALYSIS REPORT
  </h1>

Part 2: Date Line
  <p style='text-align: center; font-size: 13px; color: #666;'>
    Report Date: {report_date} | Data Extraction Date: {target_date}
  </p>

Part 3: Table of Contents
  <div id='toc'>...</div>

[PAGE BREAK]

Part 4: Master Comparison Table
  <a name='master-comparison-table'></a>
  ### **Master Comparison Table**
  | Metric | Unit | Subject | Peer1 | ... |

[PAGE BREAK]

Part 5: Market Landscape [CHỈ KHI SUBJECT CÓ DATA]
  <h2 id='market-landscape-strategy'>I. MARKET LANDSCAPE & STRATEGIC POSITIONING</h2>
  [LLM generated content với inline citations]

[PAGE BREAK]

Part 6: Detailed Highlights
  <h2 id='detailed-highlights'>II. DETAILED OPERATIONAL HIGHLIGHTS</h2>
  <a name='vcb'></a>
  ### VCB
  [LLM generated content]
  ...

[PAGE BREAK]

Part 7: References
  ---
  <h2 align='center' id='references_section'>REFERENCES</h2>
  <p id="1">[1]. <a href="https://...">https://...</a></p>
  ...
```

### PAGE_BREAK token

```html
<div style="page-break-after: always;"></div>
```

Được chèn giữa các section để **in/export PDF** hiển thị đúng trang.

---

## 12. KPI Groups & Name Map

### structured_kpi_groups (6 nhóm)

| Nhóm | Các KPI key |
|------|-------------|
| **1. Profitability** | `pbt`, `pbt_growth_yoy`, `pbt_growth_qoq`, `pat`, `net_interest_income`, `non_interest_income`, `eps` |
| **2. Balance Sheet** | `total_assets`, `total_assets_growth_yoy`, `total_assets_growth_qoq`, `total_assets_growth_qtd`, `total_assets_growth_ytd`, `equity`, `charter_capital`, `leverage_ratio` |
| **3. Lending & Deposit** | `total_credit`, `credit_growth_yoy`, `credit_growth_qoq`, `credit_growth_ytd`, `total_deposits`, `deposit_growth_yoy`, `deposit_growth_qoq`, `deposit_growth_ytd`, `loan_to_deposit_ratio`, `mlt_ratio`, `wholesale_funding_ratio` |
| **4. Profitability Ratios** | `roa`, `roe`, `nim`, `cir`, `cost_of_funds`, `lending_yields` |
| **5. Asset Quality** | `npl_ratio`, `group_2_ratio`, `llr`, `credit_cost`, `coverage_ratio` |
| **6. Other Metrics** | `casa_ratio`, `net_interest_income_growth`, `fee_income`, `operating_expenses`, `car`, `p_e_ratio`, `p_b_ratio` |

### kpi_name_map (key → display label trong bảng)

| Key | Display Label |
|-----|--------------|
| `pbt` | Profit Before Tax (PBT) |
| `pbt_growth_yoy` | PBT Growth (YoY) |
| `pbt_growth_qoq` | PBT Growth (QoQ) |
| `pat` | Profit After Tax (PAT) |
| `net_interest_income` | Net Interest Income (NII) |
| `non_interest_income` | Non-Interest Income |
| `eps` | Earnings Per Share (EPS) |
| `total_assets` | Total Assets |
| `total_assets_growth_yoy` | Assets Growth (YoY) |
| `total_assets_growth_qoq` | Assets Growth (QoQ) |
| `total_assets_growth_qtd` | Assets Growth (QTD) |
| `total_assets_growth_ytd` | Assets Growth (YTD) |
| `equity` | Owner's Equity |
| `charter_capital` | Charter Capital |
| `leverage_ratio` | Leverage Ratio |
| `total_credit` | Total Credit |
| `credit_growth_yoy` | Credit Growth (YoY) |
| `credit_growth_qoq` | Credit Growth (QoQ) |
| `credit_growth_ytd` | Credit Growth (YTD) |
| `total_deposits` | Total Deposits |
| `deposit_growth_yoy` | Deposit Growth (YoY) |
| `deposit_growth_qoq` | Deposit Growth (QoQ) |
| `deposit_growth_ytd` | Deposit Growth (YTD) |
| `loan_to_deposit_ratio` | LDR |
| `mlt_ratio` | MLT Ratio |
| `wholesale_funding_ratio` | Wholesale Funding |
| `roa` | ROA |
| `roe` | ROE |
| `nim` | NIM |
| `cir` | Cost to Income (CIR) |
| `cost_of_funds` | Cost of Funds (COF) |
| `lending_yields` | Lending Yields |
| `npl_ratio` | NPL Ratio |
| `group_2_ratio` | Group 2 Loan Ratio |
| `llr` | Loan Loss Reserve (LLR) |
| `credit_cost` | Credit Cost |
| `coverage_ratio` | NPL Coverage Ratio |
| `casa_ratio` | CASA Ratio |
| `net_interest_income_growth` | NII Growth |
| `fee_income` | Net Fee Income |
| `operating_expenses` | Operating Expenses (OPEX) |
| `car` | Capital Adequacy (CAR) |
| `p_e_ratio` | P/E Ratio |
| `p_b_ratio` | P/B Ratio |

---

## 13. Điều kiện bỏ qua Market Landscape

Section **"Market Landscape & Strategic Positioning"** chỉ được render khi subject bank có dữ liệu KPI.

### Logic kiểm tra

```python
subject_raw_kpis = subject_data.get("extracted_kpis", {})

is_subject_data_empty = (
    not subject_raw_kpis
    or all(not v for v in subject_raw_kpis.values())
)
```

### Bảng quyết định

| `extracted_kpis` của subject | `is_subject_data_empty` | Market Landscape | Highlights |
|------------------------------|------------------------|-----------------|------------|
| `{}` (rỗng) | `True` | ❌ Bỏ qua | ✅ Vẫn render |
| `{"profitability": {}}` (section rỗng) | `True` | ❌ Bỏ qua | ✅ Vẫn render |
| `{"profitability": {"pbt": {...}}}` | `False` | ✅ Render | ✅ Vẫn render |

### Tác động đến đánh số La Mã

```
Khi CÓ Market Landscape:
  I.  MARKET LANDSCAPE & STRATEGIC POSITIONING
  II. DETAILED OPERATIONAL HIGHLIGHTS

Khi KHÔNG CÓ Market Landscape:
  I.  DETAILED OPERATIONAL HIGHLIGHTS
```

---

## 14. Retry / Timeout / Giới hạn kỹ thuật

| Hàm / Bước | Timeout | Retry | Ghi chú |
|------------|---------|-------|---------|
| `LLM.ainvoke` (strategy) | 300 giây (request_timeout) | 0 (không retry) | Lỗi → `strategy_section = ""`, không raise |
| `LLM.ainvoke` (highlight × N banks) | 300 giây mỗi call | 0 (không retry) | Chạy song song qua `asyncio.gather` |
| `asyncio.gather` highlights | Không có timeout riêng | — | Tất cả highlights phải hoàn tất trước khi assemble |
| `max_tokens` LLM | — | — | 8000 tokens |
| `temperature` LLM | — | — | 0.1 |
| `top_p` LLM | — | — | 0.3 |

### Hành vi khi LLM Strategy lỗi

```python
except Exception as e:
    logger.error(f"Lỗi gọi LLM Strategy: {e}")
    strategy_section = ""   # Báo cáo vẫn được sinh, chỉ thiếu section chiến lược
```

> ⚠️ **Không raise exception** — lỗi LLM strategy không làm crash toàn bộ pipeline. Báo cáo vẫn được trả về với bảng so sánh và highlights.

---

## 15. Quick Mapping: Yêu cầu → Skill

| Yêu cầu | Skill cần gọi | Preconditions |
|---------|--------------|---------------|
| Sinh báo cáo đầy đủ (HTML) | `generate_overall_strategy(peers_list, subject_data, target_date)` | Không có — entry-point chính |
| Chỉ lấy phần highlight 1 ngân hàng | `generate_individual_highlight(bank_data)` | `bank_data` có `bank_name` + `extracted_kpis` |
| Chỉ lấy bảng so sánh KPI | `_create_master_comparison_table(subject_data, peers_list)` | Cả 2 đã qua `_map_global_indices_to_data` |
| Chỉ sinh TOC | `_generate_toc(subject_name, peers_list)` | `peers_list` là list dict có `bank_name` |
| Gán source reference ID cho KPI | `_map_global_indices_to_data(kpi_data)` | `kpi_data` dict có trường `source_url` |
| Convert `[1]` thành HTML link | `_process_ai_content_links(content)` | `global_id_to_url` đã được populate |
| Sinh báo cáo KHÔNG có Market Landscape | `generate_overall_strategy(...)` với `subject_data["extracted_kpis"] = {}` | Subject không có data |
| Sinh báo cáo sau khi research xong | Kết hợp `research_bank_async` → `generate_overall_strategy` | Research state `status == "validated"` |