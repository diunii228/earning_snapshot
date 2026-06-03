# from datetime import datetime
# import json
# import re
# from typing import Optional, List, Dict, Any
# from langchain_core.messages import HumanMessage
# from models.llm_factory import get_llm
# from graph.base_agent.prompts import OVERALL_MARKET_STRATEGY_PROMPT, INDIVIDUAL_HIGHLIGHTS_PROMPT
# import copy
# import asyncio
# import logging
# from utils.token_tracker import token_tracker

# logger = logging.getLogger(__name__)

# class BankingReporterAgent:
#     def __init__(self, model_name: Optional[str] = None):
#         self.llm = get_llm(
#             model_name=model_name, 
#             temperature=0.1,
#             top_p=0.3,
#             max_tokens=8000,
#             request_timeout=300  
#         )
#         self.global_url_to_id = {}
#         self.global_id_to_url = {}

#     def _get_anchor_id(self, text: str) -> str:
#         return text.strip().lower().replace(" ", "-")
    
#     def _get_or_create_source_id(self, url: str) -> int:
#         if not url or not isinstance(url, str) or not url.startswith('http'):
#             return None
#         if url not in self.global_url_to_id:
#             new_id = len(self.global_url_to_id) + 1
#             self.global_url_to_id[url] = new_id
#             self.global_id_to_url[new_id] = url
#         return self.global_url_to_id[url]
    
#     def _map_global_indices_to_data(self, kpi_data: Dict) -> Dict:
#         """Xử lý chuẩn xác URL dạng String đơn hoặc Mảng, gán đúng tag [1]"""
#         data = copy.deepcopy(kpi_data)
#         for cat_name, section in data.items():
#             if not isinstance(section, dict): 
#                 continue
                
#             for kpi_key, details in section.items():
#                 if not isinstance(details, dict):
#                     continue
                    
#                 url_val = details.get("source_url")
#                 ref_ids = []
                
#                 if isinstance(url_val, str) and 'http' in url_val:
#                     urls = [u.strip() for u in url_val.split(',')]
#                     for u in urls:
#                         if u.startswith('http'):
#                             idx = self._get_or_create_source_id(u)
#                             if idx: ref_ids.append(f"[{idx}]")
#                 elif isinstance(url_val, list):
#                     for u in url_val:
#                         if isinstance(u, str) and u.startswith('http'):
#                             idx = self._get_or_create_source_id(u)
#                             if idx: ref_ids.append(f"[{idx}]")
                
#                 details["source_reference_id"] = "".join(ref_ids) if ref_ids else ""
#                 if "source_url" in details: 
#                     del details["source_url"]
#         return data

#     def _generate_toc(self, subject_name: str, peers_list: List[Dict]) -> str:
#         toc_html = "<div id='toc'>\n"
#         toc_html += "  <h3 style='margin-top: 0; color: #1a365d;'>TABLE CONTENT</h3>\n"
#         toc_html += "  <ul style='list-style: none; padding-left: 0;'>\n"
#         toc_html += "    <li style='margin-bottom: 8px;'><b>1.</b> <a href='#master-comparison-table' style='text-decoration: none; color: #2c5282;'>Master Comparison Table</a></li>\n"
#         toc_html += f"    <li style='margin-bottom: 8px;'><b>2.</b> <a href='#market-landscape-strategy' style='text-decoration: none; color: #2c5282;'>Market Landscape for {subject_name}</a></li>\n"
#         toc_html += "    <li style='margin-bottom: 8px;'><b>3.</b> <a href='#detailed-highlights' style='text-decoration: none; color: #2c5282;'>Detailed Highlights of Banks</a>\n"
#         toc_html += "      <ul style='list-style: circle; padding-left: 25px; margin-top: 5px;'>\n"
        
#         subject_anchor = self._get_anchor_id(subject_name)
#         toc_html += f"        <li><a href='#{subject_anchor}' style='text-decoration: none; color: #4a5568;'>{subject_name} (Subject Bank)</a></li>\n"
        
#         for p in peers_list:
#             p_name = p.get('bank_name', 'Unknown')
#             p_anchor = self._get_anchor_id(p_name)
#             toc_html += f"        <li><a href='#{p_anchor}' style='text-decoration: none; color: #4a5568;'>{p_name}</a></li>\n"
        
#         toc_html += "      </ul>\n    </li>\n"
#         toc_html += "    <li style='margin-top: 8px;'><b>4.</b> <a href='#references_section' style='text-decoration: none; color: #2c5282;'>References</a></li>\n"
#         toc_html += "  </ul>\n</div>\n\n"
#         return toc_html

#     def _create_master_comparison_table(self, subject_data: Dict, peers_list: List[Dict]) -> str:
#         structured_kpi_groups = {
#             "1. Profitability": ["pbt", "pbt_growth_yoy", "pbt_growth_qoq", "pat", "net_interest_income", "non_interest_income", "eps"],
#             "2. Balance Sheet": ["total_assets", "total_assets_growth_yoy", "total_assets_growth_qoq", "total_assets_growth_qtd", "total_assets_growth_ytd", 
#                                  "equity", "charter_capital", "leverage_ratio"],
#             "3. Lending & Deposit": ["total_credit", "credit_growth_yoy", "credit_growth_qoq", "credit_growth_ytd", "total_deposits", "deposit_growth_yoy", 
#                                      "deposit_growth_qoq", "deposit_growth_ytd", "loan_to_deposit_ratio", "mlt_ratio", "wholesale_funding_ratio"],
#             "4. Profitability Ratios": ["roa", "roe", "nim", "cir", "cost_of_funds", "lending_yields"],
#             "5. Asset Quality": ["npl_ratio", "group_2_ratio", "llr", "credit_cost", "coverage_ratio"],
#             "6. Other Metrics": ["casa_ratio", "net_interest_income_growth", "fee_income", "operating_expenses", "car", "p_e_ratio", "p_b_ratio"]
#         }

