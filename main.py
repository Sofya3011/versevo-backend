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
from collections import Counter
from enum import Enum

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

class AnalysisType(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DETAILED = "detailed"
    FULL = "full"

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

# Хранилище документов в памяти
documents_store = {}
current_doc_id = 1

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

# ========== НАСТОЯЩИЙ ПЕРЕВОДЧИК HUGGING FACE ==========
class HuggingFaceTranslator:
    """Настоящий переводчик через Hugging Face модели"""
    
    def __init__(self):
        logger.info("🌍 Инициализация настоящего переводчика Hugging Face")
        self.translation_pipelines = {
            'en-ru': None,
            'ru-en': None,
        }
        self.fallback_translator = LocalTranslator()
        self._init_translation_models()
    
    def _init_translation_models(self):
        """Инициализация моделей перевода"""
        try:
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
            
            logger.info(f"✅ Переводчик Hugging Face готов (устройство: {device_name})")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации переводчика: {e}")
            self.model_configs = {}
    
    def _get_translation_pipeline(self, source_lang: str, target_lang: str):
        """Получить или загрузить pipeline для перевода"""
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
                    logger.info(f"🔄 Загрузка модели перевода {key} ({model_config['model']})...")
                    
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
        # Если языки совпадают - возвращаем как есть
        if source_lang == target_lang:
            return self.fallback_translator._apply_style(text, style)
        
        # Основные поддерживаемые языки
        supported_pairs = ['en-ru', 'ru-en']
        key = f"{source_lang}-{target_lang}"
        
        if key not in supported_pairs:
            # Для неподдерживаемых пар используем простой перевод
            logger.warning(f"⚠️ Неподдерживаемая пара переводов: {key}")
            return self.fallback_translator.translate(text, source_lang, target_lang, style)
        
        try:
            # Получаем pipeline
            pipeline = self._get_translation_pipeline(source_lang, target_lang)
            
            if pipeline is None:
                # Fallback на простой перевод
                logger.warning(f"⚠️ Pipeline перевода {key} не загружен")
                return self.fallback_translator.translate(text, source_lang, target_lang, style)
            
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
                translated_text = self.fallback_translator._apply_style(translated_text, style)
                
                return translated_text
            else:
                logger.warning(f"⚠️ Переводчик вернул пустой результат для {key}")
                return self.fallback_translator.translate(text, source_lang, target_lang, style)
                
        except Exception as e:
            logger.error(f"❌ Ошибка перевода {key}: {e}")
            # Fallback на простой перевод
            return self.fallback_translator.translate(text, source_lang, target_lang, style)
    
    def is_available(self, source_lang: str, target_lang: str) -> bool:
        """Проверка доступности перевода для языковой пары"""
        key = f"{source_lang}-{target_lang}"
        
        if key in self.model_configs:
            pipeline = self._get_translation_pipeline(source_lang, target_lang)
            return pipeline is not None
        
        return False

# ========== ИНИЦИАЛИЗАЦИЯ HUGGING FACE ДЛЯ АНАЛИЗА ==========
HUGGING_FACE_ENABLED = False
HF_ANALYSIS_PIPELINES = {}

def init_huggingface_for_analysis():
    """Инициализация Hugging Face моделей для анализа"""
    global HUGGING_FACE_ENABLED, HF_ANALYSIS_PIPELINES
    
    try:
        import transformers
        import torch
        
        # Проверяем доступность CUDA
        device = 0 if torch.cuda.is_available() else -1
        device_name = "CUDA" if torch.cuda.is_available() else "CPU"
        logger.info(f"🏗️ Инициализация Hugging Face анализа на {device_name}")
        
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
        logger.info("✅ Hugging Face анализ инициализирован (ленивая загрузка)")
        logger.info(f"📦 Доступные модели анализа: {list(analysis_models.keys())}")
        
        # Предзагружаем только sentiment модель (самую легкую)
        try:
            logger.info("🔄 Предзагрузка модели анализа тональности...")
            from transformers import pipeline
            sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=analysis_models["sentiment"]["model_name"],
                device=device
            )
            HF_ANALYSIS_PIPELINES["sentiment"]["pipeline"] = sentiment_pipeline
            logger.info("✅ Модель анализа тональности загружена")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить sentiment модель: {e}")
        
    except ImportError as e:
        logger.warning(f"⚠️ transformers не установлен: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Hugging Face анализа: {e}")

# Инициализируем компоненты
logger.info("=" * 60)
logger.info("🚀 ИНИЦИАЛИЗАЦИЯ VERSION 5.0")
logger.info("=" * 60)

# Инициализируем переводчики
local_translator = LocalTranslator()
hf_translator = HuggingFaceTranslator()

# Инициализируем анализ
init_huggingface_for_analysis()

# Инициализируем NLTK для анализа
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
            logger.info(f"🔄 Загрузка модели анализа {model_config['model_name']} для задачи {task}...")
            
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
            logger.info(f"✅ Модель анализа {model_config['model_name']} загружена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели анализа {task}: {e}")
            return None
    
    return HF_ANALYSIS_PIPELINES[task]["pipeline"]

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
    
    return {
        "message": "Versevo Backend API v5.0",
        "version": "5.0.0",
        "status": "running",
        "translation": {
            "huggingface_available": hf_translator.is_available('en', 'ru'),
            "fallback_available": True
        },
        "analysis": {
            "huggingface_available": HUGGING_FACE_ENABLED,
            "nltk_available": NLTK_AVAILABLE
        },
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
        "version": "5.0.0",
        "features": {
            "translation": "huggingface+fallback",
            "analysis": "huggingface+nltk+basic"
        }
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "translation": {
            "huggingface": hf_translator.is_available('en', 'ru'),
            "fallback": True
        },
        "analysis": {
            "huggingface": HUGGING_FACE_ENABLED,
            "nltk": NLTK_AVAILABLE
        },
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
        use_huggingface = hf_translator.is_available(source_lang, target_lang)
        
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
        "
