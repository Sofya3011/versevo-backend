import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    UPLOAD_FOLDER = "uploads"
    BOOKS_FOLDER = "books"
    DEEPL_AUTH_KEY = os.getenv("DEEPL_AUTH_KEY")
    DEEPL_API_URL = os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    HF_API_KEY = os.getenv("HF_API_KEY")
    TTS_MODE = os.getenv("TTS_MODE", "coqui")  # "coqui" or "elevenlabs"
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    BOOKS_FOLDER = os.getenv("BOOKS_FOLDER", "books")
    DB_PATH = os.getenv("DB_PATH", "versevo.db")
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    S3_ENDPOINT = os.getenv("S3_ENDPOINT")
    S3_KEY = os.getenv("S3_KEY")
    S3_SECRET = os.getenv("S3_SECRET")
    S3_BUCKET = os.getenv("S3_BUCKET", "versevo-audio")


settings = Settings()
