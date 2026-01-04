# main.py - Бэкенд Versevo с локальным переводчиком и OpenAI анализом
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
import re
import json
from datetime import datetime
import requests
from collections import Counter
import torch

# OpenAI импорт
from openai import OpenAI

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
    version="4.0.0"
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

# ========== ИНИЦИАЛИЗАЦИЯ OPENAI ==========
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key:
    try:
        openai_client = OpenAI(api_key=openai_api_key)
        OPENAI_ENABLED = True
        logger.info(f"✅ OpenAI инициализирован. Модель: gpt-3.5-turbo")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации OpenAI: {e}")
        openai_client = None
        OPENAI_ENABLED = False
else:
    openai_client = None
    OPENAI_ENABLED = False
    logger.warning(f"⚠️ OpenAI не настроен. Добавь OPENAI_API_KEY в переменные окружения")

# ========== МОДЕЛИ ==========
class TranslateRequest(BaseModel):
    text: str
    target_language: str = "ru"
    source_language: Optional[str] = None
    style: str = "artistic"

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "general"

# Модель для OpenAI анализа
class OpenAIAnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "full"
    language: str = "ru"

# ========== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ==========
PORT = int(os.getenv("PORT", 8080))

# Хранилище документов в памяти
documents_store = {}
current_doc_id = 1

