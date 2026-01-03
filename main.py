# main.py - СУПЕР МИНИМАЛЬНЫЙ, БЕЗ ОШИБОК
from fastapi import FastAPI
import os
import sys

print("🚀 STARTING APP...", file=sys.stderr)

# СОЗДАЕМ APP СРАЗУ - БЕЗ ИМПОРТОВ!
app = FastAPI()

print("✅ App created", file=sys.stderr)

@app.get("/")
async def root():
    print("📍 Root endpoint called", file=sys.stderr)
    return {
        "status": "running",
        "message": "Versevo API",
        "version": "1.0"
    }

@app.get("/api/flutter/health")
async def health():
    print("❤️ Health check", file=sys.stderr)
    return {"status": "healthy"}

@app.get("/test")
async def test():
    return {"test": "ok", "timestamp": "now"}

# НИКАКИХ СЛОЖНЫХ ИМПОРТОВ!
# НИКАКОЙ БД!
# НИКАКИХ СЕРВИСОВ!

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting server on port {port}", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=port)
