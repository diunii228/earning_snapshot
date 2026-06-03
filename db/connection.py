"""
Kết nối PostgreSQL qua asyncpg.
Cấu hình: DATABASE_URL trong .env (postgresql://user:pass@host:port/dbname).
"""
import logging
from typing import Optional

import asyncpg

from utils.setting import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Lấy connection pool (tạo nếu chưa có)."""
    global _pool
    if _pool is not None:
        return _pool
    settings = get_settings()
    url = settings.database_url
    if not url:
        raise ValueError(
            "DATABASE_URL chưa cấu hình. Thêm vào .env: DATABASE_URL=postgresql://user:pass@host:5432/dbname"
        )
    # asyncpg cần dsn dạng postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    _pool = await asyncpg.create_pool(
        url,
        min_size=1,
        max_size=10,
        command_timeout=60,
        ssl="disable",
    )
    logger.info("Database pool created")
    return _pool


async def close_pool() -> None:
    """Đóng pool khi thoát."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")
