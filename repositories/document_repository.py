# repositories/document_repository.py
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from models import Document

class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_document(self, user_id: int, **document_data) -> Document:
        """Создание нового документа"""
        document = Document(user_id=user_id, **document_data)
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        return document
    
    async def get_user_documents(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Document]:
        """Получение документов пользователя"""
        result = await self.db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(desc(Document.created_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
    
    async def get_document_by_id(self, document_id: int, user_id: int = None):
        """Получение документа по ID"""
        query = select(Document).where(Document.id == document_id)
        
        if user_id:
            query = query.where(Document.user_id == user_id)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def delete_document(self, document_id: int, user_id: int) -> bool:
        """Удаление документа"""
        document = await self.get_document_by_id(document_id, user_id)
        
        if document:
            await self.db.delete(document)
            await self.db.commit()
            return True
        
        return False
    
    async def get_document_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики документов пользователя"""
        # Общее количество документов
        total_result = await self.db.execute(
            select(func.count(Document.id))
            .where(Document.user_id == user_id)
        )
        total_docs = total_result.scalar() or 0
        
        # Количество документов по языкам
        language_result = await self.db.execute(
            select(Document.language, func.count(Document.id))
            .where(Document.user_id == user_id)
            .group_by(Document.language)
        )
        by_language = dict(language_result.all())
        
        # Общее количество слов
        words_result = await self.db.execute(
            select(func.sum(Document.word_count))
            .where(Document.user_id == user_id)
        )
        total_words = words_result.scalar() or 0
        
        return {
            "total_documents": total_docs,
            "by_language": by_language,
            "total_words": total_words,
            "total_reading_time": total_words // 200
        }
