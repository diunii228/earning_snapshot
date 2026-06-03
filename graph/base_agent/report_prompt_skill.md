# Reporting Agent — Prompts Skill Catalog
> **Mục đích tài liệu này**: Hướng dẫn cách viết, tuỳ chỉnh và debug các prompt trong `prompts.py` của reporting pipeline. Bao gồm các nguyên tắc thiết kế, lưu ý quan trọng, anti-pattern cần tránh, và template sửa đổi nhanh.

---

## Mục lục
1. [Tổng quan các prompt trong file](#1-tổng-quan-các-prompt-trong-file)
2. [Nguyên tắc thiết kế chung](#2-nguyên-tắc-thiết-kế-chung)
3. [Prompt: BANKING_KPI_EXTRACTION_PROMPT](#3-prompt-banking_kpi_extraction_prompt)
4. [Prompt: BANKING_KPI_VALIDATION_PROMPT](#4-prompt-banking_kpi_validation_prompt)
5. [Prompt: INDIVIDUAL_HIGHLIGHTS_PROMPT](#5-prompt-individual_highlights_prompt)
6. [Prompt: OVERALL_MARKET_STRATEGY_PROMPT](#6-prompt-overall_market_strategy_prompt)
7. [Prompt: COMPARISON_SYSTEM_PROMPT](#7-prompt-comparison_system_prompt)
8. [Kỹ thuật Citation [N] — Nguyên tắc vàng](#8-kỹ-thuật-citation-n--nguyên-tắc-vàng)
9. [Kiểm soát giọng văn và tone](#9-kiểm-soát-giọng-văn-và-tone)
10. [Anti-patterns cần tránh khi viết prompt](#10-anti-patterns-cần-tránh-khi-viết-prompt)
11. [Checklist trước khi deploy prompt mới](#11-checklist-trước-khi-deploy-prompt-mới)
12. [Quick Reference: Sửa đổi nhanh theo tình huống](#12-quick-reference-sửa-đổi-nhanh-theo-tình-huống)

---

## 1. Tổng quan các prompt trong file

| Prompt | Dùng bởi | Mục đích | LLM Temperature |
|--------|----------|---------|-----------------|
| `BANKING_KPI_EXTRACTION_PROMPT` | `BankingResearchAgent.extract_banking_kpis` | Trích KPI từ raw text | Thấp (0.1) |
| `BANKING_KPI_VALIDATION_SYSTEM_MESSAGE` | `BankingResearchAgent.validate_banking_kpis` | System role cho validate | Thấp (0.1) |
| `BANKING_KPI_VALIDATION_PROMPT` | `BankingResearchAgent.validate_banking_kpis` | Kiểm tra chất lượng KPI | Thấp (0.1) |
| `INDIVIDUAL_HIGHLIGHTS_PROMPT` | `BankingReporterAgent.generate_individual_highlight` | Phân tích highlight 1 ngân hàng | Thấp (0.1) |
| `OVERALL_MARKET_STRATEGY_PROMPT` | `BankingReporterAgent.generate_overall_strategy` | Phân tích thị trường + chiến lược | Thấp (0.1) |

### Sơ đồ prompt flow trong pipeline đầy đủ

```
[raw_content] ──► EXTRACTION_PROMPT ──► extracted_kpis (JSON)
                                              │
                                              ▼
                                     VALIDATION_PROMPT ──► validation_results
                                              │
                               ┌─────────────┘
                               ▼
              ┌────────────────────────────────────────────────┐
              │          BankingReporterAgent                  │
              │                                                │
              │  extracted_kpis ──► INDIVIDUAL_HIGHLIGHTS      │
              │                          │                     │
              │  all_kpis       ──► OVERALL_MARKET_STRATEGY    │
              │                          │                     │
              │                    HTML Report                  │
              └────────────────────────────────────────────────┘
```

---

## 2. Nguyên tắc thiết kế chung

### 2.1 Cấu trúc XML tag cho prompt dài

Tất cả các prompt phức tạp đều dùng XML tag để phân tách rõ vai trò từng phần:

```
<role>         → Định nghĩa vai trò AI (WHO)
<task>         → Mô tả nhiệm vụ tổng thể (WHAT)
<input_data>   → Dữ liệu đầu vào (INPUT)
<output_format>→ Schema/format output mong muốn (HOW TO OUTPUT)
<critical_rules> → Ràng buộc cứng không được vi phạm (CONSTRAINTS)
<tone_control> → Kiểm soát giọng văn (STYLE)
```

> **Lý do**: XML tags giúp LLM phân biệt rõ "đây là instruction" vs "đây là data". Không dùng XML tag thuần Markdown dễ bị LLM hiểu nhầm đặc biệt khi data có chứa ký tự Markdown.

### 2.2 Role Injection — Định danh AI trước khi giao nhiệm vụ

Luôn mở đầu bằng `<role>` cụ thể, không chung chung:

```
✅ "You are a Senior Banking Analyst working at {subject_bank_name}."
✅ "You are a Precision Data Extraction Engine specialized in Banking Financial Reports."
❌ "You are a helpful AI assistant."  ← quá chung, dễ gây output generic
```

### 2.3 Phân tách Instruction vs Data

Dữ liệu đầu vào luôn được bọc trong tag riêng biệt:

```xml
<input_data>
{target_bank_data}
</input_data>
```

Không nhúng trực tiếp data vào câu instruction:

```
❌ "Analyze this data: {target_bank_data} and write highlights..."
✅ Đặt data trong <input_data>, instruction trong <task>
```

### 2.4 Output Schema là Contract không thể thay đổi

Khi prompt có `<mandatory_schema_structure>` hoặc `<output_format>` với JSON schema cụ thể, đó là **contract** giữa prompt và code parser. Thay đổi key name trong prompt mà không cập nhật code sẽ gây lỗi parse.

---

## 3. Prompt: BANKING_KPI_EXTRACTION_PROMPT

### Mục đích
Trích xuất 44 KPI từ raw content bài báo → JSON có cấu trúc 6 category chuẩn.

### Các placeholder bắt buộc

| Placeholder | Giá trị ví dụ | Lưu ý |
|-------------|--------------|-------|
| `{bank_name}` | `"Vietcombank"` | Tên chính xác, không viết tắt |
| `{reporting_period}` | `"Quý 4 2025"` hoặc `"Năm 2025"` | Xác định Quarter vs Full Year |
| `{target_date}` | `"2025-12-31"` hoặc `"Latest available"` | Dùng cho P/E, P/B realtime logic |
| `{raw_content}` | Nội dung bài báo gộp | Đã format "### SOURCE X: ..." |

### Kỹ thuật thiết kế quan trọng trong prompt này

#### A. Temporal Rules — Phần quan trọng nhất
Phần `<temporal_rules>` giải quyết vấn đề **Quarter vs Accumulated** — lỗi phổ biến nhất khi extract KPI ngân hàng Việt Nam:

```
Rule 1: Income metrics (PBT, PAT...) → PHẢI là standalone quarter nếu target là Quý
Rule 2: Balance sheet metrics (Assets, Deposits...) → Point-in-time, cuối năm = cuối Q4
Rule 3: ZERO INFERENCE — cấm chia số năm cho 4 để đoán quý
Rule 4: P/E, P/B, EPS — ưu tiên Vietstock realtime nếu target_date là hôm nay
```

**Khi sửa đổi phần này**, phải giữ nguyên logic 4 rule. Có thể thêm ví dụ mới vào `<extraction_example>` nhưng không được bỏ rule nào.

#### B. Variable Instructions — Data Dictionary
Section `<variable_instructions>` là bộ từ điển tra cứu keyword tiếng Việt cho từng KPI. Khi thêm KPI mới:

```markdown
- `ten_kpi_moi`: Tên đầy đủ tiếng Anh (Từ khóa tìm kiếm tiếng Việt). Ex: "Câu trích dẫn mẫu"
```

#### C. Mandatory Schema — Contract với parser
```
<mandatory_schema_structure> định nghĩa 6 category + 44 KPI keys.
```

> ⚠️ **CRITICAL**: Nếu thêm/đổi tên KPI ở đây, phải cập nhật đồng thời:
> - `kpi_name_map` trong `reporting_agent.py`
> - `structured_kpi_groups` trong `reporting_agent.py`
> - Validation benchmark trong `BANKING_KPI_VALIDATION_PROMPT`

#### D. Output Rules — Ràng buộc format JSON

Các rule quan trọng nhất cần giữ nguyên:
- Rule 7: `value` PHẢI là số thuần (Float/Int), không có chữ "hơn", ">", "<"
- Rule 8: `reporting_quarter` chỉ set integer khi text explicitly đề cập từ "Quý/Q"
- Rule 12: P/E, P/B là realtime → null nếu target_date là quá khứ

#### E. Abort condition
```json
{ "status": "NO_FINANCIAL_DATA_FOUND" }
```
Đây là signal đặc biệt để code upstream biết bỏ qua bank này. **Không được thay đổi** string này nếu không cập nhật code parser tương ứng.

### Khi nào cần sửa prompt này

| Tình huống | Cần sửa ở đâu |
|-----------|--------------|
| Thêm KPI mới (ví dụ: `casa_growth`) | `<variable_instructions>` + `<mandatory_schema_structure>` + `<output_format>` |
| AI hay nhầm Quarter với Full Year | Thêm ví dụ vào `<extraction_example>` |
| AI trả về số có chữ "tỷ" hoặc "trillion" | Tăng cường Rule 7 trong `<output_rules>` |
| Cần support tiếng Anh trong source | Thêm English keyword song song trong `<variable_instructions>` |

---

## 4. Prompt: BANKING_KPI_VALIDATION_PROMPT

### Mục đích
Kiểm tra chất lượng bộ KPI đã extract: traceability, completeness, benchmark, logic cross-check.

### Placeholder

| Placeholder | Giá trị |
|-------------|---------|
| `{bank_name}` | Tên ngân hàng |
| `{extracted_kpis_json}` | JSON string của `extracted_kpis` |

### 4 chiều validation

```
1. Source Traceability  → mỗi KPI có source_number + source_url không?
2. Reconciliation       → logic cross-check (ROE = ROA × Leverage, PBT > PAT...)
3. Benchmark Thresholds → ROA 0.5-3%, ROE 5-30%, NIM 2-6%, NPL <5%...
4. Completeness         → 8 critical KPIs + 5 important KPIs
```

### Ngưỡng benchmark — Cách sửa đổi an toàn

Dùng helper function `update_validation_ranges()` thay vì sửa trực tiếp vào prompt:

```python
from graph.base_agent.prompts import get_banking_validation_prompt

# Thay đổi ngưỡng cho ngân hàng đặc biệt (ví dụ: digital bank có ROE cao hơn)
html = get_banking_validation_prompt(
    bank_name="Techcombank",
    extracted_kpis_json=json_str,
    custom_ranges={"roe": "10% - 40%", "nim": "3.0% - 7.0%"}
)
```

> ⚠️ Hàm `update_validation_ranges` dùng string matching chính xác với text trong prompt. Nếu sửa wording trong prompt mà không cập nhật hàm → replace sẽ không hoạt động.

### Output Schema — Contract cứng

```json
{
  "source_traceability": { "kpis_with_sources": N, "source_quality_score": 0-100, ... },
  "completeness": { "critical_kpis_found": N, "completeness_score": 0-100, ... },
  "validation_issues": [ { "severity": "critical/warning", ... } ],
  "quality_metrics": { "overall_quality_score": 0-100, ... }
}
```

Code trong `banking_agent.py` parse trực tiếp các key này. **Không đổi tên key** mà không cập nhật parser.

---

## 5. Prompt: INDIVIDUAL_HIGHLIGHTS_PROMPT

### Mục đích
Sinh phần "Operational Highlights" cho **một ngân hàng** — dạng bullet HTML list, tập trung vào driver/reasoning, không so sánh với ngân hàng khác.

### Placeholder

| Placeholder | Giá trị |
|-------------|---------|
| `{target_bank_name}` | Tên ngân hàng (ví dụ: "VCB") |
| `{target_bank_data}` | JSON string `extracted_kpis` đã qua `_map_global_indices_to_data` |

### Kỹ thuật thiết kế đặc biệt

#### A. Metric Priority — Ưu tiên metric quan trọng nhất
```
1. PBT → 2. Credit Growth → 3. CASA/Deposit → 4. Asset Quality (NPL, ROA, ROE)
```
Prompt không liệt kê hết 44 KPI mà yêu cầu AI **ưu tiên** và **bỏ qua** metric ít impact. Đây là lý do output không bị "liệt kê máy móc" toàn bộ số liệu.

#### B. Cấu trúc bullet bắt buộc: Metric → Value → Reason/Driver
```
❌ "PBT reached 20,000 billion VND."          ← thiếu driver
✅ "PBT reached 20,000 billion VND [1], driven by retail lending expansion [2]."
```

Prompt enforce điều này bằng `<analytical_depth>`:
> "Each bullet must explain WHY it happened using the reasoning or source_quote fields, not just WHAT happened."

#### C. Bold formatting rules — Quan trọng cho PDF render
```
✅ BOLD: Tên metric, con số, driver cụ thể (tên segment, sản phẩm)
❌ KHÔNG BOLD: "driven by", "attributed to", "due to", transition words
❌ KHÔNG BOLD: Toàn câu
```

Lý do: Tránh output **in đậm toàn bộ** làm mất tính phân cấp thông tin trong báo cáo.

#### D. HTML Output bắt buộc
```html
<ul>
  <li><b>[Metric Name]:</b> [Value] [Citation]. [Reason]</li>
</ul>
```

> ⚠️ Không được dùng Markdown `-` hoặc `*` cho bullets. Code `_generate_toc` và report assembler kỳ vọng HTML fragment, không phải Markdown.

#### E. Citation bắt buộc sau mỗi con số
Xem chi tiết ở [Section 8](#8-kỹ-thuật-citation-n--nguyên-tắc-vàng).

### Khi nào cần sửa prompt này

| Tình huống | Cần sửa ở đâu |
|-----------|--------------|
| Muốn thêm metric vào priority list | `<metric_priority>` |
| Output quá ngắn / quá dài | Đổi "3-5 bullet points" trong `<output_format>` |
| AI vẫn dùng từ "strong", "solid" | Tăng cường `<tone_control>` với thêm ví dụ từ cần tránh |
| Muốn thêm tiếng Việt song ngữ | Thêm language instruction trong `<output_format>` |

---

## 6. Prompt: OVERALL_MARKET_STRATEGY_PROMPT

### Mục đích
Sinh phần Market Landscape + Strategic Positioning cho **toàn bộ báo cáo** — phân tích tất cả peers, định vị subject bank, đưa ra strategic response.

### Placeholder

| Placeholder | Được replace bởi | Lưu ý |
|-------------|-----------------|-------|
| `{subject_bank_name}` | `sub_name` | Tên subject bank |
| `{bank_name}` | `sub_name` | Alias — cùng giá trị với subject_bank_name |
| `{peers_summary}` | Text tóm tắt peers | Format: `"- BankName: {json_kpis}\n"` |
| `{master_table}` | Markdown table | Output của `_create_master_comparison_table` |
| `{peers_names}` | `"TCB, ACB, MBB"` | Join bằng dấu phẩy |
| `{subject_bank_data}` | JSON string | `extracted_kpis` của subject |

> ⚠️ **Lưu ý**: `{bank_name}` và `{subject_bank_name}` đều được replace bằng cùng 1 giá trị `sub_name`. Khi sửa prompt, không được xoá một trong hai — code replace cả 2 riêng biệt trong vòng lặp dict.

### Cấu trúc 3 section của output

```
Section 1: The Market Landscape
  → Phân tích toàn thị trường (Profitability, CASA/Efficiency, Asset Quality)
  → Mention subject bank như "factual anchor", không thêm adjective

Section 2: Subject Bank Positioning (vs. The Market)
  → Mỗi "Issue/Gap" có: Observation → Threat → Strategic Response
  → Tối thiểu 2 issues

Section 2A: Defensive Strengths
  → Nơi subject bank ≥ peers

Section 3: Forward-Looking Note
  → 2-3 câu outlook + 1 Critical Threat + 1 Response
```

### Kỹ thuật thiết kế đặc biệt

#### A. Strategy Mindset Injection
```
<strategy_mindset>
You are an internal strategist of {subject_bank_name}.
Competitor performance must be framed as pressure, benchmark gap, threat.
NOT as standalone achievements.
</strategy_mindset>
```

Đây là instruction quan trọng nhất của prompt này. Không có đoạn này, AI sẽ "khen" đối thủ thay vì phân tích threat.

#### B. Comparison Enforcement — Template bắt buộc
```
[Peer Metric] vs [Subject Metric] → [Implication for Subject]
```

Ví dụ đúng:
```
"Peer A's NPL at 2.1% [3] vs VCB's 2.8% [1] indicates higher asset quality pressure."
```

Không được viết:
```
❌ "Peer A has excellent asset quality with 2.1% NPL."  ← không có implication
```

#### C. Anti-praise Rules
Section `<critical_rules>` có các rule số 10, 11, 12, 13 chuyên để ngăn AI "ca ngợi" đối thủ:

```
10. Tránh adjectives: "strong", "impressive", "dominant", "leading", "successful"
11. Frame competitor high performance → Threat cho Subject
12. Competitive Threat: Luôn translate thành pressure
13. NO PRAISE: Tone phải clinical và professional
```

#### D. Advisory Language cho Strategic Response
```
✅ DÙNG: "Consider", "Evaluate", "Explore", "Options include", "Might benefit from"
❌ KHÔNG DÙNG: "must", "should", "need to", "have to"
```

Lý do: Báo cáo tư vấn internal không được có ngôn ngữ ra lệnh — phải mang tính gợi ý.

#### E. Length control
```
"Keep it under 20 lines total."
```

Nếu output quá dài ảnh hưởng đến layout PDF, tăng cường rule này bằng cách thêm:
```
"Each Issue block MUST NOT exceed 4 lines. Violating this limit invalidates the output."
```

### Khi nào cần sửa prompt này

| Tình huống | Cần sửa ở đâu |
|-----------|--------------|
| Muốn thêm Section 4 (ví dụ: Digital Strategy) | Thêm vào `<output_format>` và `<narrative_logic_section_3>` |
| AI vẫn khen đối thủ | Tăng cường rules 10-13 trong `<critical_rules>` |
| Subject không có data → AI không nhắc subject | Đã có conditional logic trong `<narrative_logic>` — kiểm tra lại placeholder |
| Muốn thêm ngôn ngữ tiếng Việt | Thêm language tag: `<language>Vietnamese + English</language>` |

---

## 7. Prompt: COMPARISON_SYSTEM_PROMPT

### Mục đích
Prompt **legacy** — sinh báo cáo song ngữ cho cặp (target_bank vs subject_bank). Không còn là primary flow; được dùng qua `get_comparison_messages()`.

### Khác biệt so với OVERALL_MARKET_STRATEGY_PROMPT

| | COMPARISON_SYSTEM_PROMPT | OVERALL_MARKET_STRATEGY_PROMPT |
|-|--------------------------|-------------------------------|
| Scope | 1 target vs 1 subject | N peers vs 1 subject |
| Output | HTML report cặp đôi | Section trong full report |
| Gọi qua | `get_comparison_messages()` | `generate_overall_strategy()` |
| Trạng thái | Legacy | Active / primary |

### Lưu ý khi dùng
- `get_comparison_messages()` trả về list `[SystemMessage, HumanMessage]` — dùng trực tiếp với `llm.ainvoke()`.
- Prompt này có `<strict length control: 10 lines>` — nếu cần báo cáo dài hơn, dùng `OVERALL_MARKET_STRATEGY_PROMPT` thay thế.

---

## 8. Kỹ thuật Citation [N] — Nguyên tắc vàng

Citation là cơ chế liên kết số liệu trong báo cáo với URL nguồn. Toàn bộ pipeline đều phụ thuộc vào tính nhất quán của `[N]` tag.

### Luồng citation end-to-end

```
Extraction  →  source_url: "https://cafef.vn/vcb.html"
                    │
                    ▼
_map_global_indices_to_data()
  → global_url_to_id["https://cafef.vn/vcb.html"] = 1
  → source_reference_id = "[1]"
                    │
                    ▼
LLM Prompt nhận data với "[1]" gắn vào từng KPI
                    │
                    ▼
LLM output text: "PBT reached 20,000 billion VND [1]"
                    │
                    ▼
_process_ai_content_links()
  → [1] → <a href="https://cafef.vn/vcb.html">[1]</a>
                    │
                    ▼
References section: [1]. https://cafef.vn/vcb.html
```

### Instruction citation trong prompt — Pattern chuẩn

```
**CITATION MANDATORY:** Every single time you mention a number, metric, percentage,
or value, you MUST immediately append its corresponding `source_reference_id`
(e.g., [1], [2]) directly after the number. Find this ID inside the provided JSON data.

Example: "Profit Before Tax reached 20,000 billion VND [1], marking an 18.2% increase [2]."
```

> ⚠️ **Warning cần giữ nguyên**: `"Do NOT invent source tags. Only use the [x] tags explicitly given in the input_data."` — Không có warning này AI sẽ tự sinh [N] không tồn tại.

### Xử lý citation cụm: `[1, 2]` → `[1] [2]`

Code `_process_ai_content_links` tách cụm tự động với regex:
```python
re.sub(r'\[(\d+)\s*,\s*(\d+)\]', r'[\1] [\2]', content)       # cụm 2
re.sub(r'\[(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\]', r'[\1] [\2] [\3]', content)  # cụm 3
```

Tuy nhiên nếu AI sinh `[1,2,3,4]` (cụm 4+) sẽ không được xử lý. Khi thấy pattern này trong output, cần thêm instruction: `"Never combine more than 2 citation indices in one bracket."`.

---

## 9. Kiểm soát giọng văn và tone

### Bảng từ ngữ — Nên dùng vs Cần tránh

| Ngữ cảnh | ✅ Nên dùng | ❌ Cần tránh |
|---------|-----------|------------|
| Mô tả peer bank | "reached", "reported", "maintained", "recorded" | "impressive", "strong", "dominant", "excellent" |
| Strategic response | "Consider", "Evaluate", "Explore", "Options include" | "must", "should", "need to", "have to" |
| Driver/reason | "driven by", "attributed to", "due to", "resulting from" | "thanks to", "benefiting from" (quá tích cực) |
| Mô tả rủi ro | "pressure", "gap", "challenge", "constraint" | "problem", "failure", "disaster" (quá tiêu cực) |
| Intro câu | Bắt đầu trực tiếp bằng data | "Based on the data...", "According to the report..." |

### Enforcement trong prompt

Có 2 cách enforce tone:

**Cách 1: Negative list** (liệt kê từ cấm)
```
Avoid vague positive adjectives such as "strong", "solid", "impressive", "robust".
```

**Cách 2: Example-based** (đưa ví dụ đúng/sai)
```
Instead of: "Peer A performs excellently in P/B"
Write: "Peer A maintains a higher P/B ratio than Subject bank ([Value] vs [Value])"
```

Kết hợp cả 2 cách cho kết quả tốt nhất. Chỉ dùng negative list đơn thuần không đủ — AI cần thấy ví dụ cụ thể.

---

## 10. Anti-patterns cần tránh khi viết prompt

### AP-01: Placeholder collision với Python string format

**Vấn đề**: Prompt dùng `{subject_bank_name}` nhưng trong nội dung có ký tự `{` hoặc `}` (ví dụ trong JSON example).

**Giải pháp**: Escape double brace cho ký tự literal:
```python
# Trong prompt string
"example: {{ \"value\": null }}"   # → render thành: example: { "value": null }
```

Tất cả JSON example trong prompt này đã dùng `{{` và `}}`.

---

### AP-02: Instruction mâu thuẫn nhau

**Vấn đề**: Một nơi viết "Keep it under 10 lines" nhưng nơi khác trong cùng prompt yêu cầu "Write 5 issues each with 4 bullet points" → bất khả thi.

**Giải pháp**: Luôn ước tính số dòng tối thiểu cần thiết trước khi thêm length constraint.

---

### AP-03: Quên cập nhật example khi thay đổi schema

**Vấn đề**: Output schema trong `<output_format>` được cập nhật (thêm field `reporting_year`) nhưng example trong `<extraction_example>` vẫn dùng schema cũ → AI bị confused giữa instruction và example.

**Giải pháp**: Mỗi lần sửa schema, cập nhật đồng thời `<output_format>` + `<extraction_example>` + `<verification_checklist>`.

---

### AP-04: Đưa quá nhiều data vào 1 prompt call

**Vấn đề**: `peers_summary_text` chứa JSON đầy đủ của 10+ ngân hàng → vượt context window hoặc LLM bỏ sót data.

**Giải pháp hiện tại**: Chỉ truyền `extracted_kpis` (đã strip `source_quote`) vào peers_summary. Không truyền `raw_content` hay toàn bộ articles.

---

### AP-05: Thiếu fallback instruction khi data null

**Vấn đề**: AI được yêu cầu cite `[N]` nhưng `source_reference_id` của một số KPI là `""` (rỗng) → AI tự bịa citation.

**Giải pháp**: Thêm instruction:
```
"If a metric has no source_reference_id in the data, mention it WITHOUT any citation tag.
Do NOT invent or guess citation numbers."
```

---

### AP-06: HTML tag bị LLM escape thành entity

**Vấn đề**: LLM đôi khi output `&lt;ul&gt;` thay vì `<ul>` khi thấy HTML trong prompt.

**Giải pháp**: Thêm explicit instruction:
```
"Output raw HTML tags as-is. Do NOT escape HTML entities.
Output <ul>, NOT &lt;ul&gt;."
```

---

## 11. Checklist trước khi deploy prompt mới

```
□ Tất cả {placeholder} đều có giá trị được truyền vào khi gọi .format() hoặc replace()
□ JSON example trong prompt dùng {{ }} thay vì { } cho literal braces
□ Output schema key names khớp với code parser downstream
□ Instruction về citation [N] đã có "do NOT invent" warning
□ Tone control đã có cả negative list + example cụ thể
□ Length constraint thực tế khả thi (ước tính dòng)
□ Temperature LLM phù hợp với loại task (0.1 cho structured extraction, có thể tăng đến 0.3 cho narrative)
□ Đã test với edge case: subject không có data, peers rỗng, KPI toàn null
□ HTML output format đã có explicit "Do NOT escape HTML" instruction
□ Đã cập nhật CÙNG LÚC: output_format + extraction_example + verification_checklist nếu thay đổi schema
```

---

## 12. Quick Reference: Sửa đổi nhanh theo tình huống

### Thêm KPI mới (ví dụ: `digital_loan_ratio`)

1. Thêm vào `<variable_instructions>` trong `BANKING_KPI_EXTRACTION_PROMPT`:
```markdown
- `digital_loan_ratio`: Digital Loan Ratio (Tỷ lệ cho vay kỹ thuật số). Ex: "Tỷ lệ cho vay online đạt 35%"
```

2. Thêm vào `<mandatory_schema_structure>`:
```
6. **other_metrics**: [..., digital_loan_ratio]
```

3. Thêm vào `<output_format>` → `other_metrics` block.

4. Cập nhật `kpi_name_map` trong `reporting_agent.py`:
```python
"digital_loan_ratio": "Digital Loan Ratio"
```

5. Thêm vào `structured_kpi_groups["6. Other Metrics"]` trong `reporting_agent.py`.

---

### Thay đổi ngưỡng benchmark validation

```python
# Dùng helper — KHÔNG sửa trực tiếp prompt
from graph.base_agent.prompts import get_banking_validation_prompt

prompt = get_banking_validation_prompt(
    bank_name="MBB",
    extracted_kpis_json=kpi_str,
    custom_ranges={
        "roa": "0.8% - 3.5%",
        "roe": "8% - 35%"
    }
)
```

---

### Điều chỉnh độ dài output highlights

Trong `INDIVIDUAL_HIGHLIGHTS_PROMPT`, tìm dòng:
```
*(Write 3-5 bullet points...)*
```
Đổi thành số mong muốn. Lưu ý: mỗi bullet tương đương ~3-4 dòng HTML, nên 5 bullets ≈ 15-20 dòng output.

---

### Thêm temporal rule mới (ví dụ: Half-Year period)

Trong `<temporal_rules>` của `BANKING_KPI_EXTRACTION_PROMPT`, thêm Rule 5:

```
5. FOR HALF-YEAR PERIOD (e.g., "6 tháng đầu năm 2025", "H1 2025"):
   - Extract accumulated 6-month values only
   - Look for: "6 tháng đầu năm", "nửa đầu năm", "H1"
   - DO NOT use Q1 or Q2 standalone values
```

Và thêm case tương ứng vào `<extraction_example>`.

---

### Tắt Market Landscape cho toàn bộ report (không chỉ khi subject trống)

Trong `reporting_agent.py`, thay logic kiểm tra:

```python
# Hiện tại: chỉ bỏ qua khi subject data rỗng
is_subject_data_empty = not subject_raw_kpis or all(not v for v in subject_raw_kpis.values())

# Thêm flag disable hoàn toàn:
def generate_overall_strategy(self, ..., include_strategy: bool = True):
    ...
    if not is_subject_data_empty and include_strategy:
        # gọi LLM strategy
```