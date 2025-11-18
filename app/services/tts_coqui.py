import os
from TTS.api import TTS
from ..config import settings
import uuid

# Примечание: модель и параметры можно настраивать
# Убедись, что пакет TTS установлен и модель загружена/скачанa
# Для запуска в Railway может потребоваться выделенный buildpack / docker base image

TTS_MODEL = os.getenv("COQUI_TTS_MODEL", "tts_models/en/vctk/vits")  # примерный ID

def synthesize_text_to_wav(text: str, voice: str = None, style: str = None) -> str:
    """
    Возвращает путь к WAV-файлу.
    """
    # Инициализация (можно инстанцировать глобально для перформанса)
    tts = TTS(TTS_MODEL)
    out_name = f"{uuid.uuid4().hex}.wav"
    out_path = os.path.join(settings.BOOKS_FOLDER, out_name)
    # параметры model_specifics: speaker_idx, style_wav, etc.
    # basic call:
    tts.tts_to_file(text=text, file_path=out_path)
    return out_path
