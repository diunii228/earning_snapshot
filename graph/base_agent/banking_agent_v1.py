import json
import logging
from pydoc import text
import re
import asyncio
from urllib import response
import aiohttp
from utils.token_tracker import token_tracker  

from langchain_core.messages import HumanMessage, SystemMessage
from json_repair import repair_json

from models.llm_factory import get_llm
from utils.setting import LLMProvider
from schemas.state import BankingResearchState
from graph.base_agent.prompts import (
    BANKING_KPI_EXTRACTION_SYSTEM_MESSAGE,
    BANKING_KPI_VALIDATION_SYSTEM_MESSAGE,
    get_banking_extraction_prompt,
    get_banking_validation_prompt,
)
from typing import Dict, Optional, List, Tuple
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BankingResearchAgent:
    """Specialized agent for banking KPI extraction (ASYNC Version)"""
    
    def __init__(
        self, 
        provider: Optional[LLMProvider] = None,
        model_name: Optional[str] = None,
        temperature: float = 0,
        max_tokens: Optional[int] = None,
        top_p: float = 0.1,
        top_k: int = 1,
        **llm_kwargs
    ):
        try:
            self.llm = get_llm(
                provider=provider,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                top_k=top_k,
                **llm_kwargs
            )
            self.provider = provider.value if provider else "default"
            logger.info(f"Initialized BankingResearchAgent with provider: {self.provider}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {str(e)}")
            raise

    async def _perform_search(self, query: str, target_date: str | None = None, max_retries: int = 3) -> List[str]:
        """
        Sử dụng Gemini Search Grounding với xử lý lỗi định dạng Content.
        """
        if target_date:
            query = f"{query} after:{target_date} before:{target_date}"
            
        for attempt in range(max_retries):
            try:
                logger.info(f"[Attempt {attempt + 1}] Gemini Search: '{query}'")
                
                prompt = (
                    f"Bạn là một công cụ tìm kiếm dữ liệu tài chính. Hãy thực hiện chính xác truy vấn sau (bao gồm cả các toán tử site:, OR, filetype: nếu có): {query}\n"
                    f"Tuyệt đối KHÔNG lấy các tin tức rác, lừa đảo hay dịch vụ khách hàng. "
                    f"Trả về danh sách TỐI ĐA 10 URL trực tiếp chứa số liệu BCTC, lợi nhuận."
                )

                response = await self.llm.ainvoke(
                    prompt,
                    tools=[{"google_search": {}}] 
                )
                try:
                    token_tracker.add_from_response(response)
                except Exception as t_err:
                    logger.warning(f"Lỗi đếm token search: {t_err}")
                urls = []
                if 'grounding_metadata' in response.additional_kwargs:
                    metadata = response.additional_kwargs['grounding_metadata']
                    chunks = metadata.get('grounding_chunks', [])
                    for chunk in chunks:
                        if 'web' in chunk:
                            urls.append(chunk['web']['uri'])

                if not urls:
                    raw_text = ""
                    if isinstance(response.content, str):
                        raw_text = response.content
                    elif isinstance(response.content, list):
                        raw_text = " ".join([str(part) for part in response.content])
                    
                    if raw_text:
                        urls = re.findall(r'(https?://[^\s]+)', raw_text)

                unique_urls = list(set([u.strip('.,()[]<>') for u in urls if 'google.com' not in u]))
                
                if unique_urls:
                    return unique_urls
                
                logger.warning(f"Query '{query}' không trả về kết quả nào.")
                return []

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Lỗi Search (Attempt {attempt + 1}): {e}. Thử lại sau {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Thất bại sau {max_retries} lần thử search: {e}")
        
        return []
    
    async def _fetch_url(self, session, url, retries=2):
        """Fetch URL và luôn trả về Dict chứa html, pub_date, url"""
        if not isinstance(url, str) or not url.startswith("http"):
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.google.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate"
        }
        timeout = aiohttp.ClientTimeout(total=30)

        for attempt in range(retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as response:
                    if response.status == 200:
                        try:
                            html = await response.text(encoding="utf-8")
                        except UnicodeDecodeError:
                            raw = await response.read()
                            html = raw.decode("utf-8", errors="ignore")
                        
                        # Trích xuất ngày xuất bản
                        pub_date = self._extract_publication_date(html, url)
                        
                        return {
                            "html": html,
                            "pub_date": pub_date,
                            "url": url
                        }
                    logger.warning(f"Failed {url} | Status: {response.status}")
            except Exception as e:
                logger.warning(f"Error fetching {url}: {str(e)}")
            
            if attempt < retries:
                await asyncio.sleep(1)
        return None

    def _extract_publication_date(self, html: str, url: str) -> Optional[str]:
        """Bóc tách ngày từ meta tags của các báo tài chính VN"""
        soup = BeautifulSoup(html, "html.parser")
        
        meta_date = (
            soup.find("meta", property="article:published_time") or 
            soup.find("meta", {"name": "pubdate"}) or
            soup.find("meta", property="og:pubdate")
        )
        if meta_date:
            raw_date = meta_date.get("content", "")
            match = re.search(r'(\d{4}-\d{2}-\d{2})', raw_date)
            if match: return match.group(1)

        if "cafef.vn" in url:
            date_tag = soup.select_one(".td-post-date") or soup.select_one(".dateandtime")
            if date_tag:
                match = re.search(r'(\d{2}/\d{2}/\d{4})', date_tag.get_text())
                if match: return datetime.strptime(match.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")

        return None

    def _generate_intelligent_queries(self, bank_name: str, period: str) -> List[str]:        
        query_groups = {
    "profit_pbt": '"lợi nhuận trước thuế" OR "lãi trước thuế" OR "lãi ròng" OR "EPS"',
    "balance_sheet": '"tổng tài sản" OR "vốn chủ sở hữu" OR "vốn điều lệ"',
    "credit_and_quality": '"tăng trưởng tín dụng" OR "nợ xấu" OR "NPL" OR "dư nợ"',
    "ratios": '"NIM" OR "CASA" OR "ROA" OR "ROE" OR "CAR" OR "CIR"'
}
        domains = "site:cafef.vn OR site:vietstock.vn OR site:vneconomy.vn OR site:tinnhanhchungkhoan.vn"
    
        queries = []
        
        for _, keywords in query_groups.items():
            queries.append(f"{bank_name} {period} ({keywords}) {domains}")
            
        queries.append(f'báo cáo phân tích ngân hàng "{bank_name}" "{period}" analysis report filetype:pdf')
        queries.append(f'"{bank_name}" quan hệ cổ đông "{period}" kết quả kinh doanh presentation')
        
        queries.append(f'"{bank_name}" "kết quả kinh doanh" "{period}" {domains}')

        return queries
    
    def flatten_urls(self, items):
        """Recursively flatten nested url lists"""
        flat = []
        if isinstance(items, (list, tuple)):
            for item in items:
                flat.extend(self.flatten_urls(item))
        elif isinstance(items, str):
            flat.append(items)
        return flat


    def build_safe_urls(self, urls):
        """Remove invalid / non-str urls and deduplicate"""
        safe = []
        seen = set()
        for u in urls:
            if isinstance(u, str):
                u = u.strip()
                if u and u not in seen:
                    seen.add(u)
                    safe.append(u)
        return safe

    async def expand_category_links(
        self,
        state: BankingResearchState,
        max_links: int = 45
    ) -> BankingResearchState:

        input_urls = state.get("urls", [])

        if isinstance(input_urls, str):
            input_urls = [input_urls]

        if not input_urls and state.get("url"):
            input_urls = [state.get("url")]

        input_urls = self.flatten_urls(input_urls)
        input_urls = self.build_safe_urls(input_urls)

        if not input_urls:
            state["errors"].append("No valid input URLs after flattening")
            state["status"] = "failed"
            return state

        logger.info(
            f"\n[ASYNC] Scanning {len(input_urls)} source URLs for {state.get('bank_name')}..."
        )

        bank_name = state.get("bank_name", "").lower()
        reporting_period = state.get("reporting_period", "").lower()
        bank_variations = self._get_bank_variations(bank_name)

        year_match = re.search(r'20\d{2}', reporting_period)
        target_year = year_match.group(0) if year_match else str(datetime.now().year)

        period_keywords = [reporting_period]
        if 'q1' in reporting_period or 'quý 1' in reporting_period:
            period_keywords.extend(['q1', 'quý 1', 'quy 1'])
        elif 'q2' in reporting_period or 'quý 2' in reporting_period:
            period_keywords.extend(['q2', 'quý 2', 'quy 2'])
        elif 'q3' in reporting_period or 'quý 3' in reporting_period:
            period_keywords.extend(['q3', 'quý 3', 'quy 3'])
        elif 'q4' in reporting_period or 'quý 4' in reporting_period:
            period_keywords.extend(['q4', 'quý 4', 'quy 4'])

        all_candidates = []
        seen_urls = set()

        for url in input_urls:
            has_article_id = bool(re.search(r'\d{5,}', url))
            
            is_feed_page = any(kw in url.lower() for kw in ["tin-tuc", "search", "tag", "su-kien", "techcombank.html", "vietcombank.html"])
            
            if (has_article_id or "bai-viet" in url or "post" in url) and not is_feed_page:
                logger.info(f"Ưu tiên giữ lại link BÀI VIẾT gốc: {url}")
                all_candidates.append((url, 1000, "Link bài viết người dùng cung cấp"))
                seen_urls.add(url)

        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_url(session, url) for url in input_urls]
            results = await asyncio.gather(*tasks) 
        for res in results:
            if not res or not res.get("html"):
                continue

            candidates = self._extract_links_from_html(
                html_content=res["html"], 
                source_url=res["url"],
                bank_variations=bank_variations,
                period_keywords=period_keywords,
                target_year=target_year,
                target_date=state.get("target_date")
            )

            for url, score, text in candidates:
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_candidates.append((url, score, text))

        all_candidates.sort(key=lambda x: x[1], reverse=True)
        top_links = [item[0] for item in all_candidates[:max_links]]

        state["article_links"] = top_links
        state["status"] = "links_expanded" if top_links else "failed"

        logger.info(f"Found {len(top_links)} relevant links")
        return state

    async def _validate_link_health(self, session, url) -> bool:
        """Validate link lần 1, 2, 3 để lọc bỏ link lỗi (404, timeout, rác)"""
        try:
            async with session.head(url, timeout=5, allow_redirects=True) as resp:
                return resp.status == 200 and "text/html" in resp.headers.get("Content-Type", "")
        except:
            return False

    def _calculate_link_score(self, url, bank_name, period):
        score = 0
        url_lower = url.lower()
        if any(domain in url_lower for domain in ["cafef.vn", "vietstock.vn", "vneconomy.vn"]):
            score += 20
        if bank_name.lower() in url_lower:
            score += 15
        if period in url_lower:
            score += 10
        return score
    
    def _extract_links_from_html(
            self, 
            html_content: str, 
            source_url: str,
            bank_variations: List[str],
            period_keywords: List[str],
            target_year: str,
            target_date: str = None
        ) -> List[Tuple[str, int, str]]:
            candidates = []
            date_patterns = []
            if target_date:
                dt = datetime.strptime(target_date, "%Y-%m-%d")
                date_patterns = [
                    dt.strftime("%Y%m%d"),        # 20260302
                    dt.strftime("%Y/%m/%d"),      # 2026/03/02
                    dt.strftime("%d-%m-%Y"),      # 02-03-2026
                    dt.strftime("%Y-%m-%d"),      # 2026-03-02
                    dt.strftime("%d%m%Y"),        # 02032026
                ]
            
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                raw_links = soup.find_all("a", href=True)
                seen_urls = set()
                
                for a in raw_links:
                    href = a.get("href")
                    if not href: continue
                    
                    full_url = urljoin(source_url, href)
                    if full_url in seen_urls: continue

                    # Bỏ qua các link rác
                    skip_patterns = ["/tag/", "video.", ".jpg", ".png", "facebook.com", "youtube.com"]
                    if any(p in full_url.lower() for p in skip_patterns): continue
                    
                    link_text = (a.get_text() + " " + (a.get("title") or "")).strip().lower()
                    if len(link_text) < 15: continue
                    
                    score = 0
                    
                    if target_date:
                        # Kiểm tra xem URL có chứa target_date không
                        is_exact_date = any(p in full_url for p in date_patterns)
                        
                        if is_exact_date:
                            score += 100  
                        else:
                            other_date_match = re.search(r'20\d{2}[/-]?\d{2}[/-]?\d{2}', full_url)
                            if other_date_match:
                                score -= 20 
                    if any(var in link_text for var in bank_variations):
                        score += 20
                    if any(kw in link_text for kw in period_keywords):
                        score += 15
                    if any(kw in link_text for kw in ["lợi nhuận", "bctc", "nợ xấu", "tín dụng"]):
                        score += 10
                    
                    if score > 0:
                        seen_urls.add(full_url)
                        candidates.append((full_url, score, link_text))
            
            except Exception as e:
                logger.error(f"Error: {e}")
            
            return candidates

    def _get_bank_variations(self, bank_name: str) -> List[str]:
        """Get bank name variations"""
        variations = [bank_name]
        
        bank_map = {
            "vietcombank": ["vcb", "vietcombank", "ngân hàng ngoại thương"],
            "techcombank": ["tcb", "techcombank", "ngân hàng kỹ thương"],
            "vietinbank": ["ctg", "vietinbank", "ngân hàng công thương"],
            "bidv": ["bidv", "ngân hàng đầu tư và phát triển"],
            "mbb": ["mb", "mbbank"," mb bank", "ngân hàng quân đội","mbb"],
            "acb": ["acb", "ngân hàng á châu"],
            "vpbank": ["vpb", "vpbank", "ngân hàng việt nam thịnh vượng"],
            "tpbank": ["tpb", "tpbank", "ngân hàng tiên phong"],
            "hdbank": ["hdb", "hdbank", "ngân hàng phát triển thành phố hcm"]
        }
        
        for key, values in bank_map.items():
            if key in bank_name:
                variations.extend(values)
        
        return list(set(variations))
    
    async def fetch_articles_content(self, state: BankingResearchState) -> BankingResearchState:
        article_links = state.get("article_links", [])
        target_date = state.get("target_date")
        if not target_date:
            state["errors"].append("target_date is required but missing in state.")
            state["status"] = "failed"
            return state
        target_dt = datetime.strptime(target_date, "%Y-%m-%d") if target_date else None
        
        bank_name = state.get("bank_name", "").lower()
        bank_vars = self._get_bank_variations(bank_name)
        finance_kws = [
        "lợi nhuận trước thuế", "lãi trước thuế",  
        "lợi nhuận", "lãi ròng", "kết quả kinh doanh",
        "bctc", "báo cáo tài chính", "nợ xấu",
        "tín dụng", "thu nhập", "pbt", "pat",
    ]
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_url(session, url) for url in article_links]
            results = await asyncio.gather(*tasks)

        all_articles = []
        for res in results:
            if not res or not res.get("html"): continue
            
            url = res["url"]
            pub_date_str = res.get("pub_date") 
                
            try:
                soup = BeautifulSoup(res["html"], "html.parser")
                title_text = soup.find("title").get_text(strip=True) if soup.find("title") else ""
                
                sapo_tag = soup.select_one(".sapo, .td-post-content p:first-child")
                sapo_text = sapo_tag.get_text(strip=True) if sapo_tag else ""

                for tag in soup(["script", "style", "nav", "footer", "header", "iframe"]): 
                    tag.decompose()
                
                full_body_text = soup.get_text(separator="\n", strip=True)
                
                search_scope = (title_text + " " + sapo_text + " " + full_body_text).lower()

                logger.info(f"\n🔍 ĐANG KIỂM TRA TOÀN DIỆN: {url}")

                # 3. KIỂM TRA NGÀY (is_valid_date)
                is_valid_date = False 
                if pub_date_str:
                    try:
                        pub_dt = datetime.strptime(pub_date_str, "%Y-%m-%d")
                        if abs((pub_dt - target_dt).days) <= 2:
                            is_valid_date = True
                            logger.info(f"   Khớp ngày qua metadata: {pub_date_str}")
                    except ValueError:
                        pass
                if not is_valid_date:
                    scan_zone = full_body_text[:8000]

                    # Tạo pattern cho target_date và ±2 ngày xung quanh
                    date_candidates = [
                        target_dt + __import__('datetime').timedelta(days=d)
                        for d in range(-2, 3)   # -2, -1, 0, +1, +2
                    ]
                    date_patterns = []
                    for dt in date_candidates:
                        date_patterns.extend([
                            dt.strftime("%Y-%m-%d"),          # 2025-01-20
                            dt.strftime("%d/%m/%Y"),          # 20/01/2025
                            dt.strftime("%d-%m-%Y"),          # 20-01-2025
                            f"{dt.day}/{dt.month}/{dt.year}", # 20/1/2025
                            f"{dt.day}/{dt.month}",           # 20/1  (CafeF hay dùng)
                            f"{dt.day:02d}/{dt.month:02d}",   # 20/01
                            dt.strftime("%Y%m%d"),            # 20250120
                        ])

                    if any(p in scan_zone for p in date_patterns):
                        is_valid_date = True
                        logger.info(f"   Khớp ngày qua nội dung bài viết")

                # 4. KIỂM TRA KEYWORD TRONG TOÀN BỘ NỘI DUNG (Thay vì chỉ Title)
                has_bank = any(var in search_scope for var in bank_vars)
                has_finance = any(kw in search_scope for kw in finance_kws)

                if is_valid_date: 
                    if has_bank or has_finance:
                        all_articles.append({
                            "url": url,
                            "title": title_text,
                            "content": full_body_text[:20000], 
                            "pub_date": pub_date_str,
                            "is_exact_date": (pub_date_str == target_date)
                        })
                    logger.info(f"   🟢 [HỢP LỆ] Đã lấy được nội dung cho {bank_name} từ bài viết.")
                else:
                    reason = []
                    if not is_valid_date: reason.append("Sai ngày")
                    if not has_bank: reason.append("Thiếu tên Bank")
                    if not has_finance: reason.append("Thiếu keyword tài chính")
                    logger.warning(f"   🔴 [LOẠI] {', '.join(reason)} | URL: {url}")

            except Exception as e:
                logger.error(f"   ❌ Lỗi parsing {url}: {str(e)}")
        if not all_articles:
            state["errors"].append(
                f"Không tìm thấy bài nào trong khoảng {target_date} ±2 ngày "
                f"có keyword tài chính & tên bank '{bank_name}'. "
                f"Kiểm tra lại target_date hoặc mở rộng khoảng ngày."
            )
            state["status"] = "failed"
            return state
        state["articles_data"] = all_articles
        state["raw_content"] = self._format_content(all_articles)
        state["status"] = "fetched" if all_articles else "failed"
        
        return state
        # for res in results:
        #     if not res or not res.get("html"): continue
                
        #     url = res["url"]
        #     html_content = res["html"]
        #     pub_date_str = res.get("pub_date")
                
        #     try:
        #         soup = BeautifulSoup(html_content, "html.parser")
        #         for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "svg"]):
        #             tag.decompose()

        #         text = soup.get_text(separator="\n", strip=True)
        #         title_tag = soup.find("title")
        #         title_text = title_tag.get_text(strip=True).lower() if title_tag else ""

        #         if len(text) < 300: continue 

        #         # --- BƯỚC 1: LỌC KEYWORD ---
        #         finance_kws = ["lợi nhuận", "kết quả kinh doanh", "bctc", "báo cáo tài chính", "nợ xấu", "tín dụng", "thu nhập", "lãi ròng"]
        #         has_bank = any(var in title_text for var in self._get_bank_variations(bank_name))
        #         has_finance_content = any(kw in title_text for kw in finance_kws) or (period in title_text)
                
        #         if not (has_bank and has_finance_content):
        #             continue

        #         # --- BƯỚC 2: KIỂM TRA NGÀY (Khởi tạo biến trước) ---
        #         is_valid_date = False  # QUAN TRỌNG: Khởi tạo giá trị mặc định ở đây
                
        #         if target_dt:
        #             # 2.1 Kiểm tra ngày từ Metadata bóc được
        #             if pub_date_str:
        #                 pub_dt = datetime.strptime(pub_date_str, "%Y-%m-%d")
        #                 if abs((pub_dt - target_dt).days) <= 2:
        #                     is_valid_date = True
                    
        #             # 2.2 Nếu chưa khớp, kiểm tra nội dung text bài báo
        #             if not is_valid_date:
        #                 day = target_dt.day
        #                 month = target_dt.month
        #                 year = target_dt.year
                        
        #                 # Các pattern xuất hiện thực tế: "20/1", "20/01", "20-01", "tối 20/1"
        #                 date_patterns = [
        #                     target_date,
        #                     target_dt.strftime("%d/%m/%Y"),
        #                     target_dt.strftime("%d-%m-%Y"),
        #                     f"{day}/{month}/{year}",
        #                     f"{day}-{month}-{year}",
        #                     f"{day}/{month}",      # Rất quan trọng cho CafeF (vd: 20/1)
        #                     f"{day:02d}/{month:02d}", # 20/01
        #                     f"ngày {day}/{month}",
        #                     f"tối {day}/{month}"
        #                 ]
                        
        #                 content_head = text[:2000].lower()
        #                 if any(dp in content_head for dp in date_patterns):
        #                     is_valid_date = True
        #                     logger.info(f"Khớp ngày target qua nội dung: {url}")

        #         # --- BƯỚC 3: QUYẾT ĐỊNH ---
        #         if not is_valid_date:
        #             logger.warning(f"Skipping {url}: Không khớp ngày target {target_date}")
        #             continue

        #         all_articles.append({
        #             "url": url,
        #             "title": title_text,
        #             "content": text[:15000], 
        #             "pub_date": pub_date_str,
        #             "is_exact_date": (pub_date_str == target_date)
        #         })
        #         logger.info(f"Accepted: {url} | Date: {pub_date_str}")

        #     except Exception as e:
        #         logger.error(f"Error parsing {url}: {e}")

        # if not all_articles:
        #     state["errors"].append(f"Không tìm thấy bài báo đúng Keyword tài chính trong ngày {target_date}")
        #     state["status"] = "failed"
        #     return state

        # state["articles_data"] = all_articles
        # state["raw_content"] = self._format_content(all_articles)
        # state["status"] = "fetched"
        # return state
    
    def _format_content(self, articles: list) -> str:
        if not articles:
            return ""

        def sort_key(article):
            exact_weight = 1000 if article.get('is_exact_date') else 0
            
            digit_density = len(re.findall(r'\d+', article['content'])) / len(article['content']) if len(article['content']) > 0 else 0
            quality_weight = digit_density * 100
            
            return exact_weight + quality_weight

        articles.sort(key=sort_key, reverse=True)

        unique_articles = {}
        for a in articles:
            if a['title'] not in unique_articles:
                unique_articles[a['title']] = a
        
        final_list = list(unique_articles.values())

        parts = []
        total_chars = 0
        MAX_TOTAL_CHARS = 180000 
        
        for idx, article in enumerate(final_list, 1):
            header_prefix = " [NGUỒN CHÍNH XÁC NGÀY]" if article.get('is_exact_date') else ""
            
            section = f"""
    ### SOURCE {idx}:{header_prefix} {article['title']}
    URL: {article['url']}
    PUB DATE: {article.get('pub_date', 'N/A')}
    CONTENT:
    {article['content'].strip()} 
    ---
    """
            if total_chars + len(section) > MAX_TOTAL_CHARS:
                break
                
            parts.append(section)
            total_chars += len(section)

        return "\n".join(parts)
    
    async def extract_banking_kpis(self, state: BankingResearchState) -> BankingResearchState:
        """Extract banking KPIs using Async LLM"""
        target_date = state.get('target_date', 'N/A')
        bank_name = state.get('bank_name', 'Unknown Bank')
        
        logger.info(f"\n[ASYNC] Extracting KPIs for: {bank_name} (Date: {target_date})")
        
        if state.get('status') == 'failed': 
            return state
        
        raw_content = state.get('raw_content', '')
        if not raw_content:
            state['errors'].append("No content to process")
            state['status'] = 'failed'
            return state

        extraction_prompt = get_banking_extraction_prompt(
            bank_name=bank_name,
            raw_content=raw_content,
            reporting_period=state.get('reporting_period', 'Latest available'),
            target_date=None
        )
        
        try:
            messages = [
                SystemMessage(content=BANKING_KPI_EXTRACTION_SYSTEM_MESSAGE),
                HumanMessage(content=extraction_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            try:
                token_tracker.add_from_response(response)
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    usage = response.usage_metadata
                    logger.info(f"[TOKEN - Extract] Bank: {bank_name} | Input: {usage.get('input_tokens')} | Total: {usage.get('total_tokens')}")
            except Exception as t_err:
                logger.warning(f"Lỗi đếm token extract: {t_err}")
            content = response.content
            
            if not content: 
                raise ValueError("Empty LLM response")
            
            extracted_data = self._parse_json(content)

            if not extracted_data:
                raise ValueError("Could not extract valid JSON")

            import re
            source_mapping = {}
            
            matches = re.finditer(r'### SOURCE (\d+):[^\n]*\n\s*URL:\s*(https?://[^\s]+)', raw_content)
            for m in matches:
                source_mapping[int(m.group(1))] = m.group(2).strip()
            
            if source_mapping:
                for cat, kpis in extracted_data.items():
                    if isinstance(kpis, dict):
                        for kpi_name, details in kpis.items():
                            if isinstance(details, dict):
                                s_num = details.get("source_number")
                                if isinstance(s_num, int) and s_num in source_mapping:
                                    details["source_url"] = source_mapping[s_num]

            kpi_count = self._count_extracted_kpis(extracted_data)
            has_data = kpi_count > 0

            state['extracted_kpis'] = extracted_data   
            state['kpi_count'] = kpi_count            
            state['has_new_data'] = has_data
            
            if has_data:
                logger.info(f"Found {kpi_count} new KPI values for {bank_name}")
            else:
                logger.info(f"No specific KPI values found for {bank_name} on {target_date}")            

        except Exception as e:
            error_msg = f"Failed to extract KPIs for {bank_name}: {str(e)}"
            state['errors'].append(error_msg)
            state['extracted_kpis'] = {} 
            state['status'] = 'failed'
            state['has_new_data'] = False
            logger.error(error_msg)
            
        return state
    
    def _parse_json(self, content) -> Optional[Dict]:
        if isinstance(content, list):
            content = content[0].get('text', '') if content and isinstance(content[0], dict) else str(content)
        
        if not isinstance(content, str): return None
        
        result = None
        try:
            result = repair_json(content, return_objects=True)
        except:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    result = repair_json(match.group(), return_objects=True)
                except: pass
        
        if isinstance(result, list):
            logger.warning("LLM returned a list instead of a dict. Extracting first element.")
            return result[0] if (len(result) > 0 and isinstance(result[0], dict)) else {}
        
        return result if isinstance(result, dict) else None
    
    def _count_extracted_kpis(self, extracted_data: Dict) -> int:
        count = 0

        if not isinstance(extracted_data, dict):
            return 0

        ignore_root = {"bank", "bank_name", "reporting_period"}

        for section_name, section in extracted_data.items():
            if section_name in ignore_root:
                continue

            if isinstance(section, dict):
                for kpi_name, kpi in section.items():
                    if isinstance(kpi, dict) and "value" in kpi:
                        value = kpi.get("value")
                        if value not in [None, "-", "N/A", "", "null"]:
                            count += 1

        return count
    
    async def validate_banking_kpis(self, state: BankingResearchState) -> BankingResearchState:
        """Validate banking KPIs"""
        logger.info(f"\n[ASYNC] Validating KPIs for: {state['bank_name']}")
        
        if not state.get('extracted_kpis') or state.get('status') == 'failed': 
            return state
        
        validation_prompt = get_banking_validation_prompt(
            bank_name=state['bank_name'],
            extracted_kpis_json=json.dumps(state['extracted_kpis'], indent=2, ensure_ascii=False),
            target_reporting_period=state.get('reporting_period'), 
            custom_ranges=state.get('custom_ranges') 
        )
        
        try:
            messages = [
                SystemMessage(content=BANKING_KPI_VALIDATION_SYSTEM_MESSAGE),
                HumanMessage(content=validation_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            try:
                token_tracker.add_from_response(response)
            except Exception as t_err:
                logger.warning(f"Lỗi đếm token validate: {t_err}")
            
            validation_results = self._parse_json(response.content)
            if validation_results:
                state['validation_results'] = validation_results
                state['status'] = 'validated'
                
        except Exception as e:
            error_msg = f"Validation LLM parsing failed: {str(e)}"
            logger.error(error_msg)
            state['errors'].append(error_msg)
            state['status'] = 'validation_failed' 
            
        return state
