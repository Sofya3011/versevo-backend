# services/hf_translation_service.py
import requests
from ..config import settings

class HFTranslationService:
    def __init__(self):
        self.api_key = settings.HF_API_KEY
        self.model = "facebook/nllb-200-3.3B"  # Качественный перевод
    
    async def translate(self, text: str, target_lang: str = "rus_Cyrl", source_lang: str = "eng_Latn") -> str:
        """Перевод через HF NLLB"""
        
        payload = {
            "inputs": text,
            "parameters": {
                "src_lang": source_lang,
                "tgt_lang": target_lang
            }
        }
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            response = requests.post(
                f"https://api-inference.huggingface.co/models/{self.model}",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                return result[0]['translation_text']
            else:
                raise Exception(f"Translation API error: {response.status_code}")
                
        except Exception as e:
            raise Exception(f"Translation failed: {str(e)}")

# Языковые коды NLLB
NLLB_LANGUAGES = {
    "russian": "rus_Cyrl",
    "english": "eng_Latn", 
    "french": "fra_Latn",
    "german": "deu_Latn",
    "spanish": "spa_Latn",
    "chinese": "zho_Hans",
}
