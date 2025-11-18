from .celery_app import celery_app
import time
import os
from pathlib import Path
from ..app.services.extractor import extract_text_from_file
from ..app.config import settings
from .tts_coqui import synthesize_text_to_wav
from .translation_hf import translate_nllb
import boto3
import uuid

# Helper to upload to S3 (or MinIO)
def upload_to_s3(local_path: str, key: str):
    s3_endpoint = settings.S3_ENDPOINT
    s3_key = settings.S3_KEY
    s3_secret = settings.S3_SECRET
    bucket = settings.S3_BUCKET
    s3 = boto3.client("s3",
                      endpoint_url=s3_endpoint if s3_endpoint else None,
                      aws_access_key_id=s3_key,
                      aws_secret_access_key=s3_secret)
    s3.upload_file(local_path, bucket, key)
    # return public URL - adapt for your provider
    base = f"{s3_endpoint.rstrip('/')}/{bucket}" if s3_endpoint else f"https://{bucket}.s3.amazonaws.com"
    return f"{base}/{key}"

@celery_app.task(name="worker.tasks.translate_task", bind=True)
def translate_task(self, payload):
    document_id = payload["document_id"]
    mode = payload.get("mode", "artistic")
    # load doc file path from DB (simple sqlite access)
    from ..app import db, models
    session = db.SessionLocal()
    book = session.query(models.Book).filter(models.Book.id==document_id).first()
    if not book:
        session.close()
        return {"error": "book not found"}
    text = extract_text_from_file(book.file_path, book.file_type)
    session.close()
    # call HF nllb translate (function in translation_hf.py)
    # translate to Russian
    translated = translate_nllb(text, source_lang=None, target_lang="ru")
    # optionally call an LLM editor - skip here
    # save file
    out_name = f"translated_{document_id}_{uuid.uuid4().hex[:8]}.txt"
    out_path = Path(settings.BOOKS_FOLDER) / out_name
    out_path.write_text(translated, encoding="utf-8")
    # upload to S3
    key = f"translations/{out_name}"
    url = upload_to_s3(str(out_path), key)
    return {"status": "done", "url": url}

@celery_app.task(name="worker.tasks.synthesize_task", bind=True)
def synthesize_task(self, payload):
    document_id = payload["document_id"]
    voice = payload.get("voice", "default")
    style = payload.get("style", "neutral")
    from ..app import db, models
    session = db.SessionLocal()
    book = session.query(models.Book).filter(models.Book.id==document_id).first()
    if not book:
        session.close()
        return {"error": "book not found"}
    text = extract_text_from_file(book.file_path, book.file_type)
    session.close()
    # for demo limit text length; for full book split into chapters
    text_to_synth = text[:40000] if len(text) > 40000 else text
    wav_path = synthesize_text_to_wav(text_to_synth, voice=voice, style=style)
    # upload
    key = f"audio/{Path(wav_path).name}"
    url = upload_to_s3(wav_path, key)
    return {"status": "done", "audio_url": url}

@celery_app.task(name="worker.tasks.analyze_task", bind=True)
def analyze_task(self, payload):
    from ..app import db, models
    from ..app.services.analysis import analyze_text
    session = db.SessionLocal()
    book = session.query(models.Book).filter(models.Book.id==payload["document_id"]).first()
    session.close()
    if not book:
        return {"error":"book not found"}
    text = extract_text_from_file(book.file_path, book.file_type)
    result = analyze_text(text, document_id=book.id, lang_hint=book.language)
    # store result to file
    out_name = f"analysis_{book.id}_{uuid.uuid4().hex[:8]}.json"
    out_path = Path(settings.BOOKS_FOLDER) / out_name
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    key = f"analysis/{out_name}"
    # upload to S3 if configured
    try:
        url = upload_to_s3(str(out_path), key)
    except Exception:
        url = f"{settings.BASE_URL}/books/{out_path.name}"
    return {"status":"done", "result_url": url}