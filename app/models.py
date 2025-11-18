import sqlalchemy as sa
from .db import Base
from datetime import datetime

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