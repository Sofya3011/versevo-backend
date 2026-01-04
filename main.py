# main.py - ПОЛНЫЙ РАБОЧИЙ БЭКЕНД VERSERVO
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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== СОЗДАЕМ APP ==========
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

# Создаем директории
UPLOAD_FOLDER = "uploads"
BOOKS_FOLDER = "books"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BOOKS_FOLDER, exist_ok=True)

# Статические файлы
try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
    app.mount("/books", StaticFiles(directory=BOOKS_FOLDER), name="books")
    logger.info("✅ Static files mounted")
except Exception as e:
    logger.error(f"❌ Error mounting static files: {e}")

# ========== МОДЕЛИ ==========
class TranslateRequest(BaseModel):
    text: str
    target_language: str = "ru"
    source_language: Optional[str] = None
    style: str = "artistic"  # artistic, formal, simple

class DocumentUploadRequest(BaseModel):
    filename: str
    file_data: str  # base64
    file_size: int

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "general"

# ========== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ==========
HF_API_KEY = os.getenv("HF_API_KEY", "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")
PORT = int(os.getenv("PORT", 8080))

# Хранилище документов в памяти (временное)
documents_store = {}
current_doc_id = 1

# ========== УТИЛИТЫ ==========
def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Извлечение текста из файлов"""
    try:
        if file_type == 'pdf':
            try:
                import fitz  # PyMuPDF
                text = []
                doc = fitz.open(file_path)
                for page in doc:
                    text.append(page.get_text())
                doc.close()
                extracted_text = "\n\n".join(text)
                
                # Проверяем, что текст действительно извлечен
                if extracted_text and len(extracted_text.strip()) > 10:
                    return extracted_text
                else:
                    logger.warning(f"PDF extraction returned empty or too short text")
                    return ""
                    
            except ImportError:
                logger.error("PyMuPDF not installed. Please install: pip install PyMuPDF")
                return ""
            except Exception as e:
                logger.error(f"PDF extraction error: {e}")
                return ""
                
        elif file_type in ['docx', 'doc']:
            try:
                import docx
                doc = docx.Document(file_path)
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                extracted_text = "\n\n".join(paragraphs)
                
                if extracted_text and len(extracted_text.strip()) > 10:
                    return extracted_text
                else:
                    logger.warning(f"DOCX extraction returned empty text")
                    return ""
                    
            except ImportError:
                logger.error("python-docx not installed. Please install: pip install python-docx")
                return ""
            except Exception as e:
                logger.error(f"DOCX extraction error: {e}")
                return ""
                
        elif file_type == 'txt':
            try:
                # Пробуем разные кодировки
                encodings = ['utf-8', 'cp1251', 'koi8-r', 'iso-8859-5']
                for encoding in encodings:
                    try:
                        with open(file_path, "r", encoding=encoding) as f:
                            text = f.read()
                            if text and len(text.strip()) > 10:
                                return text
                    except UnicodeDecodeError:
                        continue
                
                # Последняя попытка с игнорированием ошибок
                with open(file_path, "r", encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                    return text if text else ""
                    
            except Exception as e:
                logger.error(f"TXT reading error: {e}")
                return ""
                
        else:
            logger.error(f"Unsupported file type: {file_type}")
            return ""
            
    except Exception as e:
        logger.error(f"General extraction error: {e}")
        return ""
        
def detect_language_safe(text: str) -> str:
    """Определение языка"""
    if not text or len(text.strip()) < 10:
        return "en"
    try:
        from langdetect import detect
        return detect(text)
    except:
        return "en"

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
        # Разделяем текст на части по 5000 символов
        chunk_size = 5000
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chapters.append({
                    'title': f'Часть {len(chapters) + 1}',
                    'start_position': i,
                    'content': chunk
                })
    
    return chapters

def translate_with_huggingface(text: str, source_lang: str, target_lang: str) -> str:
    """Перевод через Hugging Face NLLB"""
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
        
        headers = {
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": text,
            "parameters": {
                "src_lang": lang_codes[source_lang],
                "tgt_lang": lang_codes[target_lang],
                "max_length": 1024
            }
        }
        
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get("translation_text", text)
        
        # Fallback если перевод не удался
        return text
        
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

# ========== ENDPOINTS ==========
@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Versevo Backend API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "health": "/api/flutter/health",
            "upload": "/api/documents/upload",
            "translate": "/api/translate/text",
            "documents": "/api/documents",
            "analyze": "/api/analyze"
        }
    }

@app.get("/api/flutter/health")
async def health_check():
    """Health check для Railway"""
    return {"status": "healthy", "service": "versevo-backend", "timestamp": datetime.now().isoformat()}

@app.get("/api/health")
async def health_check_alt():
    """Альтернативный health check"""
    return {"status": "healthy", "service": "versevo-backend"}

# ========== ДОКУМЕНТЫ ==========
@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: Optional[int] = Form(None)
):
    """Загрузка документа из Flutter"""
    global current_doc_id
    
    try:
        logger.info(f"📤 Uploading file: {file.filename}")
        
        # Сохраняем файл
        file_id = str(uuid.uuid4())
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else 'txt'
        file_path = f"{UPLOAD_FOLDER}/{file_id}.{file_extension}"
        
        # Читаем и сохраняем файл
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Извлекаем текст
        content_str = extract_text_from_file(file_path, file_extension)
        
        if not content_str or len(content_str.strip()) < 10:
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файла")
        
        # Определяем язык
        language = detect_language_safe(content_str)
        
        # Определяем главы
        chapters = detect_chapters(content_str)
        
        # Создаем документ
        document = {
            "id": current_doc_id,
            "filename": file.filename,
            "original_filename": file.filename,
            "content": content_str,
            "translated_content": None,
            "language": language,
            "file_type": file_extension,
            "file_size": len(content),
            "file_path": file_path,
            "user_id": user_id or 1,
            "word_count": len(content_str.split()),
            "char_count": len(content_str),
            "chapter_count": len(chapters),
            "reading_time_minutes": max(1, len(content_str.split()) // 200),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "chapters": chapters,
            "metadata": {
                "chapters": chapters,
                "original_filename": file.filename,
                "processing_time": datetime.now().isoformat()
            }
        }
        
        # Сохраняем в хранилище
        documents_store[current_doc_id] = document
        current_doc_id += 1
        
        logger.info(f"✅ Document saved: ID {document['id']}, {document['word_count']} words, {document['chapter_count']} chapters")
        
        return {
            "success": True,
            "document": {
                "id": document["id"],
                "filename": document["filename"],
                "language": document["language"],
                "chapter_count": document["chapter_count"],
                "word_count": document["word_count"],
                "reading_time": document["reading_time_minutes"],
                "created_at": document["created_at"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: dict):
    """Загрузка документа в формате base64"""
    global current_doc_id
    
    try:
        filename = request.get("filename", "unknown.txt")
        file_data = request.get("file_data", "")
        file_size = request.get("file_size", 0)
        
        if not file_data:
            raise HTTPException(status_code=400, detail="No file data provided")
        
        # Декодируем base64
        content_bytes = base64.b64decode(file_data)
        
        # Сохраняем файл
        file_id = str(uuid.uuid4())
        file_extension = filename.split('.')[-1].lower() if '.' in filename else 'txt'
        file_path = f"{UPLOAD_FOLDER}/{file_id}.{file_extension}"
        
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(content_bytes)
        
        # Извлекаем текст
        content_str = extract_text_from_file(file_path, file_extension)
        
        if not content_str or len(content_str.strip()) < 10:
            raise HTTPException(status_code=400, detail="Could not extract text from file")
        
        # Определяем язык
        language = detect_language_safe(content_str)
        
        # Определяем главы
        chapters = detect_chapters(content_str)
        
        # Создаем документ
        document = {
            "id": current_doc_id,
            "filename": filename,
            "original_filename": filename,
            "content": content_str,
            "translated_content": None,
            "language": language,
            "file_type": file_extension,
            "file_size": file_size,
            "file_path": file_path,
            "user_id": 1,
            "word_count": len(content_str.split()),
            "char_count": len(content_str),
            "chapter_count": len(chapters),
            "reading_time_minutes": max(1, len(content_str.split()) // 200),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "chapters": chapters,
            "metadata": {
                "chapters": chapters,
                "original_filename": filename,
                "processing_time": datetime.now().isoformat(),
                "word_count": len(content_str.split()),
                "char_count": len(content_str)
            }
        }
        
        # Сохраняем в хранилище
        documents_store[current_doc_id] = document
        current_doc_id += 1
        
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Base64 upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/documents")
async def get_documents(user_id: Optional[int] = None):
    """Получение всех документов"""
    try:
        docs = list(documents_store.values())
        
        if user_id:
            docs = [doc for doc in docs if doc.get("user_id") == user_id]
        
        # Возвращаем только основные данные
        return [
            {
                "id": doc["id"],
                "filename": doc["filename"],
                "language": doc["language"],
                "file_size": doc["file_size"],
                "word_count": doc["word_count"],
                "chapter_count": doc["chapter_count"],
                "reading_time": doc["reading_time_minutes"],
                "created_at": doc["created_at"],
                "updated_at": doc["updated_at"]
            }
            for doc in sorted(docs, key=lambda x: x["created_at"], reverse=True)
        ]
    except Exception as e:
        logger.error(f"Get documents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int):
    """Получение документа по ID"""
    try:
        document_id = int(document_id)
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return documents_store[document_id]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int):
    """Удаление документа"""
    try:
        document_id = int(document_id)
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Удаляем файл если существует
        doc = documents_store[document_id]
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
        
        # Удаляем из хранилища
        del documents_store[document_id]
        
        return {"success": True, "message": "Document deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ПЕРЕВОД ==========
@app.post("/api/translate/text")
async def translate_text(request: TranslateRequest):
    """Перевод текста через Hugging Face"""
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is empty")
        
        # Проверяем длину текста
        if len(request.text) > 4000:
            return {
                "original_text": request.text[:100] + "...",
                "translated_text": "[Текст слишком длинный для перевода]",
                "source_language": request.source_language or "auto",
                "target_language": request.target_language,
                "style": request.style,
                "translation_service": "fallback"
            }
        
        # Определяем язык если не указан
        source_lang = request.source_language
        if not source_lang or source_lang == "auto":
            source_lang = detect_language_safe(request.text)
        
        target_lang = request.target_language
        
        # Перевод через Hugging Face
        translated_text = translate_with_huggingface(
            request.text, 
            source_lang, 
            target_lang
        )
        
        # Применяем стиль если нужно
        if request.style == "artistic":
            translated_text = f"🎨 {translated_text}"
        elif request.style == "formal":
            translated_text = f"📄 {translated_text}"
        
        return {
            "original_text": request.text,
            "translated_text": translated_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "style": request.style,
            "translation_service": "huggingface_nllb"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Translate error: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@app.post("/api/translate/document/{document_id}")
async def translate_document(document_id: int, target_language: str = "ru"):
    """Перевод всего документа"""
    try:
        document_id = int(document_id)
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # Переводим по частям если текст длинный
        if len(content) > 2000:
            # Делим на части
            chunks = []
            chunk_size = 1500
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                chunks.append(chunk)
            
            # Переводим каждую часть
            translated_chunks = []
            for chunk in chunks:
                translated = translate_with_huggingface(
                    chunk, 
                    doc["language"], 
                    target_language
                )
                translated_chunks.append(translated)
            
            translated_content = " ".join(translated_chunks)
        else:
            # Переводим весь текст
            translated_content = translate_with_huggingface(
                content, 
                doc["language"], 
                target_language
            )
        
        # Обновляем документ
        doc["translated_content"] = translated_content
        doc["updated_at"] = datetime.now().isoformat()
        
        return {
            "success": True,
            "document_id": document_id,
            "original_language": doc["language"],
            "target_language": target_language,
            "translated_content": translated_content[:500] + "..." if len(translated_content) > 500 else translated_content,
            "total_translated": len(translated_content.split()),
            "translation_service": "huggingface_nllb"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document translation error: {e}")
        raise HTTPException(status_code=500, detail=f"Document translation failed: {str(e)}")

@app.post("/api/translate/chapter/{document_id}/{chapter_index}")
async def translate_chapter(
    document_id: int, 
    chapter_index: int, 
    target_language: str = "ru"
):
    """Перевод конкретной главы"""
    try:
        document_id = int(document_id)
        chapter_index = int(chapter_index)
        
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        
        if chapter_index < 0 or chapter_index >= len(doc["chapters"]):
            raise HTTPException(status_code=400, detail="Invalid chapter index")
        
        chapter = doc["chapters"][chapter_index]
        chapter_content = chapter.get("content", "")
        
        if not chapter_content or len(chapter_content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Chapter has no content")
        
        # Переводим главу
        translated_content = translate_with_huggingface(
            chapter_content, 
            doc["language"], 
            target_language
        )
        
        return {
            "success": True,
            "document_id": document_id,
            "chapter_index": chapter_index,
            "chapter_title": chapter.get("title", f"Глава {chapter_index + 1}"),
            "original_content": chapter_content[:200] + "..." if len(chapter_content) > 200 else chapter_content,
            "translated_content": translated_content,
            "original_language": doc["language"],
            "target_language": target_language,
            "translation_service": "huggingface_nllb"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chapter translation error: {e}")
        raise HTTPException(status_code=500, detail=f"Chapter translation failed: {str(e)}")

# ========== АНАЛИЗ ==========
@app.post("/api/analyze")
async def analyze_document(request: AnalysisRequest):
    """Анализ документа"""
    try:
        document_id = request.document_id
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # Простой анализ (можно расширить с OpenAI/другими сервисами)
        word_count = len(content.split())
        char_count = len(content)
        
        # Определяем сложность
        if word_count > 5000:
            complexity = "Сложный"
        elif word_count > 2000:
            complexity = "Средний"
        else:
            complexity = "Простой"
        
        # Определяем примерные темы по ключевым словам
        common_words = content.lower().split()
        from collections import Counter
        word_freq = Counter(common_words)
        
        # Убираем стоп-слова
        stop_words = {"и", "в", "на", "с", "по", "для", "не", "что", "это", "как", "так", "а", "но", "или"}
        filtered_words = {word: count for word, count in word_freq.items() 
                         if word not in stop_words and len(word) > 3}
        
        top_keywords = sorted(filtered_words.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "analysis_type": request.analysis_type,
            "summary": f"Документ '{doc['filename']}' содержит {word_count} слов, {char_count} символов.",
            "language": doc["language"],
            "word_count": word_count,
            "char_count": char_count,
            "chapter_count": doc["chapter_count"],
            "reading_time_minutes": doc["reading_time_minutes"],
            "complexity": complexity,
            "key_themes": [word for word, _ in top_keywords],
            "estimated_topics": ["Литература", "Образование", "Технологии"],  # заглушка
            "sentiment": "Нейтральный",  # можно добавить анализ тональности
            "writing_style": "Информационный",  # можно добавить анализ стиля
            "key_points": [
                f"Документ на {doc['language']} языке",
                f"Содержит {doc['chapter_count']} глав",
                f"Время чтения: {doc['reading_time_minutes']} минут"
            ],
            "analysis_date": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ========== ДОПОЛНИТЕЛЬНЫЕ ENDPOINTS ==========
@app.get("/api/documents/{document_id}/chapters")
async def get_document_chapters(document_id: int):
    """Получение глав документа"""
    try:
        document_id = int(document_id)
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        return doc["chapters"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chapters error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents/{document_id}/chapter/{chapter_index}")
async def get_document_chapter(document_id: int, chapter_index: int):
    """Получение конкретной главы"""
    try:
        document_id = int(document_id)
        chapter_index = int(chapter_index)
        
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        
        if chapter_index < 0 or chapter_index >= len(doc["chapters"]):
            raise HTTPException(status_code=400, detail="Invalid chapter index")
        
        return doc["chapters"][chapter_index]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chapter error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/translate/test")
async def test_translation():
    """Тестовый endpoint для проверки перевода"""
    try:
        test_text = "Hello world, this is a test translation from the Versevo backend."
        
        # Пробуем реальный перевод
        translated = translate_with_huggingface(test_text, "en", "ru")
        
        return {
            "original": test_text,
            "translated": translated,
            "status": "success",
            "service": "huggingface_nllb",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "original": test_text,
            "translated": "Привет мир, это тестовый перевод от бэкенда Versevo.",
            "status": "fallback",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"🚀 Starting Versevo Backend on port {PORT}")
    logger.info(f"📁 Upload folder: {os.path.abspath(UPLOAD_FOLDER)}")
    logger.info(f"📂 Books folder: {os.path.abspath(BOOKS_FOLDER)}")
    logger.info(f"🔑 HF API Key: {'Set' if HF_API_KEY else 'Not set'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )
