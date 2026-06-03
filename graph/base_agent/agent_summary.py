"""
agent_summary.py
================
Agent đọc file MD/PDF → AI tóm tắt → tạo Gmail draft HTML đẹp + attach file gốc.
Dùng get_llm() theo pattern BankingReporterAgent.

Cài đặt:
    pip install pymupdf google-auth google-auth-oauthlib google-api-python-client

Setup Gmail API (một lần):
    1. https://console.cloud.google.com → tạo project → Enable Gmail API
    2. OAuth2 credentials → Download → lưu thành credentials.json
    3. Chạy lần đầu → browser mở để login Google → tự lưu token.json

Sử dụng:
    python agent_summary.py --file report.md --to boss@company.com
    python agent_summary.py --file report.pdf --to "ceo@co.com,cfo@co.com" --type financial --lang en
    python /Users/ddlyy/agent-competitor/graph/base_agent/agent_summary.py --file /Users/ddlyy/agent-competitor/outputs/Financial_Performance_Report_Q42025_20260401_1117.pdf --to ddlyy228@gmail.com --no-attach --output email.txt
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.llm_factory import get_llm  # TODO: thay bằng import thực tế
from graph.base_agent.mail_sender import create_gmail_draft


# ─── Cấu hình ────────────────────────────────────────────────────────────────

REPORT_TYPES = {
    "weekly":    "Weekly Update",
    "project":   "Project Status",
    "market":    "Market Analysis",
    "incident":  "Incident Report",
    "strategy":  "Strategy Brief",
    "financial": "Financial Summary",
}

DETAIL_LEVELS = {
    "concise":  "3–5 bullet points, only the most critical information",
    "standard": "5–8 bullet points, balanced detail",
    "detailed": "8+ bullet points, comprehensive coverage",
}


# ─── Agent ───────────────────────────────────────────────────────────────────

class SummaryEmailAgent:
    def __init__(self, model_name: Optional[str] = None):
        self.llm = get_llm(
            model_name=model_name,
            temperature=0.1,   # Thấp để AI tuân thủ format email chặt chẽ
            top_p=0.3,
            max_tokens=8000,
            request_timeout=300,
        )

    # ── Đọc file ─────────────────────────────────────────────────────────────

    def load_document(self, path: Path) -> tuple[str, str]:
        """Trả về (content, file_type)."""
        ext = path.suffix.lower()
        if ext in (".md", ".txt"):
            return path.read_text(encoding="utf-8"), "markdown"
        elif ext == ".pdf":
            return self._read_pdf(path), "pdf"
        else:
            sys.exit(f"❌ Định dạng không hỗ trợ: {ext}. Dùng .md, .txt hoặc .pdf")

    def _read_pdf(self, path: Path) -> str:
        try:
            import fitz
        except ImportError:
            sys.exit("❌ pip install pymupdf")

        doc = fitz.open(str(path))
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append(f"[Trang {i + 1}]\n{text.strip()}")
        doc.close()

        if not pages:
            sys.exit("❌ Không đọc được text từ PDF (có thể là file scan).")
        return "\n\n".join(pages)

    # ── Prompt ───────────────────────────────────────────────────────────────

    def _detect_first_run_report(self, content: str) -> bool:
        lowered = content.lower()
        return (
            "daily snapshot changes vs previous run" in lowered
            and "no prior snapshot for comparison" in lowered
        )

    def _build_prompt(
        self,
        content: str,
        to: str,
        from_name: str,
        report_type: str,
        detail: str,
        lang: str,
    ) -> str:
        lang_str = "Vietnamese" if lang == "vi" else "English"
        is_first_run_report = self._detect_first_run_report(content)

        if is_first_run_report:
            additional_rules = """
- This is the first run of the reporting period.
- Focus the email on:
  1. a short market landscape summary,
  2. the most important KPI table takeaways,
  3. the current competitive position of the subject bank.
- Do NOT pretend there is a previous-run comparison if the report says there is no prior snapshot.
- Keep the landscape section concise and executive-friendly.
- Do not add a "new today vs previous run" section for first-run reports.
"""
        else:
            additional_rules = """
- This report includes previous-run comparison data.
- Structure the email so that:
  1. the top section gives a short KPI and landscape recap,
  2. a lower section clearly lists what is new versus the previous run,
  3. the "new data" section is explicit, concrete, and easy to scan.
- Prioritize:
  1. what changed versus the previous run,
  2. which KPIs are newly added,
  3. which KPIs materially moved,
  4. which KPIs disappeared or were not refreshed.
- Make the email explicitly answer: "What is new today versus the previous run?"
"""

        return f"""You are an expert executive communications specialist.
Summarize the document below into a professional C-level email in {lang_str}.

Report type : {REPORT_TYPES[report_type]}
Detail level: {DETAIL_LEVELS[detail]}
To          : {to}
From        : {from_name}

