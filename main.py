# main.py - Бэкенд Versevo без базы данных (с добавленными эндпоинтами)
import asyncio
import time
import os
import sys
import base64
import uuid
import re
import json
import aiohttp
import google.generativeai as genai
import random
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
from collections import Counter
import logging
import tempfile
import shutil
from pathlib import Path
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
import torch
from transformers import pipeline, AutoModelForSeq2SeqLM, AutoTokenizer
import fitz  # PyMuPDF
import docx
from PIL import Image
import io
import secrets

# ========== НАСТРОЙКА APP И CORS ==========
app = FastAPI(
    title="Versevo Backend API (No Database)",
    description="Modern document reader with translation and AI features - Database moved to Flutter",
    version="9.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("versevo_nodb.log")
    ]
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
class Config:
    # Пути
    UPLOAD_FOLDER = "uploads"
    CACHE_FOLDER = "cache"
    MODELS_FOLDER = "models"
    
    # Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = "gemini-pro"
    
    # Hugging Face
    HF_TRANSLATION_MODEL = "Helsinki-NLP/opus-mt-en-ru"
    HF_SUMMARIZATION_MODEL = "Falconsai/text_summarization"
    HF_SENTIMENT_MODEL = "blanchefort/rubert-base-cased-sentiment"
    
    # Лимиты
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_CONTENT_LENGTH = 1000000  # 1M символов
    CHUNK_SIZE = 5000  # Для обработки больших документов
    
    # Кэш (в памяти вместо БД)
    IN_MEMORY_CACHE = {}
    CACHE_TTL = 3600  # 1 час

config = Config()

# Создаем директории
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(config.CACHE_FOLDER, exist_ok=True)
os.makedirs(config.MODELS_FOLDER, exist_ok=True)

# ========== В ПАМЯТИ ХРАНЕНИЕ (ЗАМЕНА БД) ==========
class InMemoryStorage:
    """Хранение данных в памяти вместо базы данных"""
    
    def __init__(self):
        self.documents = {}  # ID -> документ
        self.translations = {}  # hash -> перевод
        self.analyses = {}  # document_id -> анализ
        self.quotes = {}  # quote_id -> цитата
        self.users = {}  # user_id -> пользователь (для совместимости)
        self.next_id = 1
        
    def add_document(self, document_data: dict) -> int:
        doc_id = self.next_id
        document_data['id'] = doc_id
        document_data['created_at'] = datetime.now().isoformat()
        self.documents[doc_id] = document_data
        self.next_id += 1
        return doc_id
    
    def get_document(self, doc_id: int) -> Optional[dict]:
        return self.documents.get(doc_id)
    
    def get_all_documents(self) -> List[dict]:
        return list(self.documents.values())
    
    def delete_document(self, doc_id: int) -> bool:
        if doc_id in self.documents:
            del self.documents[doc_id]
            return True
        return False
    
    def add_translation(self, hash_key: str, translation_data: dict):
        self.translations[hash_key] = {
            **translation_data,
            'created_at': datetime.now().isoformat()
        }
    
    def get_translation(self, hash_key: str) -> Optional[dict]:
        return self.translations.get(hash_key)
    
    def add_analysis(self, document_id: int, analysis_data: dict):
        if document_id not in self.analyses:
            self.analyses[document_id] = []
        self.analyses[document_id].append({
            **analysis_data,
            'created_at': datetime.now().isoformat()
        })
    
    def get_analyses(self, document_id: int) -> List[dict]:
        return self.analyses.get(document_id, [])
    
    def add_quote(self, quote_data: dict) -> int:
        quote_id = self.next_id
        quote_data['id'] = quote_id
        quote_data['created_at'] = datetime.now().isoformat()
        self.quotes[quote_id] = quote_data
        self.next_id += 1
        return quote_id
    
    def get_all_quotes(self) -> List[dict]:
        return list(self.quotes.values())
    
    def delete_quote(self, quote_id: int) -> bool:
        if quote_id in self.quotes:
            del self.quotes[quote_id]
            return True
        return False
    
    def add_user(self, user_data: dict) -> int:
        user_id = self.next_id
        user_data['id'] = user_id
        user_data['created_at'] = datetime.now().isoformat()
        self.users[user_id] = user_data
        self.next_id += 1
        return user_id

# Создаем экземпляр хранилища в памяти
storage = InMemoryStorage()

# ========== МОДЕЛИ PYDANTIC ==========
class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    target_language: str = Field(default="ru", pattern="^(ru|en|de|fr|es|zh)$")
    source_language: Optional[str] = Field(default=None, pattern="^(ru|en|de|fr|es|zh|auto)$")
    style: str = Field(default="artistic", pattern="^(artistic|formal|simple|academic)$")

class DocumentTranslateRequest(BaseModel):
    document_id: int
    target_language: str = Field(default="ru", pattern="^(ru|en|de|fr|es|zh)$")
    source_language: Optional[str] = Field(default=None)
    style: str = Field(default="artistic")

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = Field(default="general", pattern="^(quick|standard|detailed|full)$")

class AIAnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = Field(default="full")
    language: str = Field(default="ru")
    include_summary: bool = True
    include_themes: bool = True
    include_quotes: bool = True

class FavoriteQuoteCreate(BaseModel):
    document_id: int
    quote: str = Field(..., min_length=1, max_length=2000)
    start_position: Optional[int] = Field(None, ge=0)
    end_position: Optional[int] = Field(None, ge=0)
    note: Optional[str] = Field(None, max_length=1000)

class DocumentUploadRequest(BaseModel):
    filename: str
    file_data: str  # base64
    file_size: int

class UserCreate(BaseModel):
    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: str
    password: str

