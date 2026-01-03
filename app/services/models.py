from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255))
    avatar_path = Column(String(500))
    auth_token = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    filename = Column(String(255), nullable=False)
    content = Column(Text)
    translated_content = Column(Text)
    language = Column(String(10), default='en')
    file_type = Column(String(10))
    file_size = Column(Integer, default=0)
    file_path = Column(String(500))
    word_count = Column(Integer, default=0)
    char_count = Column(Integer, default=0)
    chapter_count = Column(Integer, default=0)
    reading_time_minutes = Column(Integer, default=0)
    document_metadata = Column(JSON, default=lambda: {})  # ← ИЗМЕНИ НА document_metadata
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    chapters = relationship("Chapter", back_populates="document", cascade="all, delete-orphan")
    notes = relationship("DocumentNote", back_populates="document", cascade="all, delete-orphan")
    progress = relationship("ReadingProgress", back_populates="document", uselist=False)
    analyses = relationship("AnalysisResult", back_populates="document", cascade="all, delete-orphan")
    
    user = relationship("User")

class Chapter(Base):
    __tablename__ = "chapters"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    title = Column(String(255))
    content = Column(Text)
    word_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship("Document", back_populates="chapters")

class DocumentNote(Base):
    __tablename__ = "document_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    chapter_index = Column(Integer, default=0, nullable=False)
    note_text = Column(Text, nullable=False)
    selected_text = Column(Text)
    text_position = Column(Integer)
    color = Column(String(20), default='yellow')
    is_highlight = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    document = relationship("Document", back_populates="notes")
    user = relationship("User")

class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    chapter_index = Column(Integer, default=0, nullable=False)
    scroll_position = Column(Float, default=0.0)
    last_read_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship("Document", back_populates="progress")
    user = relationship("User")

class TranslationCache(Base):
    __tablename__ = "translation_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    original_text_hash = Column(String(64), unique=True, nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    model_used = Column(String(100))
    hit_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, default=datetime.utcnow)

class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    analysis_type = Column(String(50), default="general")
    summary = Column(Text)
    themes = Column(Text)
    sentiment = Column(String(50))
    writing_style = Column(String(100))
    key_points = Column(JSON, default=lambda: [])
    characters = Column(JSON, default=lambda: [])
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    document = relationship("Document", back_populates="analyses")

class FavoriteQuote(Base):
    __tablename__ = "favorite_quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    document_id = Column(Integer, ForeignKey('documents.id'))
    quote = Column(Text, nullable=False)
    start_position = Column(Integer)
    end_position = Column(Integer)
    chapter = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User")
    document = relationship("Document")
