import asyncio
import time
import threading
# main.py - Бэкенд Versevo с PostgreSQL и Hugging Face AI
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
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
from collections import Counter
from enum import Enum
from sqlalchemy.orm import Session

# Импортируем настройки БД
from database import get_db, SessionLocal
from models import User, Document, DocumentNote, ReadingProgress, DocumentAnalysis, FavoriteQuote, TranslationCache

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

class DocumentCreate(BaseModel):
    title: str
    filename: str
    content: str
    user_id: int
    language: str = "en"
    file_type: str = "txt"

class NoteCreate(BaseModel):
    document_id: int
    user_id: int
    text: str
    selected_text: Optional[str] = None
    chapter_index: int = 0
    is_highlight: bool = False

class AnalysisType(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DETAILED = "detailed"
    FULL = "full"

# ========== СОЗДАЕМ APP ==========
app = FastAPI(
    title="Versevo Backend API",
    description="Modern document reader with translation and AI features",
    version="6.0.0"
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
ANALYSIS_CACHE_FOLDER = "cache/analysis"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BOOKS_FOLDER, exist_ok=True)
os.makedirs(ANALYSIS_CACHE_FOLDER, exist_ok=True)

# Статические файлы
try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
    app.mount("/books", StaticFiles(directory=BOOKS_FOLDER), name="books")
    logger.info("✅ Static files mounted")
except Exception as e:
    logger.error(f"❌ Error mounting static files: {e}")

# ========== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ==========
PORT = int(os.getenv("PORT", 8080))

# Хранилище документов в памяти (для совместимости со старыми эндпоинтами)
documents_store = {}
current_doc_id = 1

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ AI ==========
# Инициализируем флаги загрузки
HUGGING_FACE_ENABLED = False
HF_ANALYSIS_PIPELINES = {}
HF_TRANSLATOR_READY = False
HF_ANALYSIS_READY = False

# ========== УПРОЩЕННЫЙ ПЕРЕВОДЧИК С УЛУЧШЕНИЯМИ ==========
class LocalTranslator:
    """Улучшенный упрощенный переводчик для fallback"""
    
    def __init__(self):
        logger.info("🚀 Инициализация улучшенного переводчика")
        # Расширенный словарь
        self.translation_dict = {
            'en-ru': {
                # Основные слова
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
                'author': 'автор',
                'title': 'название',
                'content': 'содержание',
                'analysis': 'анализ',
                'summary': 'краткое содержание',
                'character': 'персонаж',
                'plot': 'сюжет',
                'story': 'история',
                'novel': 'роман',
                'poem': 'стихотворение',
                'literature': 'литература',
                
                # Союзы и предлоги
                'the': '',
                'a': '',
                'an': '',
                'and': 'и',
                'or': 'или',
                'but': 'но',
                'in': 'в',
                'on': 'на',
                'at': 'в',
                'to': 'к',
                'for': 'для',
                'with': 'с',
                'from': 'из',
                'of': 'из',
                'by': 'от',
                
                # Частые глаголы
                'is': 'является',
                'are': 'являются',
                'was': 'был',
                'were': 'были',
                'have': 'иметь',
                'has': 'имеет',
                'do': 'делать',
                'does': 'делает',
                'can': 'мочь',
                'could': 'мог',
                'will': 'будет',
                'would': 'бы',
                
                # Прилагательные
                'good': 'хороший',
                'bad': 'плохой',
                'new': 'новый',
                'old': 'старый',
                'big': 'большой',
                'small': 'маленький',
                'beautiful': 'красивый',
                'interesting': 'интересный',
                'important': 'важный',
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
                'автор': 'author',
                'название': 'title',
                'содержание': 'content',
                'анализ': 'analysis',
                'персонаж': 'character',
                'сюжет': 'plot',
                'история': 'story',
                'литература': 'literature',
                'и': 'and',
                'или': 'or',
                'но': 'but',
                'в': 'in',
                'на': 'on',
                'для': 'for',
                'с': 'with',
            }
        }
        
        # Паттерны для литературных переводов
        self.literary_patterns = {
            'en-ru': [
                (r'\bIt is\b', 'Это'),
                (r'\bhe said\b', 'сказал он'),
                (r'\bshe said\b', 'сказала она'),
                (r'\bthey said\b', 'сказали они'),
                (r'\bI think\b', 'Я думаю'),
                (r'\byou know\b', 'знаете ли'),
                (r'\bof course\b', 'конечно'),
                (r'\bin fact\b', 'на самом деле'),
                (r'\bat first\b', 'сначала'),
                (r'\bat last\b', 'наконец'),
            ]
        }
    
    def translate(self, text: str, source_lang: str, target_lang: str, style: str = "artistic") -> str:
        """Улучшенный перевод с литературными паттернами"""
        # Если языки совпадают
        if source_lang == target_lang:
            return self._apply_style(text, style)
        
        key = f"{source_lang}-{target_lang}"
        
        # Ограничиваем длину текста
        if len(text) > 800:
            text = text[:800] + "..."
        
        # Применяем литературные паттерны
        if key in self.literary_patterns:
            for pattern, replacement in self.literary_patterns[key]:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Пробуем словарный перевод
        if key in self.translation_dict:
            result = self._dictionary_translate(text, key)
        else:
            result = text
        
        # Применяем стиль
        result = self._apply_style(result, style)
        
        # Добавляем префикс языка
        if source_lang == 'en' and target_lang == 'ru':
            result = f"[ПЕРЕВОД] {result}"
        elif source_lang == 'ru' and target_lang == 'en':
            result = f"[TRANSLATION] {result}"
        else:
            result = f"[{source_lang}→{target_lang}] {result}"
        
        return result
    
    def _dictionary_translate(self, text: str, lang_key: str) -> str:
        """Перевод по словарю"""
        words = re.findall(r'\b\w+\b|[^\w\s]', text)
        translated = []
        dict_map = self.translation_dict[lang_key]
        
        for word in words:
            if re.match(r'^\w+$', word):
                lower_word = word.lower()
                if lower_word in dict_map:
                    trans = dict_map[lower_word]
                    if trans:
                        # Сохраняем регистр первого символа
                        if word[0].isupper():
                            trans = trans[0].upper() + trans[1:] if len(trans) > 0 else trans
                        translated.append(trans)
                    else:
                        translated.append('')
                else:
                    translated.append(word)
            else:
                translated.append(word)
        
        # Собираем текст, убирая лишние пробелы перед знаками препинания
        result = ' '.join(translated)
        result = re.sub(r'\s+([.,!?;:])', r'\1', result)
        result = re.sub(r'\s+', ' ', result)
        
        return result.strip()
    
    def _apply_style(self, text: str, style: str) -> str:
        """Применение стиля к тексту"""
        if style == "artistic":
            return f"🎨 {text}"
        elif style == "formal":
            return f"📄 {text}"
        elif style == "academic":
            return f"📚 {text}"
        elif style == "simple":
            return text
        else:
            return text

# Создаем экземпляр простого переводчика сразу
local_translator = LocalTranslator()

# ========== НАСТОЯЩИЙ ПЕРЕВОДЧИК HUGGING FACE (отложенная загрузка) ==========
class HuggingFaceTranslator:
    """Настоящий переводчик через Hugging Face модели"""
    
    def __init__(self):
        self.translation_pipelines = {
            'en-ru': None,
            'ru-en': None,
        }
        self.model_configs = {}
        self.initialized = False
    
    def initialize(self):
        """Инициализация моделей перевода (ленивая загрузка)"""
        if self.initialized:
            return True
            
        try:
            logger.info("🌍 Начинаем загрузку Hugging Face переводчика...")
            from transformers import pipeline
            import torch
            
            device = 0 if torch.cuda.is_available() else -1
            device_name = "CUDA" if torch.cuda.is_available() else "CPU"
            
            # Конфигурация моделей
            self.model_configs = {
                'en-ru': {
                    'model': 'Helsinki-NLP/opus-mt-en-ru',
                    'description': 'Перевод English → Russian',
                    'max_length': 400
                },
                'ru-en': {
                    'model': 'Helsinki-NLP/opus-mt-ru-en',
                    'description': 'Перевод Russian → English',
                    'max_length': 400
                }
            }
            
            logger.info(f"✅ Hugging Face переводчик готов к ленивой загрузке (устройство: {device_name})")
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации переводчика: {e}")
            return False
    
    def _get_translation_pipeline(self, source_lang: str, target_lang: str):
        """Получить или загрузить pipeline для перевода"""
        if not self.initialized:
            return None
            
        key = f"{source_lang}-{target_lang}"
        
        if key not in self.translation_pipelines:
            return None
        
        if self.translation_pipelines[key] is None:
            try:
                from transformers import pipeline
                import torch
                
                device = 0 if torch.cuda.is_available() else -1
                
                if key in self.model_configs:
                    model_config = self.model_configs[key]
                    logger.info(f"🔄 Загружаем модель перевода {key} ({model_config['model']})...")
                    
                    self.translation_pipelines[key] = pipeline(
                        "translation",
                        model=model_config['model'],
                        device=device,
                        max_length=model_config['max_length']
                    )
                    
                    logger.info(f"✅ Модель перевода {key} загружена")
                else:
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки модели перевода {key}: {e}")
                return None
        
        return self.translation_pipelines[key]
    
    def translate(self, text: str, source_lang: str, target_lang: str, style: str = "artistic") -> str:
        """Настоящий перевод через Hugging Face"""
        # Если не инициализирован, используем fallback
        if not self.initialized:
            return local_translator.translate(text, source_lang, target_lang, style)
        
        # Если языки совпадают - возвращаем как есть
        if source_lang == target_lang:
            return local_translator._apply_style(text, style)
        
        # Основные поддерживаемые языки
        supported_pairs = ['en-ru', 'ru-en']
        key = f"{source_lang}-{target_lang}"
        
        if key not in supported_pairs:
            # Для неподдерживаемых пар используем простой перевод
            logger.warning(f"⚠️ Неподдерживаемая пара переводов: {key}")
            return local_translator.translate(text, source_lang, target_lang, style)
        
        try:
            # Получаем pipeline
            pipeline = self._get_translation_pipeline(source_lang, target_lang)
            
            if pipeline is None:
                # Fallback на простой перевод
                logger.warning(f"⚠️ Pipeline перевода {key} не загружен")
                return local_translator.translate(text, source_lang, target_lang, style)
            
            # Ограничиваем длину для памяти
            if len(text) > 1000:
                original_text = text
                text = text[:1000]
                logger.info(f"📝 Текст усечен с {len(original_text)} до {len(text)} символов")
            
            # Выполняем перевод
            logger.info(f"🔄 Перевод {len(text)} символов: {source_lang} → {target_lang}")
            
            result = pipeline(text, max_length=400, truncation=True)
            
            if result and len(result) > 0:
                translated_text = result[0].get('translation_text', text)
                logger.info(f"✅ Перевод завершен: {len(text)} → {len(translated_text)} символов")
                
                # Применяем стиль
                translated_text = local_translator._apply_style(translated_text, style)
                
                return translated_text
            else:
                logger.warning(f"⚠️ Переводчик вернул пустой результат для {key}")
                return local_translator.translate(text, source_lang, target_lang, style)
                
        except Exception as e:
            logger.error(f"❌ Ошибка перевода {key}: {e}")
            # Fallback на простой перевод
            return local_translator.translate(text, source_lang, target_lang, style)
    
    def is_available(self, source_lang: str, target_lang: str) -> bool:
        """Проверка доступности перевода для языковой пары"""
        if not self.initialized:
            return False
            
        key = f"{source_lang}-{target_lang}"
        
        if key in self.model_configs:
            pipeline = self._get_translation_pipeline(source_lang, target_lang)
            return pipeline is not None
        
        return False

# Создаем экземпляр, но НЕ инициализируем пока
hf_translator = HuggingFaceTranslator()

# ========== ФУНКЦИИ ДЛЯ ОТЛОЖЕННОЙ ЗАГРУЗКИ AI МОДЕЛЕЙ ==========
def init_huggingface_for_analysis_background():
    """Инициализация Hugging Face моделей для анализа в фоне"""
    global HUGGING_FACE_ENABLED, HF_ANALYSIS_PIPELINES, HF_ANALYSIS_READY
    
    try:
        import transformers
        import torch
        
        # Проверяем доступность CUDA
        device = 0 if torch.cuda.is_available() else -1
        device_name = "CUDA" if torch.cuda.is_available() else "CPU"
        logger.info(f"🏗️ Фоновая инициализация Hugging Face анализа на {device_name}")
        
        # Список моделей для анализа
        analysis_models = {
            "sentiment": {
                "model_name": "blanchefort/rubert-base-cased-sentiment",
                "task": "sentiment-analysis"
            },
            "summarization": {
                "model_name": "IlyaGusev/rut5_base_sum_gazeta",
                "task": "summarization"
            },
            "ner": {
                "model_name": "Babelscape/wikineural-multilingual-ner",
                "task": "ner"
            },
        }
        
        # Ленивая загрузка моделей
        HF_ANALYSIS_PIPELINES = {
            task: {"model_name": config["model_name"], "pipeline": None, "task": config["task"]}
            for task, config in analysis_models.items()
        }
        
        HUGGING_FACE_ENABLED = True
        
        # Предзагружаем только sentiment модель (самую легкую)
        try:
            logger.info("🔄 Фоновая загрузка модели анализа тональности...")
            from transformers import pipeline
            sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=analysis_models["sentiment"]["model_name"],
                device=device
            )
            HF_ANALYSIS_PIPELINES["sentiment"]["pipeline"] = sentiment_pipeline
            logger.info("✅ Модель анализа тональности загружена в фоне")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить sentiment модель: {e}")
        
        HF_ANALYSIS_READY = True
        logger.info("✅ Hugging Face анализ готов в фоне")
        
    except ImportError as e:
        logger.warning(f"⚠️ transformers не установлен: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка фоновой инициализации Hugging Face анализа: {e}")

