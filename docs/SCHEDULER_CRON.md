# Hướng dẫn lên lịch chạy Daily Crawl

## 1. Crontab (chạy crawl mỗi ngày)

Ví dụ chạy lúc 6:00 sáng mỗi ngày, từ thư mục project và dùng venv:

```bash
# Mở crontab
crontab -e

# Thêm dòng (sửa đường dẫn cho đúng máy bạn)
0 6 * * * cd /Users/vutan/Techcombank/agent-competitor && .venv/bin/python main.py crawl >> logs/crawl.log 2>&1
```

Tạo thư mục log nếu chưa có:

```bash
mkdir -p /Users/vutan/Techcombank/agent-competitor/logs
```

**Lưu ý**: Cron dùng môi trường shell mặc định. Cần đảm bảo `.env` (và `DATABASE_URL`) được load. Có thể gọi qua wrapper script:

```bash
#!/bin/bash
# scripts/run_crawl.sh
cd /Users/vutan/Techcombank/agent-competitor
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python main.py crawl
```

Rồi trong crontab:

```bash
0 6 * * * /Users/vutan/Techcombank/agent-competitor/scripts/run_crawl.sh >> /Users/vutan/Techcombank/agent-competitor/logs/crawl.log 2>&1
```

---

## 2. Chạy report sau khi crawl (tùy chọn)

- **Cách 1**: Cùng cron, chạy report ngay sau crawl (cách vài phút để crawl kịp xong):

```bash
0 6 * * * cd /path/to/agent-competitor && .venv/bin/python main.py crawl
30 6 * * * cd /path/to/agent-competitor && .venv/bin/python main.py report
```

- **Cách 2**: Chạy report tay khi cần: `python main.py report`

---

## 3. Trước khi dùng cron

1. **PostgreSQL**: Dùng Docker (trong thư mục project):

```bash
docker compose up -d
```

   - **pgAdmin có sẵn**: Trong pgAdmin, thêm Server mới → Connection: Host `localhost`, Port `5432` (nếu container agent-competitor dùng 5432; nếu trùng với Postgres cũ thì trong docker-compose đổi thành `"5433:5432"` và dùng port `5433`), Username `postgres`, Password `postgres`, Database `agent_competitor`.

   Trong `.env` đặt (đúng với docker-compose):

```env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/agent_competitor
```

2. **Migration DB**: Chạy một lần để tạo bảng (dùng Python, không cần `psql`):

```bash
python -m db.run_migration
```

3. **Biến môi trường**: Trong `.env` có `DATABASE_URL=postgresql://user:pass@host:5432/dbname` (và các API key LLM nếu dùng).

4. **Test tay**:

```bash
source .venv/bin/activate
python main.py crawl
python main.py report
```
