"""
Railway Startup Script
Загружает модели ПОСЛЕ успешного запуска healthcheck
"""
import os
import sys
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_ai_models_in_background():
    """Фоновая загрузка тяжелых моделей AI"""
    def load_models():
        try:
            logger.info("🔄 Фоновая загрузка AI моделей...")
            
            # Импортируем и инициализируем модели ПОСЛЕ запуска сервера
            time.sleep(10)  # Даем время запуститься healthcheck
            
            # Ленивая загрузка Hugging Face
            from transformers import pipeline
            
            # Загружаем только минимальные модели для старта
            logger.info("📦 Загружаем базовые модели...")
            
            # Translation pipeline (лениво загрузится при первом запросе)
            global translation_pipeline
            translation_pipeline = None  # Инициализируем позже
            
            logger.info("✅ AI модели готовы к ленивой загрузке")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки моделей: {e}")
    
    # Запускаем в отдельном потоке
    thread = threading.Thread(target=load_models, daemon=True)
    thread.start()
    return thread

def init_database():
    """Инициализация базы данных"""
    try:
        from database import engine, Base
        from models import User, Document, DocumentNote, ReadingProgress, DocumentAnalysis, FavoriteQuote, TranslationCache
        
        logger.info("🗄️  Создаем таблицы PostgreSQL...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Таблицы созданы")
        return True
    except Exception as e:
        logger.warning(f"⚠️ База данных недоступна: {e}")
        logger.info("📝 Используем in-memory хранилище для документов")
        return False

if __name__ == "__main__":
    # 1. Сначала БД
    init_database()
    
    # 2. Запускаем фоновую загрузку AI
    load_ai_models_in_background()
    
    # 3. Импортируем и запускаем приложение
    from main import app
    import uvicorn
    
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 Запуск Versevo на порту {port}")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        # Важно для Railway!
        timeout_keep_alive=30,
        access_log=True
    )
