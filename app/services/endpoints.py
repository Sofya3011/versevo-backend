from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from services.translation_service import TranslationService
from models.document import Document
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translate", tags=["translation"])

# Инициализация сервиса перевода
translation_service = TranslationService()

@router.post("/document")
async def translate_document(
    document_id: int,
    target_language: str = "ru",
    source_language: Optional[str] = None
):
    """
    Перевести весь документ
    """
    try:
        # Получаем документ из БД
        document = await Document.get(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Если исходный язык не указан, определяем автоматически
        if not source_language:
            source_language = await translation_service.detect_language(document.content)
        
        # Выполняем перевод
        translated_content = await translation_service.translate(
            text=document.content,
            source_lang=source_language,
            target_lang=target_language
        )
        
        # Сохраняем перевод в БД
        await Document.update(
            document_id,
            translated_content=translated_content,
            translation_language=target_language
        )
        
        return {
            "document_id": document_id,
            "translated_content": translated_content,
            "source_language": source_language,
            "target_language": target_language,
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@router.post("/text")
async def translate_text(
    text: str,
    target_language: str = "ru",
    source_language: Optional[str] = None
):
    """
    Перевести произвольный текст
    """
    try:
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is required")
        
        if len(text) > 5000:
            raise HTTPException(status_code=400, detail="Text too long (max 5000 chars)")
        
        # Определяем язык если не указан
        if not source_language:
            source_language = await translation_service.detect_language(text)
        
        # Выполняем перевод
        translated_text = await translation_service.translate(
            text=text,
            source_lang=source_language,
            target_lang=target_language
        )
        
        return {
            "original_text": text,
            "translated_text": translated_text,
            "source_language": source_language,
            "target_language": target_language
        }
        
    except Exception as e:
        logger.error(f"Text translation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@router.get("/languages")
async def get_supported_languages():
    """
    Получить список поддерживаемых языков
    """
    return {
        "languages": [
            {"code": "ru", "name": "Russian"},
            {"code": "en", "name": "English"},
            {"code": "de", "name": "German"},
            {"code": "fr", "name": "French"},
            {"code": "es", "name": "Spanish"},
            {"code": "it", "name": "Italian"},
            {"code": "zh", "name": "Chinese"},
            {"code": "ar", "name": "Arabic"},
            {"code": "uk", "name": "Ukrainian"},
            {"code": "pl", "name": "Polish"},
        ]
    }

@router.get("/detect")
async def detect_language(text: str):
    """
    Определить язык текста
    """
    try:
        if not text or len(text.strip()) < 10:
            raise HTTPException(status_code=400, detail="Text too short for detection")
        
        language = await translation_service.detect_language(text)
        
        return {
            "text": text[:100] + "..." if len(text) > 100 else text,
            "detected_language": language,
            "confidence": "high" if len(text) > 50 else "medium"
        }
        
    except Exception as e:
        logger.error(f"Language detection error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")