# ========== ИНИЦИАЛИЗАЦИЯ МОДЕЛЕЙ AI ==========
class AIModels:
    """Класс для управления AI моделями"""
    
    def __init__(self):
        self.translator = None
        self.summarizer = None
        self.sentiment_analyzer = None
        self.gemini = None
        self.initialized = False
        
    def initialize(self):
        """Инициализация всех AI моделей"""
        if self.initialized:
            return True
            
        try:
            logger.info("🚀 Инициализация AI моделей...")
            
            # 1. Инициализация Gemini AI
            self._init_gemini()
            
            # 2. Инициализация Hugging Face моделей
            self._init_huggingface()
            
            self.initialized = True
            logger.info("✅ Все AI модели инициализированы")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации AI моделей: {e}")
            return False
    
    def _init_gemini(self):
        """Инициализация Gemini AI"""
        try:
            if config.GEMINI_API_KEY:
                genai.configure(api_key=config.GEMINI_API_KEY)
                self.gemini = genai.GenerativeModel(config.GEMINI_MODEL)
                logger.info(f"✅ Gemini AI инициализирован (модель: {config.GEMINI_MODEL})")
            else:
                logger.warning("⚠️ GEMINI_API_KEY не установлен, Gemini AI недоступен")
                self.gemini = None
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Gemini AI: {e}")
            self.gemini = None
    
    def _init_huggingface(self):
        """Инициализация Hugging Face моделей"""
        try:
            # Проверяем доступность CUDA
            if torch.cuda.is_available():
                device = 0
                device_name = "CUDA"
                logger.info("✅ CUDA доступна")
            else:
                device = -1
                device_name = "CPU"
                logger.info("⚠️ CUDA не доступна, используем CPU")
            
            logger.info(f"🔄 Загрузка Hugging Face моделей на {device_name}...")
            
            # Переводчик
            self.translator = pipeline(
                "translation",
                model=config.HF_TRANSLATION_MODEL,
                device=device,
                max_length=512
            )
            logger.info(f"✅ Переводчик загружен: {config.HF_TRANSLATION_MODEL}")
            
            # Суммаризатор
            self.summarizer = pipeline(
                "summarization",
                model=config.HF_SUMMARIZATION_MODEL,
                device=device,
                max_length=150,
                min_length=50
            )
            logger.info(f"✅ Суммаризатор загружен: {config.HF_SUMMARIZATION_MODEL}")
            
            # Анализатор тональности
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model=config.HF_SENTIMENT_MODEL,
                device=device
            )
            logger.info(f"✅ Анализатор тональности загружен: {config.HF_SENTIMENT_MODEL}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки Hugging Face моделей: {e}")
            self.translator = None
            self.summarizer = None
            self.sentiment_analyzer = None
    
    def is_gemini_available(self):
        """Проверка доступности Gemini AI"""
        return self.gemini is not None and config.GEMINI_API_KEY
    
    def is_huggingface_available(self):
        """Проверка доступности Hugging Face"""
        return all([
            self.translator is not None,
            self.summarizer is not None,
            self.sentiment_analyzer is not None
        ])
    
    async def translate_with_gemini(self, text: str, target_lang: str, source_lang: str = "auto") -> str:
        """Перевод через Gemini AI"""
        if not self.is_gemini_available():
            raise Exception("Gemini AI не доступен")
        
        try:
            prompt = f"Переведи следующий текст с {source_lang} на {target_lang}:\n\n{text}"
            
            response = await asyncio.to_thread(
                self.gemini.generate_content,
                prompt
            )
            
            if response and response.text:
                return response.text
            else:
                raise Exception("Пустой ответ от Gemini AI")
                
        except Exception as e:
            logger.error(f"❌ Ошибка перевода Gemini AI: {e}")
            raise
    
    def translate_with_huggingface(self, text: str, target_lang: str, source_lang: str = "en") -> str:
        """Перевод через Hugging Face"""
        if not self.translator:
            raise Exception("Hugging Face переводчик не доступен")
        
        try:
            if source_lang == "en" and target_lang == "ru":
                result = self.translator(text, max_length=512, truncation=True)
                if result and len(result) > 0:
                    return result[0]['translation_text']
            
            return text
            
        except Exception as e:
            logger.error(f"❌ Ошибка перевода Hugging Face: {e}")
            raise
    
    def summarize_with_huggingface(self, text: str) -> str:
        """Суммаризация через Hugging Face"""
        if not self.summarizer:
            raise Exception("Hugging Face суммаризатор не доступен")
        
        try:
            if len(text) > 1000:
                text = text[:1000] + "..."
            
            result = self.summarizer(text, max_length=150, min_length=50, do_sample=False)
            if result and len(result) > 0:
                return result[0]['summary_text']
            return text[:200] + "..."
            
        except Exception as e:
            logger.error(f"❌ Ошибка суммаризации: {e}")
            return text[:200] + "..."
    
    def analyze_sentiment_with_huggingface(self, text: str) -> Dict[str, Any]:
        """Анализ тональности через Hugging Face"""
        if not self.sentiment_analyzer:
            raise Exception("Hugging Face анализатор тональности не доступен")
        
        try:
            if len(text) > 512:
                text = text[:512]
            
            result = self.sentiment_analyzer(text)
            if result and len(result) > 0:
                sentiment_map = {
                    "POSITIVE": "Положительный",
                    "NEGATIVE": "Отрицательный",
                    "NEUTRAL": "Нейтральный",
                    "LABEL_0": "Отрицательный",
                    "LABEL_1": "Нейтральный",
                    "LABEL_2": "Положительный"
                }
                
                label = result[0]['label'].upper()
                score = result[0]['score']
                
                return {
                    "sentiment": sentiment_map.get(label, "Нейтральный"),
                    "confidence": score,
                    "original_label": label
                }
            
            return {"sentiment": "Нейтральный", "confidence": 0.5}
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа тональности: {e}")
            return {"sentiment": "Нейтральный", "confidence": 0.5}
    
    async def analyze_with_gemini(self, text: str, analysis_type: str = "full") -> Dict[str, Any]:
        """Полный анализ через Gemini AI"""
        if not self.is_gemini_available():
            raise Exception("Gemini AI не доступен")
        
        try:
            prompts = {
                "full": f"Проанализируй следующий текст и предоставь:\n1. Краткое содержание (1-2 абзаца)\n2. Основные темы\n3. Тональность (положительная/отрицательная/нейтральная)\n4. Ключевые моменты\n5. Стиль письма\n\nТекст: {text[:3000]}",
                "summary": f"Сделай краткое содержание следующего текста (2-3 предложения):\n\n{text[:2000]}",
                "themes": f"Выдели основные темы следующего текста (3-5 тем):\n\n{text[:2000]}",
                "sentiment": f"Определи тональность следующего текста (положительная/отрицательная/нейтральная):\n\n{text[:1000]}"
            }
            
            prompt = prompts.get(analysis_type, prompts["full"])
            
            response = await asyncio.to_thread(
                self.gemini.generate_content,
                prompt
            )
            
            if response and response.text:
                return self._parse_gemini_response(response.text, analysis_type)
            else:
                raise Exception("Пустой ответ от Gemini AI")
                
        except Exception as e:
            logger.error(f"❌ Ошибка анализа Gemini AI: {e}")
            raise
    
    def _parse_gemini_response(self, response_text: str, analysis_type: str) -> Dict[str, Any]:
        """Парсинг ответа Gemini AI"""
        result = {
            "summary": "",
            "themes": [],
            "sentiment": "Нейтральный",
            "writing_style": "Информационный",
            "key_points": [],
            "ai_provider": "gemini",
            "analysis_type": analysis_type
        }
        
        try:
            lines = response_text.split('\n')
            
            for line in lines:
                line = line.strip()
                
                if not line:
                    continue
                
                if "краткое содержание" in line.lower() or "summary" in line.lower():
                    result["summary"] = line
                elif "темы" in line.lower() or "themes" in line.lower():
                    if ":" in line:
                        themes_text = line.split(":", 1)[1].strip()
                        result["themes"] = [t.strip() for t in themes_text.split(",") if t.strip()]
                elif "тональность" in line.lower() or "sentiment" in line.lower():
                    if ":" in line:
                        sentiment_text = line.split(":", 1)[1].strip().lower()
                        if "положительн" in sentiment_text:
                            result["sentiment"] = "Положительный"
                        elif "отрицательн" in sentiment_text:
                            result["sentiment"] = "Отрицательный"
                        else:
                            result["sentiment"] = "Нейтральный"
                elif "ключевые" in line.lower() or "key points" in line.lower():
                    if ":" in line:
                        points_text = line.split(":", 1)[1].strip()
                        result["key_points"] = [p.strip() for p in points_text.split(".") if p.strip()]
                elif "стиль" in line.lower() or "style" in line.lower():
                    if ":" in line:
                        result["writing_style"] = line.split(":", 1)[1].strip()
            
            if not result["summary"] and len(response_text) > 50:
                result["summary"] = response_text[:500]
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга ответа Gemini: {e}")
            result["summary"] = response_text[:500]
            return result