Email structure (follow exactly):
1. Subject: [concise, action-oriented subject line]
2. Greeting
3. Opening: 1–2 sentences — context and purpose
4. Key Findings / Executive Summary: bullet points per detail level
5. Risks / Concerns (if any): 1–3 items, omit if not applicable
6. Recommended Actions / Next Steps: 2–3 clear, owner-assignable actions
7. Closing sentence
8. Sign-off: [Name] | [Title]

Rules:
- Tone: executive, data-driven, action-oriented. No fluff.
- Use numbers and metrics wherever possible.
- Detect whether the document is the first run of the reporting period or a subsequent daily update.
{additional_rules}
- Output ONLY the email — no preamble, no explanation.

Document content:
{content}"""

    # ── Summarize ────────────────────────────────────────────────────────────

    def summarize(
        self,
        content: str,
        to: str,
        from_name: str,
        report_type: str,
        detail: str,
        lang: str,
    ) -> str:
        if len(content) > 100_000:
            print("⚠️  Tài liệu dài, chỉ lấy 100,000 ký tự đầu.")
            content = content[:100_000]

        prompt = self._build_prompt(content, to, from_name, report_type, detail, lang)

        print("🤖 Đang gọi LLM...", flush=True)
        response = self.llm.invoke(prompt)

        if isinstance(response, str):
            return response.strip()
        return response.content.strip()

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(
        self,
        file: str,
        to: str,
        from_email: str,
        from_name: str = "[Your Name & Title]",
        report_type: str = "weekly",
        detail: str = "concise",
        lang: str = "vi",
        attach_file: bool = True,
        output: Optional[str] = None,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
        model_name: Optional[str] = None,
    ) -> str:
        file_path = Path(file)
        if not file_path.exists():
            sys.exit(f"❌ Không tìm thấy file: {file}")

        print(f"📂 Đọc file: {file_path.name}")
        content, file_type = self.load_document(file_path)
        print(f"✅ Đọc thành công ({file_type}, {len(content):,} ký tự)")

        # 1. AI tóm tắt
        email_text = self.summarize(content, to, from_name, report_type, detail, lang)

        # 2. In ra terminal
        result = self._format_output(email_text, file)
        print(result)

        # 3. Lưu file nếu cần
        if output:
            Path(output).write_text(result, encoding="utf-8")
            print(f"💾 Đã lưu plain text: {output}")

        # 4. Tạo Gmail draft
        create_gmail_draft(
            email_text=email_text,
            source_file=file,
            to=to,
            from_email=from_email,
            report_type=REPORT_TYPES[report_type],
            attach_file=attach_file,
            credentials_path=credentials_path,
            token_path=token_path,
        )

        return email_text

    def _format_output(self, email_text: str, file_path: str) -> str:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        sep = "─" * 60
        return (
            f"\n{sep}\n"
            f"  📧 C-LEVEL SUMMARY EMAIL\n"
            f"  Nguồn : {file_path}\n"
            f"  Tạo lúc: {now}\n"
            f"{sep}\n\n"
            f"{email_text}\n\n"
            f"{sep}\n"
        )


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Agent tóm tắt MD/PDF → Gmail draft HTML đẹp + attach file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python agent_summary.py --file report.md --to ceo@company.com --from-email me@company.com
  python agent_summary.py --file report.pdf --to "ceo@co.com,cfo@co.com" --type financial --detail detailed
  python agent_summary.py --file notes.md --to boss@co.com --from-email me@co.com --lang en --no-attach
        """,
    )
    parser.add_argument("--file",         required=True,                            help="File .md / .txt / .pdf")
    parser.add_argument("--to",           required=True,                            help="Email người nhận (có thể nhiều, cách nhau bằng dấu phẩy)")
    parser.add_argument("--from-email",   required=True,                            help="Gmail của bạn (dùng để tạo draft)")
    parser.add_argument("--from-name",    default="[Your Name & Title]",            help="Tên & chức vụ hiển thị trong email")
    parser.add_argument("--model",        default=None,                             help="Tên model LLM")
    parser.add_argument("--type",         choices=REPORT_TYPES.keys(), default="weekly",   help="Loại báo cáo")
    parser.add_argument("--detail",       choices=DETAIL_LEVELS.keys(), default="concise", help="Độ chi tiết")
    parser.add_argument("--lang",         choices=["vi", "en"],         default="vi",      help="Ngôn ngữ email")
    parser.add_argument("--no-attach",    action="store_true",                      help="Không attach file gốc vào draft")
    parser.add_argument("--output",       default=None,                             help="Lưu plain text ra file")
    parser.add_argument("--credentials",  default="credentials.json",               help="Đường dẫn credentials.json")
    parser.add_argument("--token",        default="token.json",                     help="Đường dẫn lưu token")
    return parser.parse_args()


def main():
    args = parse_args()
    agent = SummaryEmailAgent(model_name=args.model)
    agent.run(
        file=args.file,
        to=args.to,
        from_email=args.from_email,
        from_name=args.from_name,
        report_type=args.type,
        detail=args.detail,
        lang=args.lang,
        attach_file=not args.no_attach,
        output=args.output,
        credentials_path=args.credentials,
        token_path=args.token,
    )


if __name__ == "__main__":
    main()
