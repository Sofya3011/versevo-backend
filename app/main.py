import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from pydantic import BaseModel
from .services.translator import translate_text
from .services.tts_service import synthesize_speech
from .services.analysis import analyze_text
from .config import settings
from fastapi import FastAPI
from app.services.translation_nllb import translate_text_nllb
app = FastAPI(title="Versevo Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели запросов
class AnalyzeRequest(BaseModel):
    text: str

# Создаем необходимые папки
Path(settings.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
Path(settings.BOOKS_FOLDER).mkdir(parents=True, exist_ok=True)

# Основные эндпоинты
@app.get("/")
async def root():
    return {
        "message": "Versevo Backend API", 
        "version": "1.0.0",
        "status": "active",
        "endpoints": [
            {"method": "GET", "path": "/", "description": "Информация об API"},
            {"method": "GET", "path": "/health", "description": "Статус сервера"},
            {"method": "GET", "path": "/stats", "description": "Статистика сервера"},
            {"method": "GET", "path": "/test-analysis", "description": "Тестовый анализ текста"},
            {"method": "POST", "path": "/analyze", "description": "Анализ текста через OpenAI"},
            {"method": "POST", "path": "/upload", "description": "Загрузка файла"}
        ]
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "service": "Versevo Backend",
        "timestamp": "2024-01-01T00:00:00Z"
    }
@app.post("/translate/nllb")
def translate_nllb_api(text: str, source: str, target: str):
    translated = translate_text_nllb(text, source, target)
    return {"translated": translated}
@app.get("/stats")
async def get_stats():
    return {
        "service": "Versevo Backend",
        "status": "running", 
        "version": "1.0.0",
        "features": [
            "Анализ текста через OpenAI",
            "Извлечение персонажей и тем",
            "Анализ тональности", 
            "Создание облака слов",
            "Загрузка файлов"
        ]
    }

@app.post("/analyze")
async def analyze_text_endpoint(request: AnalyzeRequest):
    """Анализ текста через OpenAI"""
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Текст не может быть пустым")
        
        result = analyze_text(request.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Загрузка файла"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Имя файла не указано")
        
        # Читаем содержимое файла
        content = await file.read()
        
        # Пытаемся декодировать как текст
        try:
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Файл должен быть текстовым (UTF-8)")
        
        file_id = str(uuid.uuid4())
        
        return {
            "id": file_id,
            "filename": file.filename,
            "status": "uploaded", 
            "message": "Файл успешно загружен",
            "preview": text_content[:200] + "..." if len(text_content) > 200 else text_content,
            "text_length": len(text_content),
            "file_size": len(content)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/test-analysis")
async def test_analysis():
    """Тестовый анализ (для проверки работы)"""
    try:
        test_text = """
        Маленький принц жил на планете, которая была чуть больше его самого, и ему очень не хватало друга.
        Однажды на его планете появилась роза, прекрасная и капризная. Маленький принц полюбил её, 
        но её капризы заставили его отправиться в путешествие по другим планетам.
        В ходе своих путешествий он встретил короля, который правил всем, но не имел подданных, 
        честолюбца, который желал лишь восхищения, и пьяницу, который пил чтобы забыть о стыде.
        """
        
        result = analyze_text(test_text)
        return {
            "test_text": test_text,
            "analysis_result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Тестовый анализ не удался: {str(e)}")
@app.post("/translate")
async def translate_endpoint(request: AnalyzeRequest):
    """Перевод текста"""
    try:
        translated = translate_text(request.text)
        return {"original": request.text, "translated": translated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка перевода: {str(e)}")
@app.post("/synthesize")
async def synthesize_endpoint(request: AnalyzeRequest):
    """Озвучка текста"""
    try:
        audio_path = synthesize_speech(request.text)
        return {"text": request.text, "audio_path": audio_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка озвучки: {str(e)}")
# Простой эндпоинт для проверки
@app.get("/ping")
async def ping():
    return {"message": "pong", "status": "ok"}

@app.get("/env-check")
async def env_check():
    """Проверка переменных окружения"""
    return {
        "openai_key_configured": bool(settings.OPENAI_API_KEY),
        "upload_folder": settings.UPLOAD_FOLDER,
        "books_folder": settings.BOOKS_FOLDER
    }


