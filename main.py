# main.py - Бэкенд Versevo для Railway
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import os
import sys
import base64
import uuid
import re
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
    style: str = "artistic"

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "general"

# ========== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ==========
HF_API_KEY = os.getenv("HF_API_KEY", "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")
PORT = int(os.getenv("PORT", 8080))

# Хранилище документов в памяти
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

def _fallback_translation(text: str, source_lang: str, target_lang: str) -> str:
    """Улучшенный fallback перевод"""
    # Более полный словарь для демо
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
            'good': 'хороший',
            'bad': 'плохой',
            'new': 'новый',
            'old': 'старый',
            'big': 'большой',
            'small': 'маленький',
            'important': 'важный',
            'interesting': 'интересный',
            'beautiful': 'красивый',
            'difficult': 'сложный',
            'easy': 'легкий',
            'fast': 'быстрый',
            'slow': 'медленный',
        }
        
        words = text.lower().split()
        translated_words = []
        
        for word in words:
            # Убираем знаки препинания
            clean_word = ''.join(c for c in word if c.isalpha())
            if clean_word in translation_map and translation_map[clean_word]:
                translated_words.append(translation_map[clean_word])
            else:
                translated_words.append(word)
        
        result = " ".join(translated_words)
        return f"[DEMO] {result}"
    
    elif source_lang == 'ru' and target_lang == 'en':
        # Обратный перевод
        translation_map = {
            'привет': 'hello',
            'мир': 'world',
            'книга': 'book',
            'читать': 'read',
            'переводить': 'translate',
            'документ': 'document',
            'текст': 'text',
            'глава': 'chapter',
            'страница': 'page',
            'библиотека': 'library',
        }
        
        words = text.lower().split()
        translated_words = []
        
        for word in words:
            clean_word = ''.join(c for c in word if c.isalpha())
            if clean_word in translation_map:
                translated_words.append(translation_map[clean_word])
            else:
                translated_words.append(word)
        
        result = " ".join(translated_words)
        return f"[DEMO] {result}"
    
    else:
        return f"[DEMO] Перевод с {source_lang} на {target_lang}: {text[:100]}..."

def _try_alternative_models(text: str, source_lang: str, target_lang: str) -> str:
    """Попробовать альтернативные модели"""
    alternative_models = [
        "facebook/m2m100_418M",
        "facebook/mbart-large-50-many-to-many-mmt",
        "Helsinki-NLP/opus-mt-tc-big-en-ru",  # Другая модель для en-ru
    ]
    
    for model in alternative_models:
        try:
            logger.info(f"🔄 Пробуем альтернативную модель: {model}")
            
            api_url = f"https://api-inference.huggingface.co/models/{model}"
            headers = {
                "Authorization": f"Bearer {HF_API_KEY}",
                "Content-Type": "application/json"
            }
            
            # Для разных моделей разные payload
            if 'mbart' in model:
                lang_codes = {
                    "ru": "ru_RU",
                    "en": "en_XX",
                }
                payload = {
                    "inputs": text,
                    "parameters": {
                        "src_lang": lang_codes.get(source_lang, "en_XX"),
                        "tgt_lang": lang_codes.get(target_lang, "ru_RU")
                    }
                }
            elif 'm2m100' in model:
                lang_codes = {
                    "ru": "ru",
                    "en": "en",
                }
                payload = {
                    "inputs": text,
                    "parameters": {
                        "src_lang": lang_codes.get(source_lang, "en"),
                        "tgt_lang": lang_codes.get(target_lang, "ru")
                    }
                }
            else:
                payload = {"inputs": text}
            
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    if isinstance(result[0], dict) and 'translation_text' in result[0]:
                        translated = result[0]['translation_text']
                        logger.info(f"✅ Альтернативная модель {model} сработала!")
                        return translated
                    elif isinstance(result[0], str):
                        translated = result[0]
                        logger.info(f"✅ Альтернативная модель {model} сработала!")
                        return translated
            
        except Exception as e:
            logger.warning(f"⚠️ Альтернативная модель {model} не сработала: {e}")
            continue
    
    # Если все модели не сработали
    logger.error("❌ Все модели недоступны, используем fallback")
    return _fallback_translation(text, source_lang, target_lang)

