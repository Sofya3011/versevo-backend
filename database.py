# database.py - БЕЗ databases
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Строка подключения Railway
DATABASE_URL = os.getenv('DATABASE_URL', 
    "postgresql://postgres:BQIGEvhzTcTvyCSYqzLtcMOMjzlVjUQg@shinkansen.proxy.rlwy.net:48342/railway"
)

# Для psycopg2
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")

logger.info("🔗 Подключение к PostgreSQL...")

# Создаем engine
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False  # Поставьте False для продакшена
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
