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

# Локальные импорты
from .db import Base, engine, get_db
from .flutter_endpoints import router as flutter_router
from .utils import detect_language_safe
from .config import settings
from sqlalchemy.orm import Session

# Создаем таблицы в БД
Base.metadata.create_all(bind=engine)

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

# Подключаем Flutter роутер
app.include_router(flutter_router)

# Монтирование статических файлов
os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(settings.BOOKS_FOLDER, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_FOLDER), name="uploads")
app.mount("/books", StaticFiles(directory=settings.BOOKS_FOLDER), name="books")

# Модели запросов/ответов
class DocumentCreate(BaseModel):
    filename: str
    content: str

class DocumentResponse(BaseModel):
    id: int
    filename: str
    content: str
    language: str
    file_type: str
    file_size: int
    created_at: str
    metadata: Dict[str, Any]

class Chapter(BaseModel):
    title: str
    start_position: int
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

def detect_chapters(text: str) -> List[Dict]:
    """Автоматическое определение глав в тексте"""
    import re
    chapters = []
    
    # Паттерны для заголовков глав
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
            
        # Проверяем, является ли строка заголовком главы
        is_chapter = False
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                is_chapter = True
                break
                
        if is_chapter:
            # Сохраняем предыдущую главу
            if current_chapter:
                current_chapter['content'] = current_chapter['content'].strip()
                chapters.append(current_chapter)
            
            # Начинаем новую главу
            current_chapter = {
                'title': line,
                'start_position': sum(len(lines[j]) + 1 for j in range(i)),
                'content': ''
            }
        elif current_chapter:
            current_chapter['content'] += line + '\n'
    
    # Добавляем последнюю главу
    if current_chapter:
        current_chapter['content'] = current_chapter['content'].strip()
        chapters.append(current_chapter)
    
    # Если глав не найдено, создаем одну главу
    if not chapters:
        chapters.append({
            'title': 'Основной текст',
            'start_position': 0,
            'content': text
        })
    
    return chapters

@app.get("/")
async def root():
    return {"message": "Versevo Backend API", "version": "2.0.0"}

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Railway"""
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

    # Генерируем расширенный анализ
    analysis_result = {
        "summary": f"Анализ документа '{document['filename']}'. Содержит {len(document['content'])} символов, {len(document['content'].split())} слов.",
        "language": document["language"],
        "char_count": len(document["content"]),
        "word_count": len(document["content"].split()),
        "chapter_count": len(document.get("chapters", [])),
        "reading_time": f"{max(1, len(document['content'].split()) // 200)} минут",
        "complexity": "Средняя" if len(document['content'].split()) > 1000 else "Простая",
        "key_themes": ["Литература", "Образование", "Познание"],
        "sentiment": "Нейтральный",
        "persons": [
            {"name": "Основной персонаж", "count": 5, "importance": "высокая"},
            {"name": "Второстепенный персонаж", "count": 3, "importance": "средняя"}
        ],
        "visuals": {
            "wordcloud": "/static/wordcloud.png",
            "topwords": "/static/topwords.png",
        }
    }
    
    return analysis_result

@app.post("/translate")
async def translate_text(request: TranslationRequest):
    """Перевод текста"""
    # Временная реализация - в продакшене подключить реальный переводчик
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
