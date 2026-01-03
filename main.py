# main.py - САМЫЙ ПРОСТОЙ (без импортов из services)
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging
import os
import uuid
import base64
from datetime import datetime

# ========== СОЗДАЕМ APP ПЕРВЫМ ДЕЛОМ ==========
app = FastAPI(
    title="Versevo Backend API",
    description="Modern document reader with AI features",
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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Директории
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Статические файлы
try:
    app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
    logger.info("✅ Static files mounted")
except Exception as e:
    logger.error(f"❌ Error mounting static files: {e}")

# Временное хранилище
documents_db = []
current_id = 1

# ========== SIMPLE ENDPOINTS ==========
@app.get("/")
async def root():
    return {
        "message": "Versevo Backend API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": [
            "/api/flutter/health",
            "/upload-base64",
            "/documents"
        ]
    }

@app.get("/api/flutter/health")
async def health_check():
    return {"status": "healthy", "service": "versevo-backend"}

@app.post("/upload-base64")
async def upload_base64(request: dict):
    try:
        filename = request.get("filename", "unknown.txt")
        file_data = request.get("file_data", "")
        file_size = request.get("file_size", 0)
        
        # Декодируем base64
        content_bytes = base64.b64decode(file_data)
        
        # Сохраняем файл
        file_id = str(uuid.uuid4())
        file_path = f"{UPLOAD_FOLDER}/{file_id}.txt"
        
        with open(file_path, "wb") as f:
            f.write(content_bytes)
        
        # Простая обработка
        text = content_bytes.decode('utf-8', errors='ignore')
        
        document = {
            "id": len(documents_db) + 1,
            "filename": filename,
            "content": text[:500] + "..." if len(text) > 500 else text,
            "file_size": file_size,
            "created_at": datetime.now().isoformat()
        }
        
        documents_db.append(document)
        return document
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents")
async def get_documents():
    return documents_db

@app.get("/test-services")
async def test_services():
    """Тестовый endpoint для проверки импорта services"""
    try:
        # Пробуем импортировать но не ломаем app
        import sys
        sys.path.append("app")
        
        try:
            from services.config import settings
            return {"services": "available", "settings": str(settings)}
        except ImportError as e:
            return {"services": "import_error", "error": str(e)}
    except Exception as e:
        return {"services": "error", "error": str(e)}

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
