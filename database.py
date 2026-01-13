# database.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

# ВАША СТРОКА ПОДКЛЮЧЕНИЯ
DATABASE_URL = "postgresql://postgres:BQIGEvhzTcTvyCSYqzLtcMOMjzlVjUQg@shinkansen.proxy.rlwy.net:48342/railway"

# Если есть переменная окружения - используем её
if os.getenv('DATABASE_URL'):
    DATABASE_URL = os.getenv('DATABASE_URL')
    logger.info(f"📦 Используем DATABASE_URL из переменных окружения")

# Fix for Railway: ensure it's postgresql://
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")

logger.info(f"🔗 Настраиваем подключение к PostgreSQL...")

try:
    # УПРОЩЕННЫЙ engine - без проверки при инициализации
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,  # Переподключаемся каждые 5 минут
        echo=False,
        # Убираем connect_args для Railway
    )
    
    # НЕ тестируем подключение здесь!
    # FastAPI должен запуститься даже если БД временно недоступна
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    logger.info("✅ SQLAlchemy engine создан (отложенное подключение)")
    
except Exception as e:
    logger.error(f"❌ Ошибка создания SQLAlchemy engine: {e}")
    # Fallback: создаем memory SQLite для тестов
    engine = create_engine("sqlite:///:memory:", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    logger.warning("⚠️ Используем SQLite in-memory как fallback")

# Dependency для получения сессии БД (с отложенным подключением)
def get_db():
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")
        # Возвращаем None если БД недоступна
        yield None
    finally:
        if db:
            db.close()

# Функция для проверки подключения (отдельно)
def test_db_connection():
    """Проверяет подключение к БД, возвращает True/False"""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
            return True
    except Exception as e:
        logger.warning(f"⚠️ БД недоступна: {e}")
        return False
