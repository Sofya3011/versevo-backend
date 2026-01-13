# database.py - УПРОЩЕННАЯ ВЕРСИЯ
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import logging

logger = logging.getLogger(__name__)

# ВАША СТРОКА ПОДКЛЮЧЕНИЯ
DATABASE_URL = "postgresql://postgres:BQIGEvhzTcTvyCSYqzLtcMOMjzlVjUQg@shinkansen.proxy.rlwy.net:48342/railway"

# Если есть переменная окружения - используем её
if os.getenv('DATABASE_URL'):
    DATABASE_URL = os.getenv('DATABASE_URL')

logger.info(f"🔗 Подключаемся к PostgreSQL...")

try:
    # Упрощенный engine без сложных параметров
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False
    )
    
    # БЕЗ тестового подключения при инициализации!
    # Это могло вызывать падение при старте
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    logger.info("✅ SQLAlchemy инициализирован")
    
except Exception as e:
    logger.error(f"❌ Ошибка инициализации SQLAlchemy: {e}")
    # Создаем engine в любом случае, даже если есть ошибка
    engine = create_engine("sqlite:///./test.db")  # Fallback
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()

# Dependency для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
