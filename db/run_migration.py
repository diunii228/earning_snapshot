import asyncio
import logging
import os
import re

from utils.setting import get_settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def load_sql(path: str) -> str:
    """Đọc nguyên file SQL — GIỮ LẠI tất cả, kể cả dòng comment.
    Không strip comment ở bước này vì comment có thể nằm giữa
    quoted string và làm lệch vị trí khi split.
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def split_sql_statements(sql: str) -> list[str]:
    """
    Split SQL script thành từng statement độc lập.

    Xử lý đúng các trường hợp hay gây lỗi khi split naïve theo ';':
      - Single-quoted strings : 'it''s fine; still same string'
      - Dollar-quoted strings : $$has ; inside$$  hoặc  $body$...$body$
      - Line comments         : -- comment đến hết dòng
      - Block comments        : /* có thể chứa ; hay ' bên trong */

    Chỉ cắt tại ';' nằm NGOÀI tất cả các context trên.
    """
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # ── Line comment --  ────────────────────────────────────────────────
        if ch == '-' and sql[i:i+2] == '--':
            end = sql.find('\n', i)
            end = end + 1 if end != -1 else n
            buf.append(sql[i:end])
            i = end

        # ── Block comment /* ... */  ─────────────────────────────────────────
        elif ch == '/' and sql[i:i+2] == '/*':
            end = sql.find('*/', i + 2)
            end = end + 2 if end != -1 else n
            buf.append(sql[i:end])
            i = end

        # ── Dollar-quoted string  $$...$$ hoặc $tag$...$tag$  ───────────────
        elif ch == '$':
            # tìm closing $ để xác định tag (vd: $$, $body$)
            tag_close = sql.find('$', i + 1)
            if tag_close != -1:
                tag = sql[i:tag_close + 1]          # vd: '$$' hoặc '$body$'
                closing = sql.find(tag, tag_close + 1)
                if closing != -1:
                    end = closing + len(tag)
                    buf.append(sql[i:end])
                    i = end
                else:
                    # tag không đóng → treat as literal
                    buf.append(ch)
                    i += 1
            else:
                buf.append(ch)
                i += 1

        # ── Single-quoted string  '...'  ('' = escaped quote)  ─────────────
        elif ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2          # escaped ''
                elif sql[j] == "'":
                    j += 1          # closing quote
                    break
                else:
                    j += 1
            buf.append(sql[i:j])
            i = j

        # ── Statement terminator  ────────────────────────────────────────────
        elif ch == ';':
            stmt = ''.join(buf).strip()
            # lọc bỏ block chỉ gồm comment / whitespace
            without_comments = re.sub(r'--[^\n]*', '', stmt)
            without_comments = re.sub(r'/\*.*?\*/', '', without_comments, flags=re.DOTALL)
            if without_comments.strip():
                statements.append(stmt)
            buf = []
            i += 1

        else:
            buf.append(ch)
            i += 1

    # phần cuối file không có dấu ;
    stmt = ''.join(buf).strip()
    without_comments = re.sub(r'--[^\n]*', '', stmt)
    without_comments = re.sub(r'/\*.*?\*/', '', without_comments, flags=re.DOTALL)
    if without_comments.strip():
        statements.append(stmt)

    return statements


async def main() -> None:
    settings = get_settings()
    url = settings.database_url
    if not url:
        logger.error("Chưa cấu hình DATABASE_URL trong .env")
        raise SystemExit(1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    try:
        import asyncpg
    except ImportError:
        logger.error("Cần cài asyncpg: pip install asyncpg")
        raise SystemExit(1)

    base = os.path.dirname(os.path.abspath(__file__))
    migrations_dir = os.path.join(base, "migrations")
    if not os.path.isdir(migrations_dir):
        logger.error("Không tìm thấy thư mục %s", migrations_dir)
        raise SystemExit(1)

    sql_files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))
    if not sql_files:
        logger.error("Không có file .sql trong %s", migrations_dir)
        raise SystemExit(1)

    conn = await asyncpg.connect(url)
    try:
        for filename in sql_files:
            sql_path = os.path.join(migrations_dir, filename)
            sql = load_sql(sql_path)
            statements = split_sql_statements(sql)
            logger.info("--- %s ---", filename)
            for stmt in statements:
                try:
                    await conn.execute(stmt)
                    preview = stmt[:60].replace("\n", " ")
                    suffix = "..." if len(stmt) > 60 else ""
                    logger.info("OK: %s%s", preview, suffix)
                except Exception as e:
                    logger.error("FAIL: %s", stmt[:120].replace("\n", " "))
                    logger.error("      → %s", e)
                    raise
    finally:
        await conn.close()

    logger.info("✅ Migration xong.")


if __name__ == "__main__":
    asyncio.run(main())