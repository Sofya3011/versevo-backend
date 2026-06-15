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
import json
import requests as http_requests
from datetime import datetime
from collections import Counter
from enum import Enum

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# ===== MODELS =====
class TranslateRequest(BaseModel):
    text: str
    target_language: str = "ru"
    source_language: Optional[str] = None
    style: str = "artistic"

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str

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

class ChatRequest(BaseModel):
    document_id: int
    question: str
    language: str = "ru"

# ===== APP =====
app = FastAPI(title="Versevo Backend API", version="5.1.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
except Exception:
    pass

PORT = int(os.getenv("PORT", 8080))

# ========== POSTGRESQL (опционально) ==========
DB_URL = os.getenv("DATABASE_URL", "")
USE_DB = bool(DB_URL)
_db_conn = None
_db_available = False

def get_db_connection():
    global _db_conn, _db_available
    if _db_conn is not None:
        return _db_conn
    if not USE_DB:
        return None
    try:
        import psycopg2
        _db_conn = psycopg2.connect(DB_URL)
        _db_conn.autocommit = True
        _db_available = True
        logger.info("PostgreSQL connected")
        return _db_conn
    except Exception as e:
        logger.warning(f"PostgreSQL unavailable: {e}")
        _db_available = False
        return None

def init_db():
    conn = get_db_connection()
    if conn is None:
        logger.info("Using in-memory storage")
        return
    try:
        cur = conn.cursor()
        for sql in [
            "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL, username VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL, theme VARCHAR(50) DEFAULT 'light', font_size INTEGER DEFAULT 16, font_family VARCHAR(100) DEFAULT 'Inter', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS documents (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, filename VARCHAR(500) NOT NULL, original_filename VARCHAR(500), content TEXT, language VARCHAR(10) DEFAULT 'en', file_type VARCHAR(10), file_path TEXT, file_id VARCHAR(255), word_count INTEGER DEFAULT 0, char_count INTEGER DEFAULT 0, chapter_count INTEGER DEFAULT 0, reading_time_minutes INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS chapters (id SERIAL PRIMARY KEY, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, title VARCHAR(500) NOT NULL, content TEXT, position INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS notes (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, text TEXT NOT NULL, context TEXT, position_offset INTEGER DEFAULT 0, color VARCHAR(50) DEFAULT 'yellow', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS quotes (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, text TEXT NOT NULL, author VARCHAR(255), color VARCHAR(50) DEFAULT 'blue', position_offset INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS bookmarks (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL, title VARCHAR(500), position_offset INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS reading_progress (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, current_chapter INTEGER DEFAULT 1, current_position INTEGER DEFAULT 0, percentage DECIMAL(5,2) DEFAULT 0.00, reading_time_seconds INTEGER DEFAULT 0, last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, document_id))",
            "CREATE TABLE IF NOT EXISTS translation_cache (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, original_text TEXT NOT NULL, translated_text TEXT NOT NULL, source_language VARCHAR(10), target_language VARCHAR(10), style VARCHAR(50) DEFAULT 'artistic', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        ]:
            cur.execute(sql)
        logger.info("PostgreSQL tables ready")
        cur.close()
    except Exception as e:
        logger.warning(f"Table creation error: {e}")

class DocumentStore:
    def __init__(self):
        self._cache = {}
        self._max_id = 0
        init_db()
        self._load_from_db()

    def _load_from_db(self):
        conn = get_db_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, filename, original_filename, content, language, file_type, file_path, file_id, word_count, char_count, chapter_count, reading_time_minutes, created_at, updated_at FROM documents ORDER BY id")
            for row in cur.fetchall():
                doc = {"id": row[0], "filename": row[1], "original_filename": row[2], "content": row[3], "language": row[4], "file_type": row[5], "file_path": row[6], "file_id": row[7], "word_count": row[8], "char_count": row[9], "chapter_count": row[10], "reading_time_minutes": row[11], "created_at": row[12].isoformat() if row[12] else None, "updated_at": row[13].isoformat() if row[13] else None}
                cur2 = conn.cursor()
                cur2.execute("SELECT title, content FROM chapters WHERE document_id = %s ORDER BY position", (row[0],))
                doc["chapters"] = [{"title": c[0], "content": c[1] or ""} for c in cur2.fetchall()] or [{"title": "Document", "content": doc.get("content", "")}]
                cur2.close()
                self._cache[row[0]] = doc
                self._max_id = max(self._max_id, row[0])
            cur.close()
        except Exception as e:
            logger.warning(f"DB load error: {e}")

    def _save_to_db(self, doc):
        conn = get_db_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO documents (id, filename, original_filename, content, language, file_type, file_path, file_id, word_count, char_count, chapter_count, reading_time_minutes, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET filename=EXCLUDED.filename, content=EXCLUDED.content, word_count=EXCLUDED.word_count, updated_at=EXCLUDED.updated_at", (doc["id"], doc["filename"], doc.get("original_filename", doc["filename"]), doc["content"], doc["language"], doc["file_type"], doc["file_path"], doc["file_id"], doc["word_count"], doc["char_count"], doc["chapter_count"], doc["reading_time_minutes"], doc["created_at"], doc["updated_at"]))
            cur.execute("DELETE FROM chapters WHERE document_id = %s", (doc["id"],))
            for i, ch in enumerate(doc.get("chapters", [])):
                cur.execute("INSERT INTO chapters (document_id, title, content, position) VALUES (%s,%s,%s,%s)", (doc["id"], ch.get("title", f"Chapter {i+1}"), ch.get("content", ""), i))
            cur.close()
        except Exception as e:
            logger.warning(f"DB save error: {e}")

    def _delete_from_db(self, doc_id):
        conn = get_db_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM chapters WHERE document_id = %s", (doc_id,))
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            cur.close()
        except Exception as e:
            logger.warning(f"DB delete error: {e}")

    def get(self, doc_id, default=None):
        return self._cache.get(doc_id, default)
    def __contains__(self, doc_id):
        return doc_id in self._cache
    def __getitem__(self, doc_id):
        return self._cache[doc_id]
    def __setitem__(self, doc_id, doc):
        self._cache[doc_id] = doc
        self._save_to_db(doc)
    def __delitem__(self, doc_id):
        if doc_id in self._cache:
            del self._cache[doc_id]
            self._delete_from_db(doc_id)
    def values(self):
        return self._cache.values()
    def keys(self):
        return self._cache.keys()
    def items(self):
        return self._cache.items()
    def pop(self, doc_id, default=None):
        doc = self._cache.pop(doc_id, default)
        if doc is not None:
            self._delete_from_db(doc_id)
        return doc
    def next_id(self):
        self._max_id += 1
        return self._max_id

documents_store = DocumentStore()

# ===== LAZY LOADING HELPERS =====
_hf_available = False
_hf_pipelines = {}
_nltk_available = False

def lazy_load_hf():
    global _hf_available, _hf_pipelines
    if _hf_available:
        return True
    try:
        import transformers
        import torch
        device = 0 if torch.cuda.is_available() else -1
        _hf_pipelines = {
            "sentiment": {"model": "blanchefort/rubert-base-cased-sentiment", "task": "sentiment-analysis", "pipeline": None},
            "ner": {"model": "Babelscape/wikineural-multilingual-ner", "task": "ner", "pipeline": None},
        }
        _hf_available = True
        return True
    except ImportError:
        return False
    except Exception as e:
        return False

def get_hf_pipeline(task):
    global _hf_pipelines
    if not _hf_available:
        if not lazy_load_hf():
            return None
    if task not in _hf_pipelines:
        return None
    if _hf_pipelines[task]["pipeline"] is None:
        try:
            from transformers import pipeline
            import torch
            device = 0 if torch.cuda.is_available() else -1
            cfg = _hf_pipelines[task]
            _hf_pipelines[task]["pipeline"] = pipeline(cfg["task"], model=cfg["model"], device=device)
        except Exception as e:
            return None
    return _hf_pipelines[task]["pipeline"]

def lazy_load_nltk():
    global _nltk_available
    if _nltk_available:
        return True
    try:
        import nltk
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
        _nltk_available = True
        return True
    except ImportError:
        return False

# ===== LOCAL TRANSLATOR =====
class LocalTranslator:
    def __init__(self):
        self.translation_dict = {
            'en-ru': {
                'hello': 'привет', 'world': 'мир', 'book': 'книга', 'read': 'читать',
                'page': 'страница', 'chapter': 'глава', 'text': 'текст', 'document': 'документ',
                'translate': 'переводить', 'library': 'библиотека', 'author': 'автор',
                'title': 'название', 'content': 'содержание', 'analysis': 'анализ',
                'summary': 'краткое содержание', 'character': 'персонаж', 'plot': 'сюжет',
                'story': 'история', 'novel': 'роман', 'poem': 'стихотворение',
                'literature': 'литература', 'the': '', 'a': '', 'an': '', 'and': 'и',
                'or': 'или', 'but': 'но', 'in': 'в', 'on': 'на', 'at': 'в', 'to': 'к',
                'for': 'для', 'with': 'с', 'from': 'из', 'of': 'из', 'by': 'от',
                'is': 'является', 'are': 'являются', 'was': 'был', 'were': 'были',
                'have': 'иметь', 'has': 'имеет', 'do': 'делать', 'does': 'делает',
                'can': 'мочь', 'could': 'мог', 'will': 'будет', 'would': 'бы',
                'good': 'хороший', 'bad': 'плохой', 'new': 'новый', 'old': 'старый',
                'big': 'большой', 'small': 'маленький', 'beautiful': 'красивый',
                'interesting': 'интересный', 'important': 'важный',
            },
            'ru-en': {
                'привет': 'hello', 'мир': 'world', 'книга': 'book', 'читать': 'read',
                'страница': 'page', 'глава': 'chapter', 'текст': 'text', 'документ': 'document',
                'автор': 'author', 'название': 'title', 'содержание': 'content',
                'анализ': 'analysis', 'персонаж': 'character', 'сюжет': 'plot',
                'история': 'story', 'литература': 'literature', 'и': 'and', 'или': 'or',
                'но': 'but', 'в': 'in', 'на': 'on', 'для': 'for', 'с': 'with',
            }
        }
        self.literary_patterns = {
            'en-ru': [
                (r'\bIt is\b', 'Это'), (r'\bhe said\b', 'сказал он'),
                (r'\bshe said\b', 'сказала она'), (r'\bthey said\b', 'сказали они'),
                (r'\bI think\b', 'Я думаю'), (r'\byou know\b', 'знаете ли'),
                (r'\bof course\b', 'конечно'), (r'\bin fact\b', 'на самом деле'),
                (r'\bat first\b', 'сначала'), (r'\bat last\b', 'наконец'),
            ]
        }

    def translate(self, text: str, source_lang: str, target_lang: str, style: str = "artistic") -> str:
        if source_lang == target_lang:
            return self._apply_style(text, style)
        key = f"{source_lang}-{target_lang}"
        if len(text) > 800:
            text = text[:800] + "..."
        if key in self.literary_patterns:
            for pattern, replacement in self.literary_patterns[key]:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        if key in self.translation_dict:
            result = self._dictionary_translate(text, key)
        else:
            result = text
        result = self._apply_style(result, style)
        return result

    def _dictionary_translate(self, text: str, lang_key: str) -> str:
        words = re.findall(r'\b\w+\b|[^\w\s]', text)
        translated = []
        dict_map = self.translation_dict[lang_key]
        for word in words:
            if re.match(r'^\w+$', word):
                lower = word.lower()
                if lower in dict_map:
                    t = dict_map[lower]
                    if t:
                        if word[0].isupper():
                            t = t[0].upper() + t[1:] if len(t) > 0 else t
                        translated.append(t)
                    else:
                        translated.append('')
                else:
                    translated.append(word)
            else:
                translated.append(word)
        result = ' '.join(translated)
        result = re.sub(r'\s+([.,!?;:])', r'\1', result)
        result = re.sub(r'\s+', ' ', result)
        return result.strip()

    def _apply_style(self, text: str, style: str) -> str:
        if style == "artistic": return text
        return text

# ===== GOOGLE TRANSLATE API =====
class GoogleTranslatorWrapper:
    def __init__(self):
        self._translator = None
        try:
            from deep_translator import GoogleTranslator
            self._translator = GoogleTranslator
        except ImportError:
            pass

    def translate(self, text: str, source: str, target: str) -> str:
        if self._translator and len(text) < 2000:
            try:
                t = self._translator(source=source, target=target)
                return t.translate(text)
            except Exception:
                pass
        return ""

    def is_available(self) -> bool:
        return self._translator is not None

google_translator = GoogleTranslatorWrapper()
local_translator = LocalTranslator()

# ===== UTILITIES =====
def extract_text_from_file(file_path: str, file_type: str) -> str:
    try:
        if file_type == 'pdf':
            try:
                import fitz
                doc = fitz.open(file_path)
                text = [page.get_text() for page in doc]
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
    if not text or len(text.strip()) < 10:
        return "en"
    cyrillic = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
    latin = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
    return "ru" if cyrillic > latin * 1.5 else "en"

def detect_chapters(text: str) -> List[Dict]:
    chapters = []
    if not text:
        return [{'title': 'Документ', 'content': 'Нет содержимого'}]
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    patterns = [
        r'^\s*(?:ГЛАВА|Глава|Г\.)\s+[IVXLCDM\d]+[\.\s].*$',
        r'^\s*(?:CHAPTER|Chapter|Ch\.)\s+[IVXLCDM\d]+[\.\s].*$',
        r'^\s*[IVXLCDM\d]+[\.\)]\s+.*$',
        r'^\s*\d+[\.\)]\s+.*$',
        r'^\s*[A-Z][A-Z\s]{2,}[\.\?!]?$',
        r'^\s*.+\n[-=]{3,}$',
    ]
    paragraphs = text.split('\n\n')
    current = None
    content = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        is_title = any(re.match(p, para, re.MULTILINE | re.IGNORECASE) for p in patterns)
        if is_title:
            if current is not None and content:
                chapters.append({'title': current, 'content': '\n\n'.join(content)})
            current = para[:100]
            content = []
        else:
            if current is None:
                current = 'Начало'
            content.append(para)
    if current and content:
        chapters.append({'title': current, 'content': '\n\n'.join(content)})
    if not chapters:
        for i in range(0, len(text), 5000):
            chunk = text[i:i + 5000]
            if chunk.strip():
                chapters.append({'title': f'Часть {len(chapters) + 1}', 'content': chunk})
    return chapters

def _similarity(s1: str, s2: str) -> float:
    words1 = set(s1.split())
    words2 = set(s2.split())
    if not words1 or not words2:
        return 0.0
    return len(words1.intersection(words2)) / len(words1.union(words2))

# ===== CHAT =====
_HF_API_KEY = os.getenv("HF_API_KEY", "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")
_HF_MODELS = ["google/flan-t5-base", "google/flan-t5-small"]

def _call_hf_api(prompt: str, max_tokens: int = 300) -> str:
    for model in _HF_MODELS:
        for attempt in range(3):
            try:
                resp = http_requests.post(
                    f"https://api-inference.huggingface.co/models/{model}",
                    headers={"Authorization": f"Bearer {_HF_API_KEY}", "Content-Type": "application/json"},
                    json={"inputs": prompt, "parameters": {"max_new_tokens": max_tokens, "temperature": 0.7, "do_sample": True}},
                    timeout=30,
                )
                if resp.status_code == 503:
                    import time; time.sleep(2 + attempt * 2)
                    continue
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        text = data[0].get("generated_text", "") if isinstance(data[0], dict) else str(data[0])
                        if text and len(text.strip()) > 3:
                            return text.strip()
                break
            except Exception:
                break
    return ""

def _generate_chat_answer(document: dict, question: str) -> str:
    content = document.get("content", "")
    title = document.get("filename", "документ")
    q = question.lower().strip()
    if not content or len(content.strip()) < 10:
        return f"Документ «{title}» пуст или недоступен для чтения."
    words = content.split()
    word_count = len(words)
    sentences = re.split(r'(?<=[.!?])\s+', content)

    if any(w in q for w in ['привет', 'здравствуй', 'хай', 'hello', 'hi']):
        return f"Привет! Я AI-ассистент по документу «{title}». Задайте любой вопрос по содержанию — постараюсь помочь!"
    if any(w in q for w in ['кто ты', 'что ты', 'ты кто', 'что ты умеешь', 'как ты работаешь']):
        return (f"Я AI-ассистент для работы с документом «{title}».\n\n"
                f"• Отвечаю на вопросы по тексту\n"
                f"• Выделяю ключевые тезисы и темы\n"
                f"• Нахожу нужные абзацы\n"
                f"• Анализирую стиль и тональность\n\n"
                f"Просто спросите!")
    if any(w in q for w in ['спасибо', 'благодар', 'спс', 'сенкс']):
        return "Пожалуйста! Если будут ещё вопросы — обращайтесь."
    if any(w in q for w in ['пока', 'до свидан', 'бай']):
        return "До свидания! Если понадобится помощь — я здесь."
    if any(w in q for w in ['помощь', 'помоги', 'хелп', 'help']):
        return (f"Вот что я умею с документом «{title}»:\n"
                f"• О чём этот документ? — краткое содержание\n"
                f"• Выдели основные тезисы — главные мысли\n"
                f"• Какие персонажи упоминаются? — имена\n"
                f"• Найди абзац про... — поиск по тексту\n"
                f"• Какой стиль? — анализ написания")
    if any(w in q for w in ['статист', 'слов', 'сколько', 'объем', 'объём']):
        avg_len = word_count / len(sentences) if sentences else 0
        return (f"📊 Статистика «{title}»:\n\n"
                f"Слов: {word_count}\n"
                f"Предложений: {len(sentences)}\n"
                f"Средняя длина предложения: {avg_len:.1f} слов\n"
                f"Время чтения: {max(1, word_count // 200)} мин")

    if any(w in q for w in ['о чём', 'о чем', 'суть', 'содержание', 'кратко']):
        key = [s.strip() for s in sentences if 30 < len(s.strip()) < 300][:4]
        if key:
            return (f"📄 Документ «{title}» — {word_count} слов.\n\nКраткое содержание:\n\n" +
                    "\n\n".join(f"{i+1}. {s}" for i, s in enumerate(key)))
        return f"📄 Документ «{title}» содержит {word_count} слов.\n\n{content[:400]}..."
    if any(w in q for w in ['тезис', 'главн', 'основн', 'темы', 'иде']):
        key = [s.strip() for s in sentences if 40 < len(s.strip()) < 250][:6]
        if len(key) >= 2:
            return ("📌 Основные тезисы «{title}»:\n\n".format(title=title) +
                    "\n\n".join(f"{i+1}. {s}" for i, s in enumerate(key)))
    if any(w in q for w in ['персонаж', 'герой', 'кто', 'люди', 'человек']):
        sample = content[:3000]
        names = re.findall(r'\b[А-Я][а-я]+\b', sample)
        unique = list(dict.fromkeys(n for n in names if len(n) > 1 and n not in {'Это','Что','Как','Для','Они','Мы','Вы','Она','Он','Глава'}))
        if unique:
            return f"👥 В документе «{title}» упоминаются: {', '.join(unique[:10])}."
    if any(w in q for w in ['найди', 'найти', 'поиск', 'абзац', 'где']):
        search = re.sub(r'(найди|найти|поиск|абзац|про|где|мне|пожалуйста)\s*', '', question, flags=re.IGNORECASE).strip()
        if len(search) > 2:
            idx = content.lower().find(search.lower())
            if idx != -1:
                start = max(0, idx - 150)
                end = min(len(content), idx + len(search) + 250)
                return f"🔍 По запросу «{search}»:\n\n...{content[start:end]}..."
            return f"🔍 По запросу «{search}» ничего не найдено."
    if any(w in q for w in ['жанр', 'стиль', 'как написан']):
        avg_len = word_count / len(sentences) if sentences else 0
        style = 'Литературный / Академический' if avg_len > 25 else 'Художественный / Описательный' if avg_len > 15 else 'Разговорный / Информационный'
        return (f"📝 Стиль «{title}»: {style}\nСредняя длина предложения: {avg_len:.1f} слов\nВсего предложений: {len(sentences)}\nОбъём: {word_count} слов")

    snippet = content[:600]
    prompt = (
        f"Ты полезный ассистент. Ответь на русском языке естественно и по делу.\n\n"
        f"Контекст документа «{title}» (первые 600 слов):\n{snippet}\n\n"
        f"Вопрос: {question}\n\nОтвет:"
    )
    ai_answer = _call_hf_api(prompt, max_tokens=250)
    if ai_answer:
        cleaned = ai_answer
        for prefix in ['Ответ:', 'ответ:', 'Assistant:', 'assistant:']:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
        cleaned = '\n'.join(lines)
        if len(cleaned) > 500:
            cleaned = cleaned[:500]
        if cleaned:
            return cleaned

    return (f"📖 Документ «{title}» — {word_count} слов.\n\n"
            f"Попробуйте задать вопрос конкретнее:\n"
            f"• «О чём этот документ?»\n"
            f"• «Выдели основные тезисы»\n"
            f"• «Какие персонажи упоминаются?»\n"
            f"• «Найди абзац про...»")

# ===== ANALYSIS =====
def _perform_basic_analysis(text: str) -> Dict[str, Any]:
    result = {"summary": "", "themes": [], "sentiment": "Нейтральный", "complexity": "Средний", "key_points": [], "statistics": {}, "language_features": {}}
    if not text or len(text.strip()) < 10:
        result["summary"] = "Текст слишком короткий для анализа"
        return result
    try:
        words = [w for w in text.split() if w.strip()]
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        word_count = len(words)
        sentence_count = len(sentences)
        avg_len = word_count / sentence_count if sentence_count > 0 else 0
        complexity = "Простой" if avg_len < 8 else "Средний" if avg_len < 15 else "Сложный"
        if sentence_count >= 3:
            summary_sents = [s.strip() for s in sentences[:4] if len(s.strip()) > 10 and not s.strip().isupper()]
            result["summary"] = " ".join(summary_sents)[:250] + "..." if summary_sents else text[:200]
        else:
            result["summary"] = text[:200]
        proper_nouns = re.findall(r'\b[A-Z][a-z]+\b', text[:1000])
        if proper_nouns:
            c = Counter([n.lower() for n in proper_nouns])
            result["themes"] = [n for n, count in c.most_common(5) if count > 1 and len(n) > 3][:3]
        if not result["themes"]:
            freq = Counter([w.lower() for w in words if len(w) > 3])
            stop = {'это','что','как','для','того','чтобы','если','когда','или','и','но','а','the','and','but','for','with','from','that','this','was','were'}
            result["themes"] = [w for w, c in freq.most_common(10) if w not in stop and c > 1][:3]
        if not result["themes"]:
            result["themes"] = ["Документ", "Текст", "Содержание"]
        result["complexity"] = complexity
        result["statistics"] = {"word_count": word_count, "sentence_count": sentence_count, "paragraph_count": len(paragraphs), "avg_sentence_length": round(avg_len, 1), "reading_time_minutes": max(1, word_count // 200)}
        cyrillic = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
        latin = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
        result["language_features"] = {"detected_language": "ru" if cyrillic > latin else "en", "has_dialogue": bool(re.search(r'["\'«»]', text)), "has_numbers": bool(re.search(r'\d+', text))}
        result["key_points"] = [f"Объем: {word_count} слов", f"Сложность: {complexity}", f"Время чтения: {max(1, word_count // 200)} мин"]
    except Exception as e:
        result["summary"] = "Произошел сбой при анализе текста"
    return result

def _perform_ai_analysis(text: str) -> Dict[str, Any]:
    result = {"summary": "", "themes": [], "sentiment": "Нейтральный", "writing_style": "Информационный", "key_points": [], "entities": [], "ai_analysis": False, "fallback": False}
    if not text or len(text.strip()) < 50:
        result["fallback"] = True
        return result
    try:
        sample = text[:2000]
        sentiment = get_hf_pipeline("sentiment")
        if sentiment:
            try:
                sr = sentiment(sample[:512])
                if sr:
                    label = sr[0].get("label", "NEUTRAL").upper()
                    score = sr[0].get("score", 0.5)
                    sentiment_map = {"POSITIVE": "Положительный", "NEGATIVE": "Отрицательный", "NEUTRAL": "Нейтральный", "LABEL_0": "Отрицательный", "LABEL_1": "Нейтральный", "LABEL_2": "Положительный"}
                    result["sentiment"] = sentiment_map.get(label, "Нейтральный")
                    result["ai_analysis"] = True
            except:
                pass
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        if len(sentences) > 2:
            summary_sents = [s for s in sentences[:3] if len(s) > 10]
            result["summary"] = " ".join(summary_sents)[:300] if summary_sents else text[:200]
        else:
            result["summary"] = text[:300]
        if not result["themes"]:
            nouns = re.findall(r'\b[A-Z][a-z]+\b', text[:1000])
            if nouns:
                c = Counter([n.lower() for n in nouns])
                result["themes"] = [n for n, count in c.most_common(5) if count > 1 and len(n) > 3][:3]
        if not result["themes"]:
            result["themes"] = ["Литература", "Текст", "Содержание"]
        word_count = len(text.split())
        result["key_points"] = [f"Тональность: {result['sentiment']}", f"Время чтения: {max(1, word_count // 200)} мин", f"Объем: {word_count} слов"]
        result["fallback"] = not result["ai_analysis"]
    except Exception:
        result["fallback"] = True
    return result

# ===== ENDPOINTS =====
@app.get("/")
async def root():
    endpoints = {"health": "/api/health", "upload": "/api/documents/upload-base64", "documents": "/api/documents", "translate": "/api/translate/text", "analyze": "/api/analyze"}
    return {"message": "Versevo Backend API v5.1", "version": "5.1.0", "status": "running", "timestamp": datetime.now().isoformat(), "endpoints": endpoints}

@app.get("/api/flutter/health")
async def flutter_health():
    return {"status": "healthy", "service": "versevo-backend", "timestamp": datetime.now().isoformat(), "version": "5.1.0"}

@app.get("/api/health")
async def health():
    return {"status": "healthy", "service": "versevo-backend", "timestamp": datetime.now().isoformat(), "version": "5.1.0"}

@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: dict):
    try:
        filename = request.get("filename", "unknown.txt")
        file_data = request.get("file_data", "")
        if not file_data:
            raise HTTPException(status_code=400, detail="No file data provided")
        content_bytes = base64.b64decode(file_data)
        file_id = str(uuid.uuid4())
        ext = filename.split('.')[-1].lower() if '.' in filename else 'txt'
        file_path = f"{UPLOAD_FOLDER}/{file_id}.{ext}"
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content_bytes)
        content_str = extract_text_from_file(file_path, ext)
        if not content_str or not content_str.strip():
            content_str = f"Документ: {filename}\nТип: {ext}\n\nСодержимое недоступно для автоматического извлечения."
        language = detect_language_safe(content_str)
        chapters = detect_chapters(content_str)
        word_count = len(content_str.split())
        char_count = len(content_str)
        doc_id = documents_store.next_id()
        doc = {
            "id": doc_id, "filename": filename, "content": content_str,
            "language": language, "file_type": ext, "file_path": file_path,
            "file_id": file_id, "word_count": word_count, "char_count": char_count,
            "chapter_count": len(chapters), "reading_time_minutes": max(1, word_count // 200),
            "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat(),
            "chapters": chapters,
        }
        documents_store[doc_id] = doc
        return {
            "id": doc["id"], "filename": doc["filename"], "language": doc["language"],
            "file_type": doc["file_type"], "word_count": doc["word_count"],
            "char_count": doc["char_count"], "chapter_count": doc["chapter_count"],
            "reading_time_minutes": doc["reading_time_minutes"], "created_at": doc["created_at"],
            "content_preview": (doc["content"][:300] + "...") if len(doc["content"]) > 300 else doc["content"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/documents")
async def get_documents():
    docs = sorted(documents_store.values(), key=lambda x: x["created_at"], reverse=True)
    return [{"id": d["id"], "filename": d["filename"], "language": d["language"], "file_type": d["file_type"], "word_count": d["word_count"], "char_count": d["char_count"], "chapter_count": d["chapter_count"], "reading_time_minutes": d["reading_time_minutes"], "created_at": d["created_at"], "content_preview": (d["content"][:200] + "...") if len(d["content"]) > 200 else d["content"]} for d in docs]

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int):
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    d = documents_store[document_id]
    return {"id": d["id"], "filename": d["filename"], "content": d["content"], "language": d["language"], "file_type": d["file_type"], "word_count": d["word_count"], "char_count": d["char_count"], "chapter_count": d["chapter_count"], "reading_time_minutes": d["reading_time_minutes"], "created_at": d["created_at"], "chapters": d["chapters"]}

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int):
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = documents_store[document_id]
    if os.path.exists(doc["file_path"]):
        try: os.remove(doc["file_path"])
        except: pass
    del documents_store[document_id]
    return {"status": "success", "message": f"Document {document_id} deleted"}

@app.post("/api/chat/ask")
async def chat_ask(request: ChatRequest):
    try:
        if request.document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = documents_store[request.document_id]
        answer = _generate_chat_answer(doc, request.question)
        if _hf_available and len(doc.get("content", "")) > 100:
            try:
                if any(w in request.question.lower() for w in ['тональность', 'настроение', 'эмоциональн']):
                    sentiment = get_hf_pipeline("sentiment")
                    if sentiment:
                        sr = sentiment(doc["content"][:512])
                        if sr:
                            label = sr[0].get("label", "NEUTRAL")
                            score = sr[0].get("score", 0.5)
                            sentiment_map = {"POSITIVE": "позитивная", "LABEL_2": "позитивная", "NEGATIVE": "негативная", "LABEL_0": "негативная", "NEUTRAL": "нейтральная", "LABEL_1": "нейтральная"}
                            answer += f"\n\nАнализ тональности: {sentiment_map.get(label, 'нейтральная')} (уверенность: {score:.0%})"
            except:
                pass
        return {"answer": answer, "document_id": request.document_id, "question": request.question, "ai_used": _hf_available}
    except HTTPException:
        raise
    except Exception as e:
        return {"answer": "Произошла ошибка при обработке вопроса. Попробуйте ещё раз.", "document_id": request.document_id, "question": request.question}

@app.post("/api/translate/text")
async def translate_text(request: TranslateRequest):
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text is empty")
        source = request.source_language
        if not source or source == "auto":
            source = detect_language_safe(request.text)
        target = request.target_language
        if source == target:
            return {"original_text": request.text, "translated_text": request.text, "source_language": source, "target_language": target, "style": request.style, "translation_service": "identity"}
        translated = google_translator.translate(request.text, source, target)
        if not translated:
            translated = local_translator.translate(request.text, source, target, request.style)
        return {"original_text": request.text, "translated_text": translated, "source_language": source, "target_language": target, "style": request.style, "translation_service": "google" if google_translator.is_available() else "local"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@app.post("/api/analyze")
async def analyze_document_endpoint(request: AnalysisRequest):
    try:
        if request.document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = documents_store[request.document_id]
        content = doc["content"]
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        result = _perform_basic_analysis(content)
        return {
            "document_id": request.document_id, "filename": doc["filename"], "language": doc["language"],
            "summary": result["summary"], "themes": result["themes"], "sentiment": result["sentiment"],
            "complexity": result["complexity"], "writing_style": "Информационный",
            "key_points": result["key_points"], "statistics": result["statistics"],
            "language_features": result["language_features"],
            "document_statistics": {"word_count": doc["word_count"], "char_count": doc["char_count"], "chapter_count": doc["chapter_count"], "reading_time_minutes": doc["reading_time_minutes"], "file_type": doc["file_type"]},
            "characters": [], "entities": [], "ai_analysis": False, "fallback": False,
            "analysis_type": request.analysis_type, "analysis_timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/api/analyze/ai/health")
async def ai_health():
    return {"status": "healthy" if _hf_available else "unavailable", "service": "huggingface", "available": _hf_available, "models_loaded": [k for k, v in _hf_pipelines.items() if v["pipeline"] is not None], "timestamp": datetime.now().isoformat()}

@app.post("/api/analyze/ai/document")
async def analyze_with_ai(request: AIAnalysisRequest):
    try:
        if request.document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = documents_store[request.document_id]
        content = doc["content"]
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        basic = _perform_basic_analysis(content)
        ai = _perform_ai_analysis(content)
        return {
            "document_id": request.document_id, "filename": doc["filename"], "language": doc["language"],
            "summary": ai.get("summary") or basic.get("summary"),
            "themes": ai.get("themes") or basic.get("themes", []),
            "sentiment": ai.get("sentiment") or basic.get("sentiment"),
            "writing_style": ai.get("writing_style") or "Информационный",
            "key_points": ai.get("key_points") or basic.get("key_points", []),
            "entities": ai.get("entities", []),
            "statistics": basic.get("statistics", {}),
            "language_features": basic.get("language_features", {}),
            "ai_analysis": ai.get("ai_analysis", False),
            "fallback": ai.get("fallback", True),
            "analysis_type": request.analysis_type,
            "analysis_timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"document_id": request.document_id, "summary": "Произошла ошибка при AI-анализе.", "themes": ["Ошибка анализа"], "sentiment": "Не определена", "writing_style": "Не определен", "key_points": ["Не удалось выполнить AI-анализ", str(e)[:100]], "entities": [], "ai_analysis": False, "fallback": True, "analysis_timestamp": datetime.now().isoformat()}

@app.get("/api/documents/{document_id}/quotes")
async def get_document_quotes(document_id: int, limit: int = 5):
    try:
        if document_id not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = documents_store[document_id]
        content = doc["content"]
        if not content or len(content.strip()) < 10:
            return {"document_id": document_id, "quotes": ["Текст документа пустой или слишком короткий"], "count": 1, "ai_analysis": False, "fallback": True}
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', content) if 30 < len(s.strip()) < 250]
        unique_quotes = []
        seen = set()
        for q in sentences:
            norm = ' '.join(q.lower().split())
            if not any(_similarity(norm, s) > 0.7 for s in seen) and len(unique_quotes) < limit:
                unique_quotes.append(q)
                seen.add(norm)
        while len(unique_quotes) < min(limit, 5):
            fallbacks = ["Каждая книга открывает новые горизонты.", "Чтение — это диалог с автором через время и пространство.", "Слова имеют силу менять восприятие мира.", "Литература хранит мудрость поколений.", "Текст — это мост между мыслью и её воплощением."]
            for f in fallbacks:
                if len(unique_quotes) < min(limit, 5):
                    unique_quotes.append(f)
        return {"document_id": document_id, "quotes": unique_quotes[:limit], "count": len(unique_quotes[:limit]), "ai_analysis": False, "fallback": False}
    except Exception as e:
        return {"document_id": document_id, "quotes": ["Цитаты временно недоступны"], "count": 1, "ai_analysis": False, "fallback": True}

# ===== AUTH =====
@app.post("/api/auth/login")
async def login_user(request: LoginRequest):
    try:
        if not request.email or "@" not in request.email:
            raise HTTPException(status_code=400, detail="Invalid email format")
        if not request.password or len(request.password) < 1:
            raise HTTPException(status_code=400, detail="Password required")
        return {"status": "success", "message": "Login successful", "token": f"demo_token_{int(datetime.now().timestamp())}", "user": {"id": 1, "email": request.email, "username": request.email.split("@")[0], "created_at": datetime.now().isoformat()}, "timestamp": datetime.now().isoformat(), "demo_mode": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")

@app.post("/api/auth/register")
async def register_user(request: RegisterRequest):
    try:
        if not request.email or "@" not in request.email:
            raise HTTPException(status_code=400, detail="Invalid email format")
        if not request.username or len(request.username) < 2:
            raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
        if not request.password or len(request.password) < 1:
            raise HTTPException(status_code=400, detail="Password required")
        return {"status": "success", "message": "Registration successful", "token": f"demo_token_{int(datetime.now().timestamp())}", "user": {"id": 2, "email": request.email, "username": request.username, "created_at": datetime.now().isoformat()}, "timestamp": datetime.now().isoformat(), "demo_mode": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration error: {str(e)}")

@app.get("/api/auth/check")
async def check_auth(token: str):
    try:
        if token and token.startswith("demo_token_"):
            return {"status": "success", "valid": True, "demo_mode": True, "timestamp": datetime.now().isoformat()}
        return {"status": "error", "valid": False, "message": "Invalid token format", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth check failed: {str(e)}")

@app.post("/api/auth/logout")
async def logout_user():
    return {"status": "success", "message": "Logout successful", "timestamp": datetime.now().isoformat(), "demo_mode": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
