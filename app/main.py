from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import asyncio
import base64
# Используем langdetect но без LangDetectError
from langdetect import detect

app = FastAPI(title="Versevo Backend API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class TranslationRequest(BaseModel):
    text: str
    source_language: str
    target_language: str
    style: str = "artistic"

class AnalyzeRequest(BaseModel):
    document_id: int

# Простая база данных в памяти (замените на реальную БД)
documents_db = []
current_id = 1

def detect_language_safe(text: str) -> str:
    """Безопасное определение языка с обработкой ошибок"""
    if not text or len(text.strip()) < 10:
        return "en"
    
    try:
        # Пробуем определить язык
        detected_lang = detect(text)
        return detected_lang
    except Exception as e:
        # Если langdetect не работает, используем простую эвристику
        logging.warning(f"Language detection failed: {e}, using fallback")
        
        # Простая эвристика по символам
        cyrillic_chars = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
        latin_chars = sum(1 for char in text if char.isalpha() and char.isascii())
        
        if cyrillic_chars > latin_chars and cyrillic_chars > 10:
            return "ru"
        else:
            return "en"

@app.get("/")
async def root():
    return {"message": "Versevo Backend API"}

@app.post("/documents/upload-base64")
async def upload_document_base64(request: dict):
    global current_id
    
    try:
        filename = request.get("filename", "unknown")
        file_data = request.get("file_data", "")
        file_size = request.get("file_size", 0)
        
        # Декодируем base64
        content_bytes = base64.b64decode(file_data)
        content_str = content_bytes.decode('utf-8', errors='ignore')
        
        # Определяем язык
        language = detect_language_safe(content_str)
        
        # Определяем тип файла
        file_type = filename.split('.')[-1].lower() if '.' in filename else "txt"
        
        document = {
            "id": current_id,
            "filename": filename,
            "content": content_str,
            "language": language,
            "file_type": file_type
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

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), filename: str = None):
    global current_id
    
    try:
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Определяем язык
        language = detect_language_safe(content_str)
        
        # Определяем тип файла
        file_type = file.filename.split('.')[-1].lower() if file.filename else "txt"
        
        document = {
            "id": current_id,
            "filename": filename or file.filename,
            "content": content_str,
            "language": language,
            "file_type": file_type
        }
        
        documents_db.append(document)
        current_id += 1
        
        return document
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: int):
    global documents_db
    initial_length = len(documents_db)
    documents_db = [doc for doc in documents_db if doc["id"] != document_id]
    
    if len(documents_db) == initial_length:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted"}

@app.post("/analyze")
async def analyze_document(request: AnalyzeRequest):
    # Имитация анализа документа
    document = next((doc for doc in documents_db if doc["id"] == request.document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Генерируем фиктивные результаты анализа
    analysis_result = {
        "summary": f"Анализ документа '{document['filename']}'. Содержит {len(document['content'])} символов.",
        "language": document["language"],
        "char_count": len(document["content"]),
        "word_count": len(document["content"].split()),
        "persons": [
            {"name": "Персонаж 1", "count": 5},
            {"name": "Персонаж 2", "count": 3}
        ],
        "visuals": {
            "wordcloud": "/static/wordcloud.png",
            "topwords": "/static/topwords.png",
            "graph": "/static/graph.png"
        }
    }
    
    return analysis_result

@app.post("/translate")
async def translate_text(request: TranslationRequest):
    # Имитация перевода
    translated_text = f"[{request.style} перевод с {request.source_language} на {request.target_language}]: {request.text}"
    
    return {
        "original_text": request.text,
        "translated_text": translated_text,
        "source_language": request.source_language,
        "target_language": request.target_language,
        "style": request.style
    }

@app.post("/translate/nllb")
async def translate_nllb(request: dict):
    # Специфичный endpoint для NLLB перевода
    text = request.get("text", "")
    source = request.get("source", "en")
    target = request.get("target", "ru")
    
    translated_text = f"[NLLB перевод с {source} на {target}]: {text}"
    
    return {"translated": translated_text}

@app.post("/audio/generate")
async def generate_audio(request: dict):
    # Имитация генерации аудио
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

