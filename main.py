# main.py - ГАРАНТИРОВАННО РАБОЧИЙ
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Versevo API is running"}

@app.get("/api/flutter/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
