# endpoints.py - ДОБАВЬ ЭТО К ТВОИМ СУЩЕСТВУЮЩИМ ЭНДПОИНТАМ
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import base64
from datetime import datetime
import hashlib
import json

from db import get_db
from models import (
    User, Document, Chapter, DocumentNote, 
    ReadingProgress, TranslationCache, AnalysisResult, FavoriteQuote
)
from schemas import (
    UserCreate, UserLogin, UserResponse,
    DocumentCreate, DocumentResponse, DocumentUpdate,
    NoteCreate, NoteResponse, ProgressCreate,
    AnalysisRequest, QuoteCreate
)

# Создай новый роутер для Flutter API
flutter_router = APIRouter(prefix="/api", tags=["flutter"])

# ==================== АВТОРИЗАЦИЯ ====================
@flutter_router.post("/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Регистрация пользователя"""
    # Проверяем, существует ли пользователь
    existing_user = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="Email или username уже занят")
    
    # Создаем пользователя
    user = User(
        username=user_data.username,
        email=user_data.email,
        auth_token=f"token_{datetime.utcnow().timestamp()}"
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user

@flutter_router.post("/auth/login", response_model=UserResponse)
async def login(login_data: UserLogin, db: Session = Depends(get_db)):
    """Логин пользователя"""
    user = db.query(User).filter(
        (User.email == login_data.email) | (User.username == login_data.email)
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Обновляем токен
    user.auth_token = f"token_{datetime.utcnow().timestamp()}"
    db.commit()
    db.refresh(user)
    
    return user

# ==================== ДОКУМЕНТЫ ====================
@flutter_router.get("/documents", response_model=List[DocumentResponse])
async def get_documents(
    user_id: int,
    skip: int = 0, 
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Получить документы пользователя"""
    documents = db.query(Document).filter(
        Document.user_id == user_id
    ).order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
    
    return documents

@flutter_router.post("/documents/upload-base64", response_model=DocumentResponse)
async def upload_document_base64(
    filename: str = Form(...),
    file_data: str = Form(...),  # Base64 строка
    file_size: int = Form(...),
    user_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Загрузить документ в формате base64"""
    try:
        # Декодируем base64
        content_bytes = base64.b64decode(file_data)
        content = content_bytes.decode('utf-8', errors='ignore')
        
        # Создаем документ
        document = Document(
            user_id=user_id,
            filename=filename,
            content=content,
            file_type=filename.split('.')[-1] if '.' in filename else 'txt',
            file_size=file_size,
            file_path=f"/uploads/{filename}",
            word_count=len(content.split()),
            char_count=len(content),
            chapter_count=1,
            reading_time_minutes=len(content.split()) // 200,
            metadata={
                "uploaded_at": datetime.utcnow().isoformat(),
                "original_filename": filename
            }
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Создаем одну главу
        chapter = Chapter(
            document_id=document.id,
            chapter_index=0,
            title=filename.split('.')[0],
            content=content,
            word_count=document.word_count
        )
        db.add(chapter)
        db.commit()
        
        return document
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

@flutter_router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Получить документ по ID"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    return document

# ==================== ЗАМЕТКИ ====================
@flutter_router.post("/notes", response_model=NoteResponse)
async def create_note(note_data: NoteCreate, db: Session = Depends(get_db)):
    """Создать заметку или выделение"""
    note = DocumentNote(**note_data.dict())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note

@flutter_router.get("/documents/{document_id}/notes", response_model=List[NoteResponse])
async def get_document_notes(document_id: int, db: Session = Depends(get_db)):
    """Получить заметки документа"""
    notes = db.query(DocumentNote).filter(
        DocumentNote.document_id == document_id
    ).order_by(DocumentNote.created_at.desc()).all()
    
    return notes

# ==================== ПРОГРЕСС ====================
@flutter_router.post("/progress")
async def save_progress(progress_data: ProgressCreate, db: Session = Depends(get_db)):
    """Сохранить прогресс чтения"""
    # Ищем существующий прогресс
    progress = db.query(ReadingProgress).filter(
        ReadingProgress.document_id == progress_data.document_id,
        ReadingProgress.user_id == progress_data.user_id
    ).first()
    
    if progress:
        progress.chapter_index = progress_data.chapter_index
        progress.scroll_position = progress_data.scroll_position
        progress.last_read_at = datetime.utcnow()
    else:
        progress = ReadingProgress(**progress_data.dict())
        db.add(progress)
    
    db.commit()
    return {"status": "success"}

@flutter_router.get("/documents/{document_id}/progress/{user_id}")
async def get_progress(document_id: int, user_id: int, db: Session = Depends(get_db)):
    """Получить прогресс чтения"""
    progress = db.query(ReadingProgress).filter(
        ReadingProgress.document_id == document_id,
        ReadingProgress.user_id == user_id
    ).first()
    
    if not progress:
        return {}
    
    return {
        "chapter_index": progress.chapter_index,
        "scroll_position": progress.scroll_position,
        "last_read_at": progress.last_read_at
    }

# ==================== ПЕРЕВОД ====================
@flutter_router.post("/translate/text")
async def translate_text(
    text: str,
    target_language: str = "ru",
    source_language: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Перевести текст (с кэшированием)"""
    if not source_language:
        # Определяем язык
        from services.language_detector import detect_language
        source_language = detect_language(text) or "en"
    
    # Проверяем кэш
    text_hash = hashlib.sha256(
        f"{text}|{source_language}|{target_language}".encode()
    ).hexdigest()
    
    cached = db.query(TranslationCache).filter(
        TranslationCache.original_text_hash == text_hash
    ).first()
    
    if cached:
        cached.hit_count += 1
        cached.last_used_at = datetime.utcnow()
        db.commit()
        return {"translated_text": cached.translated_text}
    
    # Используем твой существующий переводчик
    try:
        from translator import translate_text as hf_translate
        translated = await hf_translate(text, target_lang=target_language)
        
        # Сохраняем в кэш
        cache_entry = TranslationCache(
            original_text_hash=text_hash,
            original_text=text[:1000],  # Сохраняем только начало
            translated_text=translated,
            source_language=source_language,
            target_language=target_language,
            model_used="huggingface"
        )
        db.add(cache_entry)
        db.commit()
        
        return {"translated_text": translated}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка перевода: {str(e)}")

# ==================== АНАЛИЗ ====================
@flutter_router.post("/analyze")
async def analyze_document(analysis_request: AnalysisRequest, db: Session = Depends(get_db)):
    """Проанализировать документ"""
    document = db.query(Document).filter(Document.id == analysis_request.document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    # TODO: Интегрируй с твоим AI анализом
    # Пока возвращаем моковые данные
    analysis = AnalysisResult(
        document_id=analysis_request.document_id,
        summary="Это примерный анализ документа с использованием AI.",
        themes="Технологии, образование, литература",
        sentiment="Позитивный",
        writing_style="Формальный, академический",
        key_points=["Тезис 1", "Тезис 2", "Тезис 3"],
        characters=[{"name": "Автор", "role": "Рассказчик"}]
    )
    
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    
    return analysis

# ==================== ЦИТАТЫ ====================
@flutter_router.post("/quotes/favorites")
async def add_favorite_quote(quote_data: QuoteCreate, db: Session = Depends(get_db)):
    """Добавить цитату в избранное"""
    quote = FavoriteQuote(**quote_data.dict())
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote

@flutter_router.get("/quotes/favorites")
async def get_favorite_quotes(user_id: int, db: Session = Depends(get_db)):
    """Получить избранные цитаты пользователя"""
    quotes = db.query(FavoriteQuote).filter(
        FavoriteQuote.user_id == user_id
    ).order_by(FavoriteQuote.created_at.desc()).all()
    
    return {"quotes": quotes}
