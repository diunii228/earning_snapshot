
BANKING_KPIS = {
    "profitability": {
        "pbt": "Profit Before Tax (Lợi nhuận trước thuế)",
        "pbt_growth_yoy": "PBT Growth vs Previous Year (%)",
        "pbt_growth_qoq": "PBT Growth vs Previous Quarter (%)",
        "pat": "Profit After Tax (Lợi nhuận sau thuế)",
        "net_interest_income": "Net Interest Income",
        "non_interest_income": "Non-Interest Income",
        "eps": "Earnings Per Share (EPS - Thu nhập trên mỗi cổ phần)" 
    },
    "balance_sheet": {
        "total_assets": "Total Assets (Tổng tài sản)",
        "total_assets_growth_yoy": "Total Assets Growth vs Previous Year (%)",
        "total_assets_growth_qoq": "Total Assets Growth vs Previous Quarter (%)",
        "total_assets_growth_qtd": "Total Assets Growth QTD (%)",
        "total_assets_growth_ytd": "Total Assets Growth YTD (%)",
        "equity": "Owner's Equity (Vốn chủ sở hữu)",
        "charter_capital": "Charter Capital (Vốn điều lệ)",
        "leverage_ratio": "Leverage Ratio (Tỷ lệ đòn bẩy) %" 
    },
    "lending_deposit": {
        "total_credit": "Total Outstanding Credit (Dư nợ tín dụng)",
        "credit_growth_yoy": "Credit Growth vs Previous Year (%)",
        "credit_growth_qoq": "Credit Growth vs Previous Quarter (%)",
        "credit_growth_ytd": "Credit Growth YTD (%)",
        "total_deposits": "Total Customer Deposits (Huy động vốn)",
        "deposit_growth_yoy": "Deposit Growth vs Previous Year (%)",
        "deposit_growth_qoq": "Deposit Growth vs Previous Quarter (%)",
        "deposit_growth_ytd": "Deposit Growth YTD (%)",
        "loan_to_deposit_ratio": "Loan-to-Deposit Ratio (LDR)",
        "mlt_ratio": "Short-term Funds for MLT Loans Ratio (Tỷ lệ vốn ngắn hạn cho vay trung dài hạn) %", 
        "wholesale_funding_ratio": "Wholesale Funding Ratio (Tỷ lệ huy động vốn bán buôn) %" 
    },
    "profitability_ratios": {
        "roa": "Return on Assets (ROA) %",
        "roe": "Return on Equity (ROE) %",
        "nim": "Net Interest Margin (NIM) %",
        "cir": "Cost-to-Income Ratio (CIR) %",
        "cost_of_funds": "Cost of Funds (COF - Chi phí vốn) %",
        "lending_yields": "Lending Yields / Asset Yield (Lợi suất cho vay) %" 
    },
    "asset_quality": {
        "npl_ratio": "Non-Performing Loan Ratio (NPL/Nợ xấu) %",
        "group_2_ratio": "Group 2 Loan Ratio (Nợ nhóm 2) %",
        "llr": "Loan Loss Reserve Ratio (Dự phòng rủi ro tín dụng) %",
        "credit_cost": "Credit Cost / Cost of Risk %",
        "coverage_ratio": "NPL Coverage Ratio %"
    },
    "other_metrics": {
        "casa_ratio": "CASA Ratio (Current + Savings Account) %",
        "net_interest_income_growth": "Net Interest Income Growth %",
        "fee_income": "Fee & Commission Income",
        "operating_expenses": "Operating Expenses",
        "car": "Capital Adequacy Ratio (CAR - Tỷ lệ an toàn vốn) %",
        "p_e_ratio": "Price-to-Earnings Ratio (P/E)",
        "p_b_ratio": "Price-to-Book Ratio (P/B)" 
    }
}

