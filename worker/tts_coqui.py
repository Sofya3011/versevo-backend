import os
import uuid
from pathlib import Path
from ..app.config import settings

# Coqui TTS
try:
    from TTS.api import TTS
except Exception as e:
    TTS = None
    print("TTS import error:", e)

MODEL = os.getenv("COQUI_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")

def synthesize_text_to_wav(text: str, voice: str = None, style: str = None) -> str:
    if TTS is None:
        raise RuntimeError("Coqui TTS is not installed in this environment")
    
    # Initialize TTS - this will download model on first run
    tts = TTS(MODEL)
    
    out_name = f"{uuid.uuid4().hex}.wav"
    out_path = Path(settings.BOOKS_FOLDER) / out_name
    
    # Basic synthesis - you can extend with voice cloning etc.
    tts.tts_to_file(
        text=text,
        file_path=str(out_path),
        speaker_wav=None,  # for voice cloning provide reference audio
        language="ru"  # adjust based on text
    )
    
    return str(out_path)