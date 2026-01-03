# schemas.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# Аутентификация
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    auth_token: str
    created_at: datetime
    
    class Config:
        from_attributes = True

# Документы
class DocumentCreate(BaseModel):
    user_id: int
    filename: str
    content: Optional[str] = None
    language: str = "en"

class DocumentUpdate(BaseModel):
    translated_content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class DocumentResponse(BaseModel):
    id: int
    user_id: int
    filename: str
    content: Optional[str] = None
    translated_content: Optional[str] = None
    language: str
    file_type: str
    file_size: int
    file_path: Optional[str] = None
    word_count: int
    char_count: int
    chapter_count: int
    reading_time_minutes: int
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Заметки
class NoteCreate(BaseModel):
    document_id: int
    user_id: Optional[int] = None
    chapter_index: int = 0
    note_text: str
    selected_text: Optional[str] = None
    text_position: Optional[int] = None
    color: str = "yellow"
    is_highlight: bool = False

class NoteResponse(BaseModel):
    id: int
    document_id: int
    user_id: Optional[int]
    chapter_index: int
    note_text: str
    selected_text: Optional[str]
    text_position: Optional[int]
    color: str
    is_highlight: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Прогресс
class ProgressCreate(BaseModel):
    document_id: int
    user_id: int
    chapter_index: int = 0
    scroll_position: float = 0.0

# Анализ
class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "full"

class AnalysisResponse(BaseModel):
    summary: str
    themes: str
    sentiment: str
    writing_style: str
    key_points: List[str]
    characters: List[Dict[str, Any]]

# Цитаты
class QuoteCreate(BaseModel):
    user_id: int
    document_id: Optional[int] = None
    quote: str
    start_position: Optional[int] = None
    end_position: Optional[int] = None
    chapter: int = 0
