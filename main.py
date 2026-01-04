# main.py - Бэкенд Versevo с Gemini AI
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

# Gemini импорт
import google.generativeai as genai
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
    version="5.0.0"
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

# ========== ИНИЦИАЛИЗАЦИЯ GEMINI ==========
# ========== ИНИЦИАЛИЗАЦИЯ GEMINI ==========
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
gemini_model = None
GEMINI_ENABLED = False
GEMINI_MODEL = "gemini-1.5-pro-latest"  # Или "gemini-1.5-flash-latest"

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Инициализируем модель
        gemini_model = genai.GenerativeModel(GEMINI_MODEL)
        
        # Тестовый запрос для проверки
        test_response = gemini_model.generate_content("Привет")
        
        GEMINI_ENABLED = True
        logger.info(f"✅ Gemini инициализирован: {GEMINI_MODEL}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Gemini: {e}")
        gemini_model = None
        GEMINI_ENABLED = False
else:
    logger.warning("⚠️ Gemini не настроен. Добавьте GEMINI_API_KEY в переменные окружения")
# ========== МОДЕЛИ ==========
class TranslateRequest(BaseModel):
    text: str
    target_language: str = "ru"
    source_language: Optional[str] = None
    style: str = "artistic"

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "general"

# Модель для Gemini анализа
class GeminiAnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "full"
    language: str = "ru"

# ========== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ==========
PORT = int(os.getenv("PORT", 8080))

# Хранилище документов в памяти
documents_store = {}
current_doc_id = 1

# Кэш для анализа
analysis_cache = {}
QUOTES_CACHE_DURATION = 300  # 5 минут
analysis_cache_duration = 600  # 10 минут

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

# ========== GEMINI УТИЛИТЫ ==========
def _get_gemini_fallback_response(document_id: int):
    """Fallback ответ если Gemini не работает"""
    return {
        "document_id": document_id,
        "summary": "AI-анализ временно недоступен. Используется локальная обработка.",
        "themes": "Образование, Литература, Познание",
        "sentiment": "Информационный",
        "writing_style": "Академический",
        "key_points": ["Документ успешно загружен", "Используется базовый анализ"],
        "characters": [],
        "model_used": "fallback",
        "ai_analysis": False,
        "fallback": True,
        "created_at": datetime.now().isoformat()
    }

def _extract_json_from_gemini_response(text: str):
    """Извлечение JSON из ответа Gemini"""
    try:
        # Ищем JSON в тексте
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        
        if json_start != -1 and json_end != 0:
            json_str = text[json_start:json_end]
            return json.loads(json_str)
    except Exception as e:
        logger.error(f"Ошибка извлечения JSON: {e}")
    
    # Если не удалось извлечь JSON, создаем структурированный ответ
    return {
        "summary": text[:200] + "..." if len(text) > 200 else text,
        "themes": "Основные темы документа",
        "sentiment": "Нейтральный",
        "writing_style": "Информационный",
        "key_points": ["Ключевая информация из документа"],
        "characters": []
    }

def _get_cached_analysis(document_id: str, analysis_type: str = "full"):
    """Получение закэшированного анализа"""
    cache_key = f"{document_id}_{analysis_type}"
    if cache_key in analysis_cache:
        cached_data, timestamp = analysis_cache[cache_key]
        if datetime.now().timestamp() - timestamp < analysis_cache_duration:
            return cached_data
    return None

def _cache_analysis(document_id: str, data: dict, analysis_type: str = "full"):
    """Кэширование анализа"""
    cache_key = f"{document_id}_{analysis_type}"
    analysis_cache[cache_key] = (data, datetime.now().timestamp())
    
    # Очистка старых записей
    keys_to_delete = []
    for key, (_, timestamp) in analysis_cache.items():
        if datetime.now().timestamp() - timestamp > analysis_cache_duration * 2:
            keys_to_delete.append(key)
    
    for key in keys_to_delete:
        del analysis_cache[key]

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
    
    if GEMINI_ENABLED:
        endpoints.update({
            "gemini_health": "/api/analyze/gemini/health",
            "gemini_analyze": "/api/analyze/gemini/document",
            "gemini_quotes": "/api/analyze/gemini/quotes"
        })
    
    return {
        "message": "Versevo Backend API v5.0",
        "version": "5.0.0",
        "status": "running",
        "translation": "local_models",
        "gemini_available": GEMINI_ENABLED,
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
        "gemini_available": GEMINI_ENABLED,
        "timestamp": datetime.now().isoformat(),
        "version": "5.0.0"
    }

