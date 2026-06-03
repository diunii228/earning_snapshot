"""
Output formatter for research results.
Formats results with source links and highlighted relevant lines.
"""

import re
from typing import Any, Dict, List, Optional


def format_research_output(
    state: Dict[str, Any],
    highlight_keywords: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Format research results with source links and highlighted content.
    
    Args:
        state: ResearchState dict from research agent
        highlight_keywords: Keywords to highlight in content (defaults to state keywords)
        
    Returns:
        Formatted output dict with:
        - fields: Extracted fields with source links
        - sources: List of sources with highlighted content
        - metadata: Topic, status, etc.
    """
    articles = state.get("articles", [])
    topic = state.get("topic", "")
    keywords = highlight_keywords or state.get("keywords", [])
    
    # Build source map
    source_map = {}
    for idx, article in enumerate(articles, 1):
        source_map[idx] = {
            "index": idx,
            "title": article.get("title", "Unknown"),
            "url": article.get("url", ""),
            "content": article.get("content", ""),
        }
    
    # Extract fields from analysis if structured
    extracted_fields = _extract_fields_from_analysis(state.get("analysis", ""), source_map)
    
    # Highlight relevant lines in each article
    highlighted_sources = []
    for article in articles:
        highlighted = _highlight_relevant_lines(
            article.get("content", ""),
            keywords + [topic] if topic else keywords
        )
        highlighted_sources.append({
            "title": article.get("title", "Unknown"),
            "url": article.get("url", ""),
            "highlighted_content": highlighted,
            "original_content": article.get("content", ""),
        })
    
    return {
        "topic": topic,
        "status": state.get("status", "unknown"),
        "extracted_fields": extracted_fields,
        "sources": highlighted_sources,
        "metadata": {
            "total_sources": len(articles),
            "total_fields": len(extracted_fields),
            "keywords_used": keywords,
        }
    }


def _extract_fields_from_analysis(analysis: str, source_map: Dict) -> List[Dict[str, Any]]:
    """
    Extract structured fields from analysis text.
    Looks for patterns like:
    - Field: value (Source: X)
    - Field: value [Source X]
    - JSON-like structures
    """
    fields = []
    
    if not analysis:
        return fields
    
    # Try to extract JSON if present
    json_match = re.search(r'```json\n(.*?)\n```', analysis, re.DOTALL)
    if json_match:
        try:
            import json
            data = json.loads(json_match.group(1))
            fields = _parse_json_fields(data, source_map)
            return fields
        except:
            pass
    
    # Extract field patterns: "Field Name: value (Source: X)" or "Field: value [Source X]"
    patterns = [
        r'([^:\n]+):\s*([^\n(]+)\s*\(Source:\s*(\d+)\)',
        r'([^:\n]+):\s*([^\n\[]+)\s*\[Source\s*(\d+)\]',
        r'([^:\n]+):\s*([^\n]+)',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, analysis, re.IGNORECASE)
        for match in matches:
            field_name = match.group(1).strip()
            field_value = match.group(2).strip()
            source_num = int(match.group(3)) if len(match.groups()) > 2 and match.group(3).isdigit() else None
            
            source_info = source_map.get(source_num) if source_num else None
            
            fields.append({
                "field": field_name,
                "value": field_value,
                "source_index": source_num,
                "source_url": source_info.get("url") if source_info else None,
                "source_title": source_info.get("title") if source_info else None,
            })
    
    return fields


def _parse_json_fields(data: Any, source_map: Dict, prefix: str = "") -> List[Dict[str, Any]]:
    """Recursively parse JSON structure to extract fields."""
    fields = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            field_name = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                # Check if it's a field with metadata (source_number, source_url, etc.)
                if "value" in value or "source_number" in value:
                    source_num = value.get("source_number")
                    source_info = source_map.get(source_num) if source_num else None
                    
                    fields.append({
                        "field": field_name,
                        "value": value.get("value", value),
                        "unit": value.get("unit"),
                        "source_index": source_num,
                        "source_url": value.get("source_url") or (source_info.get("url") if source_info else None),
                        "source_title": value.get("source_title") or (source_info.get("title") if source_info else None),
                        "source_quote": value.get("source_quote"),
                        "confidence": value.get("confidence"),
                        "metadata": {k: v for k, v in value.items() if k not in ["value", "source_number", "source_url", "source_title", "source_quote", "confidence"]}
                    })
                else:
                    # Nested structure
                    fields.extend(_parse_json_fields(value, source_map, field_name))
            else:
                fields.append({
                    "field": field_name,
                    "value": value,
                    "source_index": None,
                    "source_url": None,
                    "source_title": None,
                })
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            fields.extend(_parse_json_fields(item, source_map, f"{prefix}[{idx}]"))
    
    return fields


def _highlight_relevant_lines(content: str, keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Highlight lines containing relevant keywords.
    
    Returns:
        List of dicts with:
        - line_number: Line number (1-indexed)
        - line_text: Original line text
        - highlighted_text: Line with HTML highlights
        - matched_keywords: List of keywords that matched
    """
    if not content or not keywords:
        return []
    
    lines = content.split('\n')
    highlighted_lines = []
    
    # Normalize keywords
    keywords_lower = [kw.lower() for kw in keywords if kw]
    
    for line_num, line in enumerate(lines, 1):
        line_lower = line.lower()
        matched = [kw for kw in keywords_lower if kw in line_lower]
        
        if matched:
            # Highlight matched keywords in the line
            highlighted = line
            for kw in matched:
                # Case-insensitive highlight
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                highlighted = pattern.sub(
                    lambda m: f'<mark style="background-color: #ffeb3b; padding: 2px 4px;">{m.group()}</mark>',
                    highlighted
                )
            
            highlighted_lines.append({
                "line_number": line_num,
                "line_text": line,
                "highlighted_text": highlighted,
                "matched_keywords": matched,
            })
    
    return highlighted_lines


def format_output_html(formatted_output: Dict[str, Any], output_path: str) -> None:
    """
    Format output as HTML with links and highlights.
    
    Args:
        formatted_output: Output from format_research_output()
        output_path: Path to save HTML file
    """
    html_template = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Results - {topic}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 10px;
        }}
        .field {{
            background: #fff;
            padding: 15px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
            border-left: 4px solid #3498db;
        }}
        .field-name {{
            font-weight: bold;
            color: #2c3e50;
            font-size: 1.1em;
        }}
        .field-value {{
            color: #27ae60;
            font-size: 1.1em;
            margin: 5px 0;
        }}
        .source-link {{
            display: inline-block;
            background: #3498db;
            color: white;
            padding: 4px 10px;
            border-radius: 3px;
            text-decoration: none;
            margin-top: 5px;
            font-size: 0.9em;
        }}
        .source-link:hover {{
            background: #2980b9;
        }}
        .source-section {{
            background: #f8f9fa;
            padding: 20px;
            margin: 20px 0;
            border-radius: 5px;
            border: 1px solid #dee2e6;
        }}
        .source-title {{
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .source-title a {{
            color: #2c3e50;
            text-decoration: none;
        }}
        .source-title a:hover {{
            text-decoration: underline;
        }}
        .highlighted-line {{
            background: #fff3cd;
            padding: 8px;
            margin: 5px 0;
            border-left: 3px solid #ffc107;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
        .line-number {{
            color: #6c757d;
            font-weight: bold;
            margin-right: 10px;
        }}
        mark {{
            background-color: #ffeb3b;
            padding: 2px 4px;
        }}
        .metadata {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Research Results: {topic}</h1>
        
        <div class="metadata">
            <p><strong>Status:</strong> {status}</p>
            <p><strong>Total Sources:</strong> {total_sources}</p>
            <p><strong>Total Fields Extracted:</strong> {total_fields}</p>
        </div>
        
        <h2>📋 Extracted Fields</h2>
        {fields_html}
        
        <h2>🔗 Sources with Highlighted Content</h2>
        {sources_html}
    </div>
</body>
</html>
    """
    
    # Build fields HTML
    fields_html = ""
    for field in formatted_output.get("extracted_fields", []):
        source_link = ""
        if field.get("source_url"):
            source_link = f'<a href="{field["source_url"]}" target="_blank" class="source-link">🔗 Source: {field.get("source_title", "Link")}</a>'
        
        fields_html += f"""
        <div class="field">
            <div class="field-name">{field.get("field", "Unknown")}</div>
            <div class="field-value">{field.get("value", "N/A")}</div>
            {source_link}
        </div>
        """
    
    if not fields_html:
        fields_html = "<p><em>No fields extracted</em></p>"
    
    # Build sources HTML
    sources_html = ""
    for source in formatted_output.get("sources", []):
        highlighted_lines_html = ""
        for line in source.get("highlighted_content", []):
            highlighted_lines_html += f"""
            <div class="highlighted-line">
                <span class="line-number">Line {line["line_number"]}:</span>
                {line["highlighted_text"]}
            </div>
            """
        
        sources_html += f"""
        <div class="source-section">
            <div class="source-title">
                <a href="{source.get("url", "#")}" target="_blank">{source.get("title", "Unknown")}</a>
            </div>
            {highlighted_lines_html if highlighted_lines_html else "<p><em>No relevant lines found</em></p>"}
        </div>
        """
    
    html_content = html_template.format(
        topic=formatted_output.get("topic", "Unknown"),
        status=formatted_output.get("status", "unknown"),
        total_sources=formatted_output.get("metadata", {}).get("total_sources", 0),
        total_fields=formatted_output.get("metadata", {}).get("total_fields", 0),
        fields_html=fields_html,
        sources_html=sources_html,
    )
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
