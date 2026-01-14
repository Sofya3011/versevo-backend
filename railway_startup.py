#!/usr/bin/env python3
"""
Railway Startup Script
Запускает приложение с правильными настройками для Railway
"""
import os
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("🚀 Запуск Versevo Backend на Railway...")
    
    # Ждем немного чтобы Railway успел инициализировать окружение
    logger.info("⏳ Ожидание инициализации окружения Railway...")
    time.sleep(3)
    
    # Устанавливаем переменные окружения для кэша моделей
    os.environ.setdefault('HF_HOME', '/tmp/huggingface')
    os.environ.setdefault('TRANSFORMERS_CACHE', '/tmp/huggingface')
    os.environ.setdefault('TORCH_HOME', '/tmp/torch')
    
    # Создаем директории для кэша
    os.makedirs('/tmp/huggingface', exist_ok=True)
    os.makedirs('/tmp/torch', exist_ok=True)
    
    # Импортируем и запускаем основное приложение
    from main import app
    import uvicorn
    
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🎯 Запуск FastAPI на порту {port}")
    
    # Запускаем с увеличенными таймаутами для Railway
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        timeout_keep_alive=60,
        timeout_graceful_shutdown=30
    )

if __name__ == "__main__":
    main()
