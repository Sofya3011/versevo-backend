import uuid
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, 
    Boolean, Float, JSON, BigInteger, Enum, Table, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import enum
from database import Base

# --- ВСПОМОГАТЕЛЬНЫЕ ТАБЛИЦЫ (СВЯЗИ МНОГИЕ-КО-МНОГИМ) ---

# Связь между документами и тегами (для категорий)
document_tags = Table(
    "document_tags_link",
    Base.metadata,
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"))
)

# --- ПЕРЕЧИСЛЕНИЯ (ENUMS) ---

class SubscriptionTier(enum.Enum):
    FREE = "free"
    PREMIUM = "premium"
    ULTRA = "ultra"
    ADMIN = "admin"

class DocumentFormat(enum.Enum):
    PDF = "pdf"
    EPUB = "epub"
    FB2 = "fb2"
    MOBI = "mobi"
    DJVU = "djvu"
    CBZ = "cbz"
    CBR = "cbr"
    TXT = "txt"
    DOCX = "docx"
    MANGA = "manga"

class AnalysisStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# --- ПОЛЬЗОВАТЕЛИ И БЕЗОПАСНОСТЬ ---

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Подписка
    tier = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE)
    subscription_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Профиль
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    preferred_language = Column(String(10), default="ru")
    
    # Системные поля
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)

    # Связи
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    reading_progress = relationship("ReadingProgress", back_populates="user")
    notes = relationship("DocumentNote", back_populates="user")
    dictionary = relationship("UserDictionary", back_populates="user")
    promo_usages = relationship("PromoCodeUsage", back_populates="user")
    payments = relationship("Payment", back_populates="user")

# --- СИСТЕМА ДОКУМЕНТОВ И МАНГИ ---

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    # Метаданные
    title = Column(String(500), nullable=False, index=True)
    author = Column(String(255), index=True)
    description = Column(Text)
    format = Column(Enum(DocumentFormat), nullable=False)
    source_language = Column(String(10))
    cover_url = Column(String(500))
    
    # Техническая информация
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger)
    file_hash = Column(String(64), index=True) # Для дедупликации
    
    # Статистика
    word_count = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    reading_time_est = Column(Integer) # в минутах
    
    # Статус ИИ
    analysis_status = Column(Enum(AnalysisStatus), default=AnalysisStatus.PENDING)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    owner = relationship("User", back_populates="documents")
    chapters = relationship("Chapter", back_populates="document", cascade="all, delete-orphan", order_by="Chapter.order_index")
    manga_pages = relationship("MangaPage", back_populates="document", cascade="all, delete-orphan")
    notes = relationship("DocumentNote", back_populates="document")
    analysis = relationship("DocumentAnalysis", back_populates="document", uselist=False)
    tags = relationship("Tag", secondary=document_tags, back_populates="documents")
    reading_progress = relationship("ReadingProgress", back_populates="document")

class Chapter(Base):
    __tablename__ = "chapters"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    
    order_index = Column(Integer, nullable=False)
    title = Column(String(500))
    content_text = Column(Text) # Основной текст главы
    
    # Озвучка (TTS)
    audio_path = Column(String(500))
    audio_duration = Column(Float) # в секундах
    voice_emotions_map = Column(JSONB) # Таймкоды эмоций: {"00:10": "happy", "00:45": "sad"}
    
    document = relationship("Document", back_populates="chapters")

class MangaPage(Base):
    __tablename__ = "manga_pages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    
    page_number = Column(Integer, nullable=False)
    image_url = Column(String(500), nullable=False)
    
    # OCR Данные (Координаты баблов и тексты)
    # Структура: [{"box": [x1, y1, x2, y2], "text": "оригинал", "trans": "перевод"}]
    ocr_bubbles = Column(JSONB) 
    
    document = relationship("Document", back_populates="manga_pages")

# --- ИИ АНАЛИЗ И ОБУЧЕНИЕ ---

class DocumentAnalysis(Base):
    __tablename__ = "document_analysis"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    
    summary_short = Column(String(1000))
    summary_detailed = Column(Text)
    
    # JSONB для быстрого поиска по ключам в Postgres
    characters = Column(JSONB) # Список героев, их описание и роль
    plot_points = Column(JSONB) # Ключевые события
    main_themes = Column(JSONB) # Темы (философия, любовь и т.д.)
    sentiment_analysis = Column(JSONB) # Тональность по главам
    
    ai_model_used = Column(String(50))
    
    document = relationship("Document", back_populates="analysis")

class UserDictionary(Base):
    __tablename__ = "user_dictionaries"
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    
    word = Column(String(255), nullable=False, index=True)
    translation = Column(Text)
    context_sentence = Column(Text) # В каком предложении встретилось
    
    # Для интервальных повторений
    learning_level = Column(Integer, default=0)
    next_review_at = Column(DateTime)
    
    user = relationship("User", back_populates="dictionary")

# --- ФИНАНСЫ, ПРОМО И ЛОГИ ---

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(String(100), primary_key=True) # ID от платежной системы
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="RUB")
    status = Column(String(50)) # success, pending, failed
    provider = Column(String(50)) # stripe, yookassa, robokassa
    
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="payments")

class PromoCode(Base):
    __tablename__ = "promo_codes"
    
    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    discount_percent = Column(Integer, default=0)
    trial_days = Column(Integer, default=0)
    
    max_usages = Column(Integer)
    current_usages = Column(Integer, default=0)
    
    starts_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

class PromoCodeUsage(Base):
    __tablename__ = "promo_code_usages"
    
    id = Column(Integer, primary_key=True)
    promo_id = Column(Integer, ForeignKey("promo_codes.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    used_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="promo_usages")

# --- ПОЛЬЗОВАТЕЛЬСКИЙ ОПЫТ ---

class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    
    current_chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"))
    scroll_offset = Column(Float, default=0.0) # Позиция скролла
    percent_completed = Column(Float, default=0.0)
    
    last_read_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="reading_progress")
    document = relationship("Document", back_populates="reading_progress")

class DocumentNote(Base):
    __tablename__ = "document_notes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"))
    text_anchor = Column(Text) # К какому тексту привязана заметка
    note_content = Column(Text, nullable=False)
    color_tag = Column(String(20)) # Для выделения цветом
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="notes")
    document = relationship("Document", back_populates="notes")

class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    documents = relationship("Document", secondary=document_tags, back_populates="tags")

# --- КЭШ ПЕРЕВОДА ---

class TranslationCache(Base):
    __tablename__ = "translation_cache"
    
    hash = Column(String(64), primary_key=True) # SHA-256 от исходного текста
    source_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    target_lang = Column(String(10), index=True)
    service_name = Column(String(50)) # deepl, gpt4, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

# ИНДЕКСЫ ДЛЯ ПОИСКА (ДЛЯ УСКОРЕНИЯ)
Index('idx_user_email_active', User.email, User.is_active)
Index('idx_doc_title_author', Document.title, Document.author)
