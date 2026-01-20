from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, default=datetime.now)
    
    # Связи
    documents = relationship("Document", back_populates="user")
    notes = relationship("DocumentNote", back_populates="user")
    reading_progress = relationship("ReadingProgress", back_populates="user")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    content = Column(Text)
    language = Column(String(10))
    file_type = Column(String(10))
    file_path = Column(String(500))
    file_size = Column(Integer)
    word_count = Column(Integer)
    char_count = Column(Integer)
    chapter_count = Column(Integer, default=1)
    reading_time_minutes = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Связи
    user = relationship("User", back_populates="documents")
    notes = relationship("DocumentNote", back_populates="document")
    analyses = relationship("DocumentAnalysis", back_populates="document")
    quotes = relationship("FavoriteQuote", back_populates="document")
    reading_progress = relationship("ReadingProgress", back_populates="document")

class DocumentNote(Base):
    __tablename__ = "document_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    document_id = Column(Integer, ForeignKey("documents.id"))
    note = Column(Text)
    position = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)
    
    # Связи
    user = relationship("User", back_populates="notes")
    document = relationship("Document", back_populates="notes")

class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    document_id = Column(Integer, ForeignKey("documents.id"))
    progress_percentage = Column(Float, default=0.0)
    last_position = Column(Integer, default=0)
    total_time_seconds = Column(Integer, default=0)
    last_read = Column(DateTime, default=datetime.now)
    
    # Связи
    user = relationship("User", back_populates="reading_progress")
    document = relationship("Document", back_populates="reading_progress")

class DocumentAnalysis(Base):
    __tablename__ = "document_analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    analysis_type = Column(String(50))
    summary = Column(Text)
    themes = Column(Text)
    sentiment = Column(String(50))
    writing_style = Column(String(100))
    key_points = Column(Text)
    ai_analysis = Column(Boolean, default=False)
    ai_provider = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    
    # Связи
    document = relationship("Document", back_populates="analyses")

class FavoriteQuote(Base):
    __tablename__ = "favorite_quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    quote = Column(Text, nullable=False)
    start_position = Column(Integer)
    end_position = Column(Integer)
    note = Column(Text)
    document_title = Column(String(255))
    document_language = Column(String(10))
    created_at = Column(DateTime, default=datetime.now)
    
    # Связи
    document = relationship("Document", back_populates="quotes")

class TranslationCache(Base):
    __tablename__ = "translation_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    original_text = Column(Text)
    original_text_hash = Column(String(64), index=True)
    translated_text = Column(Text)
    source_language = Column(String(10))
    target_language = Column(String(10))
    translation_service = Column(String(50))
    style = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
