RESEARCH_SYSTEM_PROMPT = """You are an expert research analyst. Your task is to:
1. Analyze content thoroughly and extract relevant information
2. Provide accurate, well-sourced findings
3. Identify key insights and patterns
4. Always cite sources when available
"""

ANALYSIS_PROMPT = """
Analyze the following content and extract key information.

Topic: {topic}
Content:
{content}

Provide a comprehensive analysis including:
1. Key findings and facts
2. Important metrics or data points
3. Notable trends or patterns
4. Sources and citations

Return your analysis in a structured format.
"""

SUMMARIZE_PROMPT = """
Summarize the following research findings.

Topic: {topic}
Findings:
{findings}

Create a clear, concise summary that:
1. Highlights the most important points
2. Organizes information logically
3. Notes any gaps or uncertainties
4. Provides actionable insights
"""

VALIDATE_PROMPT = """
Validate the following extracted information for accuracy and completeness.

Topic: {topic}
Extracted Data:
{data}

Check for:
1. Factual accuracy
2. Internal consistency
3. Source reliability
4. Completeness of information

Return validation results as JSON:
{{
    "is_valid": <true/false>,
    "confidence_score": <0-100>,
    "issues": [
        {{"field": "...", "issue": "...", "severity": "high/medium/low"}}
    ],
    "recommendations": ["..."]
}}
"""


def get_analysis_prompt(topic: str, content: str) -> str:
    return ANALYSIS_PROMPT.format(topic=topic, content=content)


def get_summarize_prompt(topic: str, findings: str) -> str:
    return SUMMARIZE_PROMPT.format(topic=topic, findings=findings)


def get_validate_prompt(topic: str, data: str) -> str:
    return VALIDATE_PROMPT.format(topic=topic, data=data)