def get_hf_analysis_pipeline(task: str):
    """Получить pipeline для задачи анализа (ленивая загрузка)"""
    if task not in HF_ANALYSIS_PIPELINES:
        logger.error(f"❌ Неизвестная задача анализа: {task}")
        return None
    
    if HF_ANALYSIS_PIPELINES[task]["pipeline"] is None and HUGGING_FACE_ENABLED:
        try:
            from transformers import pipeline
            import torch
            
            device = 0 if torch.cuda.is_available() else -1
            model_config = HF_ANALYSIS_PIPELINES[task]
            logger.info(f"🔄 Ленивая загрузка модели анализа {model_config['model_name']} для задачи {task}...")
            
            if task == "summarization":
                hf_pipeline = pipeline(
                    "summarization",
                    model=model_config["model_name"],
                    tokenizer=model_config["model_name"],
                    device=device,
                    max_length=150,
                    min_length=50
                )
            elif task == "ner":
                hf_pipeline = pipeline(
                    "ner",
                    model=model_config["model_name"],
                    device=device,
                    grouped_entities=True,
                    ignore_labels=["O"]
                )
            else:
                hf_pipeline = pipeline(
                    model_config["task"],
                    model=model_config["model_name"],
                    device=device
                )
            
            HF_ANALYSIS_PIPELINES[task]["pipeline"] = hf_pipeline
            logger.info(f"✅ Модель анализа {model_config['model_name']} лениво загружена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка ленивой загрузки модели анализа {task}: {e}")
            return None
    
    return HF_ANALYSIS_PIPELINES[task]["pipeline"]

