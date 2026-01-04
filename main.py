# main.py - Бэкенд Versevo с Hugging Face AI
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

class AIAnalysisRequest(BaseModel):
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

# ========== ИНИЦИАЛИЗАЦИЯ HUGGING FACE ==========
HUGGING_FACE_API_KEY = os.getenv('HUGGING_FACE_API_KEY')
HUGGING_FACE_ENABLED = False
HUGGING_FACE_MODELS = {}
HUGGING_FACE_API_URL = "https://api-inference.huggingface.co/models/"

# Словарь для хранения загруженных моделей
hf_pipelines = {
    "sentiment": None,
    "summarization": None,
    "translation": None,
    "ner": None,
}

def init_huggingface():
    """Инициализация Hugging Face моделей"""
    global HUGGING_FACE_ENABLED
    
    try:
        from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
        import torch
        
        # Проверяем наличие CUDA
        device = 0 if torch.cuda.is_available() else -1
        device_name = "CUDA" if torch.cuda.is_available() else "CPU"
        logger.info(f"🏗️ Инициализация Hugging Face на {device_name}")
        
        # Модели для русского языка
        models_config = {
            "sentiment": {
                "model": "blanchefort/rubert-base-cased-sentiment",
                "description": "Анализ тональности (русский)"
            },
            "summarization": {
                "model": "IlyaGusev/rut5_base_sum_gazeta",
                "description": "Суммаризация текста (русский)"
            },
            "ner": {
                "model": "Babelscape/wikineural-multilingual-ner",
                "description": "Распознавание именованных сущностей"
            },
            "translation_en_ru": {
                "model": "Helsinki-NLP/opus-mt-en-ru",
                "description": "Перевод EN→RU"
            },
            "translation_ru_en": {
                "model": "Helsinki-NLP/opus-mt-ru-en",
                "description": "Перевод RU→EN"
            }
        }
        
        # Загружаем модели (ленивая загрузка по требованию)
        HUGGING_FACE_MODELS.update(models_config)
        HUGGING_FACE_ENABLED = True
        
        logger.info("✅ Hugging Face инициализирован (ленивая загрузка моделей)")
        logger.info(f"📦 Доступно моделей: {len(models_config)}")
        
        # Предзагружаем только sentiment модель (самую легкую)
        try:
            logger.info("🔄 Предзагрузка модели анализа тональности...")
            hf_pipelines["sentiment"] = pipeline(
                "sentiment-analysis",
                model=models_config["sentiment"]["model"],
                device=device
            )
            logger.info("✅ Модель анализа тональности загружена")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить sentiment модель: {e}")
        
    except ImportError as e:
        logger.error(f"❌ Не удалось импортировать transformers: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Hugging Face: {e}")

# Инициализируем Hugging Face
init_huggingface()

def get_hf_pipeline(task: str, model_name: str = None):
    """Получить или загрузить pipeline для задачи"""
    if task not in hf_pipelines:
        logger.error(f"❌ Неизвестная задача: {task}")
        return None
    
    if hf_pipelines[task] is None and model_name:
        try:
            from transformers import pipeline
            import torch
            
            device = 0 if torch.cuda.is_available() else -1
            logger.info(f"🔄 Загрузка модели {model_name} для задачи {task}...")
            
            if task == "summarization":
                hf_pipelines[task] = pipeline(
                    "summarization",
                    model=model_name,
                    tokenizer=model_name,
                    device=device,
                    max_length=150,
                    min_length=30
                )
            elif task == "translation":
                hf_pipelines[task] = pipeline(
                    "translation",
                    model=model_name,
                    device=device
                )
            elif task == "ner":
                hf_pipelines[task] = pipeline(
                    "ner",
                    model=model_name,
                    device=device,
                    grouped_entities=True
                )
            
            logger.info(f"✅ Модель {model_name} загружена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели {model_name}: {e}")
            return None
    
    return hf_pipelines[task]

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

