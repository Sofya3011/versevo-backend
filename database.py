# database.py - АСИНХРОННАЯ ВЕРСИЯ (без databases)
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ВАША СТРОКА ПОДКЛЮЧЕНИЯ
DATABASE_URL = "postgresql://postgres:BQIGEvhzTcTvyCSYqzLtcMOMjzlVjUQg@shinkansen.proxy.rlwy.net:48342/railway"

# Для asyncpg нужно использовать asyncpg://
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

logger.info(f"🔗 Подключаемся к PostgreSQL (асинхронно)")

# Создаем асинхронный engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True
)

# Создаем асинхронную сессию
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# Dependency для получения асинхронной сессии БД
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
