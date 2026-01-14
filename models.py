# models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
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
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    notes = relationship("DocumentNote", back_populates="user", cascade="all, delete-orphan")
    reading_progress = relationship("ReadingProgress", back_populates="user", cascade="all, delete-orphan")

class Document(Base):
    """Модель документа"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_path = Column(String(1000), nullable=True)
    file_size = Column(Integer, default=0)
    file_hash = Column(String(64), nullable=True)
    
    content = Column(Text, nullable=True)
    translated_content = Column(Text, nullable=True)
    language = Column(String(10), default="en")
    
    # Статистика
    word_count = Column(Integer, default=0)
    char_count = Column(Integer, default=0)
    chapter_count = Column(Integer, default=0)
    reading_time_minutes = Column(Integer, default=0)
    
    # Метаданные - ИЗМЕНЕНО: переименовано из 'metadata' в 'document_metadata'
    document_metadata = Column(JSON, nullable=True, default=dict)  # <-- ИЗМЕНЕНИЕ ЗДЕСЬ
    chapters = Column(JSON, nullable=True, default=list)
    
    # Системные поля
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_processed = Column(Boolean, default=False)
    
    # Связи
    user = relationship("User", back_populates="documents")
    notes = relationship("DocumentNote", back_populates="document", cascade="all, delete-orphan")
    reading_progress = relationship("ReadingProgress", back_populates="document", cascade="all, delete-orphan")

class DocumentNote(Base):
    """Модель заметки к документу"""
    __tablename__ = "document_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chapter_index = Column(Integer, default=0)
    
    text = Column(Text, nullable=False)
    selected_text = Column(Text, nullable=True)
    text_position = Column(Integer, nullable=True)
    
    color = Column(String(20), default="yellow")
    is_highlight = Column(Boolean, default=False)
    
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
    scroll_position = Column(Float, default=0.0)
    percentage = Column(Float, default=0.0)
    
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
    
    summary = Column(Text, nullable=True)
    themes = Column(JSON, nullable=True, default=list)
    sentiment = Column(String(50), nullable=True)
    writing_style = Column(String(100), nullable=True)
    key_points = Column(JSON, nullable=True, default=list)
    characters = Column(JSON, nullable=True, default=list)
    entities = Column(JSON, nullable=True, default=list)
    
    statistics = Column(JSON, nullable=True, default=dict)
    language_features = Column(JSON, nullable=True, default=dict)
    
    analysis_type = Column(String(50), default="full")
    ai_provider = Column(String(50), nullable=True)
    ai_analysis = Column(Boolean, default=False)
    
    is_cached = Column(Boolean, default=True)
    cache_key = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    document = relationship("Document")

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
    """Кэш переводов"""
    __tablename__ = "translation_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(255), unique=True, index=True, nullable=False)
    
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    style = Column(String(50), default="artistic")
    
    hit_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
