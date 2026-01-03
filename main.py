from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Versevo работает!", "port": os.getenv("PORT", "8000")}

@app.get("/api/flutter/health")
def health():
    return {"status": "healthy", "service": "versevo-backend"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Запускаю на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
