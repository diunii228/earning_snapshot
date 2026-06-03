from venv import logger
from schemas.state import BankingResearchState
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
import markdown2
import re

def save_results(state: BankingResearchState, output_dir: str = "results"):
    """
    Save results to folder with timestamp
    
    Args:
        state: BankingResearchState with extraction results
        output_dir: Directory path (not file path)
    
    Returns:
        str: Path to saved JSON file
    """
    
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bank_name = state['bank_name'].replace(" ", "_")
    
    json_filename = f"{bank_name}_{timestamp}.json"
    json_path = os.path.join(output_dir, json_filename)
    
    html_filename = f"{bank_name}_{timestamp}.html"
    html_path = os.path.join(output_dir, html_filename)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Saving results to folder: {output_dir}")
    logger.info(f"{'='*60}")
    
    results = {
        "bank_name": state["bank_name"],
        "reporting_period": state.get("reporting_period", "Not specified"),
        "extraction_date": datetime.now().isoformat(),
        "extraction_timestamp": timestamp,
        
        "sources": [
            {
                "index": idx + 1,
                "title": article["title"],
                "url": article["url"],
                "content_length": article["length"]
            }
            for idx, article in enumerate(state.get("articles_data", []))
        ],
        
        "extracted_kpis": state.get("extracted_kpis", {}),
        
        "validation_results": state.get("validation_results", {}),
        
        "status": state["status"],
        "errors": state.get("errors", []),
        
        "statistics": {
            "total_sources": len(state.get("articles_data", [])),
            "total_kpis_extracted": _count_kpis(state.get("extracted_kpis", {})),
            "validation_issues": len(state.get("validation_results", {}).get("validation_issues", []))
        }
    }
    
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"JSON saved: {json_path}")
    except Exception as e:
        logger.error(f"Failed to save JSON: {e}")
        raise
    
    try:
        _generate_html_report(results, html_path)
        logger.info(f"HTML report saved: {html_path}")
    except Exception as e:
        logger.error(f"Failed to generate HTML: {e}")
    
    logger.info(f"{'='*60}\n")
    
    return json_path


def _count_kpis(extracted_kpis: dict) -> int:
    """Count total extracted KPIs"""
    count = 0
    for category in extracted_kpis.values():
        if isinstance(category, dict):
            for kpi_data in category.values():
                if isinstance(kpi_data, dict) and kpi_data.get('value') is not None:
                    count += 1
    return count