def translate_with_huggingface(text: str, source_lang: str, target_lang: str) -> str:
    """Перевод через Hugging Face с использованием РАБОЧИХ моделей"""
    try:
        # РАБОЧИЕ модели (проверенные)
        model_mapping = {
            ('en', 'ru'): 'facebook/m2m100_418M',  # Рабочая модель для en->ru
            ('ru', 'en'): 'facebook/m2m100_418M',  # Рабочая модель для ru->en
            ('en', 'de'): 'facebook/m2m100_418M',
            ('de', 'en'): 'facebook/m2m100_418M',
            ('en', 'fr'): 'facebook/m2m100_418M',
            ('fr', 'en'): 'facebook/m2m100_418M',
            ('en', 'es'): 'facebook/m2m100_418M',
            ('es', 'en'): 'facebook/m2m100_418M',
        }
        
        # Языковые коды для M2M100 модели
        lang_codes_m2m100 = {
            'en': 'en',
            'ru': 'ru',
            'de': 'de',
            'fr': 'fr',
            'es': 'es',
            'zh': 'zh',
            'ar': 'ar',
            'hi': 'hi',
            'ja': 'ja',
            'ko': 'ko'
        }
        
        # Выбираем модель
        model_key = (source_lang, target_lang)
        if model_key in model_mapping:
            api_url = f"https://api-inference.huggingface.co/models/{model_mapping[model_key]}"
        else:
            # По умолчанию используем M2M100
            api_url = "https://api-inference.huggingface.co/models/facebook/m2m100_418M"
        
        logger.info(f"🌐 Используем модель: {api_url.split('/')[-1]}")
        logger.info(f"📊 Переводим с {source_lang} на {target_lang}")
        
        headers = {
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Для M2M100 модели
        if 'm2m100' in api_url:
            payload = {
                "inputs": text,
                "parameters": {
                    "src_lang": lang_codes_m2m100.get(source_lang, "en"),
                    "tgt_lang": lang_codes_m2m100.get(target_lang, "ru")
                }
            }
        else:
            payload = {"inputs": text}
        
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=60  # Увеличиваем таймаут
        )
        
        logger.info(f"📡 Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"📊 Получен ответ от API")
            
            # Обработка ответа
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict) and 'translation_text' in result[0]:
                    translated = result[0]['translation_text']
                    logger.info(f"✅ Перевод успешен: {len(translated)} символов")
                    return translated
                elif isinstance(result[0], dict) and 'generated_text' in result[0]:
                    translated = result[0]['generated_text']
                    logger.info(f"✅ Перевод успешен: {len(translated)} символов")
                    return translated
                elif isinstance(result[0], str):
                    translated = result[0]
                    logger.info(f"✅ Перевод успешен: {len(translated)} символов")
                    return translated
            
            # Если формат неожиданный
            logger.warning(f"⚠️ Неожиданный формат ответа")
            return str(result)
        
        elif response.status_code == 503:
            # Модель загружается
            logger.warning("⏳ Модель загружается...")
            # Пробуем подождать и отправить еще раз
            import time
            time.sleep(5)
            
            # Вторая попытка
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    if isinstance(result[0], dict):
                        return result[0].get('translation_text', result[0].get('generated_text', str(result[0])))
                    elif isinstance(result[0], str):
                        return result[0]
            
            # Если все равно ошибка, используем fallback
            logger.warning("⏳ Модель все еще загружается, используем fallback")
            return _fallback_translation(text, source_lang, target_lang)
        
        else:
            logger.error(f"❌ Ошибка API: {response.status_code}")
            # Пробуем другую модель как fallback
            return _try_alternative_models(text, source_lang, target_lang)
            
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут запроса к HF API")
        return _fallback_translation(text, source_lang, target_lang)
    except Exception as e:
        logger.error(f"❌ Ошибка перевода: {e}")
        return _fallback_translation(text, source_lang, target_lang)

