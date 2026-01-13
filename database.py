# database.py
import os
from typing import Optional
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from contextlib import asynccontextmanager
import databases

# Получаем URL из переменных окружения Railway
DATABASE_URL = os.getenv("DATABASE_URL")

# Если Railway предоставляет URL с postgres://, меняем на postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Для асинхронного подключения
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1) if DATABASE_URL else None

# Создаем движок для асинхронной работы
engine = create_async_engine(ASYNC_DATABASE_URL, echo=True, future=True)

# Для синхронных операций (если нужно)
sync_engine = create_engine(DATABASE_URL) if DATABASE_URL else None

# Создаем фабрику сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Базовый класс для моделей
Base = declarative_base()

# databases для простых запросов
database = databases.Database(ASYNC_DATABASE_URL) if ASYNC_DATABASE_URL else None

# Dependency для FastAPI
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Менеджер контекста
@asynccontextmanager
async def get_db_context():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    """Инициализация базы данных (создание таблиц)"""
    async with engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)
    print("✅ База данных инициализирована")

async def close_db():
    """Закрытие соединений с БД"""
    await engine.dispose()
    if database:
        await database.disconnect()
