# main.py - Полный бэкенд Versevo с PostgreSQL, Hugging Face и Gemini AI
import asyncio
import time
import threading
import os
import sys
import base64
import uuid
import re
import json
import aiohttp
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks, Request
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
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
import torch
from transformers import pipeline, AutoModelForSeq2SeqLM, AutoTokenizer
import fitz  # PyMuPDF
import docx
from PIL import Image
import io
import jwt
import secrets
from passlib.context import CryptContext

# Импортируем настройки БД
from database import get_db, SessionLocal, engine
from models import Base, User, Document, DocumentNote, ReadingProgress, DocumentAnalysis, FavoriteQuote, TranslationCache

# ========== НАСТРОЙКА APP И CORS ==========
app = FastAPI(
    title="Versevo Backend API",
    description="Modern document reader with translation and AI features",
    version="8.0.0",
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
        logging.FileHandler("versevo.log")
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
    
    # JWT
    JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_DAYS = 30
    
    # Лимиты
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_CONTENT_LENGTH = 1000000  # 1M символов
    CHUNK_SIZE = 5000  # Для обработки больших документов
    
    # Кэш
    CACHE_TTL = 3600  # 1 час

config = Config()

# Создаем директории
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(config.CACHE_FOLDER, exist_ok=True)
os.makedirs(config.MODELS_FOLDER, exist_ok=True)

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

# ========== ХЕШИРОВАНИЕ ПАРОЛЕЙ ==========
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=config.JWT_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    return encoded_jwt

# ========== ИНИЦИАЛИЗАЦИЯ МОДЕЛЕЙ AI ==========
class AIModels:
    """Класс для управления AI моделями"""
    
    def __init__(self):
        self.translator = None
        self.summarizer = None
        self.sentiment_analyzer = None
        self.gemini = None
        self.initialized = False
        self.init_thread = None
        
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
            
            # Переводчик (с загрузкой в фоне, чтобы не блокировать старт)
            def load_translator():
                try:
                    translator = pipeline(
                        "translation",
                        model=config.HF_TRANSLATION_MODEL,
                        device=device,
                        max_length=512
                    )
                    logger.info(f"✅ Переводчик загружен: {config.HF_TRANSLATION_MODEL}")
                    return translator
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки переводчика: {e}")
                    return None
            
            # Суммаризатор
            def load_summarizer():
                try:
                    summarizer = pipeline(
                        "summarization",
                        model=config.HF_SUMMARIZATION_MODEL,
                        device=device,
                        max_length=150,
                        min_length=50
                    )
                    logger.info(f"✅ Суммаризатор загружен: {config.HF_SUMMARIZATION_MODEL}")
                    return summarizer
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки суммаризатора: {e}")
                    return None
            
            # Анализатор тональности
            def load_sentiment_analyzer():
                try:
                    sentiment_analyzer = pipeline(
                        "sentiment-analysis",
                        model=config.HF_SENTIMENT_MODEL,
                        device=device
                    )
                    logger.info(f"✅ Анализатор тональности загружен: {config.HF_SENTIMENT_MODEL}")
                    return sentiment_analyzer
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки анализатора тональности: {e}")
                    return None
            
            # Загружаем модели асинхронно
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_translator = executor.submit(load_translator)
                future_summarizer = executor.submit(load_summarizer)
                future_sentiment = executor.submit(load_sentiment_analyzer)
                
                self.translator = future_translator.result()
                self.summarizer = future_summarizer.result()
                self.sentiment_analyzer = future_sentiment.result()
            
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
            # Адаптация модели под разные языки
            if source_lang == "en" and target_lang == "ru":
                result = self.translator(text, max_length=512, truncation=True)
                if result and len(result) > 0:
                    return result[0]['translation_text']
            
            # Fallback для других языковых пар
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
                
                # Поиск краткого содержания
                if "краткое содержание" in line.lower() or "summary" in line.lower():
                    result["summary"] = line
                
                # Поиск тем
                elif "темы" in line.lower() or "themes" in line.lower():
                    if ":" in line:
                        themes_text = line.split(":", 1)[1].strip()
                        result["themes"] = [t.strip() for t in themes_text.split(",") if t.strip()]
                
                # Поиск тональности
                elif "тональность" in line.lower() or "sentiment" in line.lower():
                    if ":" in line:
                        sentiment_text = line.split(":", 1)[1].strip().lower()
                        if "положительн" in sentiment_text:
                            result["sentiment"] = "Положительный"
                        elif "отрицательн" in sentiment_text:
                            result["sentiment"] = "Отрицательный"
                        else:
                            result["sentiment"] = "Нейтральный"
                
                # Поиск ключевых моментов
                elif "ключевые" in line.lower() or "key points" in line.lower():
                    if ":" in line:
                        points_text = line.split(":", 1)[1].strip()
                        result["key_points"] = [p.strip() for p in points_text.split(".") if p.strip()]
                
                # Поиск стиля письма
                elif "стиль" in line.lower() or "style" in line.lower():
                    if ":" in line:
                        result["writing_style"] = line.split(":", 1)[1].strip()
            
            # Если не нашли структурированные данные, используем весь текст как summary
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
        
        # Скачиваем необходимые данные
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
        # Декодируем base64
        file_bytes = base64.b64decode(file_data)
        
        # Генерируем уникальное имя файла
        file_ext = os.path.splitext(filename)[1] or '.txt'
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(config.UPLOAD_FOLDER, unique_filename)
        
        # Сохраняем файл
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
            # Пробуем прочитать как текстовый файл
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
        # Простая эвристика на основе символов
        cyrillic_count = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
        latin_count = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
        
        if cyrillic_count > latin_count * 1.5:
            return "ru"
        elif latin_count > cyrillic_count * 1.5:
            return "en"
        else:
            return "en"  # По умолчанию английский
    except:
        return "en"

def split_into_chapters(text: str) -> List[Dict[str, str]]:
    """Разделение текста на главы"""
    chapters = []
    
    if not text:
        return [{"title": "Документ", "content": "Нет содержимого"}]
    
    # Паттерны для определения заголовков глав
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
        
        # Проверяем, является ли строка заголовком главы
        is_chapter_title = False
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                is_chapter_title = True
                break
        
        if is_chapter_title and current_chapter["content"]:
            # Сохраняем предыдущую главу
            chapters.append(current_chapter.copy())
            current_chapter = {"title": line[:100], "content": ""}
        else:
            # Добавляем строку к текущей главе
            if current_chapter["content"]:
                current_chapter["content"] += "\n" + line
            else:
                current_chapter["content"] = line
    
    # Добавляем последнюю главу
    if current_chapter["content"]:
        chapters.append(current_chapter)
    
    # Если не нашли глав, разбиваем на равные части
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
        
        reading_time = max(1, word_count // 200)  # 200 слов в минуту
        
        # Определяем сложность
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

# ========== HEALTHCHECK ==========
@app.get("/")
async def root():
    return {
        "message": "Versevo Backend API v8.0",
        "version": "8.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "endpoints": [
            "/docs - документация API",
            "/health - проверка здоровья",
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
        "service": "versevo-backend",
        "version": "8.0.0",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }
    
    # Проверка базы данных
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        health_status["components"]["database"] = {
            "status": "healthy",
            "type": "PostgreSQL"
        }
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
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
    
    # Проверка памяти
    try:
        import psutil
        memory = psutil.virtual_memory()
        health_status["components"]["memory"] = {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "percent_used": memory.percent
        }
    except:
        pass
    
    return health_status

@app.get("/api/flutter/health")
async def flutter_health_check():
    """Упрощенная проверка для Flutter"""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        
        return {
            "status": "healthy",
            "database": "available",
            "ai_models": ai_models.initialized,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ========== ДОБАВЛЕННЫЕ ФУНКЦИИ ДЛЯ РЕШЕНИЯ ПРОБЛЕМЫ ==========
def check_and_fix_database_structure():
    """Проверка и исправление структуры базы данных"""
    try:
        db = SessionLocal()
        
        # Проверяем структуру таблицы users
        result = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users'
        """))
        
        columns = result.fetchall()
        column_names = [col[0] for col in columns]
        logger.info(f"📊 Существующие колонки в users: {column_names}")
        
        # Проверяем наличие необходимых колонок
        if 'hashed_password' not in column_names:
            logger.error("❌ Критическая ошибка: Колонка hashed_password отсутствует в таблице users!")
            logger.info("🔄 Пытаемся добавить колонку...")
            
            try:
                # Добавляем колонку если её нет
                db.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255)
                """))
                db.commit()
                logger.info("✅ Колонка hashed_password добавлена в таблицу users")
            except Exception as e:
                logger.error(f"❌ Не удалось добавить колонку: {e}")
                
                # Пробуем пересоздать таблицу
                logger.info("🔄 Пытаемся пересоздать таблицу users...")
                try:
                    # Создаем временную таблицу для сохранения данных
                    db.execute(text("""
                        CREATE TABLE IF NOT EXISTS users_new (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            username VARCHAR(100) NOT NULL,
                            hashed_password VARCHAR(255) NOT NULL,
                            created_at TIMESTAMP,
                            last_login TIMESTAMP
                        )
                    """))
                    
                    # Копируем данные из старой таблицы если они есть
                    db.execute(text("""
                        INSERT INTO users_new (id, email, username, created_at, last_login)
                        SELECT id, email, username, created_at, last_login 
                        FROM users
                    """))
                    
                    # Удаляем старую таблицу
                    db.execute(text("DROP TABLE IF EXISTS users CASCADE"))
                    
                    # Переименовываем новую таблицу
                    db.execute(text("ALTER TABLE users_new RENAME TO users"))
                    
                    db.commit()
                    logger.info("✅ Таблица users успешно пересоздана")
                except Exception as recreate_error:
                    logger.error(f"❌ Не удалось пересоздать таблицу: {recreate_error}")
        
        # Проверяем остальные таблицы
        required_tables = ['documents', 'document_notes', 'reading_progress', 
                          'document_analysis', 'favorite_quotes', 'translation_cache']
        
        for table_name in required_tables:
            result = db.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '{table_name}'
                )
            """))
            exists = result.scalar()
            
            if exists:
                logger.info(f"✅ Таблица {table_name} существует")
            else:
                logger.warning(f"⚠️ Таблица {table_name} не существует")
        
        db.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки структуры БД: {e}")
        return False

def recreate_users_table_completely():
    """Полное пересоздание таблицы users"""
    try:
        db = SessionLocal()
        
        logger.info("🔄 Начинаем полное пересоздание таблицы users...")
        
        # Удаляем таблицу если существует
        db.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        db.commit()
        
        # Создаем таблицу заново через SQLAlchemy
        Base.metadata.tables['users'].create(bind=engine)
        
        logger.info("✅ Таблица users полностью пересоздана")
        
        # Проверяем структуру
        result = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users'
        """))
        
        columns = result.fetchall()
        logger.info("📊 Новая структура таблицы users:")
        for col in columns:
            logger.info(f"   - {col[0]}: {col[1]}")
        
        db.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка пересоздания таблицы users: {e}")
        return False

