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

# Настройка пути для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Пробуем импортировать из services
try:
    # Если services существует
    from services.db import Base, engine, get_db
    from services.utils import detect_language_safe
    from services.config import settings
    
    # Создаем таблицы в БД
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully")
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")
        
except ImportError:
    # Если services не существует, создаем заглушки
    print("⚠️  services module not found, using dummy implementations")
    
    class DummySettings:
        UPLOAD_FOLDER = "uploads"
        BOOKS_FOLDER = "books"
        DEBUG = True
    
    settings = DummySettings()
    
    def detect_language_safe(text: str) -> str:
        return "en"

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

# Создаем директории для файлов
os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(settings.BOOKS_FOLDER, exist_ok=True)

# Монтирование статических файлов
try:
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_FOLDER), name="uploads")
    app.mount("/books", StaticFiles(directory=settings.BOOKS_FOLDER), name="books")
    logger.info(f"✅ Static files mounted")
except Exception as e:
    logger.error(f"❌ Error mounting static files: {e}")

# Модели запросов/ответов
class DocumentCreate(BaseModel):
    filename: str
    content: str

class AnalysisRequest(BaseModel):
    document_id: int

class TranslationRequest(BaseModel):
    text: str
    source_language: str
    target_language: str
    style: str = "artistic"

# Временное хранилище (для демо)
documents_db = []
current_id = 1

def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Извлечение текста из различных форматов файлов"""
    try:
        if file_type == 'pdf':
            text = []
            doc = fitz.open(file_path)
            for page in doc:
                text.append(page.get_text())
            doc.close()
            return "\n\n".join(text)
        elif file_type in ['docx', 'doc']:
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        elif file_type == 'txt':
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        return f"Ошибка извлечения текста: {str(e)}"

def detect_chapters(text: str) -> List[Dict]:
    """Автоматическое определение глав в тексте"""
    import re
    chapters = []
    
    patterns = [
        r'^(Глава\s+\d+[.:]\s*.+)$',
        r'^(CHAPTER\s+\d+[.:]\s*.+)$',
        r'^(Часть\s+\d+[.:]\s*.+)$',
        r'^(Part\s+\d+[.:]\s*.+)$',
        r'^(\d+[.:]\s*.+)$',
        r'^([IVXLCDM]+[.:]\s*.+)$'
    ]
    
    lines = text.split('\n')
    current_chapter = None
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        is_chapter = False
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                is_chapter = True
                break
                
        if is_chapter:
            if current_chapter:
                current_chapter['content'] = current_chapter['content'].strip()
                chapters.append(current_chapter)
            
            current_chapter = {
                'title': line,
                'start_position': sum(len(lines[j]) + 1 for j in range(i)),
                'content': ''
            }
        elif current_chapter:
            current_chapter['content'] += line + '\n'
    
    if current_chapter:
        current_chapter['content'] = current_chapter['content'].strip()
        chapters.append(current_chapter)
    
    if not chapters:
        chapters.append({
            'title': 'Основной текст',
            'start_position': 0,
            'content': text
        })
    
    return chapters

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

@app.post("/documents/upload-base64")
async def upload_document_base64(request: dict):
    global current_id
    try:
        filename = request.get("filename", "unknown")
        file_data = request.get("file_data", "")
        file_size = request.get("file_size", 0)

        # Декодируем base64
        content_bytes = base64.b64decode(file_data)
        
        # Сохраняем файл
        file_id = str(uuid.uuid4())
        file_extension = filename.split('.')[-1].lower() if '.' in filename else 'txt'
        file_path = f"{settings.UPLOAD_FOLDER}/{file_id}.{file_extension}"
        
        with open(file_path, "wb") as f:
            f.write(content_bytes)

        # Извлекаем текст
        content_str = extract_text_from_file(file_path, file_extension)
        
        # Определяем язык
        language = detect_language_safe(content_str)
        
        # Определяем главы
        chapters = detect_chapters(content_str)
        
        # Создаем документ
        document = {
            "id": current_id,
            "filename": filename,
            "content": content_str,
            "language": language,
            "file_type": file_extension,
            "file_size": file_size,
            "file_path": file_path,
            "created_at": datetime.now().isoformat(),
            "chapters": chapters,
            "metadata": {
                "word_count": len(content_str.split()),
                "char_count": len(content_str),
                "chapter_count": len(chapters),
                "reading_time_minutes": max(1, len(content_str.split()) // 200)
            }
        }

        documents_db.append(document)
        current_id += 1
        
        return document

    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/documents")
async def get_documents():
    return documents_db

@app.get("/documents/{document_id}")
async def get_document(document_id: int):
    for doc in documents_db:
        if doc["id"] == document_id:
            return doc
    raise HTTPException(status_code=404, detail="Document not found")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: int):
    global documents_db
    initial_length = len(documents_db)
    documents_db = [doc for doc in documents_db if doc["id"] != document_id]
    
    if len(documents_db) == initial_length:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted"}

@app.post("/analyze")
async def analyze_document(request: AnalysisRequest):
    """Анализ документа с использованием AI"""
    document = next((doc for doc in documents_db if doc["id"] == request.document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    analysis_result = {
        "summary": f"Анализ документа '{document['filename']}'. Содержит {len(document['content'])} символов, {len(document['content'].split())} слов.",
        "language": document["language"],
        "char_count": len(document["content"]),
        "word_count": len(document["content"].split()),
        "chapter_count": len(document.get("chapters", [])),
        "reading_time": f"{max(1, len(document['content'].split()) // 200)} минут",
        "complexity": "Средняя" if len(document['content'].split()) > 1000 else "Простая",
        "key_themes": ["Литература", "Образование", "Познание"],
        "sentiment": "Нейтральный"
    }
    
    return analysis_result

@app.post("/translate")
async def translate_text(request: TranslationRequest):
    """Перевод текста"""
    translated_text = f"[{request.style} перевод с {request.source_language} на {request.target_language}]: {request.text}"
    
    return {
        "original_text": request.text,
        "translated_text": translated_text,
        "source_language": request.source_language,
        "target_language": request.target_language,
        "style": request.style
    }

@app.post("/audio/generate")
async def generate_audio(request: dict):
    """Генерация аудиоверсии"""
    document_id = request.get("document_id")
    voice = request.get("voice", "default")
    style = request.get("style", "neutral")
    
    return {
        "id": 1,
        "voice": voice,
        "style": style,
        "audio_url": f"/audio/generated_{document_id}.mp3",
        "duration": 300.0
    }

@app.get("/documents/{document_id}/chapters")
async def get_document_chapters(document_id: int):
    """Получение глав документа"""
    document = next((doc for doc in documents_db if doc["id"] == document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document.get("chapters", [])

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