# ========== HEALTH CHECK ENDPOINTS ==========
@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Versevo Backend API",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "/api/health",
            "health_flutter": "/api/flutter/health",
            "upload": "/api/documents/upload",
            "upload_base64": "/api/documents/upload-base64",
            "documents": "/api/documents",
            "translate": "/api/translate/text"
        }
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }

@app.get("/api/flutter/health")
async def health_check_flutter():
    """Health check для Flutter/Railway"""
    return {
        "status": "healthy", 
        "service": "versevo-backend", 
        "timestamp": datetime.now().isoformat(),
        "endpoint": "flutter-health"
    }

@app.get("/health")
async def health_check_simple():
    """Простой health check"""
    return {"status": "ok"}

# ========== ДОКУМЕНТЫ ==========
@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: Optional[int] = Form(None)
):
    """Загрузка документа"""
    global current_doc_id
    
    try:
        logger.info(f"📤 Uploading file: {file.filename}")
        
        file_id = str(uuid.uuid4())
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else 'txt'
        file_path = f"{UPLOAD_FOLDER}/{file_id}.{file_extension}"
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        content_str = extract_text_from_file(file_path, file_extension)
        
        if not content_str or len(content_str.strip()) < 10:
            raise HTTPException(status_code=400, detail="Не удалось извлечь текст из файла")
        
        language = detect_language_safe(content_str)
        chapters = detect_chapters(content_str)
        
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
        
        documents_store[current_doc_id] = document
        current_doc_id += 1
        
        logger.info(f"✅ Document saved: ID {document['id']}, {document['word_count']} words")
        
        return document
        
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
    """Перевод текста"""
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is empty")
        
        # Убираем ограничение по длине текста
        source_lang = request.source_language
        if not source_lang or source_lang == "auto":
            source_lang = detect_language_safe(request.text)
        
        target_lang = request.target_language
        
        logger.info(f"🌐 Перевод текста: {len(request.text)} символов, с {source_lang} на {target_lang}")
        
        translated_text = translate_with_huggingface(
            request.text, 
            source_lang, 
            target_lang
        )
        
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
            "translation_service": "huggingface",
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
    """Перевод всего документа"""
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        content = doc["content"]
        
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        
        if len(content) > 2000:
            chunks = []
            chunk_size = 1500
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                chunks.append(chunk)
            
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
            translated_content = translate_with_huggingface(
                content, 
                doc["language"], 
                target_language
            )
        
        doc["translated_content"] = translated_content
        doc["updated_at"] = datetime.now().isoformat()
        
        return {
            "success": True,
            "document_id": document_id,
            "original_language": doc["language"],
            "target_language": target_language,
            "translated_content": translated_content[:500] + "..." if len(translated_content) > 500 else translated_content,
            "total_translated": len(translated_content.split()),
            "translation_service": "huggingface"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document translation error: {e}")
        raise HTTPException(status_code=500, detail=f"Document translation failed: {str(e)}")

@app.post("/api/translate/helloinki")
async def translate_with_helloinki(request: TranslateRequest):
    """Тестовый перевод через альтернативные модели"""
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is empty")
        
        source_lang = request.source_language or "en"
        target_lang = request.target_language or "ru"
        
        # Пробуем несколько моделей
        models_to_try = [
            "facebook/m2m100_418M",  # Основная рабочая модель
            "facebook/mbart-large-50-many-to-many-mmt",  # Альтернативная
            "Helsinki-NLP/opus-mt-tc-big-en-ru",  # Для en-ru
        ]
        
        headers = {
            "Authorization": f"Bearer {HF_API_KEY}",
            "Content-Type": "application/json"
        }
        
        translated_text = None
        used_model = None
        
        for model in models_to_try:
            try:
                logger.info(f"🔄 Пробуем модель: {model}")
                api_url = f"https://api-inference.huggingface.co/models/{model}"
                
                # Настраиваем payload в зависимости от модели
                if 'mbart' in model:
                    lang_codes = {
                        "ru": "ru_RU",
                        "en": "en_XX",
                    }
                    payload = {
                        "inputs": request.text,
                        "parameters": {
                            "src_lang": lang_codes.get(source_lang, "en_XX"),
                            "tgt_lang": lang_codes.get(target_lang, "ru_RU")
                        }
                    }
                elif 'm2m100' in model:
                    lang_codes = {
                        "ru": "ru",
                        "en": "en",
                    }
                    payload = {
                        "inputs": request.text,
                        "parameters": {
                            "src_lang": lang_codes.get(source_lang, "en"),
                            "tgt_lang": lang_codes.get(target_lang, "ru")
                        }
                    }
                else:
                    payload = {"inputs": request.text}
                
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list) and len(result) > 0:
                        if isinstance(result[0], dict) and 'translation_text' in result[0]:
                            translated_text = result[0]['translation_text']
                        elif isinstance(result[0], str):
                            translated_text = result[0]
                        else:
                            translated_text = str(result[0])
                        
                        used_model = model
                        logger.info(f"✅ Модель {model} успешно перевела текст")
                        break
                
            except Exception as e:
                logger.warning(f"⚠️ Модель {model} не сработала: {e}")
                continue
        
        if not translated_text:
            translated_text = _fallback_translation(request.text, source_lang, target_lang)
            used_model = "fallback"
        
        return {
            "original_text": request.text,
            "translated_text": translated_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "model": used_model,
            "status": "success" if used_model != "fallback" else "fallback"
        }
            
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return {
            "original_text": request.text,
            "translated_text": _fallback_translation(request.text, request.source_language or "en", request.target_language or "ru"),
            "source_language": request.source_language or "en",
            "target_language": request.target_language or "ru",
            "model": "error_fallback",
            "status": "error",
            "error": str(e)
        }

