import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from pydantic import BaseModel

from .services.analysis import analyze_text
from .services.extractor import extract_text_from_file
from .config import settings

# Создаем приложение ОДИН раз!
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
        "endpoints": {
            "analyze": "POST /analyze - анализ текста",
            "upload": "POST /upload - загрузка файла", 
            "health": "GET /health - статус сервера",
            "test-analysis": "GET /test-analysis - тестовый анализ"
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Versevo Backend"}

@app.post("/analyze")
async def analyze_text_endpoint(request: AnalyzeRequest):
    """Анализ текста через OpenAI"""
    try:
        result = analyze_text(request.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Загрузка файла"""
    try:
        # Читаем содержимое файла
        content = await file.read()
        text_content = content.decode('utf-8')
        
        file_id = str(uuid.uuid4())
        
        return {
            "id": file_id,
            "filename": file.filename,
            "status": "uploaded", 
            "message": "Файл успешно загружен",
            "preview": text_content[:200] + "..." if len(text_content) > 200 else text_content,
            "text_length": len(text_content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

@app.get("/test-analysis")
async def test_analysis():
    """Тестовый анализ (для проверки работы)"""
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

# Дополнительные эндпоинты для расширенной функциональности
@app.post("/upload-and-analyze")
async def upload_and_analyze(file: UploadFile = File(...)):
    """Загрузка файла и немедленный анализ"""
    try:
        # Загружаем файл
        content = await file.read()
        text_content = content.decode('utf-8')
        
        # Анализируем текст
        analysis_result = analyze_text(text_content)
        
        return {
            "filename": file.filename,
            "text_length": len(text_content),
            "analysis": analysis_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

@app.get("/stats")
async def get_stats():
    """Статистика сервера"""
    return {
        "service": "Versevo Backend",
        "status": "running",
        "features": [
            "Анализ текста через OpenAI",
            "Извлечение персонажей и тем", 
            "Анализ тональности",
            "Создание облака слов",
            "Загрузка файлов"
        ]
    }

# Эндпоинты для Celery (пока закомментированы - будут работать когда добавим Redis)
"""
from celery import Celery

# Celery config - будет работать когда добавим Redis
celery = Celery(
    "versevo_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)

@app.post("/analyze-job")
def analyze_job_background(document_id: int):
    # Будет работать когда добавим Celery
    return {"message": "Celery tasks will be available soon", "status": "coming_soon"}
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
