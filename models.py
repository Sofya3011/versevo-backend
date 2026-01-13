# models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from database import Base

class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Связи
    documents = relationship("Document", back_populates="user")
    notes = relationship("DocumentNote", back_populates="user")
    reading_progress = relationship("ReadingProgress", back_populates="user")

class Document(Base):
    """Модель документа"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, txt, docx, epub
    file_path = Column(String(1000), nullable=True)
    file_size = Column(Integer, default=0)  # в байтах
    file_hash = Column(String(64), unique=True, index=True)  # для избежания дубликатов
    
    content = Column(Text, nullable=True)
    translated_content = Column(Text, nullable=True)
    language = Column(String(10), default="en")
    
    # Статистика
    word_count = Column(Integer, default=0)
    char_count = Column(Integer, default=0)
    chapter_count = Column(Integer, default=0)
    reading_time_minutes = Column(Integer, default=0)
    
    # Метаданные
    metadata = Column(JSON, nullable=True, default=dict)  # автор, год и т.д.
    chapters = Column(JSON, nullable=True, default=list)  # список глав
    
    # Системные поля
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_processed = Column(Boolean, default=False)
    
    # Связи
    user = relationship("User", back_populates="documents")
    notes = relationship("DocumentNote", back_populates="document")
    reading_progress = relationship("ReadingProgress", back_populates="document")
    analyses = relationship("DocumentAnalysis", back_populates="document")

class DocumentNote(Base):
    """Модель заметки к документу"""
    __tablename__ = "document_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chapter_index = Column(Integer, default=0)
    
    # Текст заметки
    text = Column(Text, nullable=False)
    selected_text = Column(Text, nullable=True)  # выделенный текст
    text_position = Column(Integer, nullable=True)  # позиция в тексте
    
    # Стили
    color = Column(String(20), default="yellow")  # hex цвет или название
    is_highlight = Column(Boolean, default=False)
    
    # Системные поля
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    document = relationship("Document", back_populates="notes")
    user = relationship("User", back_populates="notes")

class ReadingProgress(Base):
    """Модель прогресса чтения"""
    __tablename__ = "reading_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    chapter_index = Column(Integer, default=0)
    scroll_position = Column(Float, default=0.0)  # позиция скролла
    percentage = Column(Float, default=0.0)  # процент прочтения
    
    last_read_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    document = relationship("Document", back_populates="reading_progress")
    user = relationship("User", back_populates="reading_progress")

class DocumentAnalysis(Base):
    """Модель AI-анализа документа"""
    __tablename__ = "document_analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    
    # Результаты анализа
    summary = Column(Text, nullable=True)
    themes = Column(JSON, nullable=True, default=list)
    sentiment = Column(String(50), nullable=True)
    writing_style = Column(String(100), nullable=True)
    key_points = Column(JSON, nullable=True, default=list)
    characters = Column(JSON, nullable=True, default=list)
    entities = Column(JSON, nullable=True, default=list)
    
    # Статистика
    statistics = Column(JSON, nullable=True, default=dict)
    language_features = Column(JSON, nullable=True, default=dict)
    
    # Метрики
    analysis_type = Column(String(50), default="full")  # quick, standard, detailed, full
    ai_provider = Column(String(50), nullable=True)  # huggingface, gemini, openai, basic
    ai_analysis = Column(Boolean, default=False)
    
    # Кэширование
    is_cached = Column(Boolean, default=True)
    cache_key = Column(String(255), unique=True, index=True)
    
    # Системные поля
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    document = relationship("Document", back_populates="analyses")

class FavoriteQuote(Base):
    """Модель избранных цитат"""
    __tablename__ = "favorite_quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    quote = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    start_position = Column(Integer, nullable=True)
    end_position = Column(Integer, nullable=True)
    chapter_index = Column(Integer, nullable=True)
    
    tags = Column(JSON, nullable=True, default=list)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    document = relationship("Document")
    user = relationship("User")

class TranslationCache(Base):
    """Кэш переводов для производительности"""
    __tablename__ = "translation_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(255), unique=True, index=True, nullable=False)
    
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    style = Column(String(50), default="artistic")
    
    # Статистика использования
    hit_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # для очистки старых переводов
