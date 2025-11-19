from TTS.api import TTS
import uuid
from pathlib import Path

def synthesize_speech(text, language="ru"):
    """Озвучка текста через Coqui TTS"""
    try:
        # Инициализируем TTS (Railway установит автоматически)
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        
        # Создаем уникальное имя файла
        filename = f"audio_{uuid.uuid4().hex}.wav"
        output_path = Path("books") / filename
        
        # Генерируем аудио
        tts.tts_to_file(
            text=text,
            language=language,
            file_path=str(output_path)
        )
        
        return str(output_path)
    except Exception as e:
        return f"Ошибка озвучки: {str(e)}"