def _generate_html_report(results: dict, output_path: str):
    """Generate HTML report with source links"""
    
    html_template = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Banking KPI Report - {bank_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
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
            margin-bottom: 20px;
        }}
        
        h2 {{
            color: #34495e;
            margin-top: 30px;
            margin-bottom: 15px;
            padding-left: 10px;
            border-left: 4px solid #3498db;
        }}
        
        h3 {{
            color: #555;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        
        .meta-info {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        
        .meta-info p {{
            margin: 5px 0;
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .stat-card h3 {{
            color: white;
            font-size: 2em;
            margin: 0;
        }}
        
        .stat-card p {{
            margin-top: 5px;
            opacity: 0.9;
        }}
        
        .source {{
            background: #ecf0f1;
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid #3498db;
            border-radius: 4px;
        }}
        
        .source strong {{
            color: #2c3e50;
        }}
        
        .source a {{
            color: #3498db;
            text-decoration: none;
            word-break: break-all;
        }}
        
        .source a:hover {{
            text-decoration: underline;
        }}
        
        .source small {{
            color: #7f8c8d;
        }}
        
        .kpi {{
            background: #fff;
            padding: 15px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .kpi:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        .kpi-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        
        .kpi-name {{
            font-weight: bold;
            color: #2c3e50;
            font-size: 1.1em;
        }}
        
        .kpi-value {{
            font-size: 1.3em;
            color: #27ae60;
            font-weight: bold;
        }}
        
        .source-tag {{
            display: inline-block;
            background: #3498db;
            color: white;
            padding: 4px 10px;
            border-radius: 3px;
            font-size: 0.85em;
            text-decoration: none;
            margin-right: 10px;
        }}
        
        .source-tag:hover {{
            background: #2980b9;
        }}
        
        .confidence {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 3px;
            font-size: 0.85em;
        }}
        
        .confidence-high {{
            background: #d4edda;
            color: #155724;
        }}
        
        .confidence-medium {{
            background: #fff3cd;
            color: #856404;
        }}
        
        .confidence-low {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        .validation-summary {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            border: 1px solid #dee2e6;
        }}
        
        .validation-summary ul {{
            list-style: none;
            padding-left: 0;
        }}
        
        .validation-summary li {{
            padding: 8px 0;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .validation-summary li:last-child {{
            border-bottom: none;
        }}
        
        .issue {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        
        .issue.critical {{
            background: #f8d7da;
            border-left-color: #dc3545;
        }}
        
        .issue.high {{
            background: #fff3cd;
            border-left-color: #ffc107;
        }}
        
        .severity-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            font-weight: bold;
            margin-right: 10px;
        }}
        
        .severity-critical {{
            background: #dc3545;
            color: white;
        }}
        
        .severity-high {{
            background: #ffc107;
            color: #000;
        }}
        
        .severity-medium {{
            background: #17a2b8;
            color: white;
        }}
        
        .no-data {{
            text-align: center;
            padding: 40px;
            color: #6c757d;
            font-style: italic;
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            .container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏦 Banking KPI Report: {bank_name}</h1>
        
        <div class="meta-info">
            <p><strong> Reporting Period:</strong> {reporting_period}</p>
            <p><strong> Extraction Date:</strong> {extraction_date}</p>
            <p><strong> Status:</strong> {status}</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <h3>{source_count}</h3>
                <p>Sources Analyzed</p>
            </div>
            <div class="stat-card">
                <h3>{kpi_count}</h3>
                <p>KPIs Extracted</p>
            </div>
            <div class="stat-card">
                <h3>{issue_count}</h3>
                <p>Validation Issues</p>
            </div>
        </div>
        
        <h2> Sources ({source_count})</h2>
        {sources_html}
        
        <h2> Extracted KPIs</h2>
        {kpis_html}
        
        <h2> Validation Summary</h2>
        {validation_html}
        
        {issues_html}
    </div>
</body>
</html>
    """
    
    # Build sources HTML
    sources_html = ""
    if results["sources"]:
        for source in results["sources"]:
            sources_html += f"""
        <div class="source">
            <strong>[{source['index']}]</strong> 
            <a href="{source['url']}" target="_blank">{source['title']}</a>
            <br><small>📄 {source['content_length']:,} characters</small>
        </div>
            """
    else:
        sources_html = '<div class="no-data">No sources available</div>'
    
    # Build KPIs HTML
    kpis_html = ""
    extracted_kpis = results.get("extracted_kpis", {})
    
    if extracted_kpis:
        for category, kpis in extracted_kpis.items():
            if not isinstance(kpis, dict):
                continue
                
            kpis_html += f"<h3>📌 {category.replace('_', ' ').title()}</h3>"
            
            for kpi_name, kpi_data in kpis.items():
                if not isinstance(kpi_data, dict):
                    continue
                    
                value = kpi_data.get('value')
                if value is None:
                    continue
                
                unit = kpi_data.get('unit', '')
                source_num = kpi_data.get('source_number', '?')
                source_url = kpi_data.get('source_url', '#')
                confidence = kpi_data.get('confidence', 'unknown')
                
                confidence_class = f"confidence-{confidence}" if confidence in ['high', 'medium', 'low'] else 'confidence-medium'
                
                kpis_html += f"""
                <div class="kpi">
                    <div class="kpi-header">
                        <span class="kpi-name">{kpi_name.replace('_', ' ').title()}</span>
                        <span class="kpi-value">{value:,} {unit}</span>
                    </div>
                    <div>
                        <a href="{source_url}" target="_blank" class="source-tag">
                            Source {source_num}
                        </a>
                        <span class="confidence {confidence_class}">
                            Confidence: {confidence}
                        </span>
                    </div>
                </div>
                """
    else:
        kpis_html = '<div class="no-data">No KPIs extracted</div>'
    
    # Build validation HTML
    validation = results.get("validation_results", {})
    quality = validation.get("quality_metrics", {})
    completeness = validation.get("completeness", {})
    
    validation_html = f"""
        <div class="validation-summary">
            <ul>
                <li><strong>Overall Quality Score:</strong> {quality.get('overall_quality_score', 0)}/100</li>
                <li><strong>Completeness Score:</strong> {quality.get('completeness_score', 0)}/100</li>
                <li><strong>Accuracy Score:</strong> {quality.get('accuracy_score', 0)}/100</li>
                <li><strong>Critical KPIs Found:</strong> {completeness.get('critical_kpis_found', 0)}/7</li>
            </ul>
        </div>
    """
    
    issues = validation.get("validation_issues", [])
    issues_html = ""
    
    if issues:
        issues_html = "<h2> Validation Issues</h2>"
        for issue in issues:
            severity = issue.get('severity', 'medium')
            severity_class = f"severity-{severity}"
            
            issues_html += f"""
            <div class="issue {severity}">
                <span class="severity-badge {severity_class}">{severity.upper()}</span>
                <strong>{issue.get('field', 'Unknown field')}</strong>
                <p>{issue.get('issue', 'No description')}</p>
                <p><em>Recommendation: {issue.get('recommendation', 'None provided')}</em></p>
            </div>
            """
    
    html_content = html_template.format(
        bank_name=results["bank_name"],
        reporting_period=results.get("reporting_period", "N/A"),
        extraction_date=results["extraction_date"],
        status=results["status"],
        source_count=len(results["sources"]),
        kpi_count=results["statistics"]["total_kpis_extracted"],
        issue_count=results["statistics"]["validation_issues"],
        sources_html=sources_html,
        kpis_html=kpis_html,
        validation_html=validation_html,
        issues_html=issues_html
    )
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

async def export_to_pdf_playwright(
    report_content: str, 
    output_path: str, 
    logo_url: str = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRyDSq0LSy1LSrrOQglwrzclPeQBNGCm1Q1yw&s" 
):
    try:
        processed_content = re.sub(
            r"(### Master Comparison Table.*?\n)(|.*?\n)+", 
            r'<div class="section-landscape">\n\n\1\n</div>', 
            report_content, 
            flags=re.DOTALL
        )

        html_body = markdown2.markdown(processed_content, extras=['tables', 'fenced-code-blocks'])
        
        css_style = """
        <style>
            @page { size: A4 portrait; margin: 10mm; }
            @page landscape_page { size: A4 landscape; margin: 10mm; }

            body { 
                font-family: 'Arial', sans-serif; 
                line-height: 1.4; 
                color: #333; 
                font-size: 11px; /* Đã giảm size tổng thể */
            }

            .section-landscape {
                page: landscape_page;
                display: block;
                width: 100%;
            }
            .header-container { 
                display: flex; 
                justify-content: flex-end; 
                align-items: center; 
                border-bottom: 1px solid #1a365d; 
                padding-bottom: 5px; 
                margin-bottom: 15px; 
            }
            
            .logo { 
                width: auto;
            }
table { 
    width: 100%; 
    border-collapse: collapse; 
    table-layout: fixed; /* Ép các cột tuân thủ độ rộng chỉ định */
    font-size: 9px;      /* Hạ xuống 7px để các con số hàng triệu không bị nhảy dòng */
    margin-bottom: 20px;
    font-variant-numeric: tabular-nums; 
    line-height: 2.0;
}

th, td { 
    border: 0.5px solid #e2e8f0; 
    padding: 4px 2.5px;    /* Giảm padding ngang xuống tối thiểu */
    word-wrap: break-word; 
    text-align: center;
    overflow: hidden;
}

/* Cột Metric và Unit */
th:nth-child(1), td:nth-child(1) { width: 11%; text-align: left; font-weight: bold; }
th:nth-child(2), td:nth-child(2) { width: 6%; color: #64748b; }

th:nth-child(n+3), 
td:nth-child(n+3) { 
    width: 8.8%; 
}

/* 2. Riêng cột Techcombank (giả sử là cột thứ 3) cho rộng ra 9.3% */
/* Nếu Techcombank ở vị trí khác, hãy thay số 3 bằng vị trí tương ứng */
th:nth-child(3), 
td:nth-child(3) { 
    width: 9.3%; 
}

/* Header style */
thead th {
    background-color: #f8fafc;
    color: #1e293b;
    vertical-align: middle;
}

            /* Định dạng Header */
            th { 
                text-align: center; 
                font-weight: bold;
                height: 30px;
            }

            /* Cột Metric (cột đầu tiên): Căn trái, in đậm */
            td:first-child { 
                text-align: left; 
                font-weight: bold; 
                background-color: #f8fafc;
                width: 12%; /* Cố định độ rộng cột tên chỉ số */
            }

            /* Cột Unit (cột thứ 2): Căn giữa */
            td:nth-child(2) { 
                text-align: center; 
                width: 6%; 
                color: #64748b;
            }

            /* Tất cả các cột số liệu: CĂN PHẢI */
            td:nth-child(n+3) { 
                text-align: right; 
                padding-right: 5px;
            }
            
            h1 { font-size: 16px; }
            h2 { font-size: 14px; border-bottom: 1px solid #eee; padding-bottom: 3px; }
            h3 { font-size: 12px; }        
            
            .header-container { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1a365d; margin-bottom: 15px; }
            .report-title { font-size: 12px; font-weight: bold; color: #1a365d; }
            .logo { max-height: 30px; }
        </style>
        """

        header_html = ""
        if logo_url:
            header_html = f"""
            <div class="header-container">
                <img src="{logo_url}" class="logo">
            </div>
            """

        full_html = f"<html><head><meta charset='UTF-8'>{css_style}</head><body>{header_html}{html_body}</body></html>"

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(full_html)
            await page.wait_for_timeout(1500) 
            
            await page.pdf(
                path=output_path,
                format="A4",
                landscape=False, 
                print_background=True
            )
            await browser.close()
        print(f"PDF exported successfully: {output_path}")

    except Exception as e:
        print(f" Error during PDF export: {e}")