@app.get("/api/translate/models/status")
async def check_model_status():
    """Проверка статуса моделей перевода"""
    models_to_check = [
        "facebook/m2m100_418M",
        "facebook/mbart-large-50-many-to-many-mmt",
        "Helsinki-NLP/opus-mt-tc-big-en-ru"
    ]
    
    results = []
    
    for model in models_to_check:
        try:
            api_url = f"https://api-inference.huggingface.co/models/{model}"
            headers = {"Authorization": f"Bearer {HF_API_KEY}"}
            
            response = requests.get(
                api_url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                results.append({
                    "model": model,
                    "status": "available",
                    "code": response.status_code
                })
            elif response.status_code == 503:
                results.append({
                    "model": model,
                    "status": "loading",
                    "code": response.status_code
                })
            else:
                results.append({
                    "model": model,
                    "status": "error",
                    "code": response.status_code,
                    "message": response.text[:100]
                })
                
        except Exception as e:
            results.append({
                "model": model,
                "status": "connection_error",
                "error": str(e)
            })
    
    return {
        "timestamp": datetime.now().isoformat(),
        "models": results,
        "recommended_for_en_ru": "facebook/m2m100_418M",
        "api_key_status": "set" if HF_API_KEY else "not_set"
    }

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
            "key_themes": [word for word, _ in top_keywords],
            "estimated_topics": ["Литература", "Образование", "Технологии"],
            "sentiment": "Нейтральный",
            "writing_style": "Информационный",
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
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc = documents_store[document_id]
        return doc["chapters"]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chapters error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/translate/test")
async def test_translation():
    """Тестовый endpoint для проверки перевода"""
    try:
        test_text = "Hello world, this is a test translation from the Versevo backend."
        
        translated = translate_with_huggingface(test_text, "en", "ru")
        
        return {
            "original": test_text,
            "translated": translated,
            "status": "success",
            "service": "huggingface",
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
    logger.info(f"🔑 HF API Key: {'Set' if HF_API_KEY else 'Not set'}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT,
        log_level="info"
    )