# ========== HUGGING FACE АНАЛИЗ ==========
def analyze_with_huggingface(text: str) -> Dict[str, Any]:
    """Анализ текста с помощью Hugging Face моделей"""
    result = {
        "summary": "",
        "sentiment": "Нейтральный",
        "entities": [],
        "themes": "",
        "ai_analysis": False,
        "fallback": False,
        "model_used": []
    }
    
    if not HUGGING_FACE_ENABLED or not text or len(text.strip()) < 20:
        result["fallback"] = True
        return result
    
    try:
        # 1. Анализ тональности
        sentiment_pipeline = get_hf_pipeline("sentiment")
        if sentiment_pipeline:
            try:
                sentiment_result = sentiment_pipeline(text[:512])  # Ограничиваем длину
                if sentiment_result and len(sentiment_result) > 0:
                    label = sentiment_result[0].get("label", "NEUTRAL").upper()
                    score = sentiment_result[0].get("score", 0.5)
                    
                    sentiment_map = {
                        "POSITIVE": "Положительный",
                        "NEGATIVE": "Отрицательный", 
                        "NEUTRAL": "Нейтральный"
                    }
                    
                    result["sentiment"] = sentiment_map.get(label, "Нейтральный")
                    result["sentiment_score"] = score
                    result["model_used"].append("sentiment")
                    result["ai_analysis"] = True
            except Exception as e:
                logger.warning(f"⚠️ Ошибка анализа тональности: {e}")
        
        # 2. Суммаризация (только для длинных текстов)
        if len(text.split()) > 100:
            summarization_pipeline = get_hf_pipeline(
                "summarization", 
                HUGGING_FACE_MODELS.get("summarization", {}).get("model")
            )
            
            if summarization_pipeline:
                try:
                    # Ограничиваем текст для суммаризации
                    input_text = text[:2000]  # Ограничение для памяти
                    summary_result = summarization_pipeline(
                        input_text,
                        max_length=100,
                        min_length=30,
                        do_sample=False
                    )
                    
                    if summary_result and len(summary_result) > 0:
                        result["summary"] = summary_result[0].get("summary_text", "")
                        result["model_used"].append("summarization")
                        result["ai_analysis"] = True
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка суммаризации: {e}")
        
        # 3. Извлечение именованных сущностей (NER)
        ner_pipeline = get_hf_pipeline(
            "ner", 
            HUGGING_FACE_MODELS.get("ner", {}).get("model")
        )
        
        if ner_pipeline:
            try:
                ner_result = ner_pipeline(text[:1000])
                entities = []
                
                for entity in ner_result:
                    if isinstance(entity, dict):
                        entities.append({
                            "entity": entity.get("entity_group") or entity.get("entity"),
                            "word": entity.get("word"),
                            "score": entity.get("score", 0.0)
                        })
                
                if entities:
                    result["entities"] = entities[:10]  # Ограничиваем количество
                    result["model_used"].append("ner")
                    result["ai_analysis"] = True
                    
                    # Формируем темы из сущностей
                    entity_types = [e["entity"] for e in entities[:5]]
                    if entity_types:
                        result["themes"] = ", ".join(set(entity_types))
                        
            except Exception as e:
                logger.warning(f"⚠️ Ошибка NER анализа: {e}")
        
        # Если суммаризация не сработала, создаем простую версию
        if not result.get("summary"):
            sentences = re.split(r'(?<=[.!?])\s+', text)
            if len(sentences) > 3:
                result["summary"] = " ".join(sentences[:3]) + "..."
            else:
                result["summary"] = text[:300] + "..." if len(text) > 300 else text
        
        # Если темы не определены, создаем из частых слов
        if not result.get("themes"):
            words = [w.lower() for w in re.findall(r'\b\w{4,}\b', text)]
            stopwords = {'это', 'что', 'как', 'для', 'того', 'чтобы', 'если', 'когда'}
            filtered_words = [w for w in words if w not in stopwords]
            word_freq = Counter(filtered_words)
            common_words = [word for word, _ in word_freq.most_common(3)]
            if common_words:
                result["themes"] = ", ".join(common_words)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка Hugging Face анализа: {e}")
        result["fallback"] = True
        return result

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
    
    if HUGGING_FACE_ENABLED:
        endpoints.update({
            "ai_health": "/api/analyze/ai/health",
            "ai_analyze": "/api/analyze/ai/document",
        })
    
    return {
        "message": "Versevo Backend API v5.0",
        "version": "5.0.0",
        "status": "running",
        "translation": "simple",
        "huggingface_available": HUGGING_FACE_ENABLED,
        "timestamp": datetime.now().isoformat(),
        "endpoints": endpoints
    }