# ========== ФУНКЦИЯ ДЛЯ ФОНОВОЙ ИНИЦИАЛИЗАЦИИ ВСЕХ AI МОДЕЛЕЙ ==========
def init_all_ai_models_in_background():
    """Фоновая инициализация всех AI моделей"""
    logger.info("🚀 Запуск фоновой инициализации AI моделей...")
    
    # 1. Сначала инициализируем Hugging Face переводчик
    logger.info("🔄 Инициализация переводчика Hugging Face...")
    if hf_translator.initialize():
        global HF_TRANSLATOR_READY
        HF_TRANSLATOR_READY = True
        logger.info("✅ Переводчик Hugging Face инициализирован в фоне")
    
    # 2. Затем инициализируем анализ
    logger.info("🔄 Инициализация анализа Hugging Face...")
    init_huggingface_for_analysis_background()
    
    logger.info("🎉 Все AI модели инициализированы в фоне!")

# ========== ЗАПУСКАЕМ ФОНОВУЮ ИНИЦИАЛИЗАЦИЮ AI МОДЕЛЕЙ ==========
# Но НЕ блокируем основной поток!
ai_init_thread = threading.Thread(target=init_all_ai_models_in_background, daemon=True)
ai_init_thread.start()
logger.info("🧵 Запущен фоновый поток для инициализации AI моделей")

# ========== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ПРИ СТАРТЕ ==========
def init_database():
    """Инициализация базы данных"""
    try:
        from database import engine, Base
        from models import User, Document, DocumentNote, ReadingProgress, DocumentAnalysis, FavoriteQuote, TranslationCache
        
        logger.info("🗄️  Создаем таблицы PostgreSQL...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Таблицы созданы успешно!")
        return True
    except Exception as e:
        logger.warning(f"⚠️ База данных недоступна: {e}")
        logger.info("📝 Используем in-memory хранилище для документов")
        return False

# Запускаем инициализацию БД
init_database()

# ========== ИНИЦИАЛИЗАЦИЯ NLTK (если доступен) ==========
try:
    import nltk
    from nltk.tokenize import sent_tokenize, word_tokenize
    from nltk.corpus import stopwords
    
    # Загружаем ресурсы NLTK
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('punkt', quiet=True)
        nltk.download('stopwords', quiet=True)
        nltk.download('punkt_tab', quiet=True)
    
    NLTK_AVAILABLE = True
    logger.info("✅ NLTK успешно инициализирован")
except ImportError:
    NLTK_AVAILABLE = False
    logger.warning("⚠️ NLTK не установлен, часть анализа будет ограничена")

# ========== УТИЛИТЫ ДЛЯ АНАЛИЗА ==========
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
        
        if cyrillic > latin * 1.5:  # Учитываем коэффициент
            return "ru"
        else:
            return "en"
    except:
        return "en"

# ========== УЛУЧШЕННОЕ ОПРЕДЕЛЕНИЕ ГЛАВ ==========
def detect_chapters(text: str) -> List[Dict]:
    """Улучшенное определение глав в тексте"""
    chapters = []
    
    if not text:
        return [{'title': 'Документ', 'content': 'Нет содержимого'}]
    
    # Убираем лишние пробелы и переносы
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    
    # Паттерны для определения глав (русский и английский)
    chapter_patterns = [
        r'^\s*(?:ГЛАВА|Глава|Г\.)\s+[IVXLCDM\d]+[\.\s].*$',
        r'^\s*(?:CHAPTER|Chapter|Ch\.)\s+[IVXLCDM\d]+[\.\s].*$',
        r'^\s*[IVXLCDM\d]+[\.\)]\s+.*$',
        r'^\s*\d+[\.\)]\s+.*$',
        r'^\s*[A-Z][A-Z\s]{2,}[\.\?!]?$',  # Заголовки ВСЕМИ БУКВАМИ
        r'^\s*.+\n[-=]{3,}$',  # Заголовок с подчеркиванием
    ]
    
    # Разбиваем текст на абзацы
    paragraphs = text.split('\n\n')
    
    current_chapter = None
    chapter_content = []
    
    for i, paragraph in enumerate(paragraphs):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        
        # Проверяем, является ли абзац заголовком главы
        is_chapter_title = False
        for pattern in chapter_patterns:
            if re.match(pattern, paragraph, re.MULTILINE | re.IGNORECASE):
                is_chapter_title = True
                break
        
        if is_chapter_title:
            # Сохраняем предыдущую главу, если есть
            if current_chapter is not None and chapter_content:
                chapters.append({
                    'title': current_chapter,
                    'content': '\n\n'.join(chapter_content)
                })
            
            # Начинаем новую главу
            current_chapter = paragraph[:100]  # Ограничиваем длину заголовка
            chapter_content = []
        else:
            # Добавляем абзац к текущей главе
            if current_chapter is None:
                # Если еще нет главы, создаем первую
                current_chapter = 'Начало'
            chapter_content.append(paragraph)
    
    # Добавляем последнюю главу
    if current_chapter and chapter_content:
        chapters.append({
            'title': current_chapter,
            'content': '\n\n'.join(chapter_content)
        })
    
    # Если не нашли глав, разбиваем на части по объему
    if not chapters:
        chunk_size = 5000
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chapters.append({
                    'title': f'Часть {len(chapters) + 1}',
                    'content': chunk
                })
    
    return chapters

