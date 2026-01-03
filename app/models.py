import sqlalchemy as sa
from .db import Base
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

class Book(Base):
    __tablename__ = "books"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    filename = sa.Column(sa.String, nullable=False)
    file_path = sa.Column(sa.String, nullable=False)
    file_type = sa.Column(sa.String, nullable=False)
    language = sa.Column(sa.String, nullable=True)
    needs_translation = sa.Column(sa.Boolean, default=False)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)

class TranslationJob(Base):
    __tablename__ = "translation_jobs"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    book_id = sa.Column(sa.Integer, nullable=False)
    mode = sa.Column(sa.String, nullable=False)  # 'artistic' or 'official'
    status = sa.Column(sa.String, default="pending")
    result_path = sa.Column(sa.String, nullable=True)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)

class AudioJob(Base):
    __tablename__ = "audio_jobs"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    book_id = sa.Column(sa.Integer, nullable=False)
    voice = sa.Column(sa.String, nullable=True)
    style = sa.Column(sa.String, nullable=True)
    status = sa.Column(sa.String, default="pending")
    audio_path = sa.Column(sa.String, nullable=True)

    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)



class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255))
    avatar_path = Column(String(500))
    auth_token = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

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
    metadata = Column(JSON, default=lambda: {})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    chapters = relationship("Chapter", back_populates="document", cascade="all, delete-orphan")
    notes = relationship("DocumentNote", back_populates="document", cascade="all, delete-orphan")
    progress = relationship("ReadingProgress", back_populates="document", uselist=False)

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
    summary = Column(Text)
    themes = Column(Text)
    sentiment = Column(String(50))
    writing_style = Column(String(100))
    key_points = Column(JSON, default=lambda: [])
    characters = Column(JSON, default=lambda: [])
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    document = relationship("Document")

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