# Создаем экземпляр AI моделей
ai_models = AIModels()

# ========== ИНИЦИАЛИЗАЦИЯ NLTK ==========
def init_nltk():
    """Инициализация NLTK"""
    try:
        nltk_data_path = os.path.join(config.MODELS_FOLDER, "nltk_data")
        if not os.path.exists(nltk_data_path):
            os.makedirs(nltk_data_path, exist_ok=True)
        
        nltk.data.path.append(nltk_data_path)
        
        required_data = ['punkt', 'stopwords', 'punkt_tab']
        
        for data in required_data:
            try:
                nltk.data.find(f'tokenizers/{data}' if data == 'punkt' else f'corpora/{data}')
            except LookupError:
                logger.info(f"📥 Скачивание NLTK данных: {data}")
                nltk.download(data, quiet=True, download_dir=nltk_data_path)
        
        logger.info("✅ NLTK инициализирован")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации NLTK: {e}")
        return False

# ========== УТИЛИТЫ ==========
def save_base64_file(file_data: str, filename: str) -> str:
    """Сохранение base64 файла"""
    try:
        file_bytes = base64.b64decode(file_data)
        file_ext = os.path.splitext(filename)[1] or '.txt'
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(config.UPLOAD_FOLDER, unique_filename)
        
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        
        return file_path
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения файла: {e}")
        raise

def extract_text_from_file(file_path: str) -> tuple[str, str]:
    """Извлечение текста из файла с определением типа"""
    try:
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.pdf':
            text = extract_text_from_pdf(file_path)
            file_type = 'pdf'
        elif file_ext in ['.docx', '.doc']:
            text = extract_text_from_docx(file_path)
            file_type = 'docx' if file_ext == '.docx' else 'doc'
        elif file_ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            file_type = 'txt'
        else:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                file_type = 'txt'
            except:
                text = ""
                file_type = 'unknown'
        
        return text, file_type
        
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения текста: {e}")
        return "", "unknown"

def extract_text_from_pdf(pdf_path: str) -> str:
    """Извлечение текста из PDF"""
    try:
        text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
        return text
    except Exception as e:
        logger.error(f"❌ Ошибка чтения PDF: {e}")
        return ""

def extract_text_from_docx(docx_path: str) -> str:
    """Извлечение текста из DOCX"""
    try:
        doc = docx.Document(docx_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()])
        return text
    except Exception as e:
        logger.error(f"❌ Ошибка чтения DOCX: {e}")
        return ""

def detect_language(text: str) -> str:
    """Определение языка текста"""
    try:
        cyrillic_count = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
        latin_count = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
        
        if cyrillic_count > latin_count * 1.5:
            return "ru"
        elif latin_count > cyrillic_count * 1.5:
            return "en"
        else:
            return "en"
    except:
        return "en"

def split_into_chapters(text: str) -> List[Dict[str, str]]:
    """Разделение текста на главы"""
    chapters = []
    
    if not text:
        return [{"title": "Документ", "content": "Нет содержимого"}]
    
    patterns = [
        r'^\s*(?:Глава|ГЛАВА|Г\.)\s+[IVXLCDM\d]+[\.\s].*$',
        r'^\s*(?:Chapter|CHAPTER|Ch\.)\s+[IVXLCDM\d]+[\.\s].*$',
        r'^\s*[IVXLCDM\d]+[\.\)]\s+.*$',
        r'^\s*\d+[\.\)]\s+.*$',
        r'^\s*[A-Z][A-Z\s]{2,}[\.\?!]?$',
    ]
    
    lines = text.split('\n')
    current_chapter = {"title": "Начало", "content": ""}
    
    for line in lines:
        line = line.strip()
        
        is_chapter_title = False
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                is_chapter_title = True
                break
        
        if is_chapter_title and current_chapter["content"]:
            chapters.append(current_chapter.copy())
            current_chapter = {"title": line[:100], "content": ""}
        else:
            if current_chapter["content"]:
                current_chapter["content"] += "\n" + line
            else:
                current_chapter["content"] = line
    
    if current_chapter["content"]:
        chapters.append(current_chapter)
    
    if not chapters:
        chunk_size = 5000
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chapters.append({
                    "title": f"Часть {len(chapters) + 1}",
                    "content": chunk
                })
    
    return chapters