@app.get("/api/flutter/health")
async def flutter_health_check():
    """Эндпоинт для healthcheck Railway/Flutter"""
    return {
        "status": "healthy", 
        "service": "versevo-backend",
        "timestamp": datetime.now().isoformat(),
        "version": "5.0.0"
    }
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "translation": "simple",
        "huggingface_available": HUGGING_FACE_ENABLED,
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
        
        target_lang = request.target_language  # Исправлено здесь
        
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

# ========== AI АНАЛИЗ ==========
@app.get("/api/analyze/ai/health")
async def ai_health_check():
    """Проверка доступности AI"""
    return {
        "status": "healthy" if HUGGING_FACE_ENABLED else "unavailable",
        "service": "huggingface",
        "available": HUGGING_FACE_ENABLED,
        "models": list(HUGGING_FACE_MODELS.keys()) if HUGGING_FACE_ENABLED else [],
        "loaded_pipelines": [k for k, v in hf_pipelines.items() if v is not None],
        "huggingface_available": HUGGING_FACE_ENABLED,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/analyze/ai/document")
async def analyze_with_ai(request: AIAnalysisRequest):
    """AI-анализ документа через Hugging Face"""
    
    if not HUGGING_FACE_ENABLED:
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
            "created_at": datetime.now().isoformat(),
            "ai_provider": "huggingface",
            "ai_status": "unavailable"
        }
    
    try:
        document_id = request.document_id
        
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # Анализ через Hugging Face
        hf_result = analyze_with_huggingface(content)
        
        # Формируем ключевые точки
        key_points = [
            f"Документ на {doc['language']} языке",
            f"Содержит {doc['chapter_count']} глав",
            f"Время чтения: {doc['reading_time_minutes']} минут",
            f"Слов: {doc['word_count']}, символов: {doc['char_count']}"
        ]
        
        # Добавляем информацию об анализе
        if hf_result.get("sentiment_score"):
            key_points.append(f"Тональность: {hf_result['sentiment']} ({hf_result['sentiment_score']:.2f})")
        
        if hf_result.get("entities"):
            entity_count = len(hf_result["entities"])
            key_points.append(f"Обнаружено сущностей: {entity_count}")
        
        # Формируем персонажей из NER сущностей
        characters = []
        if hf_result.get("entities"):
            for entity in hf_result["entities"][:5]:  # Берем только первые 5
                if entity.get("entity") in ["PER", "ORG", "LOC"]:
                    characters.append({
                        "name": entity.get("word", "Неизвестно"),
                        "type": entity.get("entity", "PER"),
                        "role": "Персонаж" if entity["entity"] == "PER" else 
                               "Организация" if entity["entity"] == "ORG" else 
                               "Локация"
                    })
        
        result = {
            "document_id": document_id,
            "summary": hf_result.get("summary", "Нет данных"),
            "themes": hf_result.get("themes", "Документ, Текст, Информация"),
            "sentiment": hf_result.get("sentiment", "Нейтральный"),
            "writing_style": "Академический" if doc['word_count'] > 1000 else "Информационный",
            "key_points": key_points,
            "characters": characters if characters else [],
            "ai_analysis": hf_result.get("ai_analysis", False),
            "fallback": hf_result.get("fallback", True),
            "model_used": hf_result.get("model_used", []),
            "ai_provider": "huggingface",
            "ai_status": "available" if hf_result.get("ai_analysis") else "fallback",
            "created_at": datetime.now().isoformat()
        }
        
        return result
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
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
            "ai_provider": "huggingface",
            "ai_status": "error",
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
            "fallback": False,
            "ai_provider": "basic",
            "ai_status": "not_used"
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
    logger.info(f"🤖 Hugging Face AI Analysis: {'ENABLED' if HUGGING_FACE_ENABLED else 'DISABLED'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )
