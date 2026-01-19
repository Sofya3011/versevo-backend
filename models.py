# models.py - SQLAlchemy модели для PostgreSQL
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.sql import func
from datetime import datetime
from database import Base

class User(Base):
    """Пользователи"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"

class Document(Base):
    """Документы"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)  # Сделали nullable=True
    title = Column(String(255), nullable=True)
    filename = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    language = Column(String(10), default='en')
    file_type = Column(String(20), default='txt')
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    char_count = Column(Integer, default=0)
    chapter_count = Column(Integer, default=1)
    reading_time_minutes = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename})>"

class DocumentNote(Base):
    """Заметки к документам"""
    __tablename__ = "document_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    selected_text = Column(Text, nullable=True)
    chapter_index = Column(Integer, default=0)
    text_position = Column(Integer, nullable=True)
    color = Column(String(20), default='yellow')
    is_highlight = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<DocumentNote(id={self.id}, document_id={self.document_id})>"

class ReadingProgress(Base):
    """Прогресс чтения"""
    __tablename__ = "reading_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, nullable=True)
    chapter_index = Column(Integer, default=0)
    scroll_position = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<ReadingProgress(id={self.id}, document_id={self.document_id})>"

class DocumentAnalysis(Base):
    """Анализ документов"""
    __tablename__ = "document_analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    analysis_type = Column(String(50), nullable=False)
    summary = Column(Text, nullable=True)
    themes = Column(Text, nullable=True)
    sentiment = Column(String(50), nullable=True)
    writing_style = Column(String(100), nullable=True)
    key_points = Column(Text, nullable=True)
    entities = Column(Text, nullable=True)
    ai_analysis = Column(Boolean, default=False)
    ai_provider = Column(String(50), nullable=True)
    analysis_timestamp = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<DocumentAnalysis(id={self.id}, document_id={self.document_id})>"

class FavoriteQuote(Base):
    """Избранные цитаты"""
    __tablename__ = "favorite_quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False)
    quote = Column(Text, nullable=False)
    start_position = Column(Integer, nullable=True)
    end_position = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    document_title = Column(String(255), nullable=True)
    document_language = Column(String(10), default='en')
    
    def __repr__(self):
        return f"<FavoriteQuote(id={self.id}, document_id={self.document_id})>"

class TranslationCache(Base):
    """Кэш переводов"""
    __tablename__ = "translation_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    original_text_hash = Column(String(64), unique=True, nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    style = Column(String(50), default='artistic')
    translation_service = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<TranslationCache(id={self.id}, source={self.source_language}→target={self.target_language})>"
