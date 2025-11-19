# services/hf_tts_service.py
import requests
import uuid
from pathlib import Path
from ..config import settings

class HFTTSService:
    def __init__(self):
        self.api_key = settings.HF_API_KEY
        self.model = "suno/bark-small"
        self.base_url = "https://api-inference.huggingface.co/models"
    
    async def synthesize(self, text: str, voice: str = "announcer") -> str:
        """Синтез речи через HF Inference API"""
        
        payload = {
            "inputs": text,
            "parameters": {
                "voice_preset": voice  # announcer, narrator, female_soft, etc.
            }
        }
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            response = requests.post(
                f"{self.base_url}/{self.model}",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                # Сохраняем аудио файл
                audio_filename = f"{uuid.uuid4().hex}.wav"
                audio_path = Path(settings.BOOKS_FOLDER) / audio_filename
                
                with open(audio_path, "wb") as f:
                    f.write(response.content)
                
                return f"/books/{audio_filename}"
                
            elif response.status_code == 503:
                # Модель загружается - ждём
                return await self._synthesize_with_retry(text, voice)
            else:
                raise Exception(f"HF API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            raise Exception(f"TTS synthesis failed: {str(e)}")
    
    async def _synthesize_with_retry(self, text: str, voice: str, max_retries: int = 3):
        """Повторные попытки если модель загружается"""
        import time
        
        for attempt in range(max_retries):
            try:
                # Ждём перед повторной попыткой
                time.sleep(10 * (attempt + 1))
                
                payload = {"inputs": text, "parameters": {"voice_preset": voice}}
                headers = {"Authorization": f"Bearer {self.api_key}"}
                
                response = requests.post(
                    f"{self.base_url}/{self.model}",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                
                if response.status_code == 200:
                    audio_filename = f"{uuid.uuid4().hex}.wav"
                    audio_path = Path(settings.BOOKS_FOLDER) / audio_filename
                    
                    with open(audio_path, "wb") as f:
                        f.write(response.content)
                    
                    return f"/books/{audio_filename}"
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"TTS failed after {max_retries} retries: {str(e)}")
        
        raise Exception("Max retries exceeded for TTS")

# Голоса Bark
BARK_VOICES = {
    "announcer": "announcer",        # Диктор
    "narrator": "narrator",          # Рассказчик  
    "female_soft": "v2/en_speaker_6", # Мягкий женский
    "male_deep": "v2/en_speaker_2",   # Глубокий мужской
    "emotional": "v2/en_speaker_9",   # Эмоциональный
}
