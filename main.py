# main.py (в корне проекта - ЕДИНСТВЕННЫЙ main.py)
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import os
import sys
import base64
import uuid
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Создаем директории
UPLOAD_FOLDER = "uploads"
BOOKS_FOLDER = "books"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BOOKS_FOLDER, exist_ok=True)

# Создаем приложение
app = FastAPI(
    title="Versevo Backend API",
    description="Modern document reader with AI features",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Статические файлы
try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
    app.mount("/books", StaticFiles(directory=BOOKS_FOLDER), name="books")
    logger.info("✅ Static files mounted")
except Exception as e:
    logger.error(f"❌ Error mounting static files: {e}")

# Модели запросов
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

# Временное хранилище
documents_db = []
current_id = 1

def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Извлечение текста из файлов"""
    try:
        if file_type == 'pdf':
            import fitz
            text = []
            doc = fitz.open(file_path)
            for page in doc:
                text.append(page.get_text())
            doc.close()
            return "\n\n".join(text)
        elif file_type in ['docx', 'doc']:
            import docx
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

def detect_language_safe(text: str) -> str:
    """Определение языка"""
    if not text or len(text.strip()) < 10:
        return "en"
    try:
        from langdetect import detect
        return detect(text)
    except:
        return "en"

@app.on_event("startup")
async def startup_event():
    """При запуске"""
    port = os.getenv("PORT", "8000")
    logger.info(f"🚀 Starting Versevo Backend on port {port}")
    logger.info(f"📁 Current directory: {os.getcwd()}")
    logger.info(f"📂 Files: {os.listdir('.')}")

@app.get("/")
async def root():
    """Корневой эндпоинт"""
    logger.info("📍 Root endpoint accessed")
    return {
        "message": "Versevo Backend API", 
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "health": "/api/flutter/health",
            "upload": "/documents/upload-base64 (POST)",
            "documents": "/documents (GET)"
        }
    }

@app.get("/api/flutter/health")
async def health_check():
    """Health check для Railway"""
    logger.info("❤️ Health check endpoint accessed")
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/health")
async def health_check_alt():
    """Альтернативный health check"""
    return {"status": "healthy", "service": "versevo-backend"}

@app.post("/documents/upload-base64")
async def upload_document_base64(request: dict):
    """Загрузка документа в base64"""
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
        file_path = f"{UPLOAD_FOLDER}/{file_id}.{file_extension}"
        
        with open(file_path, "wb") as f:
            f.write(content_bytes)

        # Извлекаем текст
        content_str = extract_text_from_file(file_path, file_extension)
        
        # Определяем язык
        language = detect_language_safe(content_str)
        
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
            "metadata": {
                "word_count": len(content_str.split()),
                "char_count": len(content_str),
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
    """Получение всех документов"""
    return documents_db

@app.get("/documents/{document_id}")
async def get_document(document_id: int):
    """Получение документа по ID"""
    for doc in documents_db:
        if doc["id"] == document_id:
            return doc
    raise HTTPException(status_code=404, detail="Document not found")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: int):
    """Удаление документа"""
    global documents_db
    initial_length = len(documents_db)
    documents_db = [doc for doc in documents_db if doc["id"] != document_id]
    
    if len(documents_db) == initial_length:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted"}

@app.post("/analyze")
async def analyze_document(request: AnalysisRequest):
    """Анализ документа"""
    document = next((doc for doc in documents_db if doc["id"] == request.document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    analysis_result = {
        "summary": f"Документ '{document['filename']}'. Содержит {len(document['content'].split())} слов.",
        "language": document["language"],
        "word_count": len(document["content"].split()),
        "reading_time": f"{max(1, len(document['content'].split()) // 200)} минут",
        "complexity": "Средняя" if len(document['content'].split()) > 1000 else "Простая"
    }
    
    return analysis_result

@app.post("/translate")
async def translate_text(request: TranslationRequest):
    """Перевод текста"""
    return {
        "original_text": request.text,
        "translated_text": f"[{request.style} перевод]: {request.text}",
        "source_language": request.source_language,
        "target_language": request.target_language,
        "style": request.style
    }

# Дополнительные простые эндпоинты для Flutter
@app.post("/api/flutter/upload")
async def flutter_upload(file: UploadFile = File(...), user_id: Optional[int] = Form(None)):
    """Загрузка файла из Flutter"""
    try:
        # Простая заглушка
        return {
            "success": True,
            "message": "File uploaded successfully",
            "filename": file.filename,
            "content_type": file.content_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/flutter/documents")
async def get_flutter_documents():
    """Документы для Flutter"""
    return {
        "documents": documents_db,
        "count": len(documents_db)
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