# ========== ЛОКАЛЬНЫЙ ПЕРЕВОДЧИК ==========
class LocalTranslator:
    """Локальный переводчик с использованием трансформеров"""
    
    def __init__(self):
        self.translators = {}
        self.device = torch.device("cpu")  # Всегда используем CPU на Railway
        logger.info(f"🚀 Используем устройство: {self.device}")
        
        # НЕ предзагружаем модели - загружаем по требованию
        logger.info("⚡ Модели будут загружаться по требованию (lazy loading)")
    
    def get_translator(self, source_lang: str, target_lang: str):
        """Получить или создать переводчик для языковой пары"""
        key = f"{source_lang}-{target_lang}"
        
        if key not in self.translators:
            try:
                logger.info(f"📥 Загружаем модель для {key}...")
                
                # Используем более легкие модели
                model_mapping = {
                    "en-ru": "Helsinki-NLP/opus-mt-en-ru",
                    "ru-en": "Helsinki-NLP/opus-mt-ru-en",
                }
                
                model_name = model_mapping.get(key)
                if not model_name:
                    logger.warning(f"⚠️ Нет локальной модели для {key}")
                    return None
                
                from transformers import pipeline
                
                translator = pipeline(
                    "translation",
                    model=model_name,
                    device=-1,  # Всегда CPU
                    max_length=256,  # Уменьшим максимальную длину
                )
                
                self.translators[key] = translator
                logger.info(f"✅ Модель загружена: {key}")
                
                return translator
                    
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки модели {key}: {e}")
                return None
        
        return self.translators[key]
    
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Перевод текста с использованием локальной модели"""
        try:
            # Сначала пробуем быстрый fallback для коротких текстов
            if len(text) < 100:
                return self._quick_translation(text, source_lang, target_lang)
            
            translator = self.get_translator(source_lang, target_lang)
            
            if translator is None:
                logger.warning(f"⚠️ Локальный переводчик недоступен для {source_lang}->{target_lang}")
                return self._fallback_translation(text, source_lang, target_lang)
            
            # Ограничиваем размер текста для перевода
            MAX_TEXT_LENGTH = 500
            if len(text) > MAX_TEXT_LENGTH:
                logger.info(f"📝 Текст слишком длинный ({len(text)} символов), обрезаем до {MAX_TEXT_LENGTH}")
                text = text[:MAX_TEXT_LENGTH] + "..."
            
            # Переводим одной частью
            result = translator(text, max_length=256)
            if isinstance(result, list) and len(result) > 0:
                return result[0]['translation_text']
            else:
                return text
                
        except Exception as e:
            logger.error(f"❌ Ошибка перевода: {e}")
            return self._fallback_translation(text, source_lang, target_lang)
    
    def _quick_translation(self, text: str, source_lang: str, target_lang: str) -> str:
        """Быстрый перевод для коротких текстов"""
        if source_lang == 'en' and target_lang == 'ru':
            # Простой словарь для быстрого перевода
            common_translations = {
                'hello': 'привет',
                'world': 'мир',
                'book': 'книга',
                'read': 'читать',
                'page': 'страница',
                'chapter': 'глава',
                'text': 'текст',
                'document': 'документ',
                'translate': 'переводить',
                'library': 'библиотека',
                'the': '',
                'a': '',
                'an': '',
                'and': 'и',
                'or': 'или',
                'but': 'но',
                'is': 'является',
                'are': 'являются',
                'was': 'был',
                'were': 'были',
            }
            
            words = text.split()
            translated = []
            
            for word in words:
                lower_word = word.lower()
                if lower_word in common_translations:
                    translation = common_translations[lower_word]
                    if translation:  # Не добавляем пустые слова (артикли)
                        translated.append(translation)
                else:
                    translated.append(word)
            
            return " ".join(translated)
        return text
    
    def _split_text(self, text: str, max_length: int = 1000) -> List[str]:
        """Разбить текст на части для перевода"""
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < max_length:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _fallback_translation(self, text: str, source_lang: str, target_lang: str) -> str:
        """Fallback перевод"""
        if source_lang == 'en' and target_lang == 'ru':
            translation_map = {
                'hello': 'привет',
                'world': 'мир',
                'book': 'книга',
                'read': 'читать',
                'translate': 'переводить',
                'document': 'документ',
                'text': 'текст',
                'chapter': 'глава',
                'page': 'страница',
                'library': 'библиотека',
                'this': 'это',
                'is': '',
                'a': '',
                'test': 'тест',
                'translation': 'перевод',
                'from': 'из',
                'the': '',
                'versevo': 'версево',
                'backend': 'бэкенд',
                'for': 'для',
                'and': 'и',
                'to': 'к',
                'with': 'с',
                'on': 'на',
                'in': 'в',
                'of': 'из',
                'that': 'что',
                'it': 'это',
                'you': 'ты',
                'he': 'он',
                'she': 'она',
                'we': 'мы',
                'they': 'они',
            }
            
            words = text.lower().split()
            translated_words = []
            
            for word in words:
                clean_word = ''.join(c for c in word if c.isalpha())
                if clean_word in translation_map and translation_map[clean_word]:
                    translated_words.append(translation_map[clean_word])
                else:
                    translated_words.append(word)
            
            result = " ".join(translated_words)
            return f"[FALLBACK] {result}"
        
        return f"[FALLBACK] Перевод с {source_lang} на {target_lang}: {text[:100]}..."

# Инициализируем переводчик
translator = LocalTranslator()

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
                
                if extracted_text and len(extracted_text.strip()) > 10:
                    return extracted_text
                else:
                    logger.warning("PDF extraction returned empty or too short text")
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
                    logger.warning("DOCX extraction returned empty text")
                    return ""
                    
            except ImportError:
                logger.error("python-docx not installed. Please install: pip install python-docx")
                return ""
            except Exception as e:
                logger.error(f"DOCX extraction error: {e}")
                return ""
                
        elif file_type == 'txt':
            try:
                encodings = ['utf-8', 'cp1251', 'koi8-r', 'iso-8859-5']
                for encoding in encodings:
                    try:
                        with open(file_path, "r", encoding=encoding) as f:
                            text = f.read()
                            if text and len(text.strip()) > 10:
                                return text
                    except UnicodeDecodeError:
                        continue
                
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

def translate_with_fallback(text: str, source_lang: str, target_lang: str) -> str:
    """Перевод с fallback на базовый вариант"""
    try:
        return translator.translate(text, source_lang, target_lang)
    except Exception as e:
        logger.error(f"Fallback translation error: {e}")
        return f"[TRANSLATION ERROR] {text[:200]}..."

# ========== OPENAI УТИЛИТЫ ==========
def _get_openai_fallback_response(document_id: int, content: str = ""):
    """Fallback ответ если OpenAI не работает"""
    return {
        "document_id": document_id,
        "summary": "AI-анализ временно недоступен. Используется локальная обработка.",
        "themes": "Тематика не определена (OpenAI недоступен)",
        "sentiment": "Нейтральная",
        "writing_style": "Не определен",
        "key_points": ["AI-анализ в процессе разработки", "Попробуйте позже"],
        "characters": [],
        "model_used": "fallback",
        "ai_analysis": False,
        "fallback": True,
        "created_at": datetime.now().isoformat()
    }

# ========== HEALTH CHECK ENDPOINTS ==========
@app.get("/")
async def root():
    """Корневой эндпоинт"""
    endpoints = {
        "health": "/api/health",
        "upload": "/api/documents/upload-base64",
        "documents": "/api/documents",
        "translate": "/api/translate/text",
        "analyze": "/api/analyze",
    }
    
    if OPENAI_ENABLED:
        endpoints.update({
            "openai_health": "/api/analyze/openai/health",
            "openai_analyze": "/api/analyze/openai/document",
            "openai_quotes": "/api/analyze/openai/quotes"
        })
    
    return {
        "message": "Versevo Backend API v4.0",
        "version": "4.0.0",
        "status": "running",
        "translation": "local_models",
        "openai_available": OPENAI_ENABLED,
        "timestamp": datetime.now().isoformat(),
        "endpoints": endpoints
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "translation": "local_models",
        "openai_available": OPENAI_ENABLED,
        "timestamp": datetime.now().isoformat(),
        "version": "4.0.0"
    }

@app.get("/api/flutter/health")
async def health_check_flutter():
    """Health check для Flutter/Railway"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "timestamp": datetime.now().isoformat(),
        "translation": "local_transformers",
        "openai_available": OPENAI_ENABLED,
        "version": "4.0.0"
    }

@app.get("/health")
async def health_check_simple():
    """Простой health check"""
    return {"status": "ok", "translation": "local", "openai": OPENAI_ENABLED}

# ========== ДОКУМЕНТЫ ==========
@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: dict):
    """Загрузка документа в формате base64"""
    global current_doc_id
    
    try:
        filename = request.get("filename", "unknown.txt")
        file_data = request.get("file_data", "")
        file_size = request.get("file_size", 0)
        
        logger.info(f"📤 Base64 upload started: {filename}")
        
        if not file_data:
            raise HTTPException(status_code=400, detail="No file data provided")
        
        content_bytes = base64.b64decode(file_data)
        
        file_id = str(uuid.uuid4())
        file_extension = filename.split('.')[-1].lower() if '.' in filename else 'txt'
        file_path = f"{UPLOAD_FOLDER}/{file_id}.{file_extension}"
        
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(content_bytes)
        
        logger.info(f"💾 File saved: {file_path} ({len(content_bytes)} bytes)")
        
        content_str = extract_text_from_file(file_path, file_extension)
        
        logger.info(f"📝 Text extraction: {len(content_str)} chars")
        
        if not content_str or content_str.strip() == "":
            logger.warning("⚠️ Content is empty, using fallback text")
            content_str = f"""
            Документ: {filename}
            Тип: {file_extension}
            
            Это тестовое содержимое для проверки работы.
            
            Всего слов: примерно 20
            Язык: автоматически определен
            """
        
        language = detect_language_safe(content_str)
        chapters = detect_chapters(content_str)
        
        document = {
            "id": current_doc_id,
            "filename": filename,
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
                "char_count": len(content_str),
                "extraction_success": True
            }
        }
        
        documents_store[current_doc_id] = document
        current_doc_id += 1
        
        logger.info(f"✅ Document {document['id']} created with {document['word_count']} words")
        
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Base64 upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/documents")
async def get_documents(user_id: Optional[int] = None):
    """Получение списка документов"""
    docs = list(documents_store.values())
    if user_id:
        docs = [d for d in docs if d.get("user_id") == user_id]
    
    return [
        {
            "id": d["id"],
            "filename": d["filename"],
            "content": d["content"],
            "language": d["language"],
            "file_type": d["file_type"],
            "file_size": d["file_size"],
            "word_count": d["word_count"],
            "char_count": d["char_count"],
            "chapter_count": d["chapter_count"],
            "reading_time_minutes": d["reading_time_minutes"],
            "created_at": d["created_at"],
            "updated_at": d["updated_at"],
            "content_preview": d["content"][:200] + "..." if len(d["content"]) > 200 else d["content"],
            "chapters": d["chapters"],
            "metadata": d.get("metadata", {})
        }
        for d in sorted(docs, key=lambda x: x["created_at"], reverse=True)
    ]

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int):
    """Получение документа по ID"""
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    return documents_store[document_id]

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int):
    """Удаление документа"""
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
        
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
    """Перевод текста с использованием локальной модели"""
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is empty")
        
        source_lang = request.source_language
        if not source_lang or source_lang == "auto":
            source_lang = detect_language_safe(request.text)
        
        target_lang = request.target_language
        
        logger.info(f"🌐 Перевод текста: {len(request.text)} символов, с {source_lang} на {target_lang}")
        
        translated_text = translator.translate(request.text, source_lang, target_lang)
        
        # Применяем стиль
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
            "translation_service": "local_transformers",
            "original_length": len(request.text),
            "translated_length": len(translated_text)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Translate error: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@app.post("/api/translate/document/{document_id}")