# ========== HEALTH CHECK ENDPOINTS (ДОЛЖНЫ РАБОТАТЬ СРАЗУ!) ==========
@app.get("/")
async def root():
    """Корневой эндпоинт - работает сразу!"""
    return {
        "message": "Versevo Backend API v6.0",
        "version": "6.0.0",
        "status": "running",
        "ai_models_loading": "in_progress" if not HF_TRANSLATOR_READY else "ready",
        "database": "PostgreSQL",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/flutter/health")
async def flutter_health_check():
    """Эндпоинт для healthcheck Railway/Flutter - работает СРАЗУ!"""
    return {
        "status": "healthy", 
        "service": "versevo-backend",
        "database": "PostgreSQL",
        "timestamp": datetime.now().isoformat(),
        "version": "6.0.0",
        "ai_models": "loading_in_background" if not HF_TRANSLATOR_READY else "ready"
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint - работает СРАЗУ!"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "database": "PostgreSQL",
        "ai_translator": "ready" if HF_TRANSLATOR_READY else "loading",
        "ai_analysis": "ready" if HF_ANALYSIS_READY else "loading",
        "timestamp": datetime.now().isoformat(),
        "version": "6.0.0"
    }

# ========== ДОКУМЕНТЫ (СТАРЫЕ ЭНДПОИНТЫ ДЛЯ СОВМЕСТИМОСТИ) ==========
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
            content_str = f"Документ: {filename}\nТип: {file_extension}\n\nСодержимое недоступно для автоматического извлечения."
        
        language = detect_language_safe(content_str)
        chapters = detect_chapters(content_str)
        
        # Вычисляем статистику
        word_count = len(content_str.split())
        char_count = len(content_str)
        reading_time = max(1, word_count // 200)
        
        document = {
            "id": current_doc_id,
            "filename": filename,
            "original_filename": filename,
            "content": content_str,
            "language": language,
            "file_type": file_extension,
            "file_path": file_path,
            "file_id": file_id,
            "word_count": word_count,
            "char_count": char_count,
            "chapter_count": len(chapters),
            "reading_time_minutes": reading_time,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "chapters": chapters,
        }
        
        documents_store[current_doc_id] = document
        current_doc_id += 1
        
        logger.info(f"✅ Документ загружен: {filename} (ID: {document['id']}, слов: {word_count})")
        
        return {
            "id": document["id"],
            "filename": document["filename"],
            "language": document["language"],
            "file_type": document["file_type"],
            "word_count": document["word_count"],
            "char_count": document["char_count"],
            "chapter_count": document["chapter_count"],
            "reading_time_minutes": document["reading_time_minutes"],
            "created_at": document["created_at"],
            "content_preview": document["content"][:300] + "..." if len(document["content"]) > 300 else document["content"],
        }
        
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
    
    doc = documents_store[document_id]
    
    return {
        "id": doc["id"],
        "filename": doc["filename"],
        "content": doc["content"],
        "language": doc["language"],
        "file_type": doc["file_type"],
        "word_count": doc["word_count"],
        "char_count": doc["char_count"],
        "chapter_count": doc["chapter_count"],
        "reading_time_minutes": doc["reading_time_minutes"],
        "created_at": doc["created_at"],
        "chapters": doc["chapters"],
    }

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
        
        target_lang = request.target_language
        
        # Выбираем переводчик в зависимости от доступности
        use_huggingface = HF_TRANSLATOR_READY and hf_translator.is_available(source_lang, target_lang)
        
        if use_huggingface:
            logger.info(f"🔄 Используем Hugging Face перевод: {source_lang} → {target_lang}")
            translated_text = hf_translator.translate(
                request.text, 
                source_lang, 
                target_lang, 
                request.style
            )
            translation_service = "huggingface"
        else:
            logger.info(f"🔄 Используем fallback перевод: {source_lang} → {target_lang}")
            translated_text = local_translator.translate(
                request.text, 
                source_lang, 
                target_lang, 
                request.style
            )
            translation_service = "fallback"
        
        return {
            "original_text": request.text,
            "translated_text": translated_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "style": request.style,
            "translation_service": translation_service,
            "original_length": len(request.text),
            "translated_length": len(translated_text),
            "huggingface_used": use_huggingface,
        }
        
    except Exception as e:
        logger.error(f"Translate error: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

# ========== УЛУЧШЕННЫЙ БАЗОВЫЙ АНАЛИЗ ==========
def _perform_basic_analysis(text: str) -> Dict[str, Any]:
    """Улучшенный базовый анализ текста"""
    result = {
        "summary": "",
        "themes": [],
        "sentiment": "Нейтральный",
        "complexity": "Средний",
        "key_points": [],
        "statistics": {},
        "language_features": {},
    }
    
    if not text or len(text.strip()) < 10:
        result["summary"] = "Текст слишком короткий для анализа"
        return result
    
    try:
        # Базовые метрики
        words = [w for w in text.split() if w.strip()]
        sentences = re.split(r'[.!?]+', text)
        paragraphs = text.split('\n\n')
        
        # Убираем пустые элементы
        sentences = [s.strip() for s in sentences if s.strip()]
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        word_count = len(words)
        sentence_count = len(sentences)
        paragraph_count = len(paragraphs)
        
        # Сложность текста
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
        if avg_sentence_length < 8:
            complexity = "Простой"
        elif avg_sentence_length < 15:
            complexity = "Средний"
        else:
            complexity = "Сложный"
        
        # Создаем краткое содержание
        if sentence_count >= 3:
            summary_sentences = []
            for sent in sentences[:4]:
                clean_sent = sent.strip()
                if len(clean_sent) > 10 and not clean_sent.isupper():  # Пропускаем заголовки
                    summary_sentences.append(clean_sent)
            
            if summary_sentences:
                result["summary"] = " ".join(summary_sentences)
                if len(result["summary"]) > 250:
                    result["summary"] = result["summary"][:250] + "..."
            else:
                result["summary"] = text[:200] + "..." if len(text) > 200 else text
        else:
            result["summary"] = text[:200] + "..." if len(text) > 200 else text
        
        # Определяем темы (слова с большой буквы и частые слова)
        themes = []
        
        # Имена собственные (слова с большой буквы)
        proper_nouns = re.findall(r'\b[A-Z][a-z]+\b', text[:1000])
        if proper_nouns:
            noun_counter = Counter([n.lower() for n in proper_nouns])
            common_proper = [noun for noun, count in noun_counter.most_common(5) 
                           if count > 1 and len(noun) > 3]
            themes.extend(common_proper[:3])
        
        # Частые слова (длиной более 3 букв)
        if not themes:
            word_freq = Counter([w.lower() for w in words if len(w) > 3])
            stop_words = {'это', 'что', 'как', 'для', 'того', 'чтобы', 'если', 
                         'когда', 'или', 'и', 'но', 'а', 'the', 'and', 'but', 
                         'for', 'with', 'from', 'that', 'this', 'was', 'were'}
            common_words = [word for word, count in word_freq.most_common(10) 
                          if word not in stop_words and count > 1][:3]
            themes.extend(common_words)
        
        # Если все еще нет тем, используем общие
        if not themes:
            themes = ["Документ", "Текст", "Содержание"]
        
        result["themes"] = themes[:3]
        result["complexity"] = complexity
        result["sentiment"] = "Нейтральный"
        
        result["statistics"] = {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
            "avg_sentence_length": round(avg_sentence_length, 1),
            "avg_word_length": round(sum(len(w) for w in words) / word_count if word_count > 0 else 0, 1),
            "reading_time_minutes": max(1, word_count // 200),
        }
        
        # Анализ языка
        cyrillic = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
        latin = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
        
        result["language_features"] = {
            "detected_language": "ru" if cyrillic > latin else "en",
            "has_dialogue": bool(re.search(r'["\'«»]', text)),
            "has_numbers": bool(re.search(r'\d+', text)),
            "has_questions": "?" in text,
            "has_exclamations": "!" in text,
        }
        
        # Ключевые точки
        key_points = [
            f"Объем: {word_count} слов",
            f"Сложность: {complexity}",
            f"Время чтения: {max(1, word_count // 200)} мин",
        ]
        
        if themes:
            key_points.append(f"Темы: {', '.join(themes[:2])}")
        
        result["key_points"] = key_points
        
    except Exception as e:
        logger.error(f"Ошибка базового анализа: {e}")
        result["summary"] = "Произошел сбой при анализе текста"
        result["key_points"] = ["Не удалось выполнить анализ"]
    
    return result

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int):
    """Удаление документа"""
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Удаляем файл с диска
        doc = documents_store[document_id]
        if os.path.exists(doc["file_path"]):
            try:
                os.remove(doc["file_path"])
            except:
                pass
        
        # Удаляем из хранилища
        del documents_store[document_id]
        
        logger.info(f"🗑️ Документ удален: ID {document_id}")
        
        return {
            "status": "success",
            "message": f"Document {document_id} deleted",
            "deleted_id": document_id
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка удаления документа: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

# ========== УЛУЧШЕННЫЙ AI АНАЛИЗ ==========
def _perform_ai_analysis(text: str) -> Dict[str, Any]:
    """Улучшенный AI анализ текста через Hugging Face"""
    result = {
        "summary": "",
        "themes": [],
        "sentiment": "Нейтральный",
        "writing_style": "Информационный",
        "key_points": [],
        "entities": [],
        "ai_analysis": False,
        "fallback": False,
        "models_used": [],
    }
    
    if not HUGGING_FACE_ENABLED or not text or len(text.strip()) < 50:
        result["fallback"] = True
        return result
    
    try:
        # Берем первые 2000 символов для анализа
        sample_text = text[:2000]
        
        # 1. Анализ тональности
        sentiment_pipeline = get_hf_analysis_pipeline("sentiment")
        if sentiment_pipeline:
            try:
                sentiment_result = sentiment_pipeline(sample_text[:512])
                if sentiment_result and len(sentiment_result) > 0:
                    label = sentiment_result[0].get("label", "NEUTRAL").upper()
                    score = sentiment_result[0].get("score", 0.5)
                    
                    sentiment_map = {
                        "POSITIVE": "Положительный",
                        "NEGATIVE": "Отрицательный", 
                        "NEUTRAL": "Нейтральный",
                        "LABEL_0": "Отрицательный",
                        "LABEL_1": "Нейтральный",
                        "LABEL_2": "Положительный",
                    }
                    
                    result["sentiment"] = sentiment_map.get(label, "Нейтральный")
                    result["sentiment_score"] = round(score, 3)
                    result["models_used"].append("sentiment")
                    result["ai_analysis"] = True
            except Exception as e:
                logger.warning(f"⚠️ Ошибка анализа тональности: {e}")
        
        # 2. Суммаризация (только для достаточно длинных текстов)
        if len(text.split()) > 150:
            summarization_pipeline = get_hf_analysis_pipeline("summarization")
            
            if summarization_pipeline:
                try:
                    # Подготавливаем текст для суммаризации
                    clean_text = re.sub(r'\s+', ' ', sample_text.strip())
                    if len(clean_text) > 100:
                        summary_result = summarization_pipeline(
                            clean_text,
                            max_length=120,
                            min_length=60,
                            do_sample=False
                        )
                        
                        if summary_result and len(summary_result) > 0:
                            summary = summary_result[0].get("summary_text", "")
                            # Убираем [ПЕРЕВОД] если есть
                            summary = re.sub(r'^\[ПЕРЕВОД\]\s*', '', summary)
                            result["summary"] = summary
                            result["models_used"].append("summarization")
                            result["ai_analysis"] = True
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка суммаризации: {e}")
        
        # 3. Извлечение именованных сущностей
        ner_pipeline = get_hf_analysis_pipeline("ner")
        
        if ner_pipeline:
            try:
                ner_result = ner_pipeline(sample_text[:1000])
                entities = []
                
                for entity in ner_result:
                    if isinstance(entity, dict):
                        entity_word = entity.get("word", "")
                        entity_group = entity.get("entity_group", "")
                        
                        # Фильтруем мусор
                        if (entity_group in ["PER", "ORG", "LOC"] and 
                            len(entity_word) > 2 and 
                            not re.match(r'^\d+$', entity_word)):
                            
                            entities.append({
                                "entity": entity_group,
                                "word": entity_word,
                                "score": round(entity.get("score", 0.0), 3)
                            })
                
                if entities:
                    # Берем только уникальные сущности
                    unique_entities = []
                    seen = set()
                    for e in entities:
                        key = f"{e['entity']}_{e['word'].lower()}"
                        if key not in seen:
                            unique_entities.append(e)
                            seen.add(key)
                    
                    result["entities"] = unique_entities[:10]
                    result["models_used"].append("ner")
                    result["ai_analysis"] = True
                    
                    # Формируем темы из сущностей
                    entity_types = Counter([e["entity"] for e in result["entities"]])
                    themes = []
                    for entity_type, count in entity_types.most_common(3):
                        if entity_type == "PER":
                            themes.append("Персонажи")
                        elif entity_type == "ORG":
                            themes.append("Организации")
                        elif entity_type == "LOC":
                            themes.append("Места")
                    
                    if themes:
                        result["themes"] = themes
                        
            except Exception as e:
                logger.warning(f"⚠️ Ошибка NER анализа: {e}")
        
        # 4. Определение стиля письма
        word_count = len(text.split())
        sentence_count = len(re.split(r'[.!?]+', text))
        
        if word_count > 5000:
            writing_style = "Академический"
        elif sentence_count > 0 and word_count / sentence_count > 25:
            writing_style = "Литературный"
        elif "?" in text and "!" in text and '"' in text:
            writing_style = "Диалогический"
        else:
            writing_style = "Информационный"
        
        result["writing_style"] = writing_style
        
        # 5. Формируем ключевые точки на основе анализа
        key_points = []
        
        if result["entities"]:
            people = [e["word"] for e in result["entities"] if e["entity"] == "PER"]
            if people and len(people) > 0:
                key_points.append(f"Персонажи: {', '.join(people[:2])}")
        
        if result["sentiment"] != "Нейтральный":
            key_points.append(f"Тональность: {result['sentiment']}")
        
        key_points.append(f"Стиль письма: {writing_style}")
        
        # Добавляем базовые ключевые точки
        if word_count > 0:
            reading_time = max(1, word_count // 200)
            key_points.append(f"Время чтения: {reading_time} мин")
            key_points.append(f"Объем: {word_count} слов")
        
        result["key_points"] = key_points
        
        # 6. Если не удалось получить суммаризацию, создаем базовую
        if not result["summary"]:
            sentences = re.split(r'[.!?]+', text)
            if len(sentences) > 2:
                summary_sentences = []
                for sent in sentences[:3]:
                    clean_sent = sent.strip()
                    if len(clean_sent) > 10:  # Пропускаем очень короткие
                        summary_sentences.append(clean_sent)
                
                if summary_sentences:
                    result["summary"] = " ".join(summary_sentences)[:300] + "..."
                else:
                    result["summary"] = text[:200] + "..." if len(text) > 200 else text
            else:
                result["summary"] = text[:300] + "..." if len(text) > 300 else text
        
        # 7. Если не определили темы, используем частые слова
        if not result["themes"]:
            try:
                # Извлекаем существительные (слова с большой буквы)
                nouns = re.findall(r'\b[A-Z][a-z]+\b', text[:1000])
                if nouns:
                    noun_counter = Counter([n.lower() for n in nouns])
                    common_nouns = [noun for noun, count in noun_counter.most_common(5) 
                                  if count > 1 and len(noun) > 3]
                    if common_nouns:
                        result["themes"] = common_nouns[:3]
            except:
                pass
        
        # Если темы все еще пустые, используем общие
        if not result["themes"]:
            result["themes"] = ["Литература", "Текст", "Содержание"]
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка AI анализа: {e}")
        result["fallback"] = True
        result["summary"] = "AI анализ временно недоступен. Используется базовый анализ."
        return result

# ========== AI АНАЛИЗ ЭНДПОИНТЫ ==========
@app.get("/api/analyze/ai/health")
async def ai_health_check():
    """Проверка доступности AI"""
    return {
        "status": "ready" if HF_ANALYSIS_READY else "loading",
        "service": "huggingface",
        "available": HUGGING_FACE_ENABLED,
        "models_ready": HF_ANALYSIS_READY,
        "models_available": list(HF_ANALYSIS_PIPELINES.keys()),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/analyze/ai/document")
async def analyze_with_ai(request: AIAnalysisRequest):
    """AI-анализ документа через Hugging Face"""
    
    try:
        document_id = request.document_id
        
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        # Проверяем готовность AI
        if not HF_ANALYSIS_READY:
            return {
                "document_id": document_id,
                "summary": "AI модели еще загружаются. Пожалуйста, подождите несколько секунд и попробуйте снова.",
                "themes": ["Загрузка AI"],
                "sentiment": "Не определена",
                "writing_style": "Не определен",
                "key_points": [
                    "AI модели загружаются в фоне",
                    "Попробуйте обновить страницу через 30 секунд",
                    "Используйте базовый анализ пока"
                ],
                "ai_analysis": False,
                "fallback": True,
                "analysis_timestamp": datetime.now().isoformat(),
            }
        
        # Выполняем анализ
        logger.info(f"🔍 Начинаем AI анализ документа {document_id}")
        
        # Базовый анализ
        basic_analysis = _perform_basic_analysis(content)
        
        # AI анализ (если доступен)
        ai_analysis = _perform_ai_analysis(content)
        
        # Объединяем результаты
        result = {
            "document_id": document_id,
            "filename": doc["filename"],
            "language": doc["language"],
            
            # Основные результаты
            "summary": ai_analysis.get("summary") or basic_analysis.get("summary"),
            "themes": ai_analysis.get("themes") or basic_analysis.get("themes", []),
            "sentiment": ai_analysis.get("sentiment") or basic_analysis.get("sentiment"),
            "writing_style": ai_analysis.get("writing_style") or "Информационный",
            
            # Детали анализа
            "key_points": ai_analysis.get("key_points") or basic_analysis.get("key_points", []),
            "entities": ai_analysis.get("entities", []),
            "statistics": basic_analysis.get("statistics", {}),
            "language_features": basic_analysis.get("language_features", {}),
            
            # Метрики
            "ai_analysis": ai_analysis.get("ai_analysis", False),
            "fallback": ai_analysis.get("fallback", True),
            "models_used": ai_analysis.get("models_used", []),
            "analysis_type": request.analysis_type,
            
            # Время
            "analysis_timestamp": datetime.now().isoformat(),
            "analysis_duration_ms": 0,
        }
        
        # Добавляем дополнительную информацию из документа
        result["document_metadata"] = {
            "word_count": doc["word_count"],
            "chapter_count": doc["chapter_count"],
            "reading_time": doc["reading_time_minutes"],
            "created_at": doc["created_at"],
        }
        
        # Если AI анализ не удался, добавляем информацию о fallback
        if ai_analysis.get("fallback"):
            result["analysis_notes"] = ["Использован базовый анализ из-за недоступности AI"]
        
        logger.info(f"✅ AI анализ завершен для документа {document_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка AI анализа документа: {e}")
        
        # Fallback ответ
        return {
            "document_id": request.document_id,
            "summary": "Произошла ошибка при AI-анализе. Используется упрощенный анализ.",
            "themes": ["Ошибка анализа"],
            "sentiment": "Не определена",
            "writing_style": "Не определен",
            "key_points": [
                "Не удалось выполнить полный AI-анализ",
                "Попробуйте использовать базовый анализ",
                "Ошибка: " + str(e)[:100]
            ],
            "entities": [],
            "ai_analysis": False,
            "fallback": True,
            "analysis_timestamp": datetime.now().isoformat(),
            "error": str(e)[:200],
        }

# ========== БАЗОВЫЙ АНАЛИЗ ЭНДПОИНТ ==========
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
        
        logger.info(f"🔍 Базовый анализ документа {document_id}")
        
        # Выполняем базовый анализ
        analysis_result = _perform_basic_analysis(content)
        
        # Формируем полный ответ
        result = {
            "document_id": document_id,
            "filename": doc["filename"],
            "language": doc["language"],
            
            # Результаты анализа
            "summary": analysis_result["summary"],
            "themes": analysis_result["themes"],
            "sentiment": analysis_result["sentiment"],
            "complexity": analysis_result["complexity"],
            "writing_style": "Информационный",
            
            # Ключевые точки
            "key_points": analysis_result["key_points"],
            
            # Статистика
            "statistics": analysis_result["statistics"],
            "language_features": analysis_result["language_features"],
            
            # Метрики документа
            "document_statistics": {
                "word_count": doc["word_count"],
                "char_count": doc["char_count"],
                "chapter_count": doc["chapter_count"],
                "reading_time_minutes": doc["reading_time_minutes"],
                "file_type": doc["file_type"],
            },
            
            # Персонажи (пустой для базового анализа)
            "characters": [],
            "entities": [],
            
            # Метрики анализа
            "ai_analysis": False,
            "fallback": False,
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat(),
        }
        
        logger.info(f"✅ Базовый анализ завершен для документа {document_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка базового анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ========== ЦИТАТЫ ИЗ ДОКУМЕНТА ==========
def _similarity(s1: str, s2: str) -> float:
    """Вычисление схожести строк (упрощенное)"""
    # Используем последовательности слов для сравнения
    words1 = set(s1.split())
    words2 = set(s2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union)

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
                "document_id": document_id,
                "quotes": ["Текст документа пустой или слишком короткий"],
                "count": 1,
                "ai_analysis": False,
                "fallback": True
            }
        
        # Извлекаем предложения
        sentences = re.split(r'(?<=[.!?])\s+', content)
        quotes = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            # Берем только содержательные предложения
            if 30 < len(sentence) < 250:
                quotes.append(sentence)
                if len(quotes) >= limit * 2:  # Берем больше для фильтрации
                    break
        
        # Фильтруем похожие цитаты
        unique_quotes = []
        seen_content = set()
        
        for quote in quotes:
            # Нормализуем цитату (убираем лишние пробелы, приводим к нижнему регистру)
            normalized = ' '.join(quote.lower().split())
            
            # Проверяем, нет ли похожей цитаты
            is_similar = False
            for seen in seen_content:
                # Если цитаты похожи более чем на 70%, пропускаем
                if _similarity(normalized, seen) > 0.7:
                    is_similar = True
                    break
            
            if not is_similar and len(unique_quotes) < limit:
                unique_quotes.append(quote)
                seen_content.add(normalized)
        
        # Если не нашли достаточно цитат, добавляем запасные
        if len(unique_quotes) < limit:
            fallback_quotes = [
                "Каждая книга открывает новые горизонты.",
                "Чтение — это диалог с автором через время и пространство.",
                "Слова имеют силу менять восприятие мира.",
                "Литература хранит мудрость поколений.",
                "Текст — это мост между мыслью и её воплощением.",
            ]
            
            # Добавляем недостающие цитаты
            for i in range(limit - len(unique_quotes)):
                if i < len(fallback_quotes):
                    unique_quotes.append(fallback_quotes[i])
        
        return {
            "document_id": document_id,
            "quotes": unique_quotes[:limit],
            "count": len(unique_quotes[:limit]),
            "ai_analysis": False,
            "fallback": False,
            "extracted_from": f"{len(sentences)} предложений"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения цитат: {e}")
        return {
            "document_id": document_id,
            "quotes": [
                "Цитаты временно недоступны",
                "Попробуйте обновить страницу",
                "Ошибка обработки текста"
            ],
            "count": 3,
            "ai_analysis": False,
            "fallback": True,
            "error": str(e)[:100]
        }

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"{'='*60}")
    logger.info(f"🚀 ЗАПУСК VERSION 6.0 НА ПОРТУ {PORT}")
    logger.info(f"{'='*60}")
    logger.info(f"📁 Папка загрузок: {os.path.abspath(UPLOAD_FOLDER)}")
    logger.info(f"🔤 Перевод: Hugging Face + Fallback (загружается в фоне)")
    logger.info(f"🗄️  База данных: PostgreSQL (Railway)")
    logger.info(f"🤖 Hugging Face перевод: {'ЗАГРУЖАЕТСЯ В ФОНЕ'}")
    logger.info(f"📊 Hugging Face анализ: {'ЗАГРУЖАЕТСЯ В ФОНЕ'}")
    logger.info(f"📈 NLTK анализ: {'ДОСТУПЕН' if NLTK_AVAILABLE else 'НЕ ДОСТУПЕН'}")
    logger.info(f"💡 Healthcheck работает СРАЗУ, AI модели грузятся в фоне")
    logger.info(f"{'='*60}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info",
        access_log=True,
        timeout_keep_alive=60  # Увеличиваем timeout для Railway
    )