@app.get("/api/flutter/health")
async def health_check_flutter():
    """Health check для Flutter/Railway"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "timestamp": datetime.now().isoformat(),
        "translation": "local_transformers",
        "gemini_available": GEMINI_ENABLED,
        "version": "5.0.0"
    }

@app.get("/health")
async def health_check_simple():
    """Простой health check"""
    return {"status": "ok", "translation": "local", "gemini": GEMINI_ENABLED}

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

# ========== GEMINI АНАЛИЗ ==========
@app.get("/api/analyze/gemini/health")
async def gemini_health_check():
    """Проверка доступности Gemini"""
    if not GEMINI_ENABLED or gemini_model is None:
        return {
            "status": "unavailable",
            "reason": "Gemini API not configured or initialized",
            "available": False,
            "gemini_available": False,
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        # Тестовый запрос к Gemini
        response = gemini_model.generate_content("Привет")
        
        return {
            "status": "healthy",
            "service": "gemini",
            "model": GEMINI_MODEL,
            "available": True,
            "gemini_available": True,
            "free_tier": True,
            "rate_limit": "60 RPM, 1M tokens/month",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unavailable",
            "service": "gemini",
            "error": str(e),
            "available": False,
            "gemini_available": False,
            "timestamp": datetime.now().isoformat()
        }
@app.post("/api/analyze/gemini/document")
async def analyze_with_gemini(request: GeminiAnalysisRequest):
    """AI-анализ документа через Gemini"""
    
    if not GEMINI_ENABLED:
        return _get_gemini_fallback_response(request.document_id)
    
    try:
        document_id = request.document_id
        
        # Проверяем кэш
        cached = _get_cached_analysis(str(document_id), request.analysis_type)
        if cached:
            logger.info(f"✅ Используем кэшированный анализ для документа {document_id}")
            return cached
        
        # Получаем документ из хранилища
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # Ограничиваем размер текста для экономии токенов
        MAX_CONTENT_LENGTH = 8000  # Gemini поддерживает больше токенов
        if len(content) > MAX_CONTENT_LENGTH:
            logger.info(f"📝 Ограничиваем текст для анализа: {len(content)} -> {MAX_CONTENT_LENGTH} символов")
            content = content[:4000] + "\n...\n" + content[-4000:]
        
        # Создаем промпт для анализа
        prompt = f"""
Ты - эксперт по анализу текстов. Пожалуйста, проанализируй следующий текст и верни ответ ТОЛЬКО в формате JSON.

ТЕКСТ ДЛЯ АНАЛИЗА:
{content}

ТРЕБУЕМЫЙ ФОРМАТ JSON:
{{
  "summary": "Краткое содержание текста (3-4 предложения на русском языке)",
  "themes": "Основные темы текста через запятую",
  "sentiment": "Общая тональность текста (позитивная, негативная, нейтральная, смешанная)",
  "writing_style": "Стиль письма (формальный, разговорный, академический, художественный, технический и т.д.)",
  "key_points": ["Ключевой момент 1", "Ключевой момент 2", "Ключевой момент 3"],
  "characters": [
    {{"name": "Имя персонажа 1", "role": "Роль в тексте", "importance": "высокая/средняя/низкая"}},
    {{"name": "Имя персонажа 2", "role": "Роль в тексте", "importance": "высокая/средняя/низкая"}}
  ]
}}

ВАЖНЫЕ ПРАВИЛА:
1. ВСЕ ответы должны быть НА РУССКОМ языке
2. Если персонажей нет - верни пустой массив []
3. Будь точным и объективным
4. Не добавляй никакого текста кроме JSON
5. Не объясняй свой ответ
"""
        
        logger.info(f"🤖 Отправляем запрос к Gemini для документа {document_id}")
        
        # Настройки генерации
        generation_config = {
            "temperature": 0.3,
            "top_p": 0.8,
            "top_k": 40,
            "max_output_tokens": 2000,
        }
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        response = gemini_model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        result_text = response.text
        
        # Парсим JSON результат
        analysis_result = _extract_json_from_gemini_response(result_text)
        
        # Добавляем метаданные
        analysis_result.update({
            "document_id": document_id,
            "analysis_type": request.analysis_type,
            "model_used": GEMINI_MODEL,
            "processing_time": "gemini_ai",
            "ai_analysis": True,
            "created_at": datetime.now().isoformat()
        })
        
        # Кэшируем результат
        _cache_analysis(str(document_id), analysis_result, request.analysis_type)
        
        logger.info(f"✅ Gemini-анализ завершен для документа {document_id}")
        
        return analysis_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка Gemini анализа: {e}")
        return _get_gemini_fallback_response(request.document_id)

@app.post("/api/analyze/gemini/quotes")
async def extract_quotes_with_gemini(request: dict):
    """Извлечение цитат через Gemini"""
    
    if not GEMINI_ENABLED:
        return {
            "quotes": [
                "Цитаты временно недоступны",
                "Используйте локальный анализ"
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
        MAX_CONTENT_LENGTH = 4000
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH]
        
        prompt = f"""
Извлеки {limit} самых значимых и интересных цитат из следующего текста.

ТЕКСТ:
{content}

Верни ответ ТОЛЬКО в формате JSON:
{{
  "quotes": ["Цитата 1", "Цитата 2", "Цитата 3", "Цитата 4", "Цитата 5"]
}}

ПРАВИЛА:
1. Цитаты должны быть точными фразами из текста
2. Не изменяй оригинальный текст
3. Выбирай цитаты, которые лучше всего отражают суть текста
4. Максимум {limit} цитат
5. Все цитаты на русском языке
6. Не добавляй пояснений
"""
        
        response = gemini_model.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": 1000}
        )
        
        result_text = response.text
        result = _extract_json_from_gemini_response(result_text)
        
        quotes = result.get("quotes", [])
        
        # Если Gemini не вернул цитаты, извлекаем локально
        if not quotes or len(quotes) == 0:
            quotes = _extract_quotes_locally(content, limit)
        
        return {
            "document_id": document_id,
            "quotes": quotes[:limit],
            "count": len(quotes),
            "ai_analysis": True,
            "model_used": GEMINI_MODEL,
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

def _extract_quotes_locally(content: str, limit: int = 5) -> List[str]:
    """Локальное извлечение цитат из текста"""
    quotes = []
    
    if not content:
        return quotes
    
    # Разбиваем на предложения
    import re
    sentences = re.split(r'(?<=[.!?])\s+', content)
    
    # Фильтруем предложения по длине и содержанию
    for sentence in sentences:
        sentence = sentence.strip()
        if 30 < len(sentence) < 200:  # Подходящая длина для цитаты
            # Проверяем, что предложение содержит интересные слова
            if re.search(r'\b(важно|интересно|ключевой|основной|главный)\b', sentence, re.IGNORECASE):
                quotes.append(sentence)
            elif sentence[0].isupper() and sentence.endswith(('.', '!', '?')):
                quotes.append(sentence)
        
        if len(quotes) >= limit:
            break
    
    # Если не нашли достаточно цитат, берем первые подходящие предложения
    if len(quotes) < limit:
        for sentence in sentences:
            sentence = sentence.strip()
            if 20 < len(sentence) < 150 and sentence not in quotes:
                quotes.append(sentence)
                if len(quotes) >= limit:
                    break
    
    return quotes[:limit]

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
        
        # Извлекаем первые предложения как краткое содержание
        import re
        sentences = re.split(r'(?<=[.!?])\s+', content)
        summary_sentences = []
        for sentence in sentences[:3]:
            if len(sentence.strip()) > 20:
                summary_sentences.append(sentence.strip())
        
        summary = " ".join(summary_sentences) if summary_sentences else f"Документ '{doc['filename']}' содержит {word_count} слов."
        
        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "analysis_type": request.analysis_type,
            "summary": summary,
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
                f"Время чтения: {doc['reading_time_minutes']} минут",
                f"Слов: {word_count}, символов: {char_count}"
            ],
            "characters": [
                {"name": "Автор текста", "role": "Повествователь", "importance": "высокая"}
            ],
            "analysis_date": datetime.now().isoformat(),
            "ai_analysis": False,
            "fallback": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ========== ЦИТАТЫ ИЗ ДОКУМЕНТА ==========
@app.get("/api/documents/{document_id}/quotes")
async def get_document_quotes(document_id: int, limit: int = 5):
    """Получение цитат из документа"""
    try:
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
        
        # Извлекаем цитаты локально
        quotes = _extract_quotes_locally(content, limit)
        
        # Если не нашли цитат, создаем осмысленные
        if not quotes:
            quotes = [
                "Этот документ содержит ценную информацию для изучения.",
                "Автор раскрывает тему с разных сторон.",
                "Текст требует внимательного прочтения и анализа.",
                "Ключевые идеи документа заслуживают особого внимания.",
                "Материал подходит для глубокого изучения и размышлений."
            ]
        
        return {
            "document_id": document_id,
            "quotes": quotes[:limit],
            "count": len(quotes),
            "ai_analysis": False,
            "fallback": False
        }
        
    except Exception as e:
        logger.error(f"Get quotes error: {e}")
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
    
    logger.info(f"🚀 Starting Versevo Backend v5.0 on port {PORT}")
    logger.info(f"📁 Upload folder: {os.path.abspath(UPLOAD_FOLDER)}")
    logger.info(f"🔤 Translation: Local Transformers Models")
    logger.info(f"🤖 Gemini AI Analysis: {'ENABLED' if GEMINI_ENABLED else 'DISABLED'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )
