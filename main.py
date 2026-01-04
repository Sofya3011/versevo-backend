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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== МОДЕЛИ PYDANTIC ==========
class TranslateRequest(BaseModel):
    text: str
    target_language: str = "ru"
    source_language: Optional[str] = None
    style: str = "artistic"

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "general"

class GeminiAnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "full"
    language: str = "ru"

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

# ========== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ==========
PORT = int(os.getenv("PORT", 8080))

# Хранилище документов в памяти
documents_store = {}
current_doc_id = 1

# Кэш для анализа
analysis_cache = {}
QUOTES_CACHE_DURATION = 300
analysis_cache_duration = 600

# ========== ИНИЦИАЛИЗАЦИЯ GEMINI ==========
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
gemini_model = None
GEMINI_ENABLED = False
GEMINI_MODEL = None

if GEMINI_API_KEY:
    try:
        logger.info("🔧 Инициализация Gemini AI...")
        
        # Пробуем разные импорты
        try:
            # Новая версия
            import google.genai as genai
            from google.genai import types
            logger.info("✅ Используется новый пакет google.genai")
        except ImportError:
            try:
                # Старая версия
                import google.generativeai as genai
                logger.warning("⚠️ Используется устаревший пакет google.generativeai")
            except ImportError as e:
                logger.error(f"❌ Не удалось импортировать Gemini: {e}")
                genai = None
        
        if genai:
            genai.configure(api_key=GEMINI_API_KEY)
            
            # Пробуем разные модели
            model_variants = [
                "gemini-1.5-flash",
                "gemini-1.5-pro",
                "gemini-1.0-pro",
                "gemini-pro",
            ]
            
            for model_name in model_variants:
                try:
                    logger.info(f"🔄 Пробуем модель: {model_name}")
                    gemini_model = genai.GenerativeModel(model_name)
                    test_response = gemini_model.generate_content("Hello")
                    
                    GEMINI_MODEL = model_name
                    GEMINI_ENABLED = True
                    logger.info(f"✅ Gemini инициализирован! Модель: {GEMINI_MODEL}")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ Модель {model_name} недоступна: {str(e)[:100]}")
                    continue
            
            if not GEMINI_ENABLED:
                logger.error("❌ Все модели Gemini недоступны, проверьте API ключ и регион")
                gemini_model = None
                
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Gemini: {e}")
        gemini_model = None
        GEMINI_ENABLED = False
else:
    logger.warning("⚠️ Gemini не настроен. Добавьте GEMINI_API_KEY в переменные окружения")

# ========== УПРОЩЕННЫЙ ПЕРЕВОДЧИК ==========
class LocalTranslator:
    """Упрощенный переводчик (без torch/transformers)"""
    
    def __init__(self):
        logger.info("🚀 Используем упрощенный переводчик")
        self.simple_dict = {
            'en-ru': {
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
            },
            'ru-en': {
                'привет': 'hello',
                'мир': 'world',
                'книга': 'book',
                'читать': 'read',
                'страница': 'page',
                'глава': 'chapter',
                'текст': 'text',
                'документ': 'document',
            }
        }
    
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Простой перевод"""
        key = f"{source_lang}-{target_lang}"
        
        # Ограничиваем длину текста
        if len(text) > 500:
            text = text[:500] + "..."
        
        # Пробуем простой словарный перевод
        if key in self.simple_dict:
            words = text.split()
            translated = []
            dict_map = self.simple_dict[key]
            
            for word in words:
                lower_word = word.lower()
                if lower_word in dict_map:
                    trans = dict_map[lower_word]
                    if trans:
                        translated.append(trans)
                else:
                    translated.append(word)
            
            result = " ".join(translated)
            
            # Добавляем префикс в зависимости от стиля
            if source_lang == 'en' and target_lang == 'ru':
                return f"[ПЕРЕВОД] {result}"
            elif source_lang == 'ru' and target_lang == 'en':
                return f"[TRANSLATION] {result}"
            else:
                return f"[{source_lang}→{target_lang}] {result}"
        
        # Fallback
        return f"[{source_lang}→{target_lang}] {text}"

# Инициализируем переводчик
translator = LocalTranslator()

# ========== УТИЛИТЫ ==========
def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Извлечение текста из файлов"""
    try:
        if file_type == 'pdf':
            try:
                import fitz
                text = []
                doc = fitz.open(file_path)
                for page in doc:
                    text.append(page.get_text())
                doc.close()
                return "\n\n".join(text) if text else ""
            except:
                return ""
                
        elif file_type in ['docx', 'doc']:
            try:
                import docx
                doc = docx.Document(file_path)
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                return "\n\n".join(paragraphs) if paragraphs else ""
            except:
                return ""
                
        elif file_type == 'txt':
            try:
                with open(file_path, "r", encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except:
                return ""
                
        else:
            return ""
            
    except:
        return ""

def detect_language_safe(text: str) -> str:
    """Определение языка"""
    if not text or len(text.strip()) < 10:
        return "en"
    try:
        # Простая проверка по символам
        cyrillic = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
        latin = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
        
        if cyrillic > latin:
            return "ru"
        else:
            return "en"
    except:
        return "en"

def detect_chapters(text: str) -> List[Dict]:
    """Автоматическое определение глав в тексте"""
    chapters = []
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
    """Перевод с fallback"""
    try:
        return translator.translate(text, source_lang, target_lang)
    except:
        return f"[TRANSLATION ERROR] {text[:200]}..."

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
        })
    
    return {
        "message": "Versevo Backend API v5.0",
        "version": "5.0.0",
        "status": "running",
        "translation": "simple",
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
        "translation": "simple",
        "gemini_available": GEMINI_ENABLED,
        "timestamp": datetime.now().isoformat(),
        "version": "5.0.0"
    }

# ========== ДОКУМЕНТЫ ==========
@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: dict):
    """Загрузка документа в формате base64"""
    global current_doc_id
    
    try:
        filename = request.get("filename", "unknown.txt")
        file_data = request.get("file_data", "")
        
        if not file_data:
            raise HTTPException(status_code=400, detail="No file data provided")
        
        content_bytes = base64.b64decode(file_data)
        file_id = str(uuid.uuid4())
        file_extension = filename.split('.')[-1].lower() if '.' in filename else 'txt'
        file_path = f"{UPLOAD_FOLDER}/{file_id}.{file_extension}"
        
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(content_bytes)
        
        content_str = extract_text_from_file(file_path, file_extension)
        
        if not content_str or content_str.strip() == "":
            content_str = f"Документ: {filename}\nТип: {file_extension}"
        
        language = detect_language_safe(content_str)
        chapters = detect_chapters(content_str)
        
        document = {
            "id": current_doc_id,
            "filename": filename,
            "content": content_str,
            "language": language,
            "file_type": file_extension,
            "file_path": file_path,
            "word_count": len(content_str.split()),
            "char_count": len(content_str),
            "chapter_count": len(chapters),
            "reading_time_minutes": max(1, len(content_str.split()) // 200),
            "created_at": datetime.now().isoformat(),
            "chapters": chapters,
        }
        
        documents_store[current_doc_id] = document
        current_doc_id += 1
        
        return document
        
    except Exception as e:
        logger.error(f"Base64 upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/documents")
async def get_documents():
    """Получение списка документов"""
    docs = list(documents_store.values())
    
    return [
        {
            "id": d["id"],
            "filename": d["filename"],
            "language": d["language"],
            "file_type": d["file_type"],
            "word_count": d["word_count"],
            "char_count": d["char_count"],
            "chapter_count": d["chapter_count"],
            "reading_time_minutes": d["reading_time_minutes"],
            "created_at": d["created_at"],
            "content_preview": d["content"][:200] + "..." if len(d["content"]) > 200 else d["content"],
        }
        for d in sorted(docs, key=lambda x: x["created_at"], reverse=True)
    ]

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int):
    """Получение документа по ID"""
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    return documents_store[document_id]

# ========== ПЕРЕВОД ==========
@app.post("/api/translate/text")
async def translate_text(request: TranslateRequest):
    """Перевод текста"""
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is empty")
        
        source_lang = request.source_language
        if not source_lang or source_lang == "auto":
            source_lang = detect_language_safe(request.text)
        
        target_lang = request.target_lang
        
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
            "translation_service": "simple",
            "original_length": len(request.text),
            "translated_length": len(translated_text)
        }
        
    except Exception as e:
        logger.error(f"Translate error: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

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
        response = gemini_model.generate_content("Hello")
        return {
            "status": "healthy",
            "service": "gemini",
            "model": GEMINI_MODEL,
            "available": True,
            "gemini_available": True,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unavailable",
            "service": "gemini",
            "error": str(e)[:100],
            "available": False,
            "gemini_available": False,
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/analyze/gemini/document")
async def analyze_with_gemini(request: GeminiAnalysisRequest):
    """AI-анализ документа через Gemini"""
    
    if not GEMINI_ENABLED or gemini_model is None:
        return {
            "document_id": request.document_id,
            "summary": "AI-анализ временно недоступен. Используется локальная обработка.",
            "themes": "Образование, Литература, Познание",
            "sentiment": "Информационный",
            "writing_style": "Академический",
            "key_points": ["Документ успешно загружен", "Используется базовый анализ"],
            "characters": [],
            "ai_analysis": False,
            "fallback": True,
            "created_at": datetime.now().isoformat()
        }
    
    try:
        document_id = request.document_id
        
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # Ограничиваем размер текста
        MAX_CONTENT_LENGTH = 4000
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."
        
        prompt = f"""Проанализируй текст и верни JSON:
{{
  "summary": "краткое содержание на русском (3 предложения)",
  "themes": "основные темы через запятую",
  "sentiment": "тональность",
  "writing_style": "стиль письма",
  "key_points": ["ключевой момент 1", "ключевой момент 2", "ключевой момент 3"],
  "characters": []
}}

Текст: {content}"""
        
        response = gemini_model.generate_content(prompt)
        result_text = response.text
        
        # Пытаемся извлечь JSON
        try:
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                analysis_result = json.loads(result_text[json_start:json_end])
            else:
                analysis_result = {
                    "summary": result_text[:200] + "..." if len(result_text) > 200 else result_text,
                    "themes": "Основные темы",
                    "sentiment": "Нейтральный",
                    "writing_style": "Информационный",
                    "key_points": ["Ключевая информация"],
                    "characters": []
                }
        except:
            analysis_result = {
                "summary": result_text[:200] + "..." if len(result_text) > 200 else result_text,
                "themes": "Основные темы",
                "sentiment": "Нейтральный",
                "writing_style": "Информационный",
                "key_points": ["Ключевая информация"],
                "characters": []
            }
        
        analysis_result.update({
            "document_id": document_id,
            "model_used": GEMINI_MODEL,
            "ai_analysis": True,
            "fallback": False,
            "created_at": datetime.now().isoformat()
        })
        
        return analysis_result
        
    except Exception as e:
        logger.error(f"Gemini analysis error: {e}")
        return {
            "document_id": request.document_id,
            "summary": f"Ошибка анализа: {str(e)[:100]}",
            "themes": "Ошибка",
            "sentiment": "Не определена",
            "writing_style": "Не определен",
            "key_points": ["Произошла ошибка при анализе"],
            "characters": [],
            "ai_analysis": False,
            "fallback": True,
            "created_at": datetime.now().isoformat()
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
        
        # Простой анализ
        complexity = "Сложный" if word_count > 5000 else "Средний" if word_count > 2000 else "Простой"
        
        # Берем первые предложения как summary
        sentences = re.split(r'(?<=[.!?])\s+', content)
        summary_sentences = []
        for sentence in sentences[:3]:
            if len(sentence.strip()) > 20:
                summary_sentences.append(sentence.strip())
        
        summary = " ".join(summary_sentences) if summary_sentences else f"Документ '{doc['filename']}' содержит {word_count} слов."
        
        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "summary": summary,
            "language": doc["language"],
            "word_count": word_count,
            "char_count": char_count,
            "chapter_count": doc["chapter_count"],
            "reading_time_minutes": doc["reading_time_minutes"],
            "complexity": complexity,
            "themes": "Документ, Текст, Информация",
            "sentiment": "Нейтральный",
            "writing_style": "Информационный",
            "key_points": [
                f"Документ на {doc['language']} языке",
                f"Содержит {doc['chapter_count']} глав",
                f"Время чтения: {doc['reading_time_minutes']} минут",
                f"Слов: {word_count}, символов: {char_count}"
            ],
            "characters": [],
            "analysis_date": datetime.now().isoformat(),
            "ai_analysis": False,
            "fallback": False
        }
        
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
        
        # Извлекаем предложения
        import re
        sentences = re.split(r'(?<=[.!?])\s+', content)
        quotes = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if 20 < len(sentence) < 150:
                quotes.append(sentence)
                if len(quotes) >= limit:
                    break
        
        if not quotes:
            quotes = [
                "Этот документ содержит ценную информацию.",
                "Автор раскрывает тему с разных сторон.",
                "Текст требует внимательного прочтения.",
                "Ключевые идеи заслуживают внимания.",
                "Материал подходит для изучения."
            ]
        
        return {
            "document_id": document_id,
            "quotes": quotes[:limit],
            "count": len(quotes),
            "ai_analysis": False,
            "fallback": False
        }
        
    except Exception as e:
        return {
            "quotes": ["Цитаты временно недоступны", "Ошибка обработки"],
            "count": 2,
            "ai_analysis": False,
            "fallback": True
        }

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"🚀 Starting Versevo Backend v5.0 on port {PORT}")
    logger.info(f"📁 Upload folder: {os.path.abspath(UPLOAD_FOLDER)}")
    logger.info(f"🔤 Translation: Simple Dictionary")
    logger.info(f"🤖 Gemini AI Analysis: {'ENABLED' if GEMINI_ENABLED else 'DISABLED'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )
