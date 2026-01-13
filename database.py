# database.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
import os
from sqlalchemy import create_engine, text  # <-- ДОБАВЬТЕ text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ВАША СТРОКА ПОДКЛЮЧЕНИЯ
DATABASE_URL = "postgresql://postgres:BQIGEvhzTcTvyCSYqzLtcMOMjzlVjUQg@shinkansen.proxy.rlwy.net:48342/railway"

# Также проверяем переменные окружения на Railway
if os.getenv('DATABASE_URL'):
    DATABASE_URL = os.getenv('DATABASE_URL')
    logger.info("✅ Используем DATABASE_URL из переменных окружения")

# Преобразуем для SQLAlchemy если нужно
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")

logger.info(f"🔗 Подключаемся к PostgreSQL")

# Создаем engine с настройками для Railway
try:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        },
        echo=False
    )
    
    # Тестируем подключение - ИСПРАВЛЕННАЯ СТРОКА
    with engine.connect() as conn:
        # БЫЛО: result = conn.execute("SELECT version()")
        # СТАЛО: используем text()
        result = conn.execute(text("SELECT version()"))  # <-- ИСПРАВЛЕНО
        logger.info(f"✅ PostgreSQL подключен: {result.fetchone()[0][:50]}...")
        
except Exception as e:
    logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
    raise

# Создаем сессию
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
