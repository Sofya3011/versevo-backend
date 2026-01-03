from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import asyncio
import base64
import uuid
import sys
import os
from datetime import datetime

# Импорты для работы с файлами
import fitz  # PyMuPDF
import docx

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Versevo Backend API",
    description="Modern document reader with AI features",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Временное хранилище (для демо)
documents_db = []
current_id = 1

def detect_language_safe(text: str) -> str:
    """Безопасное определение языка"""
    if not text or len(text.strip()) < 10:
        return "en"
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        # Эвристика по символам
        cyrillic_chars = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
        latin_chars = sum(1 for char in text if char.isalpha() and char.isascii())
        return "ru" if cyrillic_chars > latin_chars and cyrillic_chars > 10 else "en"

def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Извлечение текста из различных форматов файлов"""
    try:
        if file_type == 'pdf':
            return _extract_pdf(file_path)
        elif file_type in ['docx', 'doc']:
            return _extract_docx(file_path)
        elif file_type == 'txt':
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        else:
            # Для неизвестных форматов пробуем прочитать как текст
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        return f"Ошибка извлечения текста: {str(e)}"

def _extract_pdf(path: str) -> str:
    """Извлечение текста из PDF"""
    text = []
    try:
        doc = fitz.open(path)
        for page in doc:
            text.append(page.get_text())
        doc.close()
    except Exception as e:
        return f"Ошибка чтения PDF: {str(e)}"
    return "\n\n".join(text)

def _extract_docx(path: str) -> str:
    """Извлечение текста из DOCX"""
    try:
        doc = docx.Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        return f"Ошибка чтения DOCX: {str(e)}"

@app.on_event("startup")
async def startup_event():
    """Логирование при запуске"""
    port = os.getenv("PORT", "8000")
    logger.info(f"🚀 Starting Versevo Backend on port {port}")
    logger.info(f"📁 Current working directory: {os.getcwd()}")
    logger.info(f"📂 Files in directory: {os.listdir('.')}")

@app.get("/")
async def root():
    logger.info("📍 Root endpoint accessed")
    return {"message": "Versevo Backend API", "version": "2.0.0"}

@app.get("/api/flutter/health")
async def health_check():
    """Health check endpoint for Railway"""
    logger.info("❤️ Health check endpoint accessed")
    return {"status": "healthy", "service": "versevo-backend", "timestamp": datetime.now().isoformat()}

@app.get("/api/health")
async def health_check_alt():
    """Alternative health check endpoint"""
    return {"status": "healthy", "service": "versevo-backend"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
