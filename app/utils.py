import os
from .config import settings
from langdetect import detect, LangDetectException

os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(settings.BOOKS_FOLDER, exist_ok=True)

def detect_language_safe(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"

def save_upload_file(upload_file, destination: str):
    with open(destination, "wb") as buffer:
        buffer.write(upload_file.file.read())