BANKING_KPI_EXTRACTION_PROMPT = """
TASK:
<task_context>
    You are a Senior Financial Analyst AI.
    TARGET BANK: {bank_name}
    REPORTING PERIOD: {reporting_period}, example "Quý 4 2025" or "Năm 2025"
    ANALYSIS DATE (TODAY): {target_date}
    Extract ALL REQUIRED banking KPIs from the content.
</task_context>

<instruction_objective>
    Extract ALL specified banking KPIs from the provided raw content. 
    TARGET REPORTING PERIOD (FILTER ONLY): {reporting_period}

IMPORTANT:
The parameter {reporting_period} is a FILTER CONDITION.
It is NOT a factual statement about the article.

You MUST determine the actual period strictly from the article text.
    If multiple sources provide the same KPI, prioritize the one from the article with the publication date closest to {target_date} or the most detailed report.
</instruction_objective>

<temporal_rules>
CRITICAL TEMPORAL RULES (QUARTER VS. ACCUMULATED):
Financial articles ALWAYS mention both Standalone Quarter (Quý) and Accumulated (Lũy kế/Cả năm) figures. You MUST explicitly distinguish them based on the METRIC TYPE!

1. FOR INCOME & PROFITABILITY METRICS (PBT, PAT, Income, Expenses, EPS):
   - IF {reporting_period} IS A QUARTER (e.g., "Quý 4 2025", "Quý 3 2025", "Quý 2 2025", "Quý 1 2025", "Q4 2025"...): Extract ONLY the standalone 3-month value. Look for: "trong quý", "riêng quý IV", "3 tháng cuối năm". STRICTLY IGNORE accumulated values like "lũy kế", "cả năm". If only accumulated is available, return null.
   - IF {reporting_period} IS A FULL YEAR (e.g., "Năm 2025"): Extract ONLY the 12-month accumulated value. IGNORE standalone Q4 values.

2. FOR BALANCE SHEET & ASSET QUALITY METRICS (Assets, Credit, Deposits, NPL, Equity, CAR):
   - These are POINT-IN-TIME metrics. The balance at the end of the year ("cuối năm", "kết thúc năm", "31/12") is EXACTLY THE SAME as the balance at the end of Q4 ("cuối quý 4").
   - Therefore, if {reporting_period} is a Quarter (like "Q4 2025"), you MUST ACCEPT values labeled as "cuối năm" or "kết thúc năm". DO NOT return null for these metrics just because the text says "năm 2025".

3. ZERO INFERENCE FOR QUARTERS (LUẬT CẤM SUY DIỄN):
   - If the content does NOT explicitly contain words like "quý", "q4", "3 tháng cuối năm", you MUST NOT assume the data is for a quarter. 
   - You are STRICTLY FORBIDDEN from dividing full-year numbers by 4 to guess a quarter. 
   - If {reporting_period} is a Quarter but the text ONLY talks about Full Year (and lacks explicit standalone quarter data), you MUST return null for all profitability metrics.

<extraction_example>
TEXT: "Ngân hàng TMCP Phát triển TP.HCM (HDBank - Mã: HDB) mới công bố kết quả kinh doanh năm 2025 với lợi nhuận trước thuế đạt hơn 21.300 tỷ đồng, tăng 27,4% so với năm trước và vượt kế hoạch Đại hội đồng cổ đông. Riêng quý IV/2025, HDBank ghi nhận lợi nhuận hơn 6.500 tỷ đồng, tăng 60% so với cùng kỳ.
Với kết quả trên, HDBank là ngân hàng thứ 7 ghi nhận lợi nhuận trên 20.000 tỷ đồng trong năm 2025. Đồng thời HDBank đã vượt ACB, để lọt vào Top3 ngân hàng tư nhân lãi lớn nhất hệ thống trong năm vừa qua.
Kết thúc năm 2025, tổng tài sản hợp nhất HDBank đạt 931 nghìn tỷ đồng, tăng 33,5% so với cuối năm 2024. Tổng huy động vốn đạt 832 nghìn tỷ đồng, trong đó tiền gửi khách hàng tăng 28,2%, cho thấy niềm tin thị trường tiếp tục được củng cố.
Dư nợ tín dụng đạt 588 nghìn tỷ đồng, tăng 34,3%, tập trung vào các lĩnh vực có hệ số rủi ro hợp lý và dư địa tăng trưởng dài hạn như SME, chuỗi cung ứng, sản xuất - kinh doanh, xuất khẩu và các dự án xanh. Song hành với tăng trưởng, HDBank tiếp tục kiểm soát rủi ro hiệu quả với tỷ lệ nợ xấu ở mức 1,66%.
Trong năm 2025, ROE HDBank đạt 25,3% - thuộc nhóm cao nhất hệ thống, ROA đạt 2,1%, cho thấy hiệu quả sử dụng vốn vượt trội so với mặt bằng ngành. Trong năm, HDBank đã thực hiện chia cổ tức và cổ phiếu thưởng với tổng tỷ lệ gần 30%, thể hiện cam kết rõ ràng với cổ đông."

CASE A: If {reporting_period} is "Quý 4 2025"
You MUST output STRICTLY in your JSON format like this:
"profitability": {{
  "pbt": {{
    "value": 6500, 
    "unit": "billion VND",
    "reporting_quarter": 4,
    "reasoning": "Found standalone Q4 value: 6500. Found accumulated year value: 21300. Selected 6500 because target is Quý 4. Ignored 21300."
  }},
  "pbt_growth_yoy": {{
    "value": 60, 
    "unit": "%",
    "reporting_quarter": 4,
    "reasoning": "Selected 60% as it is Q4 YoY growth. Ignored 27.4% full-year growth."
  }}
}},
"balance_sheet": {{
  "total_assets": {{
    "value": 931000, 
    "unit": "billion VND",
    "reporting_quarter": 4,
    "reasoning": "Point-in-time metric. End of year balance is exactly the same as end of Q4 balance."
  }}
}},
"lending_deposit": {{
  "total_deposits": {{
    "value": 832000, 
    "unit": "billion VND",
    "reporting_quarter": 4,
    "reasoning": "Point-in-time metric. Applied end of year balance to Q4."
  }}
}}

CASE B: If {reporting_period} is "Năm 2025"
You MUST output STRICTLY in your JSON format like this:
"profitability": {{
  "pbt": {{
    "value": 21300, 
    "unit": "billion VND",
    "reporting_quarter": null,
    "reasoning": "Found standalone Q4 value: 6500. Found accumulated year value: 21300. Selected 21300 because target is Full Year. Ignored 6500."
  }},
  "pbt_growth_yoy": {{
    "value": 27.4, 
    "unit": "%",
    "reporting_quarter": null,
    "reasoning": "Selected 27.4% as it is full-year growth. Ignored 60% Q4 growth."
  }}
}},
"balance_sheet": {{
  "total_assets": {{
    "value": 931000, 
    "unit": "billion VND",
    "reporting_quarter": null,
    "reasoning": "Extracted year-end balance."
  }}
}},
"lending_deposit": {{
  "total_deposits": {{
    "value": 832000, 
    "unit": "billion VND",
    "reporting_quarter": null,
    "reasoning": "Extracted year-end balance."
  }}
}}
</extraction_example>
</temporal_rules>

<variable_instructions>
Below is the Data Dictionary defining each variable. Look for the EXACT Vietnamese keywords in the text to extract the correct value.

### 1. PROFITABILITY (LỢI NHUẬN)
- `pbt`: Profit Before Tax (Lợi nhuận trước thuế). Ex: "Lãi trước thuế đạt 10.000 tỷ"
- `pbt_growth_yoy`: PBT Growth Year-over-Year (Tăng trưởng LNTT so với cùng kỳ). Ex: "Lợi nhuận tăng 20% so với cùng kỳ năm trước" 
- `pbt_growth_qoq`: PBT Growth Quarter-over-Quarter (Tăng trưởng LNTT so với quý trước). Ex: "Lãi tăng 5% so với quý 3"
- `pat`: Profit After Tax (Lợi nhuận sau thuế / Lãi ròng). Ex: "Lãi ròng thu về 8.000 tỷ"
- `net_interest_income`: Net Interest Income / NII (Thu nhập lãi thuần). Ex: "Thu nhập lãi thuần đạt 15.000 tỷ"
- `non_interest_income`: Non-Interest Income (Lãi thuần từ dịch vụ / Thu nhập ngoài lãi). Ex: "Thu nhập ngoài lãi 3.000 tỷ"
- `eps`: Earnings Per Share (Lãi cơ bản trên cổ phiếu). Ex: "EPS đạt 3.500 đồng"

### 2. BALANCE SHEET (BẢNG CÂN ĐỐI KẾ TOÁN)
- `total_assets`: Total Assets (Tổng tài sản). Ex: "Tổng tài sản đạt 1 triệu tỷ đồng"
- `total_assets_growth_yoy`: Assets Growth YoY (Tăng trưởng tài sản so với cùng kỳ năm trước). 
- `total_assets_growth_qoq`: Assets Growth QoQ (Tăng trưởng tài sản so với quý liền trước).
- `total_assets_growth_qtd`: Assets Growth Quarter-to-Date (Tăng trưởng TS so với đầu quý).
- `equity`: Owner's Equity (Vốn chủ sở hữu). Ex: "Vốn chủ sở hữu đạt 100.000 tỷ"
- `charter_capital`: Charter Capital (Vốn điều lệ). Ex: "Tăng vốn điều lệ lên 50.000 tỷ"
- `leverage_ratio`: Leverage Ratio (Tỷ lệ đòn bẩy tài chính). Ex: "Đòn bẩy ở mức 10 lần"

### 3. LENDING & DEPOSIT (TÍN DỤNG & HUY ĐỘNG)
- `total_credit`: Total Outstanding Loans (Tổng dư nợ tín dụng / Cho vay khách hàng). Ex: "Dư nợ cho vay đạt 500.000 tỷ"
- `credit_growth_yoy`: Credit Growth YoY (Tăng trưởng tín dụng so với cùng kỳ). 
- `credit_growth_qoq`: Credit Growth QoQ (Tăng trưởng tín dụng so với quý trước). 
- `total_deposits`: Customer Deposits (Huy động vốn / Tiền gửi khách hàng). Ex: "Huy động vốn đạt 600.000 tỷ"
- `deposit_growth_yoy`: Deposit Growth YoY (Tăng trưởng huy động so với cùng kỳ).
- `deposit_growth_qoq`: Deposit Growth QoQ (Tăng trưởng huy động so với quý trước).
- `loan_to_deposit_ratio`: Loan-to-Deposit / LDR (Tỷ lệ dư nợ trên vốn huy động). Ex: "Tỷ lệ LDR đạt 80%"
- `mlt_ratio`: Short-term funds for MLT loans (Tỷ lệ vốn ngắn hạn cho vay trung dài hạn). 
- `wholesale_funding_ratio`: Wholesale Funding Ratio (Tỷ lệ huy động vốn bán buôn / từ liên ngân hàng).

### 4. PROFITABILITY RATIOS (CHỈ SỐ SINH LỜI)
- `roa`: Return on Assets (Tỷ suất sinh lời trên tài sản). Ex: "ROA đạt 1.5%"
- `roe`: Return on Equity (Tỷ suất sinh lời trên vốn chủ sở hữu). Ex: "ROE duy trì mức 20%"
- `nim`: Net Interest Margin (Biên lãi thuần). Ex: "NIM mở rộng lên 4.5%"
- `cir`: Cost-to-Income Ratio (Tỷ lệ chi phí trên thu nhập). Ex: "Tỷ lệ CIR giảm về 30%"
- `cost_of_funds`: Cost of Funds / COF (Chi phí vốn / Chi phí huy động). Ex: "Chi phí vốn giảm còn 4%"
- `lending_yields`: Lending Yields (Lợi suất cho vay / Sinh lời tài sản). Ex: "Lợi suất cho vay đạt 8%"

### 5. ASSET QUALITY (CHẤT LƯỢNG TÀI SẢN)
- `npl_ratio`: Non-Performing Loan Ratio (Tỷ lệ nợ xấu). Ex: "Tỷ lệ nợ xấu kiểm soát ở mức 1.2%"
- `group_2_ratio`: Group 2 Loan Ratio (Tỷ lệ nợ cần chú ý / Nợ nhóm 2). Ex: "Nợ nhóm 2 chiếm 1.5%"
- `llr`: Loan Loss Reserve (Giá trị trích lập / Số dư dự phòng rủi ro). Ex: "Trích lập dự phòng 5.000 tỷ"
- `credit_cost`: Credit Cost / Cost of Risk (Chi phí rủi ro tín dụng). Ex: "Chi phí rủi ro tín dụng ở mức 1.5%"
- `coverage_ratio`: NPL Coverage Ratio (Tỷ lệ bao phủ nợ xấu). Ex: "Bao phủ nợ xấu lên tới 250%"

### 6. OTHER METRICS (CHỈ SỐ KHÁC)
- `casa_ratio`: CASA Ratio (Tỷ lệ tiền gửi không kỳ hạn). Ex: "Tỷ lệ CASA dẫn đầu đạt 40%"
- `net_interest_income_growth`: NII Growth (Tăng trưởng thu nhập lãi thuần). Ex: "Thu nhập lãi thuần tăng 15%"
- `fee_income`: Net Fee & Commission Income (Lãi thuần từ hoạt động dịch vụ). Ex: "Lãi từ dịch vụ đạt 2.000 tỷ"
- `operating_expenses`: Operating Expenses / OPEX (Chi phí hoạt động). Ex: "Chi phí hoạt động ở mức 5.000 tỷ"
- `car`: Capital Adequacy Ratio (Tỷ lệ an toàn vốn). Ex: "Hệ số CAR đạt 12%"
- `p_e_ratio`: Price-to-Earnings Ratio (Chỉ số P/E). Ex: "Định giá P/E ở mức 8.5 lần"
- `p_b_ratio`: Price-to-Book Ratio (Chỉ số P/B). Ex: "P/B giao dịch ở 1.2 lần"
</variable_instructions>

<mandatory_schema_structure>
You MUST return a JSON object with these EXACT keys based on the 44-KPI standard. If data is missing for a key, set "value" to null but DO NOT REMOVE the key.
1. **profitability**: [pbt, pbt_growth_yoy, pbt_growth_qoq, pat, net_interest_income, non_interest_income, eps]
2. **balance_sheet**: [total_assets, total_assets_growth_yoy, total_assets_growth_qoq, total_assets_growth_qtd, total_assets_growth_ytd, equity, charter_capital, leverage_ratio]
3. **lending_deposit**: [total_credit, credit_growth_yoy, credit_growth_qoq, credit_growth_ytd, total_deposits, deposit_growth_yoy, deposit_growth_qoq, deposit_growth_ytd, loan_to_deposit_ratio, mlt_ratio, wholesale_funding_ratio]
4. **profitability_ratios**: [roa, roe, nim, cir, cost_of_funds, lending_yields]
5. **asset_quality**: [npl_ratio, group_2_ratio, llr, credit_cost, coverage_ratio]
6. **other_metrics**: [casa_ratio, net_interest_income_growth, fee_income, operating_expenses, car, p_e_ratio, p_b_ratio]

CRITICAL METRIC RULES:
- DO NOT confuse P/E (Price-to-Earnings) or P/B ratios with EPS or Stock Price. 
- P/E and P/B are ALWAYS small multiplier numbers (usually between 0.5 and 30.0 times). 
- EPS (Earnings Per Share) is an absolute currency value (usually 1,000 to 15,000 VND).
</mandatory_schema_structure>

<critical_rules>
CRITICAL EXTRACTION & REASONING RULES:
1. Every KPI MUST include: source_number, source_url, source_quote
  * source_url: exact URL from content
  * source_quote: verbatim text excerpt supporting the value

2. If multiple sources discuss the same KPI, prioritize the most specific/recent one
</critical_rules>

<reasoning_extraction_rules>
REASONING EXTRACTION RULES:
- The 'reasoning' field should capture WHY the KPI value occurred or changed. 
- Include the exact Vietnamese or English quote that supports the value.

**What to extract:**
1. **Direct causes mentioned in text:**
   - "driven by X% credit growth"
   - "due to increased provision costs"
   - "resulted from higher NIM expansion"
   - "supported by strong fee income"

2. **Business drivers:**
   - Product performance (e.g., "retail lending surged")
   - Market conditions (e.g., "benefiting from rate hikes")
   - Strategic initiatives (e.g., "digital transformation paying off")
   - Risk events (e.g., "impacted by NPL cleanup")

3. **Comparative context (if mentioned):**
   - "outpacing industry average due to..."
   - "lagging peers because of..."

**Format guidelines:**
- Keep it concise: 1-2 sentences maximum
- Use direct language from source when possible
- Focus on causal relationships, not just descriptions
- If multiple reasons exist, prioritize the primary driver

**Examples:**
"PBT growth driven by 18% YoY credit expansion and NIM improvement to 4.2%"
"ROE declined due to higher provision costs from NPL cleanup initiative"
"Total assets grew 12% QoQ, fueled by corporate lending push in Q3"

**If no reasoning is found:**
- Set to null (not empty string)
- Do NOT invent or infer reasons not stated in source
</reasoning_extraction_rules>

<content>
CONTENT:
{raw_content}
</content>

<output_format>
OUTPUT FORMAT (STRICT):
{{
  "profitability": {{
    "pbt": {{...}},
    "pbt_growth_yoy": {{...}},
    "pbt_growth_qoq": {{...}},
    "pat": {{...}},
    "net_interest_income": {{...}},
    "non_interest_income": {{...}},
    "eps": {{...}}
  }},
  "balance_sheet": {{
    "total_assets": {{...}},
    "total_assets_growth_yoy": {{...}},
    "total_assets_growth_qoq": {{...}},
    "total_assets_growth_qtd": {{...}},
    "equity": {{...}},
    "charter_capital": {{...}},
    "leverage_ratio": {{...}}
  }},
  "lending_deposit": {{
    "total_credit": {{...}},
    "credit_growth_yoy": {{...}},
    "credit_growth_qoq": {{...}},
    "credit_growth_ytd": {{...}},
    "deposit_growth_yoy": {{...}},
    "deposit_growth_qoq": {{...}},
    "loan_to_deposit_ratio": {{...}},
    "mlt_ratio": {{...}},
    "wholesale_funding_ratio": {{...}}
  }},
  "profitability_ratios": {{
    "roa": {{...}},
    "roe": {{...}},
    "nim": {{...}},
    "cir": {{...}},
    "cost_of_funds": {{...}},
    "lending_yields": {{...}}
  }},
  "asset_quality": {{
    "npl_ratio": {{...}},
    "group_2_ratio": {{...}},
    "llr": {{...}},
    "credit_cost": {{...}},
    "coverage_ratio": {{...}}
  }},
  "other_metrics": {{
    "casa_ratio": {{...}},
    "net_interest_income_growth": {{...}},
    "fee_income": {{...}},
    "operating_expenses": {{...}},
    "car": {{...}},
    "p_e_ratio": {{...}},
    "p_b_ratio": {{...}}
  }}
}}
FIELD TEMPLATE FOR EACH KPI:
{{
  "value": null,
  "unit": null,
  "reporting_period": "{reporting_period}",
  "reporting_quarter": null,
  "reporting_year": null,
  "target_date": "{target_date}",
  "reasoning": null,
  "comparison": null,
  "source_number": null,
  "source_url": null,
  "source_quote": null,
  "confidence": null
}}
</output_format>

<verification_checklist>
VERIFICATION CHECKLIST before returning:
- Every KPI has EXACTLY ONE "source_number" (Integer).
- Every KPI has EXACTLY ONE "source_url" (String).  
- Every KPI has EXACTLY ONE "source_quote" (String).
- source_number matches "SOURCE X:" in content.
- source_url is copied exactly from "URL:" line.
- All values have proper units.
- All periods are clearly specified.
- I have VERIFIED that the source text explicitly mentions the quarter before setting "reporting_quarter" to an integer.
- 'reasoning' extracts actual causal explanation (not generic description).
- 'reasoning' is null only when truly no explanation exists in source.
</verification_checklist>

<output_rules>
CRITICAL OUTPUT RULES:

1. You must output ONLY valid JSON.
2. SELECT THE SINGLE BEST SOURCE for each KPI. DO NOT use arrays. `source_url` and `source_quote` MUST be single strings. `source_number` MUST be a single integer.
   - Example Correct: "source_url": "https://link1.com"
   - Example Wrong: "source_url": ["https://link1.com"]
3. Do not include any introductory text, markdown formatting (like ```json), or explanations outside the JSON.
4. Use double quotes (") for keys and string values, never single quotes (').
5. Do not include trailing commas after the last item in a list or object.
6. If a value is not found, use null (not "N/A" or "None").
7. The "value" field MUST BE A PURE NUMBER (Integer or Float). 
   - DO NOT include words like "hơn", "khoảng", ">", "<", or currency symbols. 
   - Example: If text says "hơn 6.500 tỷ", extract ONLY 6500.
8. For "reporting_quarter" field (CRITICAL EVIDENCE CHECK):
    - It MUST reflect what is explicitly stated in the source text, not just the {reporting_period} parameter.
    - If the source text EXPLICITLY provides data for a standalone quarter (e.g., uses words like "Quý 4", "Q4", "trong quý IV") AND it matches {reporting_period}, set it to the integer (e.g., 4).
    - If the text DOES NOT mention the quarter, OR if the data is accumulated year-end data, you MUST set "reporting_quarter" to null.
9. Do NOT omit any KPI from the mandatory set
10. Do NOT add new KPIs beyond the mandatory set
11. RULES FOR "reporting_year" (YEAR-END DATA CHECK):
    - If the source text refers to accumulated data for the entire year (e.g., "lũy kế cả năm", "kết quả cả năm", "lợi nhuận năm 2025 đạt..."), you MUST set "reporting_year" to the corresponding integer (e.g., 2025).
    - If "reporting_year" is identified as the primary period for the KPI value, "reporting_quarter" should typically be null unless the text explicitly states it is "Accumulated as of Q4".
    - Always prioritize the year mentioned in the context of the financial figure over the global {reporting_period} if there is a conflict.

12. DAILY TRACKING FIDELITY (TEMPORAL ALIGNMENT):
    - Since this is a daily tracking task, you must prioritize data published on or around {target_date}. 
    - If the article mentions multiple years (e.g., comparing 2025 vs 2024), ensure the "value" extracted belongs strictly to the period matching the current earning season.
    - Explicitly state in 'reasoning' if a value is "Lũy kế" (Accumulated) or "Standalone" to prevent mixing Full Year data with Quarter-only data in the Master Table.

13. NUMERIC CLEANING FOR MASTER TABLE:
    - Ensure all extracted "value" figures are cleaned for a high-density 10-column table. 
    - Use standard floating point (e.g., 12500.5), not Vietnamese formatting.

RULES FOR 'reasoning' FIELD:
To prevent Quarter vs Year confusion, your reasoning MUST follow this exact format if you find financial figures:
- "Found standalone quarter value: [X]. Found accumulated value: [Y]. Selected [Z] because target period is {reporting_period}."
- If the article only mentions one type, state that explicitly.
- If it's a general reason for growth/decline (e.g., "driven by 20% credit growth"), include it after the temporal check.

CRITICAL: Before extracting, quickly scan the <content>. 
1. Look for the YEAR mentioned in the {reporting_period} parameter.
2. If the text ONLY discusses financial results from PREVIOUS YEARS (e.g., target is 2026, but text only talks about 2025) AND contains ABSOLUTELY ZERO (0) metrics for the specific year in {reporting_period}, YOU MUST ABORT.
3. If no relevant financial data for {bank_name} matching the target year is found, return EXACTLY and ONLY:
{{ "status": "NO_FINANCIAL_DATA_FOUND" }}
</output_rules>
"""