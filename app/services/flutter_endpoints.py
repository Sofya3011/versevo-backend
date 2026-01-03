# flutter_endpoints.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import base64
from datetime import datetime
import hashlib
import uuid
import os

from db import get_db
from models import User, Document, Chapter, DocumentNote, ReadingProgress, TranslationCache
import schemas

router = APIRouter(prefix="/api", tags=["flutter"])

# ==================== АВТОРИЗАЦИЯ ====================
@router.post("/auth/register", response_model=schemas.UserResponse)
async def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
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
        auth_token=f"token_{datetime.utcnow().timestamp()}_{uuid.uuid4().hex[:8]}"
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/auth/login", response_model=schemas.UserResponse)
async def login(login_data: schemas.UserLogin, db: Session = Depends(get_db)):
    """Логин пользователя"""
    user = db.query(User).filter(
        (User.email == login_data.email) | (User.username == login_data.email)
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Обновляем токен
    user.auth_token = f"token_{datetime.utcnow().timestamp()}_{uuid.uuid4().hex[:8]}"
    db.commit()
    db.refresh(user)
    
    return user

# ==================== ДОКУМЕНТЫ ====================
@router.get("/documents", response_model=List[schemas.DocumentResponse])
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

@router.post("/documents/upload-base64", response_model=schemas.DocumentResponse)
async def upload_document_base64(
    filename: str = Form(...),
    file_data: str = Form(...),
    file_size: int = Form(...),
    user_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Загрузить документ в формате base64"""
    try:
        # Проверяем пользователя
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Декодируем base64
        content_bytes = base64.b64decode(file_data)
        content = content_bytes.decode('utf-8', errors='ignore')
        
        # Определяем язык (используем твою функцию из main.py)
        from main import detect_language_safe
        language = detect_language_safe(content)
        
        # Определяем главы (используем твою функцию из main.py)
        from main import detect_chapters
        chapters_data = detect_chapters(content)
        
        # Сохраняем файл
        os.makedirs("uploads", exist_ok=True)
        file_extension = filename.split('.')[-1] if '.' in filename else 'txt'
        file_id = str(uuid.uuid4())
        file_path = f"uploads/{file_id}.{file_extension}"
        
        with open(file_path, "wb") as f:
            f.write(content_bytes)
        
        # Создаем документ
        document = Document(
            user_id=user_id,
            filename=filename,
            content=content,
            language=language,
            file_type=file_extension,
            file_size=file_size,
            file_path=file_path,
            word_count=len(content.split()),
            char_count=len(content),
            chapter_count=len(chapters_data),
            reading_time_minutes=max(1, len(content.split()) // 200),
            metadata={
                "uploaded_at": datetime.utcnow().isoformat(),
                "original_filename": filename,
                "user_username": user.username
            }
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Создаем главы
        for idx, chapter_data in enumerate(chapters_data):
            chapter = Chapter(
                document_id=document.id,
                chapter_index=idx,
                title=chapter_data['title'],
                content=chapter_data['content'],
                word_count=len(chapter_data['content'].split())
            )
            db.add(chapter)
        
        db.commit()
        
        return document
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {str(e)}")

@router.get("/documents/{document_id}", response_model=schemas.DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Получить документ по ID"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    return document

@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Удалить документ"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    # Удаляем файл
    if document.file_path and os.path.exists(document.file_path):
        os.remove(document.file_path)
    
    db.delete(document)
    db.commit()
    
    return {"status": "deleted"}

# ==================== ЗАМЕТКИ ====================
@router.post("/notes", response_model=schemas.NoteResponse)
async def create_note(note_data: schemas.NoteCreate, db: Session = Depends(get_db)):
    """Создать заметку или выделение"""
    note = DocumentNote(**note_data.dict())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note

@router.get("/documents/{document_id}/notes", response_model=List[schemas.NoteResponse])
async def get_document_notes(document_id: int, db: Session = Depends(get_db)):
    """Получить заметки документа"""
    notes = db.query(DocumentNote).filter(
        DocumentNote.document_id == document_id
    ).order_by(DocumentNote.created_at.desc()).all()
    
    return notes

@router.delete("/notes/{note_id}")
async def delete_note(note_id: int, db: Session = Depends(get_db)):
    """Удалить заметку"""
    note = db.query(DocumentNote).filter(DocumentNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    
    db.delete(note)
    db.commit()
    
    return {"status": "deleted"}

# ==================== ПРОГРЕСС ====================
@router.post("/progress")
async def save_progress(progress_data: schemas.ProgressCreate, db: Session = Depends(get_db)):
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

@router.get("/documents/{document_id}/progress/{user_id}", response_model=schemas.ProgressResponse)
async def get_progress(document_id: int, user_id: int, db: Session = Depends(get_db)):
    """Получить прогресс чтения"""
    progress = db.query(ReadingProgress).filter(
        ReadingProgress.document_id == document_id,
        ReadingProgress.user_id == user_id
    ).first()
    
    if not progress:
        raise HTTPException(status_code=404, detail="Прогресс не найден")
    
    return progress

# ==================== ПЕРЕВОД ====================
@router.post("/translate/text")
async def translate_text(
    request: schemas.TranslateRequest,
    db: Session = Depends(get_db)
):
    """Перевести текст (с кэшированием)"""
    if not request.text:
        raise HTTPException(status_code=400, detail="Текст не может быть пустым")
    
    # Определяем язык если не указан
    source_lang = request.source_language
    if not source_lang:
        from main import detect_language_safe
        source_lang = detect_language_safe(request.text) or "en"
    
    # Проверяем кэш
    text_hash = hashlib.sha256(
        f"{request.text}|{source_lang}|{request.target_language}".encode()
    ).hexdigest()
    
    cached = db.query(TranslationCache).filter(
        TranslationCache.original_text_hash == text_hash
    ).first()
    
    if cached:
        cached.hit_count += 1
        cached.last_used_at = datetime.utcnow()
        db.commit()
        return {
            "original_text": request.text,
            "translated_text": cached.translated_text,
            "source_language": source_lang,
            "target_language": request.target_language
        }
    
    try:
        # Используем твой существующий переводчик из translator.py
        from translator import translate_text as hf_translate
        translated = await hf_translate(request.text, target_lang=request.target_language)
        
        # Сохраняем в кэш
        cache_entry = TranslationCache(
            original_text_hash=text_hash,
            original_text=request.text[:1000],
            translated_text=translated,
            source_language=source_lang,
            target_language=request.target_language,
            model_used="huggingface"
        )
        db.add(cache_entry)
        db.commit()
        
        return {
            "original_text": request.text,
            "translated_text": translated,
            "source_language": source_lang,
            "target_language": request.target_language
        }
        
    except Exception as e:
        # Fallback - возвращаем оригинал
        return {
            "original_text": request.text,
            "translated_text": f"[Перевод временно недоступен] {request.text}",
            "source_language": source_lang,
            "target_language": request.target_language,
            "error": str(e)
        }

# ==================== ЗДОРОВЬЕ ====================
@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Проверка работоспособности API и БД"""
    try:
        # Проверяем подключение к БД
        db.execute("SELECT 1")
        
        # Получаем статистику
        users_count = db.query(User).count()
        documents_count = db.query(Document).count()
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "statistics": {
                "users": users_count,
                "documents": documents_count
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
