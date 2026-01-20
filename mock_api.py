# mock_api.py - Обработка API запросов с мок-данными
from datetime import datetime
import json
from fastapi import HTTPException
import hashlib

class MockAPI:
    def __init__(self):
        self.documents = []
        self._init_mock_documents()
    
    def _init_mock_documents(self):
        """Инициализация тестовых документов"""
        self.documents = [
            {
                "id": 1,
                "title": "Будущее образования и AI",
                "filename": "education_ai.pdf",
                "content": """
                ГЛАВА 1. ВВЕДЕНИЕ
                
                Искусственный интеллект трансформирует образование. 
                Он предлагает персонализированные учебные планы, 
                автоматизирует оценку заданий и создает 
                интерактивные учебные среды.
                
                ГЛАВА 2. ПЕРСОНАЛИЗАЦИЯ ОБУЧЕНИЯ
                
                AI анализирует стиль обучения каждого студента 
                и адаптирует материал под его потребности. 
                Это повышает эффективность обучения на 40%.
                
                ГЛАВА 3. БУДУЩИЕ ВЫЗОВЫ
                
                Этические вопросы, приватность данных и 
                подготовка учителей остаются ключевыми 
                вызовами для внедрения AI в образование.
                """,
                "language": "ru",
                "file_type": "pdf",
                "word_count": 180,
                "char_count": 1200,
                "chapter_count": 3,
                "reading_time_minutes": 4,
                "created_at": "2024-01-20T10:30:00",
                "chapters": [
                    {"title": "Введение", "content": "Искусственный интеллект трансформирует образование..."},
                    {"title": "Персонализация", "content": "AI анализирует стиль обучения каждого студента..."},
                    {"title": "Будущие вызовы", "content": "Этические вопросы и приватность данных..."}
                ]
            },
            {
                "id": 2,
                "title": "Краткая история технологий",
                "filename": "tech_history.txt",
                "content": """
                От изобретения колеса до искусственного интеллекта - 
                технологии постоянно развивались, изменяя общество.
                
                Промышленная революция, цифровая революция и 
                сейчас - эра AI и квантовых вычислений.
                """,
                "language": "ru",
                "file_type": "txt",
                "word_count": 50,
                "char_count": 350,
                "chapter_count": 1,
                "reading_time_minutes": 1,
                "created_at": "2024-01-19T14:45:00",
                "chapters": [
                    {"title": "История технологий", "content": "От изобретения колеса до искусственного интеллекта..."}
                ]
            }
        ]
    
    def get_documents(self, skip=0, limit=50):
        """Получить список документов"""
        return self.documents[skip:skip+limit]
    
    def get_document(self, document_id):
        """Получить документ по ID"""
        for doc in self.documents:
            if doc["id"] == document_id:
                return doc
        return None
    
    def upload_document(self, filename, content):
        """Загрузить новый документ"""
        new_id = max([d["id"] for d in self.documents], default=0) + 1
        
        # Простой анализ текста
        words = content.split()
        chars = len(content)
        
        new_doc = {
            "id": new_id,
            "title": filename.split('.')[0],
            "filename": filename,
            "content": content,
            "language": self._detect_language(content),
            "file_type": filename.split('.')[-1] if '.' in filename else 'txt',
            "word_count": len(words),
            "char_count": chars,
            "chapter_count": content.count('\n\n') + 1,
            "reading_time_minutes": max(1, len(words) // 200),
            "created_at": datetime.now().isoformat(),
            "chapters": self._split_into_chapters(content)
        }
        
        self.documents.append(new_doc)
        return new_doc
    
    def _detect_language(self, text):
        """Простое определение языка"""
        cyrillic = sum(1 for c in text if 'а' <= c <= 'я' or 'А' <= c <= 'Я')
        latin = sum(1 for c in text if 'a' <= c <= 'z' or 'A' <= c <= 'Z')
        return 'ru' if cyrillic > latin else 'en'
    
    def _split_into_chapters(self, text):
        """Разбить текст на главы"""
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        chapters = []
        
        for i, para in enumerate(paragraphs):
            if len(para) > 100 or any(keyword in para.lower() for keyword in ['глава', 'chapter', 'раздел']):
                chapters.append({
                    "title": f"Глава {len(chapters)+1}",
                    "content": para
                })
            elif chapters:
                chapters[-1]["content"] += "\n\n" + para
            else:
                chapters.append({
                    "title": "Документ",
                    "content": para
                })
        
        return chapters if chapters else [{"title": "Документ", "content": text}]
    
    def translate_text(self, text, target_lang, source_lang="auto", style="artistic"):
        """Перевод текста (мок)"""
        translations = {
            "en-ru": {
                "Hello world": "Привет мир",
                "Artificial intelligence": "Искусственный интеллект",
                "Machine learning": "Машинное обучение",
                "Future of education": "Будущее образования"
            },
            "ru-en": {
                "Привет мир": "Hello world",
                "Искусственный интеллект": "Artificial intelligence"
            }
        }
        
        key = f"{source_lang}-{target_lang}" if source_lang != "auto" else f"en-{target_lang}"
        
        if key in translations:
            for original, translated in translations[key].items():
                if original in text:
                    text = text.replace(original, translated)
        
        # Добавляем стиль
        if style == "artistic":
            text = f"🎨 {text}"
        elif style == "formal":
            text = f"📄 {text}"
        
        return {
            "original_text": text,
            "translated_text": text + " [переведено локально]",
            "source_language": source_lang,
            "target_language": target_lang,
            "style": style,
            "translation_service": "mock"
        }
    
    def analyze_document(self, document_id, analysis_type="full"):
        """Анализ документа (мок)"""
        doc = self.get_document(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "language": doc["language"],
            "summary": f"Документ '{doc['title']}' содержит {doc['word_count']} слов на тему образования и технологий.",
            "themes": ["Образование", "Технологии", "Искусственный интеллект"],
            "sentiment": "Положительный",
            "writing_style": "Информационный",
            "key_points": [
                f"Документ содержит {doc['word_count']} слов",
                f"Разделен на {doc['chapter_count']} глав",
                "Основная тема - влияние AI на образование"
            ],
            "ai_analysis": True,
            "ai_provider": "gemini",
            "analysis_type": analysis_type
        }

# Глобальный экземпляр
mock_api = MockAPI()