def calculate_statistics(text: str) -> Dict[str, Any]:
    """Расчет статистики текста"""
    try:
        words = word_tokenize(text) if text else []
        sentences = sent_tokenize(text) if text else []
        
        word_count = len(words)
        char_count = len(text)
        sentence_count = len(sentences)
        
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
        avg_word_length = sum(len(w) for w in words) / word_count if word_count > 0 else 0
        
        reading_time = max(1, word_count // 200)
        
        if avg_sentence_length < 10:
            complexity = "Простой"
        elif avg_sentence_length < 20:
            complexity = "Средний"
        else:
            complexity = "Сложный"
        
        return {
            "word_count": word_count,
            "char_count": char_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": round(avg_sentence_length, 1),
            "avg_word_length": round(avg_word_length, 1),
            "reading_time_minutes": reading_time,
            "complexity": complexity
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка расчета статистики: {e}")
        return {
            "word_count": len(text.split()) if text else 0,
            "char_count": len(text) if text else 0,
            "reading_time_minutes": 1
        }

def generate_hash(text: str) -> str:
    """Генерация хэша для текста"""
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

# ========== HEALTHCHECK ==========
@app.get("/")
async def root():
    return {
        "message": "Versevo Backend API v9.0 (No Database)",
        "version": "9.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "note": "База данных перенесена во Flutter приложение",
        "endpoints": [
            "/docs - документация API",
            "/health - проверка здоровья",
            "/api/flutter/health - проверка для Flutter",
            "/api/documents - управление документами",
            "/api/translate - перевод",
            "/api/analyze - анализ",
            "/api/quotes - избранные цитаты"
        ]
    }

@app.get("/health")
async def health_check():
    """Полная проверка здоровья системы"""
    health_status = {
        "status": "healthy",
        "service": "versevo-backend-nodb",
        "version": "9.0.0",
        "timestamp": datetime.now().isoformat(),
        "note": "Работает без базы данных, данные в памяти",
        "components": {}
    }
    
    # Проверка AI моделей
    health_status["components"]["ai_models"] = {
        "huggingface": {
            "available": ai_models.is_huggingface_available(),
            "translator": ai_models.translator is not None,
            "summarizer": ai_models.summarizer is not None,
            "sentiment_analyzer": ai_models.sentiment_analyzer is not None
        },
        "gemini": {
            "available": ai_models.is_gemini_available(),
            "api_key_set": bool(config.GEMINI_API_KEY)
        }
    }
    
    # Проверка файловой системы
    try:
        upload_folder_exists = os.path.exists(config.UPLOAD_FOLDER)
        health_status["components"]["file_system"] = {
            "status": "healthy" if upload_folder_exists else "warning",
            "upload_folder": upload_folder_exists,
            "cache_folder": os.path.exists(config.CACHE_FOLDER)
        }
    except:
        health_status["components"]["file_system"] = {"status": "error"}
    
    # Данные в памяти
    health_status["components"]["in_memory_storage"] = {
        "documents_count": len(storage.documents),
        "translations_count": len(storage.translations),
        "analyses_count": sum(len(v) for v in storage.analyses.values()),
        "quotes_count": len(storage.quotes)
    }
    
    return health_status

# ========== ДОБАВЛЕННЫЕ ЭНДПОИНТЫ ДЛЯ Flutter ==========
@app.get("/api/flutter/health")
async def flutter_health_check():
    """Упрощенная проверка для Flutter (возвращает всегда здоров)"""
    return {
        "status": "healthy",
        "database": "moved_to_flutter",
        "ai_models": ai_models.initialized,
        "timestamp": datetime.now().isoformat(),
        "message": "База данных перенесена во Flutter приложение"
    }

@app.get("/api/db/tables")
async def get_database_tables():
    """Получение информации о таблицах (возвращает пустые данные)"""
    return {
        "status": "success",
        "note": "База данных перенесена во Flutter приложение",
        "tables": [],
        "data": {},
        "total_tables": 0
    }

@app.get("/api/sql/examples")
async def get_sql_examples():
    """Примеры SQL запросов для Flutter"""
    return {
        "examples": [
            {
                "name": "Активные пользователи",
                "sql": "SELECT * FROM users WHERE last_login >= NOW() - INTERVAL '7 days'",
                "description": "Пользователи активные за последние 7 дней"
            },
            {
                "name": "Статистика документов",
                "sql": "SELECT language, COUNT(*) as count, AVG(word_count) as avg_words FROM documents GROUP BY language",
                "description": "Статистика документов по языкам"
            }
        ],
        "note": "Эти запросы выполняются в Flutter приложении с локальной MySQL"
    }

@app.post("/api/dev/fix-database")
async def fix_database():
    """Заглушка для совместимости"""
    return {
        "status": "success",
        "message": "База данных перенесена во Flutter приложение",
        "timestamp": datetime.now().isoformat()
    }

# ========== ОТЧЕТЫ (МОК ДАННЫЕ) ==========

@app.get("/api/reports/user-activity")
async def get_user_activity_report(start_date: str = None, end_date: str = None):
    """Мок отчет по активности пользователей"""
    mock_users = [
        {
            "id": 1,
            "email": "alexey.ivanov@mail.ru",
            "username": "Алексей Иванов",
            "created_at": "2026-01-05T14:20:00",
            "last_login": "2026-01-20T15:30:00",
            "documents_count": 3,
            "notes_count": 2,
            "activity_status": "active"
        },
        {
            "id": 2,
            "email": "maria.smirnova@gmail.com",
            "username": "Мария Смирнова",
            "created_at": "2026-01-07T10:15:00",
            "last_login": "2026-01-20T11:45:00",
            "documents_count": 2,
            "notes_count": 1,
            "activity_status": "active"
        }
    ]
    
    return {
        "report_type": "user_activity_mock",
        "summary": {
            "total_users": 2,
            "active_users": 2,
            "total_documents": 5
        },
        "data": mock_users,
        "is_mock": True
    }

@app.get("/api/reports/document-statistics")
async def get_document_statistics_report():
    """Мок статистика по документам"""
    return {
        "report_type": "document_statistics_mock",
        "summary": {
            "total_documents": len(storage.documents),
            "total_words": sum(d.get("word_count", 0) for d in storage.documents.values()),
            "languages_distribution": {"ru": 2, "en": 1}
        },
        "data": list(storage.documents.values()),
        "is_mock": True
    }

# ========== ДОКУМЕНТЫ ==========
@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: DocumentUploadRequest):
    """Загрузка документа в формате base64"""
    try:
        if request.file_size > config.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл слишком большой. Максимум: {config.MAX_FILE_SIZE // 1024 // 1024}MB")
        
        logger.info(f"📤 Загрузка файла: {request.filename}")
        
        file_path = save_base64_file(request.file_data, request.filename)
        content, file_type = extract_text_from_file(file_path)
        
        if not content.strip():
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файла")
        
        language = detect_language(content)
        chapters = split_into_chapters(content)
        stats = calculate_statistics(content)
        
        # Сохраняем в памяти вместо БД
        document_data = {
            "filename": request.filename,
            "content": content[:config.MAX_CONTENT_LENGTH],
            "language": language,
            "file_type": file_type,
            "file_path": file_path,
            "file_size": request.file_size,
            "word_count": stats["word_count"],
            "char_count": stats["char_count"],
            "chapter_count": len(chapters),
            "reading_time_minutes": stats["reading_time_minutes"]
        }
        
        doc_id = storage.add_document(document_data)
        
        logger.info(f"✅ Документ загружен: ID {doc_id}, {stats['word_count']} слов")
        
        return {
            "id": doc_id,
            "filename": request.filename,
            "language": language,
            "file_type": file_type,
            "word_count": stats["word_count"],
            "char_count": stats["char_count"],
            "chapter_count": len(chapters),
            "reading_time_minutes": stats["reading_time_minutes"],
            "created_at": datetime.now().isoformat(),
            "content_preview": content[:300] + "..." if len(content) > 300 else content,
            "chapters": chapters
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/api/documents")
async def get_documents(skip: int = 0, limit: int = 50):
    """Получение списка документов"""
    try:
        documents = storage.get_all_documents()
        if skip > 0:
            documents = documents[skip:]
        if limit > 0:
            documents = documents[:limit]
        
        return documents
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения документов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения документов: {str(e)}")

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int):
    """Получение документа по ID"""
    try:
        document = storage.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        chapters = split_into_chapters(document.get("content", ""))
        
        return {
            "id": document_id,
            "filename": document.get("filename", ""),
            "content": document.get("content", ""),
            "language": document.get("language", "en"),
            "file_type": document.get("file_type", "txt"),
            "word_count": document.get("word_count", 0),
            "char_count": document.get("char_count", 0),
            "chapter_count": document.get("chapter_count", 1),
            "reading_time_minutes": document.get("reading_time_minutes", 1),
            "created_at": document.get("created_at", datetime.now().isoformat()),
            "chapters": chapters
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения документа: {str(e)}")

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int):
    """Удаление документа"""
    try:
        document = storage.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        # Удаляем файл с диска
        file_path = document.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        # Удаляем из памяти
        storage.delete_document(document_id)
        
        logger.info(f"🗑️ Документ удален: ID {document_id}")
        
        return {
            "status": "success",
            "message": f"Документ {document_id} удален",
            "deleted_id": document_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка удаления документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {str(e)}")

# ========== ПЕРЕВОД ==========
@app.post("/api/translate/text")
async def translate_text(request: TranslateRequest):
    """Перевод текста"""
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Текст пустой")
        
        source_lang = request.source_language or detect_language(request.text)
        target_lang = request.target_language
        
        logger.info(f"🌐 Перевод текста: {source_lang} → {target_lang}, {len(request.text)} символов")
        
        # Генерируем хэш для кэширования
        text_hash = generate_hash(f"{request.text}:{source_lang}:{target_lang}:{request.style}")
        
        # Проверяем кэш
        cached = storage.get_translation(text_hash)
        if cached:
            logger.info("✅ Использован кэшированный перевод")
            return {
                "original_text": request.text,
                "translated_text": cached.get("translated_text", ""),
                "source_language": source_lang,
                "target_language": target_lang,
                "style": request.style,
                "translation_service": cached.get("translation_service", "cached"),
                "original_length": len(request.text),
                "translated_length": len(cached.get("translated_text", "")),
                "translation_timestamp": cached.get("created_at", datetime.now().isoformat()),
                "cached": True
            }
        
        translated_text = None
        translation_service = "unknown"
        
        # Пробуем Hugging Face
        try:
            if ai_models.is_huggingface_available():
                translated_text = ai_models.translate_with_huggingface(
                    request.text, target_lang, source_lang
                )
                translation_service = "huggingface"
                logger.info("✅ Перевод выполнен через Hugging Face")
        except Exception as hf_error:
            logger.warning(f"⚠️ Hugging Face перевод не удался: {hf_error}")
        
        # Пробуем Gemini
        if not translated_text and ai_models.is_gemini_available():
            try:
                translated_text = await ai_models.translate_with_gemini(
                    request.text, target_lang, source_lang
                )
                translation_service = "gemini"
                logger.info("✅ Перевод выполнен через Gemini AI")
            except Exception as gemini_error:
                logger.warning(f"⚠️ Gemini AI перевод не удался: {gemini_error}")
        
        # Fallback
        if not translated_text:
            translation_service = "fallback"
            
            if source_lang == "en" and target_lang == "ru":
                translations = {
                    "hello": "привет", "world": "мир", "book": "книга",
                    "read": "читать", "document": "документ", "text": "текст",
                    "translate": "переводить", "analysis": "анализ"
                }
                
                words = request.text.split()
                translated_words = []
                for word in words:
                    translated_words.append(translations.get(word.lower(), word))
                translated_text = " ".join(translated_words)
            else:
                translated_text = f"[Перевод недоступен] {request.text}"
        
        # Применяем стиль
        if request.style == "artistic":
            translated_text = f"🎨 {translated_text}"
        elif request.style == "formal":
            translated_text = f"📄 {translated_text}"
        elif request.style == "academic":
            translated_text = f"📚 {translated_text}"
        
        # Сохраняем в кэш
        storage.add_translation(text_hash, {
            "original_text": request.text,
            "translated_text": translated_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "style": request.style,
            "translation_service": translation_service
        })
        
        return {
            "original_text": request.text,
            "translated_text": translated_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "style": request.style,
            "translation_service": translation_service,
            "original_length": len(request.text),
            "translated_length": len(translated_text),
            "translation_timestamp": datetime.now().isoformat(),
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка перевода: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка перевода: {str(e)}")

@app.post("/api/translate/document/{document_id}")
async def translate_document(
    document_id: int,
    request: DocumentTranslateRequest
):
    """Перевод всего документа"""
    try:
        document = storage.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        content = document.get("content", "")
        if not content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        source_lang = request.source_language or document.get("language", "en")
        target_lang = request.target_language
        
        logger.info(f"🌐 Перевод документа {document_id}: {source_lang} → {target_lang}")
        
        # Разбиваем на части
        chunks = []
        chunk_size = 2000
        
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk)
        
        translated_chunks = []
        translation_service = "unknown"
        
        # Переводим каждую часть
        for i, chunk in enumerate(chunks):
            logger.info(f"🔄 Перевод части {i+1}/{len(chunks)} ({len(chunk)} символов)")
            
            try:
                if ai_models.is_huggingface_available():
                    translated_chunk = ai_models.translate_with_huggingface(
                        chunk, target_lang, source_lang
                    )
                    translation_service = "huggingface"
                elif ai_models.is_gemini_available():
                    translated_chunk = await ai_models.translate_with_gemini(
                        chunk, target_lang, source_lang
                    )
                    translation_service = "gemini"
                else:
                    if source_lang == "en" and target_lang == "ru":
                        translated_chunk = f"[Часть {i+1}] {chunk[:500]}..."
                    else:
                        translated_chunk = f"[Перевод недоступен] {chunk[:500]}..."
                    translation_service = "fallback"
                
                translated_chunks.append(translated_chunk)
                
            except Exception as chunk_error:
                logger.error(f"❌ Ошибка перевода части {i+1}: {chunk_error}")
                translated_chunks.append(f"[Ошибка перевода] {chunk[:500]}...")
        
        # Собираем переведенный документ
        translated_content = "\n\n".join(translated_chunks)
        
        # Применяем стиль
        if request.style == "artistic":
            translated_content = f"🎨 ХУДОЖЕСТВЕННЫЙ ПЕРЕВОД\n\n{translated_content}"
        elif request.style == "formal":
            translated_content = f"📄 ФОРМАЛЬНЫЙ ПЕРЕВОД\n\n{translated_content}"
        elif request.style == "academic":
            translated_content = f"📚 АКАДЕМИЧЕСКИЙ ПЕРЕВОД\n\n{translated_content}"
        
        # Создаем новый документ с переводом
        translated_doc_data = {
            "filename": f"translated_{target_lang}_{document.get('filename', 'document')}",
            "content": translated_content,
            "language": target_lang,
            "file_type": document.get("file_type", "txt"),
            "file_path": f"{document.get('file_path', '')}.translated",
            "file_size": len(translated_content.encode('utf-8')),
            "word_count": len(translated_content.split()),
            "char_count": len(translated_content),
            "chapter_count": document.get("chapter_count", 1),
            "reading_time_minutes": document.get("reading_time_minutes", 1)
        }
        
        translated_doc_id = storage.add_document(translated_doc_data)
        
        logger.info(f"✅ Документ переведен: новый ID {translated_doc_id}")
        
        return {
            "document_id": document_id,
            "translated_document_id": translated_doc_id,
            "original_filename": document.get("filename", ""),
            "translated_filename": translated_doc_data["filename"],
            "source_language": source_lang,
            "target_language": target_lang,
            "style": request.style,
            "translation_service": translation_service,
            "original_length": len(content),
            "translated_length": len(translated_content),
            "chunks_translated": len(chunks),
            "translation_timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка перевода документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка перевода документа: {str(e)}")

# ========== АНАЛИЗ ==========
@app.post("/api/analyze")
async def analyze_document(request: AnalysisRequest):
    """Базовый анализ документа"""
    try:
        document = storage.get_document(request.document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        content = document.get("content", "")
        if not content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        logger.info(f"🔍 Базовый анализ документа {request.document_id}")
        
        sentences = sent_tokenize(content) if len(content) > 100 else [content]
        
        if len(sentences) >= 3:
            summary = " ".join(sentences[:3])
        else:
            summary = content[:500] + "..." if len(content) > 500 else content
        
        themes = []
        words = word_tokenize(content.lower())
        word_freq = Counter(words)
        
        stop_words = set(stopwords.words('russian' if document.get("language") == 'ru' else 'english'))
        common_words = [word for word, count in word_freq.most_common(20) 
                       if word not in stop_words and len(word) > 3]
        
        themes = common_words[:5]
        
        sentiment = "Нейтральный"
        if ai_models.is_huggingface_available():
            try:
                sentiment_result = ai_models.analyze_sentiment_with_huggingface(content[:512])
                sentiment = sentiment_result["sentiment"]
            except:
                pass
        
        stats = calculate_statistics(content)
        
        avg_sentence_len = stats["avg_sentence_length"]
        if avg_sentence_len > 25:
            writing_style = "Академический"
        elif avg_sentence_len > 15:
            writing_style = "Литературный"
        else:
            writing_style = "Информационный"
        
        key_points = [
            f"Объем: {stats['word_count']} слов",
            f"Сложность: {stats['complexity']}",
            f"Время чтения: {stats['reading_time_minutes']} минут",
            f"Язык: {document.get('language', 'unknown')}"
        ]
        
        if themes:
            key_points.append(f"Основные темы: {', '.join(themes[:3])}")
        
        analysis_data = {
            "document_id": request.document_id,
            "analysis_type": request.analysis_type,
            "summary": summary,
            "themes": themes,
            "sentiment": sentiment,
            "writing_style": writing_style,
            "key_points": key_points,
            "statistics": stats,
            "ai_analysis": False
        }
        
        storage.add_analysis(request.document_id, analysis_data)
        
        return {
            "document_id": request.document_id,
            "filename": document.get("filename", ""),
            "language": document.get("language", "en"),
            "summary": summary,
            "themes": themes,
            "sentiment": sentiment,
            "writing_style": writing_style,
            "key_points": key_points,
            "statistics": stats,
            "ai_analysis": False,
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

@app.post("/api/analyze/ai/document")
async def analyze_with_ai(request: AIAnalysisRequest):
    """AI анализ документа"""
    try:
        document = storage.get_document(request.document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        content = document.get("content", "")
        if not content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        logger.info(f"🤖 AI анализ документа {request.document_id}")
        
        content_for_analysis = content[:5000]
        
        ai_provider = None
        ai_analysis = {}
        
        if ai_models.is_gemini_available():
            try:
                ai_analysis = await ai_models.analyze_with_gemini(content_for_analysis, request.analysis_type)
                ai_provider = "gemini"
                logger.info("✅ Анализ выполнен через Gemini AI")
            except Exception as gemini_error:
                logger.warning(f"⚠️ Gemini AI анализ не удался: {gemini_error}")
        
        if not ai_analysis and ai_models.is_huggingface_available():
            try:
                summary = ai_models.summarize_with_huggingface(content_for_analysis)
                sentiment_result = ai_models.analyze_sentiment_with_huggingface(content_for_analysis)
                
                words = word_tokenize(content_for_analysis.lower())
                word_freq = Counter(words)
                stop_words = set(stopwords.words('russian' if document.get("language") == 'ru' else 'english'))
                themes = [word for word, count in word_freq.most_common(10) 
                         if word not in stop_words and len(word) > 3][:5]
                
                ai_analysis = {
                    "summary": summary,
                    "themes": themes,
                    "sentiment": sentiment_result["sentiment"],
                    "writing_style": "Информационный",
                    "key_points": [
                        f"Проанализировано с помощью Hugging Face",
                        f"Тональность: {sentiment_result['sentiment']}",
                        f"Уверенность: {sentiment_result['confidence']:.2f}"
                    ],
                    "ai_provider": "huggingface"
                }
                
                ai_provider = "huggingface"
                logger.info("✅ Анализ выполнен через Hugging Face")
                
            except Exception as hf_error:
                logger.warning(f"⚠️ Hugging Face анализ не удался: {hf_error}")
        
        if not ai_analysis:
            sentences = sent_tokenize(content_for_analysis) if len(content_for_analysis) > 100 else [content_for_analysis]
            summary = " ".join(sentences[:3]) if len(sentences) >= 3 else content_for_analysis[:500]
            
            ai_analysis = {
                "summary": summary,
                "themes": ["Текст", "Документ", "Информация"],
                "sentiment": "Нейтральный",
                "writing_style": "Информационный",
                "key_points": [
                    "AI анализ временно недоступен",
                    "Используется упрощенный анализ",
                    "Попробуйте позже"
                ],
                "ai_provider": "fallback"
            }
            
            ai_provider = "fallback"
        
        stats = calculate_statistics(content_for_analysis)
        
        analysis_data = {
            "document_id": request.document_id,
            "analysis_type": request.analysis_type,
            "summary": ai_analysis.get("summary", ""),
            "themes": ai_analysis.get("themes", []),
            "sentiment": ai_analysis.get("sentiment", "Нейтральный"),
            "writing_style": ai_analysis.get("writing_style", "Информационный"),
            "key_points": ai_analysis.get("key_points", []),
            "statistics": stats,
            "ai_analysis": True,
            "ai_provider": ai_provider
        }
        
        storage.add_analysis(request.document_id, analysis_data)
        
        return {
            "document_id": request.document_id,
            "filename": document.get("filename", ""),
            "language": document.get("language", "en"),
            "summary": ai_analysis.get("summary", ""),
            "themes": ai_analysis.get("themes", []),
            "sentiment": ai_analysis.get("sentiment", "Нейтральный"),
            "writing_style": ai_analysis.get("writing_style", "Информационный"),
            "key_points": ai_analysis.get("key_points", []),
            "statistics": stats,
            "ai_analysis": True,
            "ai_provider": ai_provider,
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка AI анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка AI анализа: {str(e)}")

@app.get("/api/analyze/ai/health")
async def ai_health_check():
    """Проверка доступности AI"""
    return {
        "status": "ready" if ai_models.initialized else "initializing",
        "huggingface": {
            "available": ai_models.is_huggingface_available(),
            "translator": ai_models.translator is not None,
            "summarizer": ai_models.summarizer is not None,
            "sentiment_analyzer": ai_models.sentiment_analyzer is not None
        },
        "gemini": {
            "available": ai_models.is_gemini_available(),
            "api_key_set": bool(config.GEMINI_API_KEY)
        },
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/analyze/gemini/document")
async def analyze_with_gemini(request: AIAnalysisRequest):
    """Анализ документа через Gemini AI"""
    try:
        if not ai_models.is_gemini_available():
            raise HTTPException(status_code=503, detail="Gemini AI не доступен. Установите GEMINI_API_KEY.")
        
        document = storage.get_document(request.document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        content = document.get("content", "")
        if not content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        logger.info(f"🌟 Gemini AI анализ документа {request.document_id}")
        
        content_for_analysis = content[:10000]
        ai_analysis = await ai_models.analyze_with_gemini(content_for_analysis, request.analysis_type)
        stats = calculate_statistics(content_for_analysis)
        
        analysis_data = {
            "document_id": request.document_id,
            "analysis_type": request.analysis_type,
            "summary": ai_analysis.get("summary", ""),
            "themes": ai_analysis.get("themes", []),
            "sentiment": ai_analysis.get("sentiment", "Нейтральный"),
            "writing_style": ai_analysis.get("writing_style", "Информационный"),
            "key_points": ai_analysis.get("key_points", []),
            "statistics": stats,
            "ai_analysis": True,
            "ai_provider": "gemini"
        }
        
        storage.add_analysis(request.document_id, analysis_data)
        
        return {
            "document_id": request.document_id,
            "filename": document.get("filename", ""),
            "language": document.get("language", "en"),
            "summary": ai_analysis.get("summary", ""),
            "themes": ai_analysis.get("themes", []),
            "sentiment": ai_analysis.get("sentiment", "Нейтральный"),
            "writing_style": ai_analysis.get("writing_style", "Информационный"),
            "key_points": ai_analysis.get("key_points", []),
            "statistics": stats,
            "ai_analysis": True,
            "ai_provider": "gemini",
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка Gemini AI анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка Gemini AI анализа: {str(e)}")

# ========== ЦИТАТЫ ==========
@app.get("/api/documents/{document_id}/quotes")
async def get_document_quotes(document_id: int, limit: int = 5):
    """Получение цитат из документа"""
    try:
        document = storage.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        content = document.get("content", "")
        if not content:
            return {
                "document_id": document_id,
                "quotes": ["Документ не содержит текста"],
                "count": 1
            }
        
        sentences = sent_tokenize(content)
        quotes = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if 20 < len(sentence) < 200:
                quotes.append(sentence)
                if len(quotes) >= limit * 3:
                    break
        
        if len(quotes) < limit:
            words = word_tokenize(content.lower())
            word_freq = Counter(words)
            stop_words = set(stopwords.words('russian' if document.get("language") == 'ru' else 'english'))
            
            significant_words = [word for word, count in word_freq.most_common(50) 
                               if word not in stop_words and len(word) > 3]
            
            for i in range(limit - len(quotes)):
                if i < len(significant_words):
                    quotes.append(f"Важное понятие: '{significant_words[i]}'")
                else:
                    quotes.append("Эта мысль заслуживает внимания.")
        
        quotes = quotes[:limit]
        
        return {
            "document_id": document_id,
            "quotes": quotes,
            "count": len(quotes),
            "ai_generated": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения цитат: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения цитат: {str(e)}")

# ========== ИЗБРАННЫЕ ЦИТАТЫ ==========
@app.post("/api/quotes/favorites")
async def add_favorite_quote(request: FavoriteQuoteCreate):
    """Добавление цитаты в избранное"""
    try:
        document = storage.get_document(request.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        quote_data = {
            "document_id": request.document_id,
            "quote": request.quote,
            "start_position": request.start_position,
            "end_position": request.end_position,
            "note": request.note,
            "document_title": document.get("filename", ""),
            "document_language": document.get("language", "en")
        }
        
        quote_id = storage.add_quote(quote_data)
        
        logger.info(f"❤️ Добавлена избранная цитата: ID {quote_id}")
        
        return {
            "id": quote_id,
            "quote": request.quote,
            "document_id": request.document_id,
            "document_title": document.get("filename", ""),
            "created_at": datetime.now().isoformat(),
            "note": request.note,
            "status": "added_to_favorites"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка добавления избранной цитаты: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка добавления цитаты: {str(e)}")

@app.get("/api/quotes/favorites")
async def get_favorite_quotes(skip: int = 0, limit: int = 50):
    """Получение списка избранных цитат"""
    try:
        quotes = storage.get_all_quotes()
        if skip > 0:
            quotes = quotes[skip:]
        if limit > 0:
            quotes = quotes[:limit]
        
        return quotes
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения избранных цитат: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения цитат: {str(e)}")

@app.delete("/api/quotes/favorites/{quote_id}")
async def delete_favorite_quote(quote_id: int):
    """Удаление цитаты из избранного"""
    try:
        if not storage.delete_quote(quote_id):
            raise HTTPException(status_code=404, detail="Цитата не найдена")
        
        logger.info(f"🗑️ Удалена избранная цитата: ID {quote_id}")
        
        return {
            "status": "success",
            "message": f"Цитата {quote_id} удалена из избранного",
            "deleted_id": quote_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка удаления цитаты: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления цитаты: {str(e)}")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
@app.get("/api/storage/stats")
async def get_storage_stats():
    """Получение статистики хранилища"""
    return {
        "documents_count": len(storage.documents),
        "translations_count": len(storage.translations),
        "analyses_count": sum(len(v) for v in storage.analyses.values()),
        "quotes_count": len(storage.quotes),
        "next_id": storage.next_id,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/storage/clear")
async def clear_storage():
    """Очистка хранилища (для тестирования)"""
    storage.documents.clear()
    storage.translations.clear()
    storage.analyses.clear()
    storage.quotes.clear()
    storage.next_id = 1
    
    logger.info("🧹 Хранилище очищено")
    
    return {
        "status": "success",
        "message": "Хранилище очищено",
        "timestamp": datetime.now().isoformat()
    }

# ========== АУТЕНТИФИКАЦИЯ (для совместимости) ==========
@app.post("/api/auth/register")
async def register_user(request: UserCreate):
    """Регистрация пользователя (заглушка)"""
    user_data = {
        "email": request.email,
        "username": request.username,
        "hashed_password": f"hashed_{request.password}",
        "created_at": datetime.now().isoformat(),
        "last_login": datetime.now().isoformat()
    }
    
    user_id = storage.add_user(user_data)
    
    return {
        "id": user_id,
        "email": request.email,
        "username": request.username,
        "token": f"mock_token_{user_id}",
        "created_at": datetime.now().isoformat(),
        "last_login": datetime.now().isoformat(),
        "message": "Регистрация успешна (mock)"
    }

@app.post("/api/auth/login")
async def login_user(request: UserLogin):
    """Вход пользователя (заглушка)"""
    # Ищем пользователя
    user = None
    for u in storage.users.values():
        if u.get("email") == request.email:
            user = u
            break
    
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    
    return {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "token": f"mock_token_{user['id']}",
        "created_at": user.get("created_at", datetime.now().isoformat()),
        "last_login": datetime.now().isoformat(),
        "message": "Вход успешен (mock)"
    }

# ========== ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ ==========
@app.post("/api/demo/seed")
async def seed_demo_data():
    """Создание демонстрационных данных"""
    try:
        # Пример текстов для демонстрации
        demo_texts = [
            {
                "filename": "Война и мир (отрывок).txt",
                "content": """Война и мир. Л.Н. Толстой.
                
                Глава I
                — Eh bien, mon prince, Gênes et Lucques ne sont plus que des apanages, des поместья, de la famille Buonaparte. 
                Non, je vous préviens, que si vous ne me dites pas, que nous avons la guerre, si vous vous permettez encore de pallier toutes les infamies, 
                toutes les atrocités de cet Antichrist (ma parole, j'y crois) — je ne vous connais plus, vous n'êtes plus mon ami, 
                vous n'êtes plus мой верный раб, comme vous dites...
                
                Так говорила в июле 1805 года известная Анна Павловна Шерер, фрейлина и приближенная императрицы Марии Феодоровны, 
                встречая важного и чиновного князя Василия, первого приехавшего на ее вечер. Анна Павловна кашляла несколько дней, 
                у нее был грипп, как она говорила (грипп был тогда новое слово, употреблявшееся только редкими).""",
                "language": "ru"
            },
            {
                "filename": "Pride and Prejudice (excerpt).txt",
                "content": """Pride and Prejudice. Jane Austen.
                
                Chapter 1
                It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.
                
                However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered the rightful property of some one or other of their daughters.
                
                "My dear Mr. Bennet," said his lady to him one day, "have you heard that Netherfield Park is let at last?"
                
                Mr. Bennet replied that he had not.""",
                "language": "en"
            }
        ]
        
        added_ids = []
        for demo_text in demo_texts:
            doc_data = {
                "filename": demo_text["filename"],
                "content": demo_text["content"],
                "language": demo_text["language"],
                "file_type": "txt",
                "file_path": f"/demo/{demo_text['filename']}",
                "file_size": len(demo_text["content"].encode('utf-8')),
                "word_count": len(demo_text["content"].split()),
                "char_count": len(demo_text["content"]),
                "chapter_count": 1,
                "reading_time_minutes": max(1, len(demo_text["content"].split()) // 200)
            }
            
            doc_id = storage.add_document(doc_data)
            added_ids.append(doc_id)
        
        logger.info(f"🌱 Создано {len(added_ids)} демонстрационных документов")
        
        return {
            "status": "success",
            "message": f"Создано {len(added_ids)} демонстрационных документов",
            "document_ids": added_ids,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания демо данных: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== СТАТИЧЕСКИЕ ФАЙЛЫ ==========
try:
    app.mount("/uploads", StaticFiles(directory=config.UPLOAD_FOLDER), name="uploads")
    logger.info(f"✅ Статические файлы подключены: {config.UPLOAD_FOLDER}")
except Exception as e:
    logger.warning(f"⚠️ Не удалось подключить статические файлы: {e}")

# ========== МИДЛВАР ДЛЯ Flutter healthcheck ==========
@app.middleware("http")
async def add_flutter_healthcheck_middleware(request: Request, call_next):
    if request.url.path == "/api/flutter/health":
        response = JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "database": "moved_to_flutter",
                "ai_models": ai_models.initialized,
                "timestamp": datetime.now().isoformat(),
                "message": "База данных перенесена во Flutter приложение"
            }
        )
        return response
    
    response = await call_next(request)
    return response

# ========== ИНИЦИАЛИЗАЦИЯ ПРИ СТАРТЕ ==========
@app.on_event("startup")
async def startup_event():
    """Инициализация при старте приложения"""
    logger.info("🚀 Запуск Versevo Backend v9.0 (Без базы данных)")
    
    try:
        # Инициализация NLTK
        if init_nltk():
            logger.info("✅ NLTK инициализирован")
        else:
            logger.warning("⚠️ Ошибка инициализации NLTK")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации NLTK: {e}")
    
    # Инициализация AI моделей в фоне
    async def init_ai_background():
        try:
            if ai_models.initialize():
                logger.info("✅ AI модели инициализированы")
            else:
                logger.warning("⚠️ Не удалось инициализировать AI модели")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации AI моделей: {e}")
    
    asyncio.create_task(init_ai_background())
    
    logger.info(f"🌐 Сервер готов на порту {os.getenv('PORT', 8000)}")
    logger.info("💾 База данных ПЕРЕНЕСЕНА во Flutter приложение")
    logger.info("📊 Данные хранятся в памяти (InMemoryStorage)")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"{'='*60}")
    logger.info(f"🚀 VERSION 9.0 - БЕЗ БАЗЫ ДАННЫХ (БД во Flutter)")
    logger.info(f"{'='*60}")
    logger.info(f"📁 Папка загрузок: {config.UPLOAD_FOLDER}")
    logger.info(f"🤖 AI Модели: Hugging Face + Gemini (реальные)")
    logger.info(f"🗄️  Хранилище: InMemory (вместо БД)")
    logger.info(f"🔤 Перевод: Реальный через AI модели")
    logger.info(f"📊 Анализ: Полный AI анализ")
    logger.info(f"❤️ Избранные цитаты: В памяти")
    logger.info(f"{'='*60}")
    logger.info(f"🛠️  Дополнительные функции:")
    logger.info(f"   - /api/storage/stats - статистика хранилища")
    logger.info(f"   - /api/storage/clear - очистка хранилища")
    logger.info(f"   - /api/demo/seed - демонстрационные данные")
    logger.info(f"{'='*60}")
    logger.info(f"🌐 Эндпоинты для Flutter:")
    logger.info(f"   - GET /api/flutter/health - проверка здоровья")
    logger.info(f"   - GET /api/db/tables - информация о таблицах")
    logger.info(f"   - GET /api/sql/examples - примеры SQL")
    logger.info(f"{'='*60}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=True
    )
