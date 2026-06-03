import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


def fetch_url_content(url: str, timeout: int = 30) -> Dict[str, Any]:
    """Fetch and parse content from a URL."""
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        
        text = soup.get_text(separator="\n", strip=True)
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else "No title"
        
        return {
            "url": url,
            "title": title_text,
            "content": text[:15000],  # Limit content
            "length": len(text),
            "success": True,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return {
            "url": url,
            "title": "",
            "content": "",
            "length": 0,
            "success": False,
            "error": str(e),
        }


def extract_links(url: str, keywords: List[str] = None, max_links: int = 10) -> List[str]:
    """Extract relevant links from a webpage."""
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        keywords = keywords or []
        
        scored_links = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            
            full_url = urljoin(url, href)
            
            # Skip unwanted links
            if any(x in full_url.lower() for x in [
                "/tag/", "/category/", "/author/",
                "facebook.com", "twitter.com", "linkedin.com",
                ".jpg", ".png", ".pdf", ".zip"
            ]):
                continue
            
            # Score links
            score = 0
            text_content = (a.get_text() + " " + full_url).lower()
            
            for keyword in keywords:
                if keyword.lower() in text_content:
                    score += 1
            
            if score > 0 or not keywords:
                scored_links.append((full_url, score))
        
        scored_links.sort(key=lambda x: x[1], reverse=True)
        return [url for url, _ in scored_links[:max_links]]
        
    except Exception as e:
        logger.error(f"Failed to extract links from {url}: {e}")
        return []


def format_sources(articles: List[Dict]) -> str:
    """Format multiple articles with source attribution."""
    formatted_parts = []
    
    for idx, article in enumerate(articles, 1):
        section = f"""
{'='*80}
SOURCE {idx}: {article.get('title', 'Unknown')}
URL: {article.get('url', 'N/A')}
{'='*80}

{article.get('content', '')}
"""
        formatted_parts.append(section)
    
    return "\n".join(formatted_parts)


def parse_json_response(content: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    try:
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        
        import json
        return json.loads(content)
    except Exception as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return None


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    # Remove excessive whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()
