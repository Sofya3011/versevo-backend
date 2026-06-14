from fastapi import FastAPI, HTTPException
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
from datetime import datetime
from collections import Counter
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== МОДЕЛИ ==========
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

class ChatRequest(BaseModel):
    document_id: int
    question: str
    language: str = "ru"

# ========== APP ==========
app = FastAPI(title="Versevo Backend API", version="5.1.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
except Exception:
    pass

PORT = int(os.getenv("PORT", 8080))

documents_store = {}
current_doc_id = 1

# Флаги ленивой инициализации
_hf_loaded = False
_nltk_loaded = False
_hf_translator = None
_local_translator = None

# ========== ЛОКАЛЬНЫЙ ПЕРЕВОДЧИК (лёгкий, без зависимостей) ==========
def _get_local_translator():
    global _local_translator
    if _local_translator is None:
        _local_translator = _LocalTranslator()
    return _local_translator

class _LocalTranslator:
    def __init__(self):
        self.translation_dict = {
            'en-ru': {
                'hello': 'привет', 'world': 'мир', 'book': 'книга',
                'read': 'читать', 'page': 'страница', 'chapter': 'глава',
                'text': 'текст', 'document': 'документ', 'translate': 'переводить',
                'library': 'библиотека', 'author': 'автор', 'title': 'название',
                'content': 'содержание', 'analysis': 'анализ', 'summary': 'краткое содержание',
                'character': 'персонаж', 'plot': 'сюжет', 'story': 'история',
                'novel': 'роман', 'literature': 'литература',
                'the': '', 'a': '', 'an': '', 'and': 'и', 'or': 'или',
                'but': 'но', 'in': 'в', 'on': 'на', 'at': 'в', 'to': 'к',
                'for': 'для', 'with': 'с', 'from': 'из', 'of': 'из',
                'is': 'является', 'are': 'являются', 'was': 'был', 'were': 'были',
                'have': 'иметь', 'has': 'имеет', 'can': 'мочь', 'could': 'мог',
                'will': 'будет', 'would': 'бы',
                'good': 'хороший', 'bad': 'плохой', 'new': 'новый', 'old': 'старый',
                'big': 'большой', 'small': 'маленький', 'beautiful': 'красивый',
                'interesting': 'интересный', 'important': 'важный',
            },
            'ru-en': {
                'привет': 'hello', 'мир': 'world', 'книга': 'book',
                'читать': 'read', 'глава': 'chapter', 'текст': 'text',
                'документ': 'document', 'автор': 'author', 'название': 'title',
                'содержание': 'content', 'анализ': 'analysis',
                'и': 'and', 'или': 'or', 'но': 'but', 'в': 'in', 'на': 'on',
            }
        }

    def translate(self, text: str, source_lang: str, target_lang: str, style: str = "artistic") -> str:
        if source_lang == target_lang:
            return text
        if len(text) > 800:
            text = text[:800] + "..."
        key = f"{source_lang}-{target_lang}"
        if key in self.translation_dict:
            words = re.findall(r'\b\w+\b|[^\w\s]', text)
            translated = []
            d = self.translation_dict[key]
            for word in words:
                if re.match(r'^\w+$', word):
                    w = word.lower()
                    t = d.get(w, word)
                    translated.append(t if t else '')
                else:
                    translated.append(word)
            result = ' '.join(translated)
            result = re.sub(r'\s+([.,!?;:])', r'\1', result)
            result = re.sub(r'\s+', ' ', result).strip()
            return result
        return text

# ========== HF ПЕРЕВОДЧИК (ленивая загрузка) ==========
def _get_hf_translator():
    global _hf_translator
    if _hf_translator is None:
        _hf_translator = _HFTranslator()
    return _hf_translator

class _HFTranslator:
    def __init__(self):
        self._pipelines = {}
        self._model_configs = {
            'en-ru': {'model': 'Helsinki-NLP/opus-mt-en-ru', 'max_length': 400},
            'ru-en': {'model': 'Helsinki-NLP/opus-mt-ru-en', 'max_length': 400},
        }
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        try:
            from transformers import pipeline
            import torch
            self._device = 0 if torch.cuda.is_available() else -1
            self._loaded = True
            logger.info("HF translator ready")
        except ImportError:
            logger.warning("transformers not installed, using local translator only")
            self._loaded = False

    def _get_pipeline(self, key: str):
        if key in self._pipelines:
            return self._pipelines[key]
        self._ensure_loaded()
        if not self._loaded or key not in self._model_configs:
            return None
        try:
            from transformers import pipeline
            cfg = self._model_configs[key]
            logger.info(f"Loading translation model {cfg['model']}...")
            self._pipelines[key] = pipeline(
                "translation", model=cfg['model'],
                device=self._device, max_length=cfg['max_length']
            )
            logger.info(f"Model {cfg['model']} loaded")
            return self._pipelines[key]
        except Exception as e:
            logger.error(f"Failed to load translation model: {e}")
            return None

    def translate(self, text: str, source_lang: str, target_lang: str, style: str = "artistic") -> str:
        if source_lang == target_lang:
            return text
        key = f"{source_lang}-{target_lang}"
        pipe = self._get_pipeline(key)
        if pipe is None:
            return _get_local_translator().translate(text, source_lang, target_lang, style)
        try:
            if len(text) > 1000:
                text = text[:1000]
            result = pipe(text, max_length=400, truncation=True)
            if result and len(result) > 0:
                return result[0].get('translation_text', text)
        except Exception as e:
            logger.error(f"HF translate error: {e}")
        return _get_local_translator().translate(text, source_lang, target_lang, style)

    def is_available(self, source_lang: str, target_lang: str) -> bool:
        key = f"{source_lang}-{target_lang}"
        if key not in self._model_configs:
            return False
        self._ensure_loaded()
        return self._loaded and self._get_pipeline(key) is not None

# ========== HF АНАЛИЗ (ленивая загрузка) ==========
_hf_analysis_ready = False
_hf_analysis_pipelines = {}

def _ensure_hf_analysis():
    global _hf_analysis_ready, _hf_analysis_pipelines
    if _hf_analysis_ready:
        return True
    try:
        import transformers
        import torch
        device = 0 if torch.cuda.is_available() else -1
        models = {
            "sentiment": {"model_name": "blanchefort/rubert-base-cased-sentiment", "task": "sentiment-analysis"},
            "summarization": {"model_name": "IlyaGusev/rut5_base_sum_gazeta", "task": "summarization"},
            "ner": {"model_name": "Babelscape/wikineural-multilingual-ner", "task": "ner"},
        }
        _hf_analysis_pipelines = {
            task: {"model_name": cfg["model_name"], "pipeline": None, "task": cfg["task"]}
            for task, cfg in models.items()
        }
        _hf_analysis_ready = True
        logger.info("HF analysis initialized (lazy loading)")
        return True
    except ImportError:
        logger.warning("transformers not available for analysis")
        return False
    except Exception as e:
        logger.error(f"HF analysis init error: {e}")
        return False

def _get_hf_analysis_pipeline(task: str):
    if not _hf_analysis_ready:
        return None
    if task not in _hf_analysis_pipelines:
        return None
    if _hf_analysis_pipelines[task]["pipeline"] is not None:
        return _hf_analysis_pipelines[task]["pipeline"]
    try:
        from transformers import pipeline
        import torch
        device = 0 if torch.cuda.is_available() else -1
        cfg = _hf_analysis_pipelines[task]
        logger.info(f"Loading analysis model {cfg['model_name']}...")
        if task == "summarization":
            pipe = pipeline("summarization", model=cfg["model_name"],
                          tokenizer=cfg["model_name"], device=device,
                          max_length=150, min_length=50)
        elif task == "ner":
            pipe = pipeline("ner", model=cfg["model_name"], device=device,
                          grouped_entities=True, ignore_labels=["O"])
        else:
            pipe = pipeline(cfg["task"], model=cfg["model_name"], device=device)
        _hf_analysis_pipelines[task]["pipeline"] = pipe
        logger.info(f"Model {cfg['model_name']} loaded")
        return pipe
    except Exception as e:
        logger.error(f"Failed to load analysis model {task}: {e}")
        return None

# ========== NLTK (ленивая загрузка) ==========
_nltk_available = False

def _ensure_nltk():
    global _nltk_available
    if _nltk_available:
        return True
    try:
        import nltk
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords', quiet=True)
        _nltk_available = True
        return True
    except ImportError:
        return False

# ========== УТИЛИТЫ ==========
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
                paras = [p.text for p in doc.paragraphs if p.text.strip()]
                return "\n\n".join(paras) if paras else ""
            except:
                return ""
        elif file_type == 'txt':
            try:
                with open(file_path, "r", encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except:
                return ""
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
    current_chapter = None
    chapter_content = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        is_title = any(re.match(p, paragraph, re.MULTILINE | re.IGNORECASE) for p in patterns)
        if is_title:
            if current_chapter is not None and chapter_content:
                chapters.append({'title': current_chapter, 'content': '\n\n'.join(chapter_content)})
            current_chapter = paragraph[:100]
            chapter_content = []
        else:
            if current_chapter is None:
                current_chapter = 'Начало'
            chapter_content.append(paragraph)
    if current_chapter and chapter_content:
        chapters.append({'title': current_chapter, 'content': '\n\n'.join(chapter_content)})
    if not chapters:
        for i in range(0, len(text), 5000):
            chunk = text[i:i + 5000]
            if chunk.strip():
                chapters.append({'title': f'Часть {len(chapters) + 1}', 'content': chunk})
    return chapters

# ========== HEALTH ==========
@app.get("/")
async def root():
    return {
        "message": "Versevo Backend API v5.1",
        "version": "5.1.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
    }

@app.get("/api/health")
@app.get("/api/flutter/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "versevo-backend",
        "version": "5.1.0",
        "timestamp": datetime.now().isoformat(),
    }

@app.get("/api/warmup")
async def warmup():
    """Для Railway: держит контейнер в памяти, не даёт заснуть."""
    return {"status": "warm", "timestamp": datetime.now().isoformat()}

# ========== AI HEALTH ==========
@app.get("/api/analyze/ai/health")
async def ai_health_check():
    available = _ensure_hf_analysis()
    return {
        "status": "healthy" if available else "unavailable",
        "available": available,
        "models_loaded": [k for k, v in _hf_analysis_pipelines.items() if v["pipeline"] is not None],
        "models_available": list(_hf_analysis_pipelines.keys()),
        "timestamp": datetime.now().isoformat()
    }

# ========== ДОКУМЕНТЫ ==========
@app.post("/api/documents/upload-base64")
async def upload_document_base64(request: dict):
    global current_doc_id
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
        if not content_str or content_str.strip() == "":
            content_str = f"Документ: {filename}\nТип: {ext}\n\nСодержимое недоступно."
        language = detect_language_safe(content_str)
        chapters = detect_chapters(content_str)
        word_count = len(content_str.split())
        char_count = len(content_str)
        reading_time = max(1, word_count // 200)
        doc = {
            "id": current_doc_id, "filename": filename, "content": content_str,
            "language": language, "file_type": ext, "file_path": file_path,
            "file_id": file_id, "word_count": word_count, "char_count": char_count,
            "chapter_count": len(chapters), "reading_time_minutes": reading_time,
            "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat(),
            "chapters": chapters,
        }
        documents_store[current_doc_id] = doc
        current_doc_id += 1
        return {
            "id": doc["id"], "filename": doc["filename"],
            "language": doc["language"], "file_type": doc["file_type"],
            "word_count": doc["word_count"], "char_count": doc["char_count"],
            "chapter_count": doc["chapter_count"],
            "reading_time_minutes": doc["reading_time_minutes"],
            "created_at": doc["created_at"],
        }
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/documents")
async def get_documents():
    docs = list(documents_store.values())
    return [{
        "id": d["id"], "filename": d["filename"],
        "language": d["language"], "file_type": d["file_type"],
        "word_count": d["word_count"], "char_count": d["char_count"],
        "chapter_count": d["chapter_count"],
        "reading_time_minutes": d["reading_time_minutes"],
        "created_at": d["created_at"],
    } for d in sorted(docs, key=lambda x: x["created_at"], reverse=True)]

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int):
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    d = documents_store[document_id]
    return {
        "id": d["id"], "filename": d["filename"], "content": d["content"],
        "language": d["language"], "file_type": d["file_type"],
        "word_count": d["word_count"], "char_count": d["char_count"],
        "chapter_count": d["chapter_count"],
        "reading_time_minutes": d["reading_time_minutes"],
        "created_at": d["created_at"], "chapters": d["chapters"],
    }

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int):
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = documents_store[document_id]
    if os.path.exists(doc["file_path"]):
        try:
            os.remove(doc["file_path"])
        except:
            pass
    del documents_store[document_id]
    return {"status": "success", "deleted_id": document_id}

# ========== ПЕРЕВОД ==========
@app.post("/api/translate/text")
async def translate_text(request: TranslateRequest):
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is empty")
        source_lang = request.source_language
        if not source_lang or source_lang == "auto":
            source_lang = detect_language_safe(request.text)
        target_lang = request.target_language
        hf = _get_hf_translator()
        used_hf = hf.is_available(source_lang, target_lang)
        if used_hf:
            translated = hf.translate(request.text, source_lang, target_lang, request.style)
        else:
            translated = _get_local_translator().translate(request.text, source_lang, target_lang, request.style)
        return {
            "translated_text": translated,
            "source_language": source_lang,
            "target_language": target_lang,
            "translation_service": "huggingface" if used_hf else "fallback",
        }
    except Exception as e:
        logger.error(f"Translate error: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

# ========== БАЗОВЫЙ АНАЛИЗ ==========
def _perform_basic_analysis(text: str) -> Dict[str, Any]:
    result = {"summary": "", "themes": [], "sentiment": "Нейтральный",
              "complexity": "Средний", "key_points": [], "statistics": {},
              "language_features": {}}
    if not text or len(text.strip()) < 10:
        result["summary"] = "Текст слишком короткий"
        return result
    _ensure_nltk()
    words = [w for w in text.split() if w.strip()]
    sentences = re.split(r'[.!?]+', text)
    paragraphs = text.split('\n\n')
    sentences = [s.strip() for s in sentences if s.strip()]
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    wc = len(words)
    sc = len(sentences)
    avg = wc / sc if sc > 0 else 0
    complexity = "Простой" if avg < 8 else "Средний" if avg < 15 else "Сложный"
    result["complexity"] = complexity
    if sc >= 3:
        summary = " ".join(s.strip() for s in sentences[:4] if len(s.strip()) > 10 and not s.strip().isupper())
        result["summary"] = (summary[:250] + "...") if len(summary) > 250 else summary
    else:
        result["summary"] = text[:200] + "..." if len(text) > 200 else text
    proper = re.findall(r'\b[A-Z][a-z]+\b', text[:1000])
    themes = []
    if proper:
        c = Counter(n.lower() for n in proper)
        themes = [n for n, _ in c.most_common(5) if c[n] > 1 and len(n) > 3][:3]
    if not themes:
        word_freq = Counter(w.lower() for w in words if len(w) > 3)
        stop = {'это','что','как','для','того','чтобы','если','когда','или','и','но','а',
                'the','and','but','for','with','from','that','this','was','were'}
        themes = [w for w, _ in word_freq.most_common(10) if w not in stop and word_freq[w] > 1][:3]
    result["themes"] = themes[:3] if themes else ["Документ", "Текст", "Содержание"]
    result["statistics"] = {
        "word_count": wc, "sentence_count": sc, "paragraph_count": len(paragraphs),
        "avg_sentence_length": round(avg, 1),
        "reading_time_minutes": max(1, wc // 200),
    }
    cyrillic = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
    latin = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
    result["language_features"] = {
        "detected_language": "ru" if cyrillic > latin else "en",
        "has_dialogue": bool(re.search(r'["\'«»]', text)),
    }
    result["key_points"] = [
        f"Объем: {wc} слов", f"Сложность: {complexity}",
        f"Время чтения: {max(1, wc // 200)} мин",
    ]
    if themes:
        result["key_points"].append(f"Темы: {', '.join(themes[:2])}")
    return result

@app.post("/api/analyze")
async def analyze_document(request: AnalysisRequest):
    if request.document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = documents_store[request.document_id]
    content = doc["content"]
    if not content or len(content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Document has no content")
    r = _perform_basic_analysis(content)
    return {
        "document_id": request.document_id, "filename": doc["filename"],
        "language": doc["language"],
        "summary": r["summary"], "themes": r["themes"],
        "sentiment": r["sentiment"], "complexity": r["complexity"],
        "writing_style": "Информационный",
        "key_points": r["key_points"],
        "statistics": r["statistics"],
        "language_features": r["language_features"],
        "characters": [], "entities": [],
        "ai_analysis": False, "fallback": False,
        "analysis_timestamp": datetime.now().isoformat(),
    }

# ========== AI АНАЛИЗ (HuggingFace) ==========
@app.post("/api/analyze/ai/document")
async def analyze_with_ai(request: AIAnalysisRequest):
    try:
        did = request.document_id
        if did not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = documents_store[did]
        content = doc["content"]
        if not content or len(content.strip()) < 10:
            raise HTTPException(status_code=400, detail="Document has no content")
        basic = _perform_basic_analysis(content)
        ai = {"summary": "", "themes": [], "sentiment": "Нейтральный",
              "writing_style": "Информационный", "key_points": [],
              "entities": [], "ai_analysis": False, "fallback": True, "models_used": []}
        if _ensure_hf_analysis():
            sample = content[:2000]
            sentiment_pipe = _get_hf_analysis_pipeline("sentiment")
            if sentiment_pipe:
                try:
                    sr = sentiment_pipe(sample[:512])
                    if sr:
                        label = sr[0].get("label", "NEUTRAL").upper()
                        score = sr[0].get("score", 0.5)
                        sm = {"POSITIVE": "Положительный", "NEGATIVE": "Отрицательный", "NEUTRAL": "Нейтральный",
                              "LABEL_0": "Отрицательный", "LABEL_1": "Нейтральный", "LABEL_2": "Положительный"}
                        ai["sentiment"] = sm.get(label, "Нейтральный")
                        ai["models_used"].append("sentiment")
                        ai["ai_analysis"] = True
                        ai["fallback"] = False
                except Exception as e:
                    logger.warning(f"Sentiment error: {e}")
            if len(content.split()) > 150:
                summ_pipe = _get_hf_analysis_pipeline("summarization")
                if summ_pipe:
                    try:
                        clean = re.sub(r'\s+', ' ', sample.strip())
                        if len(clean) > 100:
                            sr2 = summ_pipe(clean, max_length=120, min_length=60, do_sample=False)
                            if sr2:
                                summary = sr2[0].get("summary_text", "")
                                ai["summary"] = re.sub(r'^\[ПЕРЕВОД\]\s*', '', summary)
                                ai["models_used"].append("summarization")
                                ai["ai_analysis"] = True
                                ai["fallback"] = False
                    except Exception as e:
                        logger.warning(f"Summarization error: {e}")
            ner_pipe = _get_hf_analysis_pipeline("ner")
            if ner_pipe:
                try:
                    ner_result = ner_pipe(sample[:1000])
                    entities = []
                    seen = set()
                    for e in ner_result:
                        if isinstance(e, dict):
                            word = e.get("word", "")
                            group = e.get("entity_group", "")
                            if group in ["PER", "ORG", "LOC"] and len(word) > 2 and not re.match(r'^\d+$', word):
                                key = f"{group}_{word.lower()}"
                                if key not in seen:
                                    entities.append({"entity": group, "word": word, "score": round(e.get("score", 0), 3)})
                                    seen.add(key)
                    if entities:
                        ai["entities"] = entities[:10]
                        et = Counter(e["entity"] for e in ai["entities"])
                        themes = []
                        for et_type, _ in et.most_common(3):
                            if et_type == "PER": themes.append("Персонажи")
                            elif et_type == "ORG": themes.append("Организации")
                            elif et_type == "LOC": themes.append("Места")
                        if themes:
                            ai["themes"] = themes
                        ai["models_used"].append("ner")
                        ai["ai_analysis"] = True
                        ai["fallback"] = False
                except Exception as e:
                    logger.warning(f"NER error: {e}")
        wc = len(content.split())
        sc = len(re.split(r'[.!?]+', content))
        ws = "Академический" if wc > 5000 else "Литературный" if sc > 0 and wc / sc > 25 else "Информационный"
        ai["writing_style"] = ws
        kp = []
        if ai["entities"]:
            people = [e["word"] for e in ai["entities"] if e["entity"] == "PER"]
            if people:
                kp.append(f"Персонажи: {', '.join(people[:2])}")
        if ai["sentiment"] != "Нейтральный":
            kp.append(f"Тональность: {ai['sentiment']}")
        kp.append(f"Стиль письма: {ws}")
        kp.append(f"Время чтения: {max(1, wc // 200)} мин")
        kp.append(f"Объем: {wc} слов")
        ai["key_points"] = kp if kp else basic["key_points"]
        if not ai["summary"]:
            ai["summary"] = basic["summary"]
        if not ai["themes"]:
            ai["themes"] = basic["themes"]
        return {
            "document_id": did, "filename": doc["filename"], "language": doc["language"],
            "summary": ai["summary"], "themes": ai["themes"],
            "sentiment": ai["sentiment"], "writing_style": ai["writing_style"],
            "key_points": ai["key_points"], "entities": ai["entities"],
            "statistics": basic["statistics"],
            "language_features": basic["language_features"],
            "ai_analysis": ai["ai_analysis"], "fallback": ai["fallback"],
            "models_used": ai["models_used"],
            "analysis_timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return {
            "document_id": request.document_id,
            "summary": "Ошибка AI-анализа. Используйте базовый анализ.",
            "themes": [], "sentiment": "Не определена",
            "writing_style": "Не определен",
            "key_points": ["Ошибка выполнения AI-анализа"],
            "entities": [], "ai_analysis": False, "fallback": True,
            "analysis_timestamp": datetime.now().isoformat(),
        }

# ========== ЧАТ ==========
@app.post("/api/chat/ask")
async def chat_ask(request: ChatRequest):
    try:
        did = request.document_id
        if did not in documents_store:
            raise HTTPException(status_code=404, detail="Document not found")
        doc = documents_store[did]
        content = doc.get("content", "")
        title = doc.get("filename", "документ")
        q = request.question.lower()
        if not content or len(content.strip()) < 10:
            return {"answer": f"Документ «{title}» пуст."}
        words = content.split()
        wc = len(words)
        sentences = re.split(r'(?<=[.!?])\s+', content)
        answer = ""
        if any(w in q for w in ['о чём', 'о чем', 'суть', 'содержание', 'кратко']):
            key = [s.strip() for s in sentences if 30 < len(s.strip()) < 300][:4]
            if key:
                answer = f"📄 Документ «{title}» — {wc} слов.\n\nКраткое содержание:\n\n" + "\n\n".join(f"{i+1}. {s}" for i, s in enumerate(key))
        elif any(w in q for w in ['тезис', 'главн', 'основн', 'темы', 'иде']):
            key = [s.strip() for s in sentences if 40 < len(s.strip()) < 250][:6]
            if len(key) >= 2:
                answer = f"📌 Основные тезисы «{title}»:\n\n" + "\n\n".join(f"{i+1}. {s}" for i, s in enumerate(key))
        elif any(w in q for w in ['персонаж', 'герой', 'кто', 'люди', 'человек']):
            names = re.findall(r'\b[А-Я][а-я]+\b', content[:3000])
            unique = list(dict.fromkeys(n for n in names if len(n) > 1 and n not in ['Это','Что','Как','Для','Они','Мы','Вы','Она','Он','Глава']))
            if unique:
                answer = f"👥 В документе «{title}» упоминаются: {', '.join(unique[:10])}."
        elif any(w in q for w in ['найди', 'найти', 'поиск', 'абзац', 'где']):
            search = re.sub(r'(найди|найти|поиск|абзац|про|где|мне|пожалуйста)\s*', '', request.question, flags=re.IGNORECASE).strip()
            if len(search) > 2:
                idx = content.lower().find(search.lower())
                if idx != -1:
                    start = max(0, idx - 150)
                    end = min(len(content), idx + len(search) + 250)
                    answer = f"🔍 По запросу «{search}»:\n\n...{content[start:end]}..."
                else:
                    answer = f"🔍 По запросу «{search}» ничего не найдено."
        elif any(w in q for w in ['жанр', 'стиль', 'как написан']):
            avg_len = wc / len(sentences) if sentences else 0
            style = 'Литературный / Академический' if avg_len > 25 else 'Художественный' if avg_len > 15 else 'Информационный'
            answer = f"📝 Стиль «{title}»: {style}\nСредняя длина предложения: {avg_len:.1f} слов\nОбъём: {wc} слов"
        if not answer:
            answer = (f"📖 Документ «{title}» — {wc} слов.\n\n"
                      f"Чтобы получить ответ, попробуйте:\n"
                      f"• «О чём этот документ?»\n"
                      f"• «Выдели основные тезисы»\n"
                      f"• «Какие персонажи?»\n"
                      f"• «Найди абзац про...»")
        if _ensure_hf_analysis() and len(content) > 100:
            try:
                pipe = _get_hf_analysis_pipeline("sentiment")
                if pipe and any(w in q for w in ['тональность', 'настроение', 'эмоциональн']):
                    sr = pipe(content[:512])
                    if sr:
                        label = sr[0].get("label", "NEUTRAL")
                        score = sr[0].get("score", 0.5)
                        sm = {"POSITIVE": "позитивная", "LABEL_2": "позитивная",
                              "NEGATIVE": "негативная", "LABEL_0": "негативная",
                              "NEUTRAL": "нейтральная", "LABEL_1": "нейтральная"}
                        answer += f"\n\nАнализ тональности: {sm.get(label, 'нейтральная')} (уверенность: {score:.0%})"
            except:
                pass
        return {"answer": answer}
    except HTTPException:
        raise
    except Exception as e:
        return {"answer": "Произошла ошибка при обработке вопроса."}

# ========== АУТЕНТИФИКАЦИЯ ==========
@app.post("/api/auth/login")
async def login_user(request: LoginRequest):
    if not request.email or "@" not in request.email:
        raise HTTPException(status_code=400, detail="Invalid email")
    if not request.password:
        raise HTTPException(status_code=400, detail="Password required")
    return {
        "status": "success",
        "token": f"demo_token_{int(datetime.now().timestamp())}",
        "user": {"id": 1, "email": request.email, "username": request.email.split("@")[0]},
        "demo_mode": True,
    }

@app.post("/api/auth/register")
async def register_user(request: RegisterRequest):
    if not request.email or "@" not in request.email:
        raise HTTPException(status_code=400, detail="Invalid email")
    if not request.username or len(request.username) < 2:
        raise HTTPException(status_code=400, detail="Username too short")
    if not request.password:
        raise HTTPException(status_code=400, detail="Password required")
    return {
        "status": "success",
        "token": f"demo_token_{int(datetime.now().timestamp())}",
        "user": {"id": 2, "email": request.email, "username": request.username},
        "demo_mode": True,
    }

@app.get("/api/auth/check")
async def check_auth(token: str):
    valid = token and token.startswith("demo_token_")
    return {"status": "success" if valid else "error", "valid": valid, "demo_mode": True}

@app.post("/api/auth/logout")
async def logout_user():
    return {"status": "success", "message": "Logout successful"}

# ========== ЦИТАТЫ ==========
@app.get("/api/documents/{document_id}/quotes")
async def get_document_quotes(document_id: int, limit: int = 5):
    if document_id not in documents_store:
        raise HTTPException(status_code=404, detail="Document not found")
    content = documents_store[document_id].get("content", "")
    if not content or len(content.strip()) < 10:
        return {"document_id": document_id, "quotes": ["Текст пуст"], "count": 1}
    sentences = re.split(r'(?<=[.!?])\s+', content)
    quotes = [s.strip() for s in sentences if 30 < len(s.strip()) < 250][:limit * 2]
    unique, seen = [], set()
    for q in quotes:
        norm = ' '.join(q.lower().split())
        if not any(len(set(norm.split()) & set(s.split())) / max(len(set(norm.split()) | set(s.split())), 1) > 0.7 for s in seen):
            unique.append(q)
            seen.add(norm)
        if len(unique) >= limit:
            break
    if len(unique) < limit:
        fallback = ["Каждая книга открывает новые горизонты.",
                    "Чтение — это диалог с автором через время и пространство.",
                    "Слова имеют силу менять восприятие мира.",
                    "Литература хранит мудрость поколений.",
                    "Текст — это мост между мыслью и её воплощением."]
        unique.extend(fallback[:limit - len(unique)])
    return {"document_id": document_id, "quotes": unique[:limit], "count": min(limit, len(unique))}

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Versevo API v5.1 on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", access_log=True)
