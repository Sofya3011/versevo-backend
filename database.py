import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

# Получаем URL из Railway (он дает postgresql://, нам нужно postgresql+asyncpg://)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    # Fallback для локальной разработки (обязательно укажи asyncpg)
    DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/versevo"

# Создаем асинхронный движок
# pool_pre_ping проверяет живое ли соединение перед использованием
engine = create_async_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    echo=False # Поставь True для отладки SQL запросов
)

# Асинхронная фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

# Асинхронная функция для получения сессии БД (Dependency Injection)
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
