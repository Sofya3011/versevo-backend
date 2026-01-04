# main.py - Versevo Backend API (исправленный)
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import os
import sys
import base64
import uuid
import json
from datetime import datetime
import requests

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# FastAPI
app = FastAPI(
    title="Versevo Backend API",
    description="Modern document reader with translation and AI features",
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

# Директории
UPLOAD_FOLDER = "uploads"
BOOKS_FOLDER = "books"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BOOKS_FOLDER, exist_ok=True)

try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
    app.mount("/books", StaticFiles(directory=BOOKS_FOLDER), name="books")
    logger.info("✅ Static files mounted")
except Exception as e:
    logger.error(f"❌ Error mounting static files: {e}")

# Модели
class TranslateRequest(BaseModel):
    text: str
    target_language: str = "ru"
    source_language: Optional[str] = None
    style: str = "artistic"

class DocumentUploadRequest(BaseModel):
    filename: str
    file_data: str
    file_size: int

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "general"

# Глобальные настройки
HF_API_KEY = os.getenv("HF_API_KEY", "demo_key")
documents_store: Dict[int, Dict[str, Any]] = {}
current_doc_id = 1

# Утилиты
def extract_text_from_file(file_path: str, file_type: str) -> str:
    try:
        if file_type == "pdf":
            import fitz
            text = []
            doc = fitz.open(file_path)
            for page in doc:
                text.append(page.get_text())
            doc.close()
            return "\n\n".join(text)
        elif file_type in ["docx", "doc"]:
            import docx
            doc = docx.Document(file_path)
            return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        elif file_type == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        else:
            return ""
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        return ""

def detect_language_safe(text: str) -> str:
    if not text or len(text.strip()) < 10:
        return "en"
    try:
        from langdetect import detect
        return detect(text)
    except:
        return "en"

def detect_chapters(text: str) -> List[Dict]:
    chapters = []
    chunk_size = 5000
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i+chunk_size]
        if chunk.strip():
            chapters.append({
                "title": f"Часть {len(chapters)+1}",
                "start_position": i,
                "content": chunk
            })
    return chapters

def translate_with_huggingface(text: str, source_lang: str, target_lang: str) -> str:
    try:
        lang_codes = {
            "ru": "rus_Cyrl", "en": "eng_Latn", "de": "deu_Latn",
            "fr": "fra_Latn", "es": "spa_Latn", "it": "ita_Latn",
            "zh": "zho_Hans", "ar": "arb_Arab", "uk": "ukr_Cyrl",
            "pl": "pol_Latn", "ja": "jpn_Jpan", "ko": "kor_Hang",
        }
        if source_lang not in lang_codes or target_lang not in lang_codes:
            raise ValueError("Unsupported language")

        api_url = "https://api-inference.huggingface.co/models/facebook/nllb-200-distilled-600M"
        headers = {"Authorization": f"Bearer {HF_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "inputs": text,
            "parameters": {"src_lang": lang_codes[source_lang], "tgt_lang": lang_codes[target_lang]}
        }
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get("translation_text", text)
        return text
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

# Endpoints
@app.get("/")
async def root():
    return {"message": "Versevo Backend API", "version": "2.0.0", "status": "running"}

@app.get("/api/flutter/health")
async def health_check():
    return {"status": "healthy", "service": "versevo-backend", "timestamp": datetime.now().isoformat()}

@app.get("/api/health")
async def health_check_alt():
    return {"status": "healthy", "service": "versevo-backend"}

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), user_id: Optional[int] = Form(None)):
    global current_doc_id
    try:
        file_id = str(uuid.uuid4())
        ext = file.filename.split(".")[-1].lower()
        path = f"{UPLOAD_FOLDER}/{file_id}.{ext}"
        content = await file.read()
        with open(path, "wb") as f:
            f.write(content)

        text = extract_text_from_file(path, ext)
        if not text.strip():
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст")

        lang = detect_language_safe(text)
        chapters = detect_chapters(text)

        document = {
            "id": current_doc_id,
            "filename": file.filename,
            "content": text,
            "language": lang,
            "file_type": ext,
            "file_size": len(content),
            "file_path": path,
            "user_id": user_id or 1,
            "word_count": len(text.split()),
            "char_count": len(text),
            "chapter_count": len(chapters),
            "reading_time_minutes": max(1, len(text.split()) // 200),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "chapters": chapters,
            "content_preview": text[:200] + "..." if len(text) > 200 else text
        }
        documents_store[current_doc_id] = document
        current_doc_id += 1
        return document
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: dict):
    global current_doc_id
    try:
        filename = request.get("filename", "unknown.txt")
        file_data = request.get("file_data", "")
        file_size = request.get("file_size", 0)
        if not file_data:
            raise HTTPException(status_code=400, detail="No file data provided")

        content_bytes = base64.b64decode(file_data)
        file_id = str(uuid.uuid4())
        ext = filename.split(".")[-1].lower()
        path = f"{UPLOAD_FOLDER}/{file_id}.{ext}"
        with open(path, "wb") as f:
            f.write(content_bytes)

        text = extract_text_from_file(path, ext)
        if not text.strip():
            text = "⚠️ Не удалось извлечь текст, файл сохранён."

        lang = detect_language_safe(text)
        chapters = detect_chapters(text)

        document = {
            "id": current_doc_id,
            "filename": filename,
            "content": text,
            "language": lang,
            "file_type": ext,
            "file_size": file_size,
            "file_path": path,
            "user_id": 1,
            "word_count": len(text.split()),
            "char_count": len(text),
            "chapter_count": len(chapters),
            "reading_time_minutes": max(1, len(text.split()) // 200),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "chapters": chapters,
            "content_preview": text[:200]
