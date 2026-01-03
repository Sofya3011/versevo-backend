import sys
import os

# Добавляем путь к app в sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Теперь можно импортировать из app.services
try:
    from services.db import Base, engine, get_db
    from services.models import Document
    from services.utils import detect_language_safe
    print("✅ Services imported successfully from app/services")
    
    # Пробуем создать таблицы
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created")
    except Exception as e:
        print(f"⚠️ Could not create tables: {e}")
        
except ImportError as e:
    print(f"❌ Could not import from services: {e}")
    print("⚠️ Using fallback implementations")
    
    # Заглушки если не получилось импортировать
    class DummyDB:
        def get_db(self):
            return None
    
    get_db = DummyDB().get_db
    Document = None
    
    def detect_language_safe(text: str):
        return "en"
