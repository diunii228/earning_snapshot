"""
gmail_sender.py
===============
Module tạo Gmail draft với HTML format đẹp và attach file gốc.

Setup một lần:
    1. Vào https://console.cloud.google.com → tạo project
    2. Enable Gmail API
    3. Tạo OAuth2 credentials → download credentials.json
    4. pip install google-auth google-auth-oauthlib google-api-python-client

Lần đầu chạy sẽ mở browser để đăng nhập Google, sau đó lưu token.json.
"""

import base64
import mimetypes
import os
import re
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime
from typing import Optional
from email import encoders

# Google API
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    raise ImportError(
        "Thiếu thư viện Google:\n"
        "  pip install google-auth google-auth-oauthlib google-api-python-client"
    )

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


# ─── Auth ────────────────────────────────────────────────────────────────────

def get_gmail_service(
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
):
    """Xác thực OAuth2 và trả về Gmail service."""
    creds = None

    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_path).exists():
                raise FileNotFoundError(
                    f"Không tìm thấy {credentials_path}.\n"
                    "Hướng dẫn: https://console.cloud.google.com → Gmail API → OAuth2 credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        Path(token_path).write_text(creds.to_json())
        print(f"✅ Đã lưu token xác thực: {token_path}")

    return build("gmail", "v1", credentials=creds)


# ─── HTML Template ───────────────────────────────────────────────────────────

def _email_text_to_html(email_text: str, report_type: str, source_file: str) -> str:
    """Chuyển plain text email thành HTML đẹp."""

    # Tách subject nếu có
    subject_match = re.search(r"^Subject:\s*(.+)$", email_text, re.MULTILINE)
    subject_line = subject_match.group(1).strip() if subject_match else ""
    body = re.sub(r"^Subject:\s*.+\n?", "", email_text, flags=re.MULTILINE).strip()

    # Convert bullet points và line breaks
    lines = body.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        is_bullet = stripped.startswith(("- ", "• ", "* ", "· ")) or re.match(r"^\d+\.\s", stripped)

        if is_bullet:
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = re.sub(r"^[-•*·]\s|^\d+\.\s", "", stripped)
            # Bold text trước dấu : trong bullet
            content = re.sub(r"^(\*\*(.+?)\*\*|(.+?):)", lambda m: f"<strong>{m.group(0).strip('*').rstrip(':')}</strong>:", content, count=1)
            html_lines.append(f"  <li>{content}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if not stripped:
                html_lines.append("<br>")
            else:
                # Heading detection (ALL CAPS hoặc kết thúc bằng :)
                if stripped.isupper() or (stripped.endswith(":") and len(stripped) < 60):
                    html_lines.append(f'<p class="section-heading">{stripped}</p>')
                else:
                    html_lines.append(f"<p>{stripped}</p>")

    if in_list:
        html_lines.append("</ul>")

    body_html = "\n".join(html_lines)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    font-size: 14px;
    line-height: 1.7;
    color: #1a1a1a;
    margin: 0;
    padding: 0;
    background: #f5f5f5;
  }}
  .wrapper {{
    max-width: 680px;
    margin: 24px auto;
    background: #ffffff;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  }}
  .header {{
    background: #1a1a2e;
    padding: 28px 36px;
    border-bottom: 3px solid #e8a020;
  }}
  .header-badge {{
    display: inline-block;
    background: #e8a020;
    color: #1a1a2e;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 3px;
    margin-bottom: 10px;
  }}
  .header-title {{
    color: #ffffff;
    font-size: 20px;
    font-weight: 600;
    margin: 0;
    line-height: 1.3;
  }}
  .meta-bar {{
    background: #f8f8f8;
    border-bottom: 1px solid #e8e8e8;
    padding: 12px 36px;
    font-size: 12px;
    color: #666;
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
  }}
  .meta-item strong {{ color: #1a1a1a; font-weight: 600; }}
  .body {{
    padding: 32px 36px;
  }}
  p {{
    margin: 0 0 12px 0;
    color: #2c2c2c;
  }}
  ul {{
    margin: 8px 0 16px 0;
    padding-left: 20px;
  }}
  li {{
    margin-bottom: 8px;
    color: #2c2c2c;
  }}
  .section-heading {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #888;
    margin: 24px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #ebebeb;
  }}
  strong {{ color: #1a1a1a; }}
  .footer {{
    background: #f8f8f8;
    border-top: 1px solid #e8e8e8;
    padding: 14px 36px;
    font-size: 11px;
    color: #aaa;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .footer-source {{ font-family: monospace; font-size: 10px; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <div class="header-badge">{report_type}</div>
    <p class="header-title">{subject_line or "Executive Summary"}</p>
  </div>
  <div class="meta-bar">
    <span>📅 <strong>{now}</strong></span>
    <span>📎 <strong>{Path(source_file).name}</strong></span>
  </div>
  <div class="body">
    {body_html}
  </div>
  <div class="footer">
    <span>Generated by Summary Agent</span>
    <span class="footer-source">{source_file}</span>
  </div>
</div>
</body>
</html>"""


# ─── Build MIME message ──────────────────────────────────────────────────────

def build_draft_message(
    to: str,
    from_email: str,
    subject: str,
    html_body: str,
    plain_body: str,
    attach_path: Optional[str] = None,
) -> dict:
    """Tạo MIME message với HTML + plaintext fallback + optional attachment."""
    msg = MIMEMultipart("mixed")
    msg["To"] = to
    msg["From"] = from_email
    msg["Subject"] = subject

    # HTML + plain text alternative
    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(plain_body, "plain", "utf-8"))
    alternative.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alternative)

    # Attach file gốc nếu có
    if attach_path:
        path = Path(attach_path)
        if path.exists():
            mime_type, _ = mimetypes.guess_type(str(path))
            main_type, sub_type = (mime_type or "application/octet-stream").split("/", 1)

            with open(path, "rb") as f:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=path.name,
                )
                msg.attach(part)
            print(f"📎 Đã attach file: {path.name}")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"message": {"raw": raw}}


# ─── Create Draft ────────────────────────────────────────────────────────────

def create_gmail_draft(
    email_text: str,
    source_file: str,
    to: str,
    from_email: str,
    report_type: str = "Executive Summary",
    attach_file: bool = True,
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> str:
    """
    Tạo Gmail draft từ email text đã được AI generate.

    Returns:
        draft_id (str)
    """
    # Tách subject
    subject_match = re.search(r"^Subject:\s*(.+)$", email_text, re.MULTILINE)
    subject = subject_match.group(1).strip() if subject_match else f"[{report_type}] Executive Summary"

    # Build HTML
    html_body = _email_text_to_html(email_text, report_type, source_file)

    # Plain text (bỏ subject line)
    plain_body = re.sub(r"^Subject:\s*.+\n?", "", email_text, flags=re.MULTILINE).strip()

    # Attach file gốc
    attach_path = source_file if attach_file else None

    # Build MIME
    draft_body = build_draft_message(
        to=to,
        from_email=from_email,
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
        attach_path=attach_path,
    )

    # Gọi Gmail API
    print("📧 Đang tạo draft trên Gmail...", flush=True)
    service = get_gmail_service(credentials_path, token_path)

    try:
        draft = service.users().drafts().create(userId="me", body=draft_body).execute()
        draft_id = draft["id"]
        print(f"✅ Draft đã tạo! ID: {draft_id}")
        print(f"   Mở Gmail → Drafts để xem và gửi.")
        return draft_id
    except HttpError as e:
        raise RuntimeError(f"Gmail API error: {e}") from e