async def translate_document(document_id: int, target_language: str = "ru"):
    """Перевод всего документа С ОГРАНИЧЕНИЯМИ"""
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # ОГРАНИЧЕНИЕ: Максимум 10,000 символов для перевода
        MAX_TRANSLATION_LENGTH = 10000
        
        if len(content) > MAX_TRANSLATION_LENGTH:
            return {
                "success": False,
                "document_id": document_id,
                "error": f"Документ слишком большой для перевода ({len(content)} символов). Максимум: {MAX_TRANSLATION_LENGTH} символов.",
                "suggestion": "Попробуйте переводить по одной главе за раз.",
                "available_chapters": len(doc.get("chapters", [])),
                "translation_service": "limited"
            }
        
        logger.info(f"🌐 Перевод документа {document_id}: {len(content)} символов")
        
        # Разбиваем на части для перевода
        if len(content) > 2000:
            chunks = []
            chunk_size = 1500
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                chunks.append(chunk)
            
            translated_chunks = []
            for i, chunk in enumerate(chunks):
                logger.info(f"📝 Переводим часть {i+1}/{len(chunks)}")
                translated = translate_with_fallback(chunk, doc["language"], target_language)
                translated_chunks.append(translated)
            
            translated_content = " ".join(translated_chunks)
        else:
            translated_content = translate_with_fallback(content, doc["language"], target_language)
        
        doc["translated_content"] = translated_content
        doc["updated_at"] = datetime.now().isoformat()
        
        return {
            "success": True,
            "document_id": document_id,
            "original_language": doc["language"],
            "target_language": target_language,
            "translated_content": translated_content[:500] + "..." if len(translated_content) > 500 else translated_content,
            "total_translated": len(translated_content.split()),
            "translation_service": "local_transformers",
            "warning": "Перевод может занять некоторое время для больших документов."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document translation error: {e}")
        raise HTTPException(status_code=500, detail=f"Document translation failed: {str(e)}")

@app.get("/api/translate/test")
async def test_translation():
    """Тестовый endpoint для проверки перевода"""
    try:
        test_text = "Hello world, this is a test translation from the Versevo backend with local models."
        
        translated = translator.translate(test_text, "en", "ru")
        
        return {
            "original": test_text,
            "translated": translated,
            "status": "success",
            "service": "local_transformers",
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

@app.get("/api/translate/status")
async def translation_status():
    """Статус переводчика"""
    return {
        "status": "active",
        "translation": "local_transformers",
        "available_models": ["en-ru", "ru-en"],
        "device": str(translator.device),
        "loaded_models": list(translator.translators.keys()),
        "timestamp": datetime.now().isoformat()
    }

# ========== OPENAI АНАЛИЗ ==========
@app.get("/api/analyze/openai/health")
async def openai_health_check():
    """Проверка доступности OpenAI"""
    if not OPENAI_ENABLED:
        return {
            "status": "unavailable",
            "reason": "OPENAI_API_KEY not set in environment",
            "available": False,
            "openai_available": False,
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        # Тестовый запрос к OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        
        return {
            "status": "healthy",
            "service": "openai",
            "model": "gpt-3.5-turbo",
            "available": True,
            "openai_available": True,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unavailable",
            "service": "openai",
            "error": str(e),
            "available": False,
            "openai_available": False,
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/analyze/openai/document")
async def analyze_with_openai(request: OpenAIAnalysisRequest):
    """AI-анализ документа через OpenAI"""
    
    if not OPENAI_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="OpenAI service is not configured. Please set OPENAI_API_KEY environment variable."
        )
    
    try:
        document_id = request.document_id
        
        # Получаем документ из хранилища
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # Ограничиваем размер текста для экономии токенов
        MAX_CONTENT_LENGTH = 4000
        if len(content) > MAX_CONTENT_LENGTH:
            logger.info(f"📝 Ограничиваем текст для анализа: {len(content)} -> {MAX_CONTENT_LENGTH} символов")
            content = content[:2000] + "\n...\n" + content[-2000:]
        
        # Создаем промпт для анализа
        prompt = f"""
ПРОАНАЛИЗИРУЙ ЭТОТ ТЕКСТ И ВЕРНИ ОТВЕТ ТОЛЬКО В ФОРМАТЕ JSON:

ТЕКСТ ДЛЯ АНАЛИЗА:
{content}

ТРЕБУЕМЫЙ ФОРМАТ JSON:
{{
  "summary": "Краткое содержание текста (3-4 предложения)",
  "themes": "Основные темы текста через запятую",
  "sentiment": "Общая тональность текста (позитивная, негативная, нейтральная, смешанная)",
  "writing_style": "Стиль письма (формальный, разговорный, академический, художественный и т.д.)",
  "key_points": ["Ключевой момент 1", "Ключевой момент 2", "Ключевой момент 3"],
  "characters": [
    {{"name": "Имя персонажа 1", "role": "Роль в тексте", "importance": "высокая/средняя/низкая"}},
    {{"name": "Имя персонажа 2", "role": "Роль в тексте", "importance": "высокая/средняя/низкая"}}
  ]
}}

ПРАВИЛА:
1. ВСЕ ответы должны быть НА РУССКОМ языке
2. Если персонажей нет - верни пустой массив
3. Будь точным и объективным
4. Не добавляй никакого текста кроме JSON
"""
        
        logger.info(f"🤖 Отправляем запрос к OpenAI для документа {document_id}")
        
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=[
                {"role": "system", "content": "Ты эксперт по анализу текстов. Ты говоришь на русском языке."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            max_tokens=1500
        )
        
        result_text = response.choices[0].message.content
        
        # Парсим JSON результат
        analysis_result = json.loads(result_text)
        
        # Добавляем метаданные
        analysis_result.update({
            "document_id": document_id,
            "analysis_type": request.analysis_type,
            "model_used": response.model,
            "processing_time": "openai_gpt3.5",
            "ai_analysis": True,
            "created_at": datetime.now().isoformat()
        })
        
        logger.info(f"✅ AI-анализ завершен для документа {document_id}")
        
        return analysis_result
        
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON от OpenAI: {e}")
        logger.error(f"Полученный текст: {result_text[:500]}...")
        # Возвращаем fallback ответ
        return _get_openai_fallback_response(document_id, content)
    except Exception as e:
        logger.error(f"❌ Ошибка OpenAI анализа: {e}")
        raise HTTPException(status_code=500, detail=f"OpenAI analysis failed: {str(e)}")

@app.post("/api/analyze/openai/quotes")
async def extract_quotes_with_openai(request: dict):
    """Извлечение цитат через OpenAI"""
    
    if not OPENAI_ENABLED:
        return {
            "quotes": [
                "Цитаты временно недоступны",
                "AI-сервис настройте позже"
            ],
            "count": 2,
            "ai_analysis": False,
            "fallback": True
        }
    
    try:
        document_id = request.get("document_id")
        limit = request.get("limit", 5)
        
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            return {
                "quotes": ["Текст документа пустой"],
                "count": 1,
                "ai_analysis": False,
                "fallback": True
            }
        
        # Ограничиваем размер текста
        MAX_CONTENT_LENGTH = 3000
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH]
        
        prompt = f"""
ИЗВЛЕКИ {limit} САМЫХ ЗНАЧИМЫХ ЦИТАТ ИЗ ТЕКСТА:

ТЕКСТ:
{content}

ВЕРНИ ТОЛЬКО JSON В ФОРМАТЕ:
{{
  "quotes": ["Цитата 1", "Цитата 2", "Цитата 3"]
}}

ПРАВИЛА:
1. Цитаты должны быть точными фразами из текста
2. Не изменяй оригинальный текст
3. Выбирай цитаты, которые лучше всего отражают суть
4. Максимум {limit} цитат
5. Все на русском языке
"""
        
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
            max_tokens=800
        )
        
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        quotes = result.get("quotes", [])
        
        return {
            "document_id": document_id,
            "quotes": quotes,
            "count": len(quotes),
            "ai_analysis": True,
            "model_used": response.model,
            "fallback": False
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения цитат: {e}")
        return {
            "quotes": [
                "Цитаты временно недоступны",
                "Произошла ошибка при обработке"
            ],
            "count": 2,
            "ai_analysis": False,
            "error": str(e),
            "fallback": True
        }

# ========== БАЗОВЫЙ АНАЛИЗ ==========
@app.post("/api/analyze")
async def analyze_document(request: AnalysisRequest):
    """Базовый анализ документа"""
    try:
        document_id = request.document_id
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        word_count = len(content.split())
        char_count = len(content)
        
        if word_count > 5000:
            complexity = "Сложный"
        elif word_count > 2000:
            complexity = "Средний"
        else:
            complexity = "Простой"
        
        common_words = content.lower().split()
        word_freq = Counter(common_words)
        
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
            "themes": ", ".join([word for word, _ in top_keywords]),
            "sentiment": "Нейтральный",
            "writing_style": "Информационный",
            "key_points": [
                f"Документ на {doc['language']} языке",
                f"Содержит {doc['chapter_count']} глав",
                f"Время чтения: {doc['reading_time_minutes']} минут"
            ],
            "characters": [],
            "analysis_date": datetime.now().isoformat(),
            "ai_analysis": False,
            "fallback": False
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
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        return doc["chapters"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chapters error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"🚀 Starting Versevo Backend v4.0 on port {PORT}")
    logger.info(f"📁 Upload folder: {os.path.abspath(UPLOAD_FOLDER)}")
    logger.info(f"🔤 Translation: Local Transformers Models")
    logger.info(f"🤖 OpenAI Analysis: {'ENABLED' if OPENAI_ENABLED else 'DISABLED'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )
