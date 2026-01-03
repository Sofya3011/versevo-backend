# main.py - ДОБАВЬ ЭТО!
from fastapi import FastAPI
from fastapi.responses import FileResponse
import os
import time

app = FastAPI()

# Добавь favicon чтобы избежать 499 ошибок
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("favicon.ico") if os.path.exists("favicon.ico") else {"status": "no icon"}

@app.get("/")
def root():
    print(f"📍 Root at {time.time()}", flush=True)
    return {"status": "alive", "app": "versevo", "timestamp": time.time()}

@app.get("/api/flutter/health")
def health():
    print(f"❤️ Health check at {time.time()}", flush=True)
    return {
        "status": "healthy", 
        "service": "versevo-backend",
        "timestamp": time.time(),
        "memory": "ok"
    }

@app.get("/api/health")
def health2():
    return {"status": "healthy", "check": "alternative"}

# ДОБАВЬ ОБРАБОТКУ СИГНАЛОВ
import signal
import sys

def handle_exit(signum, frame):
    print(f"🚨 Received signal {signum}, exiting gracefully", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting on port {port} at {time.time()}", flush=True)
    import uvicorn
    
    # Запускаем с максимальными настройками стабильности
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        access_log=True,
        log_level="info",
        timeout_keep_alive=30,
        limit_concurrency=100
    )
