# run_mock_server.py
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Versevo Mock API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Мок данные
DOCUMENTS = [
    {
        "id": 1,
        "title": "Тестовый документ",
        "filename": "test.pdf",
        "content": "Это тестовый документ для демонстрации работы системы.",
        "word_count": 10,
        "created_at": "2024-01-20T10:00:00"
    }
]

@app.get("/")
async def root():
    return {"message": "Versevo Mock API", "status": "running"}

@app.get("/api/health")
async def health():
    return {"status": "healthy", "database": "mock"}

@app.get("/api/documents")
async def get_documents():
    return DOCUMENTS

@app.get("/api/documents/{document_id}")
async def get_document(document_id: int):
    for doc in DOCUMENTS:
        if doc["id"] == document_id:
            return doc
    raise HTTPException(status_code=404, detail="Документ не найден")

@app.post("/api/documents/upload-base64")
async def upload_document(data: dict):
    new_id = max([d["id"] for d in DOCUMENTS], default=0) + 1
    
    new_doc = {
        "id": new_id,
        "title": data.get("filename", "Новый документ"),
        "filename": data.get("filename", "unknown.txt"),
        "content": "[Содержимое документа]",
        "word_count": 100,
        "created_at": "2024-01-20T10:00:00"
    }
    
    DOCUMENTS.append(new_doc)
    return new_doc

if __name__ == "__main__":
    print("🚀 Запуск мок-сервера на http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
