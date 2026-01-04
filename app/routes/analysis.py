# routes/analysis.py
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import time
from models.analysis import AnalysisRequest
from services.openai_service import OpenAIService
from services.document_service import DocumentService  # Предполагаем, что у тебя есть сервис для документов

router = APIRouter(prefix="/api/analyze", tags=["analysis"])
openai_service = OpenAIService()

@router.post("/document")
async def analyze_document(request: AnalysisRequest) -> Dict[str, Any]:
    """
    Анализ документа через OpenAI
    """
    try:
        print(f"🔍 Начинаем анализ документа {request.document_id}")
        start_time = time.time()
        
        # 1. Получаем документ из БД
        # document = await DocumentService.get_document(request.document_id)
        # content = document.content
        
        # Пока используем тестовый контент
        test_content = """
        Всем известно, что холостой мужчина, обладающий хорошим состоянием, 
        нуждается в жене. Какими бы ни были чувства или взгляды такого человека, 
        это истина настолько прочно укоренилась в умах окружающих семей, 
        что его сразу считают законной собственностью той или иной молодой леди.
        """
        
        # 2. Анализируем через OpenAI
        analysis_result = openai_service.analyze_text(
            text=test_content,
            analysis_type=request.analysis_type
        )
        
        # 3. Добавляем ID документа
        analysis_result["document_id"] = request.document_id
        analysis_result["analysis_type"] = request.analysis_type
        
        processing_time = time.time() - start_time
        print(f"✅ Анализ завершен за {processing_time:.2f} секунд")
        
        return analysis_result
        
    except Exception as e:
        print(f"❌ Ошибка анализа документа: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка анализа: {str(e)}"
        )

@router.post("/text")
async def analyze_raw_text(text: str, analysis_type: str = "full") -> Dict[str, Any]:
    """
    Анализ произвольного текста
    """
    try:
        if not text or len(text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Текст слишком короткий для анализа"
            )
        
        result = openai_service.analyze_text(text, analysis_type)
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка анализа текста: {str(e)}"
        )

@router.get("/quotes/{document_id}")
async def get_document_quotes(document_id: int, limit: int = 5):
    """
    Получить значимые цитаты из документа
    """
    try:
        # Получаем документ
        # document = await DocumentService.get_document(document_id)
        # content = document.content
        
        test_content = """
        Гордость есть общее всем глупцам свойство.
        Человек, который гордится, редко бывает благодарен, 
        ибо он считает, что получает не более, чем ему следует.
        """
        
        quotes = openai_service.extract_quotes(test_content, max_quotes=limit)
        
        return {
            "document_id": document_id,
            "quotes": quotes,
            "count": len(quotes)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка извлечения цитат: {str(e)}"
        )

@router.get("/health")
async def analysis_health():
    """
    Проверка работоспособности сервиса анализа
    """
    try:
        # Тестовый запрос к OpenAI
        test_response = openai_service.analyze_text(
            "Тестовый текст для проверки работы.",
            analysis_type="quick"
        )
        
        return {
            "status": "healthy",
            "openai_available": not test_response.get("fallback", False),
            "model": test_response.get("model_used", "unknown"),
            "timestamp": time.time()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }
