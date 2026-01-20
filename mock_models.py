# mock_models.py - Модели для эмуляции SQLAlchemy
from datetime import datetime

class User:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.email = kwargs.get('email')
        self.username = kwargs.get('username')
        self.hashed_password = kwargs.get('hashed_password')
        self.created_at = kwargs.get('created_at')
        self.last_login = kwargs.get('last_login')

class Document:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.user_id = kwargs.get('user_id')
        self.title = kwargs.get('title', '')
        self.filename = kwargs.get('filename')
        self.content = kwargs.get('content', '')
        self.language = kwargs.get('language', 'ru')
        self.file_type = kwargs.get('file_type', 'txt')
        self.file_path = kwargs.get('file_path')
        self.file_size = kwargs.get('file_size', 0)
        self.word_count = kwargs.get('word_count', 0)
        self.char_count = kwargs.get('char_count', 0)
        self.chapter_count = kwargs.get('chapter_count', 0)
        self.reading_time_minutes = kwargs.get('reading_time_minutes', 0)
        self.created_at = kwargs.get('created_at', datetime.now())
        self.updated_at = kwargs.get('updated_at', datetime.now())

class DocumentNote:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.document_id = kwargs.get('document_id')
        self.user_id = kwargs.get('user_id')
        self.text = kwargs.get('text')
        self.selected_text = kwargs.get('selected_text')
        self.chapter_index = kwargs.get('chapter_index')
        self.text_position = kwargs.get('text_position')
        self.color = kwargs.get('color', 'yellow')
        self.is_highlight = kwargs.get('is_highlight', False)
        self.created_at = kwargs.get('created_at', datetime.now())

class DocumentAnalysis:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.document_id = kwargs.get('document_id')
        self.analysis_type = kwargs.get('analysis_type', 'full')
        self.summary = kwargs.get('summary', '')
        self.themes = kwargs.get('themes', '')
        self.sentiment = kwargs.get('sentiment', 'Нейтральный')
        self.writing_style = kwargs.get('writing_style', 'Информационный')
        self.key_points = kwargs.get('key_points', '')
        self.entities = kwargs.get('entities', '')
        self.ai_analysis = kwargs.get('ai_analysis', False)
        self.ai_provider = kwargs.get('ai_provider', '')
        self.analysis_timestamp = kwargs.get('analysis_timestamp', datetime.now())
        self.created_at = kwargs.get('created_at', datetime.now())

class FavoriteQuote:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.document_id = kwargs.get('document_id')
        self.user_id = kwargs.get('user_id')
        self.quote = kwargs.get('quote')
        self.start_position = kwargs.get('start_position')
        self.end_position = kwargs.get('end_position')
        self.note = kwargs.get('note')
        self.document_title = kwargs.get('document_title')
        self.document_language = kwargs.get('document_language')
        self.created_at = kwargs.get('created_at', datetime.now())

class TranslationCache:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.original_text_hash = kwargs.get('original_text_hash')
        self.original_text = kwargs.get('original_text')
        self.translated_text = kwargs.get('translated_text')
        self.source_language = kwargs.get('source_language')
        self.target_language = kwargs.get('target_language')
        self.style = kwargs.get('style')
        self.translation_service = kwargs.get('translation_service')
        self.created_at = kwargs.get('created_at', datetime.now())
