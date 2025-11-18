import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pathlib import Path
from celery import Celery
import shutil
import json
from . import db, models
from .services.extractor import extract_text_from_file
from .services.analysis import analyze_text
from .config import settings
# Эндпоинты
@app.get("/")
async def root():
    return {
        "message": "Versevo Backend API", 
        "version": "1.0.0",
        "endpoints": {
            "analyze": "POST /analyze - анализ текста",
            "upload": "POST /upload - загрузка файла",
            "health": "GET /health - статус сервера"
        }
    }
# Celery config - broker URL from env
celery = Celery(
    "versevo_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
)

app = FastAPI(title="Versevo Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure folders
Path(settings.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
Path(settings.BOOKS_FOLDER).mkdir(parents=True, exist_ok=True)

# DB init
db.init_db()

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    file_id = uuid.uuid4().hex
    ext = Path(file.filename).suffix
    dest = Path(settings.UPLOAD_FOLDER) / f"{file_id}{ext}"
    content = await file.read()
    dest.write_bytes(content)

    # extract text (sync)
    try:
        text = extract_text_from_file(str(dest), file.content_type)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {e}")

    # save metadata to DB
    session = db.SessionLocal()
    book = models.Book(
        filename=file.filename,
        file_path=str(dest),
        file_type=file.content_type or ext,
        language="unknown",
        needs_translation=False
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    session.close()

    return {"id": book.id, "filename": book.filename, "preview": text[:300]}

@app.post("/translate-job")
def create_translation_job(document_id: int, mode: str = "artistic"):
    """
    Enqueue translation job (using HF NLLB or LibreTranslate)
    Returns celery task id
    """
    session = db.SessionLocal()
    book = session.query(models.Book).filter(models.Book.id == document_id).first()
    session.close()
    if not book:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = {"document_id": document_id, "mode": mode}
    task = celery.send_task("worker.tasks.translate_task", args=[payload])
    return {"task_id": task.id}

@app.post("/synthesize-job")
def create_synthesize_job(document_id: int, voice: str = "default", style: str = "neutral"):
    session = db.SessionLocal()
    book = session.query(models.Book).filter(models.Book.id == document_id).first()
    session.close()
    if not book:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = {"document_id": document_id, "voice": voice, "style": style}
    task = celery.send_task("worker.tasks.synthesize_task", args=[payload])
    return {"task_id": task.id}

@app.post("/analyze-job")
def analyze_job(document_id: int):
    payload = {"document_id": document_id}
    task = celery.send_task("worker.tasks.analyze_task", args=[payload])
    return {"task_id": task.id}

@app.get("/task/{task_id}")
def get_task_status(task_id: str):
    res = celery.AsyncResult(task_id)
    response = {"id": task_id, "state": res.state}
    try:
        result = res.get(timeout=0.5)
        response["result"] = result
    except Exception:
        pass

    return JSONResponse(response)
