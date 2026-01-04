# models/analysis.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class AnalysisRequest(BaseModel):
    document_id: int
    analysis_type: str = "full"  # full, quick, themes_only
    language: str = "ru"

class CharacterAnalysis(BaseModel):
    name: str
    role: str
    importance: str  # high, medium, low
    description: Optional[str] = None

class AnalysisResponse(BaseModel):
    document_id: int
    summary: str
    themes: str
    sentiment: str
    writing_style: str
    key_points: List[str]
    characters: List[CharacterAnalysis]
    created_at: datetime
    model_used: str
    processing_time: float
    token_count: int