#         kpi_name_map = {
#             "pbt": "Profit Before Tax (PBT)", "pbt_growth_yoy": "PBT Growth (YoY)", "pbt_growth_qoq": "PBT Growth (QoQ)", "pat": "Profit After Tax (PAT)",
#             "net_interest_income": "Net Interest Income (NII)", "non_interest_income": "Non-Interest Income", "eps": "Earnings Per Share (EPS)",
#             "total_assets": "Total Assets", "total_assets_growth_yoy": "Assets Growth (YoY)", "total_assets_growth_qoq": "Assets Growth (QoQ)",
#             "total_assets_growth_qtd": "Assets Growth (QTD)", "total_assets_growth_ytd": "Assets Growth (YTD)",
#             "equity": "Owner's Equity", "charter_capital": "Charter Capital", "leverage_ratio": "Leverage Ratio",
#             "total_credit": "Total Credit", "credit_growth_yoy": "Credit Growth (YoY)", "credit_growth_qoq": "Credit Growth (QoQ)", "credit_growth_ytd": "Credit Growth (YTD)",
#             "total_deposits": "Total Deposits", "deposit_growth_yoy": "Deposit Growth (YoY)", "deposit_growth_qoq": "Deposit Growth (QoQ)", "deposit_growth_ytd": "Deposit Growth (YTD)",
#             "loan_to_deposit_ratio": "LDR", "mlt_ratio": "MLT Ratio", "wholesale_funding_ratio": "Wholesale Funding",
#             "roa": "ROA", "roe": "ROE", "nim": "NIM", "cir": "Cost to Income (CIR)", "cost_of_funds": "Cost of Funds (COF)", "lending_yields": "Lending Yields",
#             "npl_ratio": "NPL Ratio", "group_2_ratio": "Group 2 Loan Ratio", "llr": "Loan Loss Reserve (LLR)", "credit_cost": "Credit Cost", "coverage_ratio": "NPL Coverage Ratio",
#             "casa_ratio": "CASA Ratio", "net_interest_income_growth": "NII Growth", "fee_income": "Net Fee Income", "operating_expenses": "Operating Expenses (OPEX)",
#             "car": "Capital Adequacy (CAR)", "p_e_ratio": "P/E Ratio", "p_b_ratio": "P/B Ratio"
#         }

#         def get_clean_value(bank_data, target_key):
#             if not isinstance(target_key, str): return None, "-"
#             extracted = bank_data.get('extracted_kpis', {}) or {}
            
#             if target_key in extracted:
#                 details = extracted[target_key]
#                 if isinstance(details, list): details = details[0]
#                 if isinstance(details, dict):
#                     return details.get('value'), details.get('unit', '-')
            
#             for section in extracted.values():
#                 if isinstance(section, dict) and target_key in section:
#                     details = section[target_key]
#                     if isinstance(details, list): details = details[0]
#                     if isinstance(details, dict):
#                         return details.get('value'), details.get('unit', '-')
                        
#             return None, "-"

#         def format_display(val, is_subject=False):
#             if val is None or val == "-" or val == "": return "-"
#             try:
#                 num_val = float(val)
#                 return f"{num_val:,.0f}" if abs(num_val) >= 1000 else f"{num_val:,.1f}"
#             except:
#                 return str(val)
        
#         sub_name = subject_data.get('bank_name', 'Subject')
#         header = f"| **Metric** | **Unit** | <span style='color: #c60000; font-weight: bold;'>{sub_name} (Subject)</span> |"
#         sep = "|---|---|---|"
#         for p in peers_list:
#             header += f" **{p.get('bank_name', 'Peer')}** |"
#             sep += "---|"
        
#         table_content = f"{header}\n{sep}\n"

#         for group_name, kpi_list in structured_kpi_groups.items(): 
#             for key in kpi_list: 
#                 s_val, s_unit = get_clean_value(subject_data, key)
#                 peer_vals = []
#                 has_data = s_val is not None and str(s_val).strip() not in ["", "-"]
#                 common_unit = s_unit if s_unit != "-" else "-"

#                 for p in peers_list:
#                     p_val, p_unit = get_clean_value(p, key)
#                     peer_vals.append(p_val)
#                     if p_val is not None and str(p_val).strip() not in ["", "-"]: has_data = True
#                     if common_unit == "-" and p_unit != "-": common_unit = p_unit
                
#                 if has_data:
#                     label = kpi_name_map.get(key, key.replace('_', ' ').title())
#                     row = f"| {label} | {common_unit} | {format_display(s_val, is_subject=True)} |"
#                     for v in peer_vals: row += f" {format_display(v)} |"
#                     table_content += row + "\n"
#         return f"### **Master Comparison Table**\n\n{table_content}\n"
    
#     async def generate_individual_highlight(self, bank_data: Dict) -> str:
#         name = bank_data.get('bank_name', 'Unknown Bank')
#         prompt = INDIVIDUAL_HIGHLIGHTS_PROMPT.format(
#             target_bank_name=name,
#             target_bank_data=json.dumps(bank_data.get('extracted_kpis', {}), ensure_ascii=False)
#         )
#         response = await self.llm.ainvoke([HumanMessage(content=prompt)])
#         token_tracker.add_from_response(response)
#         content = self._process_ai_content_links(response.content)
#         anchor_id = self._get_anchor_id(name)
#         return f"<a name='{anchor_id}'></a>\n### {name}\n{content}\n"

#     async def generate_overall_strategy(self, peers_list: List[Dict], subject_data: Dict, target_date: Optional[str] = None) -> str:
#         self.global_url_to_id = {}
#         self.global_id_to_url = {}

#         sub_name = subject_data.get('bank_name') or "Subject Bank"
#         indexed_subject_kpis = self._map_global_indices_to_data(subject_data.get("extracted_kpis", {}))
#         subject_to_process = {"bank_name": sub_name, "extracted_kpis": indexed_subject_kpis}
#         if target_date:
#             try:
#                 report_date = datetime.strptime(target_date, "%Y-%m-%d").strftime("%Y-%m-%d")
#             except:
#                 report_date = target_date
#         else:
#             report_date = datetime.now().strftime("%Y-%m-%d")
#         indexed_peers = []
#         peers_summary_text = ""
#         for p in peers_list:
#             if not isinstance(p, dict): continue
#             p_name = p.get('bank_name', 'Unknown Peer')
#             p_kpis = self._map_global_indices_to_data(p.get("extracted_kpis", {}))
#             indexed_peers.append({"bank_name": p_name, "extracted_kpis": p_kpis})
#             peers_summary_text += f"- {p_name}: {json.dumps(p_kpis, ensure_ascii=False)}\n"

#         master_table = self._create_master_comparison_table(subject_to_process, indexed_peers)
        
#         logger.info(f"--- Đang phân tích chiến lược cho {sub_name} ---")
#         final_prompt = OVERALL_MARKET_STRATEGY_PROMPT
#         for placeholder, value in {
#             "{subject_bank_name}": sub_name,
#             "{bank_name}": sub_name,
#             "{peers_summary}": peers_summary_text,
#             "{master_table}": master_table,
#             "{peers_names}": ", ".join([p['bank_name'] for p in indexed_peers]),
#             "{subject_bank_data}": json.dumps(indexed_subject_kpis, ensure_ascii=False)
#         }.items():
#             final_prompt = final_prompt.replace(placeholder, str(value))

#         try:
#             response = await self.llm.ainvoke([HumanMessage(content=final_prompt)])
#             token_tracker.add_from_response(response)
#             strategy_content = self._process_ai_content_links(response.content)
#         except Exception as e:
#             logger.error(f"Lỗi gọi LLM Strategy: {e}")
#             strategy_content = "Strategic analysis currently unavailable."

#         all_banks_for_highlights = [subject_to_process] + indexed_peers
#         highlight_tasks = [self.generate_individual_highlight(bank) for bank in all_banks_for_highlights]
#         highlights = await asyncio.gather(*highlight_tasks)

#         # RENDER REFERENCES THẬT
#         reference_footer = "\n\n---\n<h2 align='center' id='references_section'>REFERENCES</h2>\n\n"
#         if self.global_id_to_url:
#             reference_footer += '<div style="page-break-inside: avoid; width: 100%;">'
#             for idx in sorted(self.global_id_to_url.keys()):
#                 url = self.global_id_to_url[idx]
#                 reference_footer += f'<p id="{idx}" style="margin-bottom: 8px; line-height: 1.4;">[{idx}]. <a href="{url}" target="_blank">{url}</a></p>\n'
#             reference_footer += '</div>'
#         else:
#             reference_footer += "<p>No specific references extracted.</p>"

#         toc_content = self._generate_toc(sub_name, indexed_peers)
#         PAGE_BREAK = '<div style="page-break-after: always;"></div>\n\n'

#         return "\n\n".join([
#             f"<h1 style='text-align: center; font-size: 28px; text-transform: uppercase; margin-top: 30px; margin-bottom: 20px;'>COMPETITORS ANALYSIS REPORT</h1>\n\n",
#             f"<p style='text-align: center; font-size: 13px; color: #666; margin-bottom: 30px;'>Report Date: {report_date}</p>\n\n",           
#             toc_content, PAGE_BREAK,
#             f"<a name='master-comparison-table'></a>\n{master_table}", PAGE_BREAK,
#             f"<h2 id='market-landscape-strategy'>I. MARKET LANDSCAPE & STRATEGY FOR {sub_name.upper()}</h2>\n\n{strategy_content}", PAGE_BREAK,
#             f"<h2 id='detailed-highlights'>II. DETAILED BANK HIGHLIGHTS</h2>\n\n" + "\n".join(highlights), PAGE_BREAK,
#             reference_footer
#         ])

#     def _process_ai_content_links(self, content: Any) -> str:
#         """Biến tag [1] thành thẻ HTML chứa link URL gốc để click mượt trên PDF/Web"""
#         if isinstance(content, list): content = content[0].get('text', '') if content else ""
#         content = str(content)
#         content = re.sub(r'\(https?://[^\s)]+\)', "", content)
#         content = re.sub(r'\[(\d+)\]\s*\[(\d+)\]', r'[\1] [\2]', content)
#         content = re.sub(r'\[(\d+)\s*,\s*(\d+)\]', r'[\1] [\2]', content)

#         def replace_with_html_link(match):
#             idx_str = match.group(1)
#             try:
#                 idx = int(idx_str)
#                 actual_url = self.global_id_to_url.get(idx, f"#{idx}")
#                 return f'<a href="{actual_url}" target="_blank" style="font-weight: bold; text-decoration: none; color: #1a365d;">[{idx}]</a>'
#             except ValueError:
#                 return f"[{idx_str}]"

#         return re.sub(r'\[(\d+)\]', replace_with_html_link, content)
    

from datetime import datetime
import json
import re
from typing import Optional, List, Dict, Any
from langchain_core.messages import HumanMessage
from models.llm_factory import get_llm
from graph.base_agent.prompts import OVERALL_MARKET_STRATEGY_PROMPT, INDIVIDUAL_HIGHLIGHTS_PROMPT
import copy
import asyncio
import logging
from utils.token_tracker import token_tracker

logger = logging.getLogger(__name__)

class BankingReporterAgent:
    def __init__(self, model_name: Optional[str] = None):
        self.llm = get_llm(
            model_name=model_name, 
            temperature=0.1, # Giữ Temperature thấp (0.1) để AI tuân thủ tuyệt đối giọng điệu lạnh lùng, trung lập
            top_p=0.3,
            max_tokens=8000,
            request_timeout=300  
        )
        self.global_url_to_id = {}
        self.global_id_to_url = {}

    def _get_anchor_id(self, text: str) -> str:
        return text.strip().lower().replace(" ", "-")
    
    def _get_or_create_source_id(self, url: str) -> int:
        if not url or not isinstance(url, str) or not url.startswith('http'):
            return None
        if url not in self.global_url_to_id:
            new_id = len(self.global_url_to_id) + 1
            self.global_url_to_id[url] = new_id
            self.global_id_to_url[new_id] = url
        return self.global_url_to_id[url]
    
    def _map_global_indices_to_data(self, kpi_data: Dict) -> Dict:
        """Xử lý chuẩn xác URL dạng String đơn hoặc Mảng, gán đúng tag [1]"""
        data = copy.deepcopy(kpi_data)
        for cat_name, section in data.items():
            if not isinstance(section, dict): 
                continue
                
            for kpi_key, details in section.items():
                if not isinstance(details, dict):
                    continue
                    
                url_val = details.get("source_url")
                ref_ids = []
                
                if isinstance(url_val, str) and 'http' in url_val:
                    urls = [u.strip() for u in url_val.split(',')]
                    for u in urls:
                        if u.startswith('http'):
                            idx = self._get_or_create_source_id(u)
                            if idx: ref_ids.append(f"[{idx}]")
                elif isinstance(url_val, list):
                    for u in url_val:
                        if isinstance(u, str) and u.startswith('http'):
                            idx = self._get_or_create_source_id(u)
                            if idx: ref_ids.append(f"[{idx}]")
                
                details["source_reference_id"] = "".join(ref_ids) if ref_ids else ""
                if "source_url" in details: 
                    del details["source_url"]
        return data

    def _generate_toc(self, subject_name: str, peers_list: List[Dict]) -> str:
        toc_html = "<div id='toc'>\n"
        toc_html += "  <h3 style='margin-top: 0; color: #1a365d;'>TABLE OF CONTENTS</h3>\n"
        toc_html += "  <ul style='list-style: none; padding-left: 0;'>\n"
        toc_html += "    <li style='margin-bottom: 8px;'><b>1.</b> <a href='#master-comparison-table' style='text-decoration: none; color: #2c5282;'>Master Comparison Table</a></li>\n"
        toc_html += f"    <li style='margin-bottom: 8px;'><b>2.</b> <a href='#daily-snapshot-changes' style='text-decoration: none; color: #2c5282;'>Daily Snapshot Changes</a></li>\n"
        toc_html += f"    <li style='margin-bottom: 8px;'><b>3.</b> <a href='#market-landscape-strategy' style='text-decoration: none; color: #2c5282;'>Market Landscape & Strategic Positioning</a></li>\n"
        toc_html += "    <li style='margin-bottom: 8px;'><b>4.</b> <a href='#detailed-highlights' style='text-decoration: none; color: #2c5282;'>Detailed Operational Highlights</a>\n"
        toc_html += "      <ul style='list-style: circle; padding-left: 25px; margin-top: 5px;'>\n"
        
        subject_anchor = self._get_anchor_id(subject_name)
        toc_html += f"        <li><a href='#{subject_anchor}' style='text-decoration: none; color: #4a5568;'><b>{subject_name} (Subject Bank)</b></a></li>\n"
        
        for p in peers_list:
            p_name = p.get('bank_name', 'Unknown')
            p_anchor = self._get_anchor_id(p_name)
            toc_html += f"        <li><a href='#{p_anchor}' style='text-decoration: none; color: #4a5568;'>{p_name}</a></li>\n"
        
        toc_html += "      </ul>\n    </li>\n"
        toc_html += "    <li style='margin-top: 8px;'><b>5.</b> <a href='#references_section' style='text-decoration: none; color: #2c5282;'>References</a></li>\n"
        toc_html += "  </ul>\n</div>\n\n"
        return toc_html

    def _format_kpi_label(self, kpi_name: str) -> str:
        return str(kpi_name).replace("_", " ").upper()

    def _format_change_value(self, value: Any) -> str:
        if value is None or value == "":
            return "-"
        try:
            num_val = float(value)
            return f"{num_val:,.0f}" if abs(num_val) >= 1000 else f"{num_val:,.2f}"
        except Exception:
            return str(value)

    def _render_daily_change_list(self, change_items: List[Dict[str, Any]], mode: str) -> str:
        if not change_items:
            return "<li>None</li>"

        lines = []
        for item in change_items[:8]:
            label = self._format_kpi_label(item.get("kpi_name", "unknown"))
            unit = f" {item.get('unit')}" if item.get("unit") else ""
            if mode == "changed":
                lines.append(
                    f"<li><strong>{label}</strong>: {self._format_change_value(item.get('old_value'))}"
                    f" → {self._format_change_value(item.get('new_value'))}{unit}</li>"
                )
            elif mode == "added":
                lines.append(
                    f"<li><strong>{label}</strong>: new at {self._format_change_value(item.get('new_value'))}{unit}</li>"
                )
            else:
                lines.append(
                    f"<li><strong>{label}</strong>: removed from {self._format_change_value(item.get('old_value'))}{unit}</li>"
                )
        return "".join(lines)

    def _create_daily_snapshot_changes_section(self, subject_data: Dict, peers_list: List[Dict]) -> str:
        all_banks = [subject_data] + peers_list
        blocks = []

        for bank in all_banks:
            changes = bank.get("daily_changes") or {}
            previous_target_date = bank.get("previous_target_date")
            current_target_date = bank.get("target_date")
            if not previous_target_date:
                summary = (
                    f"<p style='margin:0;color:#4a5568;'>No prior snapshot for comparison. "
                    f"This is the first stored snapshot for {bank.get('bank_name', 'this bank')} in the selected reporting period.</p>"
                )
            else:
                summary = (
                    f"<p style='margin:0 0 10px 0;color:#4a5568;'>"
                    f"Comparing <strong>{current_target_date}</strong> vs <strong>{previous_target_date}</strong> | "
                    f"Changed: <strong>{changes.get('changed_count', 0)}</strong> | "
                    f"Added: <strong>{changes.get('added_count', 0)}</strong> | "
                    f"Removed: <strong>{changes.get('removed_count', 0)}</strong></p>"
                    f"<p style='margin:8px 0 4px 0;'><strong>Changed KPIs</strong></p><ul>{self._render_daily_change_list(changes.get('changed', []), 'changed')}</ul>"
                    f"<p style='margin:8px 0 4px 0;'><strong>New KPIs</strong></p><ul>{self._render_daily_change_list(changes.get('added', []), 'added')}</ul>"
                    f"<p style='margin:8px 0 4px 0;'><strong>Removed KPIs</strong></p><ul>{self._render_daily_change_list(changes.get('removed', []), 'removed')}</ul>"
                )

            blocks.append(
                f"<div style='margin-bottom:18px; padding:14px 16px; border:1px solid #d9e2ec; border-radius:6px;'>"
                f"<h3 style='margin-top:0; margin-bottom:10px; color:#1a365d;'>{bank.get('bank_name', 'Unknown Bank')}</h3>"
                f"{summary}</div>"
            )

        return "<h2 id='daily-snapshot-changes'>II. DAILY SNAPSHOT CHANGES VS PREVIOUS RUN</h2>\n\n" + "\n".join(blocks)

    def _create_master_comparison_table(self, subject_data: Dict, peers_list: List[Dict]) -> str:
        structured_kpi_groups = {
            "1. Profitability": ["pbt", "pbt_growth_yoy", "pbt_growth_qoq", "pat", "net_interest_income", "non_interest_income", "eps"],
            "2. Balance Sheet": ["total_assets", "total_assets_growth_yoy", "total_assets_growth_qoq", "total_assets_growth_qtd", "total_assets_growth_ytd", 
                                 "equity", "charter_capital", "leverage_ratio"],
            "3. Lending & Deposit": ["total_credit", "credit_growth_yoy", "credit_growth_qoq", "credit_growth_ytd", "total_deposits", "deposit_growth_yoy", 
                                     "deposit_growth_qoq", "deposit_growth_ytd", "loan_to_deposit_ratio", "mlt_ratio", "wholesale_funding_ratio"],
            "4. Profitability Ratios": ["roa", "roe", "nim", "cir", "cost_of_funds", "lending_yields"],
            "5. Asset Quality": ["npl_ratio", "group_2_ratio", "llr", "credit_cost", "coverage_ratio"],
            "6. Other Metrics": ["casa_ratio", "net_interest_income_growth", "fee_income", "operating_expenses", "car", "p_e_ratio", "p_b_ratio"]
        }

        kpi_name_map = {
            "pbt": "Profit Before Tax (PBT)", "pbt_growth_yoy": "PBT Growth (YoY)", "pbt_growth_qoq": "PBT Growth (QoQ)", "pat": "Profit After Tax (PAT)",
            "net_interest_income": "Net Interest Income (NII)", "non_interest_income": "Non-Interest Income", "eps": "Earnings Per Share (EPS)",
            "total_assets": "Total Assets", "total_assets_growth_yoy": "Assets Growth (YoY)", "total_assets_growth_qoq": "Assets Growth (QoQ)",
            "total_assets_growth_qtd": "Assets Growth (QTD)", "total_assets_growth_ytd": "Assets Growth (YTD)",
            "equity": "Owner's Equity", "charter_capital": "Charter Capital", "leverage_ratio": "Leverage Ratio",
            "total_credit": "Total Credit", "credit_growth_yoy": "Credit Growth (YoY)", "credit_growth_qoq": "Credit Growth (QoQ)", "credit_growth_ytd": "Credit Growth (YTD)",
            "total_deposits": "Total Deposits", "deposit_growth_yoy": "Deposit Growth (YoY)", "deposit_growth_qoq": "Deposit Growth (QoQ)", "deposit_growth_ytd": "Deposit Growth (YTD)",
            "loan_to_deposit_ratio": "LDR", "mlt_ratio": "MLT Ratio", "wholesale_funding_ratio": "Wholesale Funding",
            "roa": "ROA", "roe": "ROE", "nim": "NIM", "cir": "Cost to Income (CIR)", "cost_of_funds": "Cost of Funds (COF)", "lending_yields": "Lending Yields",
            "npl_ratio": "NPL Ratio", "group_2_ratio": "Group 2 Loan Ratio", "llr": "Loan Loss Reserve (LLR)", "credit_cost": "Credit Cost", "coverage_ratio": "NPL Coverage Ratio",
            "casa_ratio": "CASA Ratio", "net_interest_income_growth": "NII Growth", "fee_income": "Net Fee Income", "operating_expenses": "Operating Expenses (OPEX)",
            "car": "Capital Adequacy (CAR)", "p_e_ratio": "P/E Ratio", "p_b_ratio": "P/B Ratio"
        }

        def get_clean_value(bank_data, target_key):
            if not isinstance(target_key, str): return None, "-"
            extracted = bank_data.get('extracted_kpis', {}) or {}
            
            if target_key in extracted:
                details = extracted[target_key]
                if isinstance(details, list): details = details[0]
                if isinstance(details, dict):
                    return details.get('value'), details.get('unit', '-')
            
            for section in extracted.values():
                if isinstance(section, dict) and target_key in section:
                    details = section[target_key]
                    if isinstance(details, list): details = details[0]
                    if isinstance(details, dict):
                        return details.get('value'), details.get('unit', '-')
                        
            return None, "-"

        def format_display(val, is_subject=False):
            if val is None or val == "-" or val == "": return "-"
            try:
                num_val = float(val)
                return f"{num_val:,.0f}" if abs(num_val) >= 1000 else f"{num_val:,.1f}"
            except:
                return str(val)
        
        sub_name = subject_data.get('bank_name', 'Subject')
        header = f"| **Metric** | **Unit** | <span style='color: #c60000; font-weight: bold;'>{sub_name} (Subject)</span> |"
        sep = "|---|---|---|"
        for p in peers_list:
            header += f" **{p.get('bank_name', 'Peer')}** |"
            sep += "---|"
        
        table_content = f"{header}\n{sep}\n"

        for group_name, kpi_list in structured_kpi_groups.items(): 
            for key in kpi_list: 
                s_val, s_unit = get_clean_value(subject_data, key)
                peer_vals = []
                has_data = s_val is not None and str(s_val).strip() not in ["", "-"]
                common_unit = s_unit if s_unit != "-" else "-"

                for p in peers_list:
                    p_val, p_unit = get_clean_value(p, key)
                    peer_vals.append(p_val)
                    if p_val is not None and str(p_val).strip() not in ["", "-"]: has_data = True
                    if common_unit == "-" and p_unit != "-": common_unit = p_unit
                
                if has_data:
                    label = kpi_name_map.get(key, key.replace('_', ' ').title())
                    row = f"| {label} | {common_unit} | {format_display(s_val, is_subject=True)} |"
                    for v in peer_vals: row += f" {format_display(v)} |"
                    table_content += row + "\n"
        return f"### **Master Comparison Table**\n\n{table_content}\n"
    
    # def _create_master_comparison_table(self, subject_data: Dict, peers_list: List[Dict]) -> str:
    
    #     # ================================================================
    #     # 4 CORE COMPARABLE AREAS - theo yêu cầu mới
    #     # Mỗi group có section header + sub-groups logic rõ ràng
    #     # ================================================================
    #     structured_kpi_groups = {
    #         "1. Balance Sheet Growth": [
    #             "total_assets", "total_assets_growth_yoy", "total_assets_growth_ytd",
    #             "total_assets_growth_qoq",
    #             "total_credit", "credit_growth_yoy", "credit_growth_ytd", "credit_growth_qoq",
    #             "total_deposits", "deposit_growth_yoy", "deposit_growth_ytd", "deposit_growth_qoq",
    #             "loan_to_deposit_ratio",
    #         ],
    #         "2. CASA": [
    #             "casa_ratio",
    #         ],
    #         "3. Asset Quality": [
    #             "npl_ratio", "group_2_ratio", "coverage_ratio", "llr", "credit_cost",
    #         ],
    #         "4. Profitability": [
    #             # Headline
    #             "pbt", "pbt_growth_yoy", "pbt_growth_qoq",
    #             "pat",
    #             # Income decomposition
    #             "net_interest_income", "net_interest_income_growth",
    #             "non_interest_income", "fee_income",
    #             # Margin & efficiency
    #             "nim", "cost_of_funds", "lending_yields", "cir",
    #             # Returns
    #             "roe", "roa",
    #             # Per-share
    #             "eps",
    #         ],
    #         # Giữ lại nhóm bổ sung nhưng tách biệt khỏi 4 core areas
    #         "5. Capital & Funding": [
    #             "equity", "charter_capital", "car",
    #             "mlt_ratio", "wholesale_funding_ratio", "leverage_ratio",
    #         ],
    #         "6. Market Valuation": [
    #             "p_e_ratio", "p_b_ratio",
    #         ],
    #     }

    #     # Section display names — dùng để render header rows trong bảng
    #     section_display = {
    #         "1. Balance Sheet Growth": "BALANCE SHEET GROWTH",
    #         "2. CASA":                 "CASA",
    #         "3. Asset Quality":        "ASSET QUALITY",
    #         "4. Profitability":        "PROFITABILITY",
    #         "5. Capital & Funding":    "CAPITAL & FUNDING",
    #         "6. Market Valuation":     "MARKET VALUATION",
    #     }

    #     # Sub-group separators bên trong Profitability & Balance Sheet
    #     # key = kpi key ngay TRƯỚC khi bắt đầu sub-group mới → render 1 dòng label nhỏ
    #     subgroup_labels = {
    #         # Balance Sheet Growth
    #         "total_credit":            "— Credit",
    #         "total_deposits":          "— Deposit",
    #         "loan_to_deposit_ratio":   "— Liquidity",
    #         # Profitability
    #         "net_interest_income":     "— Income Decomposition",
    #         "nim":                     "— Margin & Efficiency",
    #         "roe":                     "— Returns",
    #         "eps":                     "— Per Share",
    #     }

    #     kpi_name_map = {
    #         "pbt":                      "Profit Before Tax (PBT)",
    #         "pbt_growth_yoy":           "PBT Growth (YoY)",
    #         "pbt_growth_qoq":           "PBT Growth (QoQ)",
    #         "pat":                      "Profit After Tax (PAT)",
    #         "net_interest_income":      "Net Interest Income (NII)",
    #         "net_interest_income_growth":"NII Growth (YoY)",
    #         "non_interest_income":      "Non-Interest Income (NFI)",
    #         "fee_income":               "Net Fee Income",
    #         "eps":                      "Earnings Per Share (EPS)",
    #         "total_assets":             "Total Assets",
    #         "total_assets_growth_yoy":  "Assets Growth (YoY)",
    #         "total_assets_growth_qoq":  "Assets Growth (QoQ)",
    #         "total_assets_growth_qtd":  "Assets Growth (QTD)",
    #         "total_assets_growth_ytd":  "Assets Growth (YTD)",
    #         "equity":                   "Owner's Equity",
    #         "charter_capital":          "Charter Capital",
    #         "leverage_ratio":           "Leverage Ratio",
    #         "total_credit":             "Total Credit (Gross Loans)",
    #         "credit_growth_yoy":        "Credit Growth (YoY)",
    #         "credit_growth_qoq":        "Credit Growth (QoQ)",
    #         "credit_growth_ytd":        "Credit Growth (YTD)",
    #         "total_deposits":           "Total Customer Deposits",
    #         "deposit_growth_yoy":       "Deposit Growth (YoY)",
    #         "deposit_growth_qoq":       "Deposit Growth (QoQ)",
    #         "deposit_growth_ytd":       "Deposit Growth (YTD)",
    #         "loan_to_deposit_ratio":    "Net Loan-to-Deposit Ratio (LDR)",
    #         "mlt_ratio":                "MLT Ratio",
    #         "wholesale_funding_ratio":  "Wholesale Funding Ratio",
    #         "roa":                      "Return on Assets (ROA)",
    #         "roe":                      "Return on Equity (ROE)",
    #         "nim":                      "Net Interest Margin (NIM)",
    #         "cir":                      "Cost-to-Income Ratio (CIR)",
    #         "cost_of_funds":            "Cost of Funds (COF)",
    #         "lending_yields":           "Lending Yields",
    #         "npl_ratio":                "NPL Ratio",
    #         "group_2_ratio":            "Group 2 Loan Ratio",
    #         "llr":                      "Loan Loss Reserve (LLR)",
    #         "credit_cost":              "Credit Cost",
    #         "coverage_ratio":           "NPL Coverage Ratio",
    #         "casa_ratio":               "CASA Ratio",
    #         "operating_expenses":       "Operating Expenses (OPEX)",
    #         "car":                      "Capital Adequacy Ratio (CAR)",
    #         "p_e_ratio":                "P/E Ratio",
    #         "p_b_ratio":                "P/B Ratio",
    #     }

    #     # ----------------------------------------------------------------
    #     def get_clean_value(bank_data: Dict, target_key: str):
    #         """Extract (value, unit) from extracted_kpis, searching nested dicts."""
    #         if not isinstance(target_key, str):
    #             return None, "-"
    #         extracted = bank_data.get('extracted_kpis', {}) or {}

    #         # Direct lookup
    #         if target_key in extracted:
    #             details = extracted[target_key]
    #             if isinstance(details, list):
    #                 details = details[0]
    #             if isinstance(details, dict):
    #                 return details.get('value'), details.get('unit', '-')

    #         # Nested lookup
    #         for section in extracted.values():
    #             if isinstance(section, dict) and target_key in section:
    #                 details = section[target_key]
    #                 if isinstance(details, list):
    #                     details = details[0]
    #                 if isinstance(details, dict):
    #                     return details.get('value'), details.get('unit', '-')

    #         return None, "-"

    #     def format_display(val):
    #         """Format numeric values; return '-' for missing data."""
    #         if val is None or val == "-" or val == "":
    #             return "-"
    #         try:
    #             num_val = float(val)
    #             return f"{num_val:,.0f}" if abs(num_val) >= 1000 else f"{num_val:,.2f}"
    #         except (ValueError, TypeError):
    #             return str(val)

    #     # ----------------------------------------------------------------
    #     # Build header row
    #     # ----------------------------------------------------------------
    #     sub_name = subject_data.get('bank_name', 'Subject')

    #     # Subject column highlighted in red-bold
    #     subject_col = f"<span style='color:#c60000;font-weight:bold;'>{sub_name}</span>"

    #     header = f"| **Metric** | **Unit** | {subject_col} |"
    #     sep    = "|:---|:---:|:---:|"
    #     for p in peers_list:
    #         header += f" **{p.get('bank_name', 'Peer')}** |"
    #         sep    += ":---:|"

    #     table_rows = [header, sep]

    #     # ----------------------------------------------------------------
    #     # Build data rows — group by section, insert section headers
    #     # ----------------------------------------------------------------
    #     for group_key, kpi_list in structured_kpi_groups.items():

    #         section_title = section_display.get(group_key, group_key)
    #         peer_col_blanks = " |" * len(peers_list)

    #         # ── Section header row (spans all columns visually via bold + shading hint)
    #         num_cols = 2 + 1 + len(peers_list)  # Metric + Unit + Subject + peers
    #         section_row = (
    #             f"| **{'&nbsp;' * 2}{section_title}** "
    #             f"| | |" + peer_col_blanks
    #         )
    #         table_rows.append(section_row)

    #         for key in kpi_list:

    #             # ── Sub-group label row (light separator inside a section)
    #             if key in subgroup_labels:
    #                 label_row = (
    #                     f"| *{subgroup_labels[key]}* "
    #                     f"| | |" + peer_col_blanks
    #                 )
    #                 table_rows.append(label_row)

    #             # ── Collect values
    #             s_val, s_unit = get_clean_value(subject_data, key)
    #             peer_vals     = []
    #             common_unit   = s_unit if s_unit and s_unit != "-" else "-"
    #             has_data      = s_val is not None and str(s_val).strip() not in ("", "-")

    #             for p in peers_list:
    #                 p_val, p_unit = get_clean_value(p, key)
    #                 peer_vals.append(p_val)
    #                 if p_val is not None and str(p_val).strip() not in ("", "-"):
    #                     has_data = True
    #                 if common_unit == "-" and p_unit and p_unit != "-":
    #                     common_unit = p_unit

    #             # ── Skip row entirely if no bank has data for this KPI
    #             if not has_data:
    #                 continue

    #             label = kpi_name_map.get(key, key.replace('_', ' ').title())

    #             # Subject value: bold + red if present
    #             s_display = format_display(s_val)
    #             if s_display != "-":
    #                 s_display = f"<span style='color:#c60000;font-weight:bold;'>{s_display}</span>"

    #             row = f"| &nbsp;&nbsp;&nbsp;&nbsp;{label} | {common_unit} | {s_display} |"
    #             for v in peer_vals:
    #                 row += f" {format_display(v)} |"

    #             table_rows.append(row)

    #     # ----------------------------------------------------------------
    #     # Assemble final output
    #     # ----------------------------------------------------------------
    #     table_md = "\n".join(table_rows)

    #     return (
    #         "### **Master Comparison Table**\n\n"
    #         "> *Columns: Subject bank highlighted in "
    #         "<span style='color:#c60000'>red</span>. "
    #         "Metrics grouped by 4 core comparable areas.*\n\n"
    #         f"{table_md}\n"
    #     )
    
    async def generate_individual_highlight(self, bank_data: Dict) -> str:
        name = bank_data.get('bank_name', 'Unknown Bank')
        extracted_kpis = bank_data.get('extracted_kpis', {})

        # ── Lấy source quotes để build executive summary context ─────────────
        source_context = self._build_source_context(extracted_kpis)

        # Strip _source_quotes khỏi payload gửi LLM — tránh làm nặng JSON
        kpis_for_payload = {
            k: v for k, v in extracted_kpis.items()
            if k != "_source_quotes"
        }

        highlight_payload = {
            "extracted_kpis": kpis_for_payload,
            "daily_changes": bank_data.get("daily_changes", {}),
            "target_date": bank_data.get("target_date"),
            "previous_target_date": bank_data.get("previous_target_date"),
        }

        # ── Build prompt — inject source context nếu có ───────────────────────
        base_prompt = INDIVIDUAL_HIGHLIGHTS_PROMPT.format(
            target_bank_name=name,
            target_bank_data=json.dumps(highlight_payload, ensure_ascii=False, default=str)
        )

        if source_context:
            executive_summary_instruction = f"""

    === YÊU CẦU BỔ SUNG: EXECUTIVE SUMMARY ===
    Dựa trên SOURCE CONTEXT bên dưới, hãy viết thêm 1 đoạn EXECUTIVE SUMMARY ngay đầu phần highlight của {name}.
    Yêu cầu:
    - Dài 3-5 dòng, súc tích, không bullet point.
    - Giải thích rõ các KPI chính tăng/giảm là do nguyên nhân gì (dựa vào nội dung bài báo).
    - Dùng ngôn ngữ phân tích tài chính, trung lập, không cảm tính.
    - Đặt trong thẻ HTML: <div class='executive-summary' style='background:#f0f4f8;border-left:4px solid #2c5282;padding:12px 16px;margin-bottom:16px;border-radius:4px;font-style:italic;'> ... </div>

    {source_context}
    ===========================================
    """
            full_prompt = base_prompt + executive_summary_instruction
        else:
            full_prompt = base_prompt

        response = await self.llm.ainvoke([HumanMessage(content=full_prompt)])
        token_tracker.add_from_response(response)
        content = self._process_ai_content_links(response.content)
        anchor_id = self._get_anchor_id(name)
        return f"<a name='{anchor_id}'></a>\n### {name}\n{content}\n"

    async def generate_overall_strategy(self, peers_list: List[Dict], subject_data: Dict, target_date: Optional[str] = None) -> str:
        self.global_url_to_id = {}
        self.global_id_to_url = {}

        sub_name = subject_data.get('bank_name') or "Subject Bank"
        
        # 1. Kiểm tra dữ liệu đầu vào của Subject Bank
        subject_raw_kpis = subject_data.get("extracted_kpis", {})
        
        # Định nghĩa điều kiện: Nếu không có bất kỳ key nào trong extracted_kpis hoặc kpis rỗng
        is_subject_data_empty = not subject_raw_kpis or all(not v for v in subject_raw_kpis.values())

        if target_date:
            try:
                report_date = datetime.strptime(target_date, "%Y-%m-%d").strftime("%B %d, %Y")
            except:
                report_date = target_date
        else:
            report_date = datetime.now().strftime("%B %d, %Y")

        # Chuẩn bị dữ liệu cho phần Highlights và Table (vẫn cần thiết)
        indexed_subject_kpis = self._map_global_indices_to_data(subject_raw_kpis)
        subject_to_process = {
            "bank_name": sub_name,
            "extracted_kpis": indexed_subject_kpis,
            "daily_changes": subject_data.get("daily_changes", {}),
            "target_date": subject_data.get("target_date"),
            "previous_target_date": subject_data.get("previous_target_date"),
        }
        
        indexed_peers = []
        peers_summary_text = ""
        for p in peers_list:
            if not isinstance(p, dict): continue
            p_name = p.get('bank_name', 'Unknown Peer')
            p_kpis = self._map_global_indices_to_data(p.get("extracted_kpis", {}))
            indexed_peers.append({
                "bank_name": p_name,
                "extracted_kpis": p_kpis,
                "daily_changes": p.get("daily_changes", {}),
                "target_date": p.get("target_date"),
                "previous_target_date": p.get("previous_target_date"),
            })
            peers_summary_text += f"- {p_name}: {json.dumps(p_kpis, ensure_ascii=False, default=str)}\n"

        master_table = self._create_master_comparison_table(subject_to_process, indexed_peers)
        
        # 2. Xử lý logic Market Landscape
        strategy_section = ""
        if not is_subject_data_empty:
            logger.info(f"--- Đang phân tích chiến lược cho {sub_name} ---")
            final_prompt = OVERALL_MARKET_STRATEGY_PROMPT
            for placeholder, value in {
                "{subject_bank_name}": sub_name,
                "{bank_name}": sub_name,
                "{peers_summary}": peers_summary_text,
                "{master_table}": master_table,
                "{peers_names}": ", ".join([p['bank_name'] for p in indexed_peers]),
                "{subject_bank_data}": json.dumps(indexed_subject_kpis, ensure_ascii=False, default=str)
            }.items():
                final_prompt = final_prompt.replace(placeholder, str(value))

            try:
                response = await self.llm.ainvoke([HumanMessage(content=final_prompt)])
                token_tracker.add_from_response(response)
                strategy_content = self._process_ai_content_links(response.content)
                strategy_section = f"<h2 id='market-landscape-strategy'>I. MARKET LANDSCAPE & STRATEGIC POSITIONING</h2>\n\n{strategy_content}\n\n"
            except Exception as e:
                logger.error(f"Lỗi gọi LLM Strategy: {e}")
                strategy_section = "" # Nếu lỗi AI cũng không show
        else:
            logger.warning(f"Bỏ qua Market Landscape: {sub_name} không có dữ liệu tài chính.")
            strategy_section = "" # Không gán gì cả nếu không có data

        # 3. Tổng hợp báo cáo
        all_banks_for_highlights = [subject_to_process] + indexed_peers
        highlight_tasks = [self.generate_individual_highlight(bank) for bank in all_banks_for_highlights]
        highlights = await asyncio.gather(*highlight_tasks)

        reference_footer = "\n\n---\n<h2 align='center' id='references_section'>REFERENCES</h2>\n\n"
        if self.global_id_to_url:
            reference_footer += '<div style="page-break-inside: avoid; width: 100%;">'
            for idx in sorted(self.global_id_to_url.keys()):
                url = self.global_id_to_url[idx]
                reference_footer += f'<p id="{idx}" style="margin-bottom: 8px; line-height: 1.4;">[{idx}]. <a href="{url}" target="_blank">{url}</a></p>\n'
            reference_footer += '</div>'
        else:
            reference_footer += "<p>No specific references extracted.</p>"

        toc_content = self._generate_toc(sub_name, indexed_peers)
        daily_changes_section = self._create_daily_snapshot_changes_section(subject_to_process, indexed_peers)
        PAGE_BREAK = '<div style="page-break-after: always;"></div>\n\n'