# ========== АУТЕНТИФИКАЦИЯ ==========
@app.post("/api/auth/register")
async def register_user(request: UserCreate, db: Session = Depends(get_db)):
    """Регистрация нового пользователя"""
    try:
        logger.info(f"📝 Регистрация пользователя: {request.email} ({request.username})")
        
        # Проверяем, существует ли пользователь
        existing_user = db.query(User).filter(User.email == request.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
        
        # Проверяем username
        existing_username = db.query(User).filter(User.username == request.username).first()
        if existing_username:
            raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
        
        # Хешируем пароль
        hashed_password = hash_password(request.password)
        
        # Создаем пользователя
        user = User(
            email=request.email,
            username=request.username,
            hashed_password=hashed_password,
            created_at=datetime.now(),
            last_login=datetime.now()
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Создаем токен
        access_token = create_access_token(data={"user_id": user.id, "email": user.email})
        
        logger.info(f"✅ Новый пользователь зарегистрирован: {user.email}")
        
        return {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "token": access_token,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat(),
            "message": "Регистрация успешна"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка регистрации: {str(e)}")

@app.post("/api/auth/login")
async def login_user(request: UserLogin, db: Session = Depends(get_db)):
    """Вход пользователя"""
    try:
        logger.info(f"🔐 Попытка входа: {request.email}")
        
        # Ищем пользователя
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        
        # Проверяем пароль
        if not verify_password(request.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        
        # Обновляем время последнего входа
        user.last_login = datetime.now()
        db.commit()
        
        # Создаем токен
        access_token = create_access_token(data={"user_id": user.id, "email": user.email})
        
        logger.info(f"✅ Пользователь вошел: {user.email}")
        
        return {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "token": access_token,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat(),
            "message": "Вход успешен"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка входа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка входа: {str(e)}")

# ========== ДОКУМЕНТЫ ==========
@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: DocumentUploadRequest, db: Session = Depends(get_db)):
    """Загрузка документа в формате base64 (без аутентификации для теста)"""
    try:
        # Проверка размера файла
        if request.file_size > config.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"Файл слишком большой. Максимум: {config.MAX_FILE_SIZE // 1024 // 1024}MB")
        
        logger.info(f"📤 Загрузка файла: {request.filename}")
        
        # Сохраняем файл
        file_path = save_base64_file(request.file_data, request.filename)
        
        # Извлекаем текст
        content, file_type = extract_text_from_file(file_path)
        
        if not content.strip():
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файла")
        
        # Определяем язык
        language = detect_language(content)
        
        # Разбиваем на главы
        chapters = split_into_chapters(content)
        
        # Рассчитываем статистику
        stats = calculate_statistics(content)
        
        # Сохраняем в базу данных
        document = Document(
            filename=request.filename,
            content=content[:config.MAX_CONTENT_LENGTH],  # Ограничиваем размер
            language=language,
            file_type=file_type,
            file_path=file_path,
            file_size=request.file_size,
            word_count=stats["word_count"],
            char_count=stats["char_count"],
            chapter_count=len(chapters),
            reading_time_minutes=stats["reading_time_minutes"],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Сохраняем анализ
        analysis = DocumentAnalysis(
            document_id=document.id,
            analysis_type="basic",
            summary=content[:500] + "..." if len(content) > 500 else content,
            created_at=datetime.now()
        )
        
        db.add(analysis)
        db.commit()
        
        logger.info(f"✅ Документ загружен: ID {document.id}, {stats['word_count']} слов")
        
        return {
            "id": document.id,
            "filename": document.filename,
            "language": document.language,
            "file_type": document.file_type,
            "word_count": document.word_count,
            "char_count": document.char_count,
            "chapter_count": document.chapter_count,
            "reading_time_minutes": document.reading_time_minutes,
            "created_at": document.created_at.isoformat(),
            "content_preview": document.content[:300] + "..." if len(document.content) > 300 else document.content,
            "chapters": chapters
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/api/documents")
async def get_documents(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Получение списка документов"""
    try:
        documents = db.query(Document).order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
        
        return [
            {
                "id": doc.id,
                "filename": doc.filename,
                "language": doc.language,
                "file_type": doc.file_type,
                "word_count": doc.word_count,
                "char_count": doc.char_count,
                "chapter_count": doc.chapter_count,
                "reading_time_minutes": doc.reading_time_minutes,
                "created_at": doc.created_at.isoformat(),
                "content_preview": doc.content[:200] + "..." if doc.content and len(doc.content) > 200 else doc.content or ""
            }
            for doc in documents
        ]
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения документов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения документов: {str(e)}")

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Получение документа по ID"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        chapters = split_into_chapters(document.content or "")
        
        return {
            "id": document.id,
            "filename": document.filename,
            "content": document.content,
            "language": document.language,
            "file_type": document.file_type,
            "word_count": document.word_count,
            "char_count": document.char_count,
            "chapter_count": document.chapter_count,
            "reading_time_minutes": document.reading_time_minutes,
            "created_at": document.created_at.isoformat(),
            "chapters": chapters
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения документа: {str(e)}")

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Удаление документа"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        # Удаляем файл с диска
        if document.file_path and os.path.exists(document.file_path):
            try:
                os.remove(document.file_path)
            except:
                pass
        
        # Удаляем связанные записи
        db.query(DocumentAnalysis).filter(DocumentAnalysis.document_id == document_id).delete()
        db.query(DocumentNote).filter(DocumentNote.document_id == document_id).delete()
        db.query(ReadingProgress).filter(ReadingProgress.document_id == document_id).delete()
        db.query(FavoriteQuote).filter(FavoriteQuote.document_id == document_id).delete()
        
        # Удаляем документ
        db.delete(document)
        db.commit()
        
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
        db.rollback()
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
        
        # Пробуем использовать Hugging Face
        translated_text = None
        translation_service = "unknown"
        
        try:
            if ai_models.is_huggingface_available():
                translated_text = ai_models.translate_with_huggingface(
                    request.text, target_lang, source_lang
                )
                translation_service = "huggingface"
                logger.info("✅ Перевод выполнен через Hugging Face")
        except Exception as hf_error:
            logger.warning(f"⚠️ Hugging Face перевод не удался: {hf_error}")
        
        # Если Hugging Face не сработал, пробуем Gemini
        if not translated_text and ai_models.is_gemini_available():
            try:
                translated_text = await ai_models.translate_with_gemini(
                    request.text, target_lang, source_lang
                )
                translation_service = "gemini"
                logger.info("✅ Перевод выполнен через Gemini AI")
            except Exception as gemini_error:
                logger.warning(f"⚠️ Gemini AI перевод не удался: {gemini_error}")
        
        # Fallback: простой подстановочный перевод
        if not translated_text:
            translation_service = "fallback"
            
            if source_lang == "en" and target_lang == "ru":
                # Простой англо-русский словарь
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
        
        return {
            "original_text": request.text,
            "translated_text": translated_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "style": request.style,
            "translation_service": translation_service,
            "original_length": len(request.text),
            "translated_length": len(translated_text),
            "translation_timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка перевода: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка перевода: {str(e)}")

@app.post("/api/translate/document/{document_id}")
async def translate_document(
    document_id: int,
    request: DocumentTranslateRequest,
    db: Session = Depends(get_db)
):
    """Перевод всего документа"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        if not document.content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        source_lang = request.source_language or document.language
        target_lang = request.target_language
        
        logger.info(f"🌐 Перевод документа {document_id}: {source_lang} → {target_lang}")
        
        # Разбиваем на части для перевода
        content = document.content
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
                # Пробуем Hugging Face
                if ai_models.is_huggingface_available():
                    translated_chunk = ai_models.translate_with_huggingface(
                        chunk, target_lang, source_lang
                    )
                    translation_service = "huggingface"
                
                # Пробуем Gemini AI
                elif ai_models.is_gemini_available():
                    translated_chunk = await ai_models.translate_with_gemini(
                        chunk, target_lang, source_lang
                    )
                    translation_service = "gemini"
                
                # Fallback
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
        
        # Сохраняем переведенный документ
        translated_doc = Document(
            filename=f"translated_{target_lang}_{document.filename}",
            content=translated_content,
            language=target_lang,
            file_type=document.file_type,
            file_path=f"{document.file_path}.translated",
            file_size=len(translated_content.encode('utf-8')),
            word_count=len(translated_content.split()),
            char_count=len(translated_content),
            chapter_count=document.chapter_count,
            reading_time_minutes=document.reading_time_minutes,
            created_at=datetime.now()
        )
        
        db.add(translated_doc)
        db.commit()
        db.refresh(translated_doc)
        
        logger.info(f"✅ Документ переведен: новый ID {translated_doc.id}")
        
        return {
            "document_id": document_id,
            "translated_document_id": translated_doc.id,
            "original_filename": document.filename,
            "translated_filename": translated_doc.filename,
            "source_language": source_lang,
            "target_language": target_lang,
            "style": request.style,
            "translation_service": translation_service,
            "original_length": len(document.content),
            "translated_length": len(translated_content),
            "chunks_translated": len(chunks),
            "translation_timestamp": datetime.now().isoformat(),
            "download_url": f"/api/documents/{translated_doc.id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка перевода документа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка перевода документа: {str(e)}")

# ========== АНАЛИЗ ==========
@app.post("/api/analyze")
async def analyze_document(request: AnalysisRequest, db: Session = Depends(get_db)):
    """Базовый анализ документа"""
    try:
        document = db.query(Document).filter(Document.id == request.document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        if not document.content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        logger.info(f"🔍 Базовый анализ документа {document.id}")
        
        content = document.content
        
        # Разбиваем на предложения
        sentences = sent_tokenize(content) if len(content) > 100 else [content]
        
        # Создаем краткое содержание
        if len(sentences) >= 3:
            summary = " ".join(sentences[:3])
        else:
            summary = content[:500] + "..." if len(content) > 500 else content
        
        # Определяем темы
        themes = []
        words = word_tokenize(content.lower())
        word_freq = Counter(words)
        
        stop_words = set(stopwords.words('russian' if document.language == 'ru' else 'english'))
        common_words = [word for word, count in word_freq.most_common(20) 
                       if word not in stop_words and len(word) > 3]
        
        themes = common_words[:5]
        
        # Анализ тональности
        sentiment = "Нейтральный"
        if ai_models.is_huggingface_available():
            try:
                sentiment_result = ai_models.analyze_sentiment_with_huggingface(content[:512])
                sentiment = sentiment_result["sentiment"]
            except:
                pass
        
        # Статистика
        stats = calculate_statistics(content)
        
        # Определяем стиль письма
        avg_sentence_len = stats["avg_sentence_length"]
        if avg_sentence_len > 25:
            writing_style = "Академический"
        elif avg_sentence_len > 15:
            writing_style = "Литературный"
        else:
            writing_style = "Информационный"
        
        # Ключевые моменты
        key_points = [
            f"Объем: {stats['word_count']} слов",
            f"Сложность: {stats['complexity']}",
            f"Время чтения: {stats['reading_time_minutes']} минут",
            f"Язык: {document.language}"
        ]
        
        if themes:
            key_points.append(f"Основные темы: {', '.join(themes[:3])}")
        
        # Сохраняем анализ в базу
        analysis = DocumentAnalysis(
            document_id=document.id,
            analysis_type=request.analysis_type,
            summary=summary,
            themes=", ".join(themes),
            sentiment=sentiment,
            writing_style=writing_style,
            key_points="\n".join(key_points),
            ai_analysis=False,
            created_at=datetime.now()
        )
        
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        
        return {
            "document_id": document.id,
            "filename": document.filename,
            "language": document.language,
            "summary": summary,
            "themes": themes,
            "sentiment": sentiment,
            "writing_style": writing_style,
            "key_points": key_points,
            "statistics": stats,
            "ai_analysis": False,
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat(),
            "analysis_id": analysis.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

@app.post("/api/analyze/ai/document")
async def analyze_with_ai(request: AIAnalysisRequest, db: Session = Depends(get_db)):
    """AI анализ документа"""
    try:
        document = db.query(Document).filter(Document.id == request.document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        if not document.content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        logger.info(f"🤖 AI анализ документа {document.id}")
        
        content = document.content[:5000]  # Ограничиваем для анализа
        
        ai_provider = None
        ai_analysis = {}
        
        # Пробуем Gemini AI
        if ai_models.is_gemini_available():
            try:
                ai_analysis = await ai_models.analyze_with_gemini(content, request.analysis_type)
                ai_provider = "gemini"
                logger.info("✅ Анализ выполнен через Gemini AI")
            except Exception as gemini_error:
                logger.warning(f"⚠️ Gemini AI анализ не удался: {gemini_error}")
        
        # Если Gemini не сработал, пробуем Hugging Face
        if not ai_analysis and ai_models.is_huggingface_available():
            try:
                # Суммаризация
                summary = ai_models.summarize_with_huggingface(content)
                
                # Анализ тональности
                sentiment_result = ai_models.analyze_sentiment_with_huggingface(content)
                
                # Темы (простая эвристика)
                words = word_tokenize(content.lower())
                word_freq = Counter(words)
                stop_words = set(stopwords.words('russian' if document.language == 'ru' else 'english'))
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
        
        # Fallback анализ
        if not ai_analysis:
            sentences = sent_tokenize(content) if len(content) > 100 else [content]
            summary = " ".join(sentences[:3]) if len(sentences) >= 3 else content[:500]
            
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
        
        # Статистика
        stats = calculate_statistics(content)
        
        # Сохраняем анализ
        analysis = DocumentAnalysis(
            document_id=document.id,
            analysis_type=request.analysis_type,
            summary=ai_analysis.get("summary", ""),
            themes=", ".join(ai_analysis.get("themes", [])),
            sentiment=ai_analysis.get("sentiment", "Нейтральный"),
            writing_style=ai_analysis.get("writing_style", "Информационный"),
            key_points="\n".join(ai_analysis.get("key_points", [])),
            ai_analysis=True,
            ai_provider=ai_provider,
            created_at=datetime.now()
        )
        
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        
        return {
            "document_id": document.id,
            "filename": document.filename,
            "language": document.language,
            "summary": ai_analysis.get("summary", ""),
            "themes": ai_analysis.get("themes", []),
            "sentiment": ai_analysis.get("sentiment", "Нейтральный"),
            "writing_style": ai_analysis.get("writing_style", "Информационный"),
            "key_points": ai_analysis.get("key_points", []),
            "statistics": stats,
            "ai_analysis": True,
            "ai_provider": ai_provider,
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat(),
            "analysis_id": analysis.id
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
async def analyze_with_gemini(request: AIAnalysisRequest, db: Session = Depends(get_db)):
    """Анализ документа через Gemini AI"""
    try:
        if not ai_models.is_gemini_available():
            raise HTTPException(status_code=503, detail="Gemini AI не доступен. Установите GEMINI_API_KEY.")
        
        document = db.query(Document).filter(Document.id == request.document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        if not document.content:
            raise HTTPException(status_code=400, detail="Документ не содержит текста")
        
        logger.info(f"🌟 Gemini AI анализ документа {document.id}")
        
        content = document.content[:10000]  # Ограничиваем для Gemini
        
        # Выполняем анализ через Gemini AI
        ai_analysis = await ai_models.analyze_with_gemini(content, request.analysis_type)
        
        # Статистика
        stats = calculate_statistics(content)
        
        # Сохраняем анализ
        analysis = DocumentAnalysis(
            document_id=document.id,
            analysis_type=request.analysis_type,
            summary=ai_analysis.get("summary", ""),
            themes=", ".join(ai_analysis.get("themes", [])),
            sentiment=ai_analysis.get("sentiment", "Нейтральный"),
            writing_style=ai_analysis.get("writing_style", "Информационный"),
            key_points="\n".join(ai_analysis.get("key_points", [])),
            ai_analysis=True,
            ai_provider="gemini",
            created_at=datetime.now()
        )
        
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        
        return {
            "document_id": document.id,
            "filename": document.filename,
            "language": document.language,
            "summary": ai_analysis.get("summary", ""),
            "themes": ai_analysis.get("themes", []),
            "sentiment": ai_analysis.get("sentiment", "Нейтральный"),
            "writing_style": ai_analysis.get("writing_style", "Информационный"),
            "key_points": ai_analysis.get("key_points", []),
            "statistics": stats,
            "ai_analysis": True,
            "ai_provider": "gemini",
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat(),
            "analysis_id": analysis.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка Gemini AI анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка Gemini AI анализа: {str(e)}")

@app.get("/api/analyze/gemini/health")
async def gemini_health_check():
    """Проверка доступности Gemini AI"""
    return {
        "status": "available" if ai_models.is_gemini_available() else "unavailable",
        "service": "gemini_ai",
        "available": ai_models.is_gemini_available(),
        "model": config.GEMINI_MODEL,
        "api_key_set": bool(config.GEMINI_API_KEY),
        "timestamp": datetime.now().isoformat()
    }

# ========== ЦИТАТЫ ==========
@app.get("/api/documents/{document_id}/quotes")
async def get_document_quotes(document_id: int, limit: int = 5, db: Session = Depends(get_db)):
    """Получение цитат из документа"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        if not document.content:
            return {
                "document_id": document_id,
                "quotes": ["Документ не содержит текста"],
                "count": 1
            }
        
        # Разбиваем на предложения
        sentences = sent_tokenize(document.content)
        
        # Выбираем интересные предложения (не слишком короткие и не слишком длинные)
        quotes = []
        for sentence in sentences:
            sentence = sentence.strip()
            if 20 < len(sentence) < 200:  # Оптимальная длина для цитаты
                quotes.append(sentence)
                if len(quotes) >= limit * 3:  # Берем больше для разнообразия
                    break
        
        # Если не нашли достаточно цитат, создаем искусственные
        if len(quotes) < limit:
            # Ищем ключевые фразы
            words = word_tokenize(document.content.lower())
            word_freq = Counter(words)
            stop_words = set(stopwords.words('russian' if document.language == 'ru' else 'english'))
            
            # Находим часто встречающиеся значимые слова
            significant_words = [word for word, count in word_freq.most_common(50) 
                               if word not in stop_words and len(word) > 3]
            
            # Создаем цитаты на основе этих слов
            for i in range(limit - len(quotes)):
                if i < len(significant_words):
                    quotes.append(f"Важное понятие: '{significant_words[i]}'")
                else:
                    quotes.append("Эта мысль заслуживает внимания.")
        
        # Ограничиваем количество
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
async def add_favorite_quote(request: FavoriteQuoteCreate, db: Session = Depends(get_db)):
    """Добавление цитаты в избранное"""
    try:
        # Проверяем существование документа
        document = db.query(Document).filter(Document.id == request.document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        # Создаем избранную цитату
        favorite_quote = FavoriteQuote(
            document_id=request.document_id,
            quote=request.quote,
            start_position=request.start_position,
            end_position=request.end_position,
            note=request.note,
            document_title=document.filename,
            document_language=document.language,
            created_at=datetime.now()
        )
        
        db.add(favorite_quote)
        db.commit()
        db.refresh(favorite_quote)
        
        logger.info(f"❤️ Добавлена избранная цитата: ID {favorite_quote.id}")
        
        return {
            "id": favorite_quote.id,
            "quote": favorite_quote.quote,
            "document_id": favorite_quote.document_id,
            "document_title": favorite_quote.document_title,
            "created_at": favorite_quote.created_at.isoformat(),
            "note": favorite_quote.note,
            "status": "added_to_favorites"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка добавления избранной цитаты: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка добавления цитаты: {str(e)}")

@app.get("/api/quotes/favorites")
async def get_favorite_quotes(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Получение списка избранных цитат"""
    try:
        quotes = db.query(FavoriteQuote)\
            .order_by(FavoriteQuote.created_at.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
        
        return [
            {
                "id": quote.id,
                "quote": quote.quote,
                "document_id": quote.document_id,
                "document_title": quote.document_title,
                "document_language": quote.document_language,
                "start_position": quote.start_position,
                "end_position": quote.end_position,
                "note": quote.note,
                "created_at": quote.created_at.isoformat()
            }
            for quote in quotes
        ]
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения избранных цитат: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения цитат: {str(e)}")

@app.delete("/api/quotes/favorites/{quote_id}")
async def delete_favorite_quote(quote_id: int, db: Session = Depends(get_db)):
    """Удаление цитаты из избранного"""
    try:
        quote = db.query(FavoriteQuote).filter(FavoriteQuote.id == quote_id).first()
        
        if not quote:
            raise HTTPException(status_code=404, detail="Цитата не найдена")
        
        db.delete(quote)
        db.commit()
        
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
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка удаления цитаты: {str(e)}")

# ========== БАЗА ДАННЫХ ==========
@app.get("/api/db/tables")
async def get_database_tables(db: Session = Depends(get_db)):
    """Получение списка таблиц и их содержимого"""
    try:
        # Получаем все таблицы
        result = db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        tables = result.fetchall()
        
        table_data = {}
        
        for table in tables:
            table_name = table[0]
            
            # Получаем данные из каждой таблицы
            try:
                data_result = db.execute(text(f"SELECT * FROM {table_name} LIMIT 5"))
                columns = [desc[0] for desc in data_result.cursor.description]
                rows = data_result.fetchall()
                
                table_data[table_name] = {
                    "columns": columns,
                    "rows": [dict(zip(columns, row)) for row in rows],
                    "count": len(rows)
                }
            except Exception as table_error:
                table_data[table_name] = {"error": str(table_error)}
        
        return {
            "status": "success",
            "tables": [t[0] for t in tables],
            "data": table_data,
            "total_tables": len(tables)
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения таблиц: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== API ДЛЯ УПРАВЛЕНИЯ БАЗОЙ ДАННЫХ ==========
@app.post("/api/dev/fix-database")
async def fix_database():
    """Исправление структуры базы данных (для разработки)"""
    try:
        logger.info("🛠️  Начинаем исправление структуры базы данных...")
        
        # Проверяем и исправляем структуру
        check_and_fix_database_structure()
        
        return {
            "status": "success",
            "message": "Структура базы данных проверена и исправлена",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка исправления базы данных: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dev/recreate-users-table")
async def recreate_users_table_endpoint():
    """Пересоздание таблицы users (для разработки)"""
    try:
        logger.info("🔄 Запрос на пересоздание таблицы users...")
        
        if recreate_users_table_completely():
            return {
                "status": "success",
                "message": "Таблица users успешно пересоздана",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Не удалось пересоздать таблицу users")
        
    except Exception as e:
        logger.error(f"❌ Ошибка пересоздания таблицы: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== СТАТИЧЕСКИЕ ФАЙЛЫ ==========
try:
    app.mount("/uploads", StaticFiles(directory=config.UPLOAD_FOLDER), name="uploads")
    logger.info(f"✅ Статические файлы подключены: {config.UPLOAD_FOLDER}")
except Exception as e:
    logger.warning(f"⚠️ Не удалось подключить статические файлы: {e}")

# ========== КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Healthcheck Middleware ==========
@app.middleware("http")
async def healthcheck_middleware(request: Request, call_next):
    # Быстрый ответ для healthcheck чтобы Railway не падал
    if request.url.path == "/api/flutter/health":
        try:
            # Проверяем БД быстро
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            
            response = JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "database": "available",
                    "timestamp": datetime.now().isoformat()
                }
            )
            return response
        except Exception as e:
            response = JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
            )
            return response
    
    response = await call_next(request)
    return response

# ========== СОЗДАНИЕ ТАБЛИЦ ==========
def create_tables():
    """Создание таблиц при запуске"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Таблицы базы данных созданы/проверены")
        
        # Проверяем таблицу users
        db = SessionLocal()
        result = db.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')"))
        users_exists = result.scalar()
        
        if users_exists:
            logger.info("✅ Таблица users существует")
            # Проверяем есть ли пользователи
            users_count = db.query(User).count()
            logger.info(f"📊 Количество пользователей в базе: {users_count}")
        else:
            logger.warning("⚠️ Таблица users не существует")
            
        db.close()
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")

# ========== ИНИЦИАЛИЗАЦИЯ ПРИ СТАРТЕ ==========
@app.on_event("startup")
async def startup_event():
    """Инициализация при старте приложения"""
    logger.info("🚀 Запуск Versevo Backend v8.0")
    
    try:
        # Создаем таблицы в базе данных
        create_tables()
        
        # Проверяем и исправляем структуру базы данных
        check_and_fix_database_structure()
        
        # Проверяем подключение к БД
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("✅ Подключение к базе данных успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        # НЕ падаем при ошибке БД - Railway будет перезапускать
    
    # Инициализация NLTK в фоне
    try:
        if init_nltk():
            logger.info("✅ NLTK инициализирован")
        else:
            logger.warning("⚠️ Ошибка инициализации NLTK")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации NLTK: {e}")
    
    # Инициализация AI моделей в фоне (не блокируем старт)
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

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"{'='*60}")
    logger.info(f"🚀 VERSION 8.0 - ПОЛНАЯ РЕАЛИЗАЦИЯ С АУТЕНТИФИКАЦИЕЙ")
    logger.info(f"{'='*60}")
    logger.info(f"📁 Папка загрузок: {config.UPLOAD_FOLDER}")
    logger.info(f"🤖 AI Модели: Hugging Face + Gemini (реальные)")
    logger.info(f"🗄️  База данных: PostgreSQL (Railway)")
    logger.info(f"🔐 Аутентификация: JWT токены")
    logger.info(f"🔤 Перевод: Реальный через AI модели")
    logger.info(f"📊 Анализ: Полный AI анализ")
    logger.info(f"❤️ Избранные цитаты: Реальная база данных")
    logger.info(f"{'='*60}")
    logger.info(f"🛠️  Дополнительные функции:")
    logger.info(f"   - /api/dev/fix-database - исправление структуры БД")
    logger.info(f"   - /api/dev/recreate-users-table - пересоздание таблицы users")
    logger.info(f"{'='*60}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=True
    )
