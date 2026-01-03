import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    DEEPL_AUTH_KEY = os.getenv("DEEPL_AUTH_KEY")
    HF_API_KEY = os.getenv("HF_API_KEY")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    
    # App Settings
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/versevo")
    
    # Redis/Celery
    CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/1")
    
    # Storage
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    BOOKS_FOLDER = os.getenv("BOOKS_FOLDER", "books")
    
    # S3 (опционально)
    S3_ENDPOINT = os.getenv("S3_ENDPOINT")
    S3_KEY = os.getenv("S3_KEY")
    S3_SECRET = os.getenv("S3_SECRET")
    S3_BUCKET = os.getenv("S3_BUCKET", "versevo-audio")
    
    # AI Services
    DEEPL_API_URL = os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
    TTS_MODE = os.getenv("TTS_MODE", "coqui")


settings = Settings()