# 1. Khởi tạo danh sách các phần của báo cáo
        report_parts = [
            f"<h1 style='text-align: center; font-size: 28px; text-transform: uppercase; margin-top: 30px; margin-bottom: 20px;'> COMPETITORS ANALYSIS - FINANCIAL PERFORMANCE REPORT</h1>\n\n",
            f"<p style='text-align: center; font-size: 13px; color: #666; margin-bottom: 30px;'> Report Date: {report_date} | Data Extraction Date: {target_date}</p>\n\n",           
            toc_content, PAGE_BREAK
        ]

        report_parts.append(f"<a name='master-comparison-table'></a>\n{master_table}")
        report_parts.append(PAGE_BREAK)

        report_parts.append(daily_changes_section)
        report_parts.append(PAGE_BREAK)

        # 2. Sử dụng biến đếm để đánh số La Mã linh hoạt
        # Nếu có strategy_section thì nó là I, nếu không có thì Highlights sẽ là I
        current_section_idx = 3
        
        def get_roman_idx(n):
            numerals = {
                1: "I",
                2: "II",
                3: "III",
                4: "IV",
                5: "V",
            }
            return numerals.get(n, str(n))

        # CHỈ THÊM SECTION CHIẾN LƯỢC NẾU CÓ DATA
        if strategy_section:
            roman_num = get_roman_idx(current_section_idx)
            # Giả định tiêu đề I đã có sẵn trong biến strategy_content từ prompt AI
            # Hoặc bạn có thể bọc thủ công như sau:
            report_parts.append(f"<h2 id='market-landscape-strategy'>{roman_num}. MARKET LANDSCAPE & STRATEGIC POSITIONING</h2>\n\n{strategy_content}")
            report_parts.append(PAGE_BREAK)
            current_section_idx += 1

        # THÊM SECTION HIGHLIGHTS VỚI SỐ THỨ TỰ LINH HOẠT
        roman_num = get_roman_idx(current_section_idx)
        report_parts.append(f"<h2 id='detailed-highlights'>{roman_num}. DETAILED OPERATIONAL HIGHLIGHTS</h2>\n\n" + "\n".join(highlights))
        report_parts.append(PAGE_BREAK)
        current_section_idx += 1

        # THÊM REFERENCES
        report_parts.append(reference_footer)

        return "\n\n".join(report_parts)

    def _process_ai_content_links(self, content: Any) -> str:
        """Biến tag [1], [1, 2] thành thẻ HTML chứa link URL gốc để click mượt trên PDF/Web"""
        if isinstance(content, list): content = content[0].get('text', '') if content else ""
        content = str(content)
        # Loại bỏ các link URL thô không cần thiết nếu AI lỡ sinh ra
        content = re.sub(r'\(https?://[^\s)]+\)', "", content)
        
        # Tách các cụm [1, 2, 3] thành [1] [2] [3] để dễ dàng thay thế từng số bằng HTML anchor
        content = re.sub(r'\[(\d+)\s*,\s*(\d+)\]', r'[\1] [\2]', content)
        content = re.sub(r'\[(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\]', r'[\1] [\2] [\3]', content)

        def replace_with_html_link(match):
            idx_str = match.group(1)
            try:
                idx = int(idx_str)
                actual_url = self.global_id_to_url.get(idx, f"#{idx}")
                return f'<a href="{actual_url}" target="_blank" style="font-weight: bold; text-decoration: none; color: #1a365d;">[{idx}]</a>'
            except ValueError:
                return f"[{idx_str}]"

        return re.sub(r'\[(\d+)\]', replace_with_html_link, content)
    
    def _build_source_context(self, extracted_kpis: Dict) -> str:
        """
        Lấy top 3 source quotes từ _source_quotes (được gắn bởi banking_agent.py)
        và format thành context block để inject vào prompt.
        """
        quotes = extracted_kpis.get("_source_quotes", [])
        if not quotes:
            return ""

        parts = ["=== SOURCE CONTEXT (top articles by relevance score) ==="]
        for q in quotes[:3]:
            parts.append(
                f"\n[Rank #{q.get('rank', '?')}] {q.get('title', 'Untitled')}"
                f"\nURL: {q.get('url', '')}"
                f"\nDate: {q.get('pub_date', 'N/A')}"
                f"\n---\n{q.get('quote', '')[:10000]}"
                f"\n{'='*60}"
            )
        return "\n".join(parts)
