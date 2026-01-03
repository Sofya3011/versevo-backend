import os
import hashlib
from typing import Optional
from langdetect import detect, LangDetectException
from .config import settings

os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(settings.BOOKS_FOLDER, exist_ok=True)

def detect_language_safe(text: str) -> str:
    """Безопасное определение языка"""
    if not text or len(text.strip()) < 10:
        return "en"
    try:
        return detect(text)
    except LangDetectException:
        # Эвристика по символам
        cyrillic_chars = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
        latin_chars = sum(1 for char in text if char.isalpha() and char.isascii())
        return "ru" if cyrillic_chars > latin_chars and cyrillic_chars > 10 else "en"
    except Exception:
        return "unknown"

def save_upload_file(upload_file, destination: str):
    """Сохранение загруженного файла"""
    with open(destination, "wb") as buffer:
        buffer.write(upload_file.file.read())

def calculate_text_hash(text: str) -> str:
    """Вычисление хэша текста для кэширования"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def format_file_size(size_bytes: int) -> str:
    """Форматирование размера файла"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"
