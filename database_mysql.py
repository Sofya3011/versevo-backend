# database_mysql.py - Подключение к MySQL
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# MySQL конфигурация
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "versevo")

# Формируем URL для MySQL
DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# Если нет MySQL, используем SQLite для локальной разработки
if not all([MYSQL_USER, MYSQL_HOST, MYSQL_DATABASE]):
    DATABASE_URL = "sqlite:///./versevo_mysql.db"
    print("⚠️ Используем SQLite (MySQL не настроен)")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={
        'charset': 'utf8mb4',
        'connect_timeout': 10
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_mysql_connection():
    """Проверка подключения к MySQL"""
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        print("✅ Подключение к MySQL успешно")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к MySQL: {e}")
        print(f"📌 URL: {DATABASE_URL.replace(MYSQL_PASSWORD, '***')}")
        return False
