import requests
import time
from ..config import settings

class HFTranslationService:
    def __init__(self):
        self.api_key = settings.HF_API_KEY
        self.model = "facebook/nllb-200-3.3B"
    
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
            elif response.status_code == 503:
                return await self._translate_with_retry(text, target_lang, source_lang)
            else:
                raise Exception(f"Translation API error: {response.status_code}")
                
        except Exception as e:
            raise Exception(f"Translation failed: {str(e)}")
    
    async def _translate_with_retry(self, text: str, target_lang: str, source_lang: str, max_retries: int = 3):
        """Повторные попытки перевода"""
        for attempt in range(max_retries):
            try:
                time.sleep(5 * (attempt + 1))
                
                payload = {
                    "inputs": text,
                    "parameters": {
                        "src_lang": source_lang,
                        "tgt_lang": target_lang
                    }
                }
                
                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = requests.post(
                    f"https://api-inference.huggingface.co/models/{self.model}",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result[0]['translation_text']
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"Translation failed after {max_retries} retries: {str(e)}")
        
        raise Exception("Max retries exceeded for translation")

# Языковые коды NLLB
NLLB_LANGUAGES = {
    "russian": "rus_Cyrl",
    "english": "eng_Latn", 
    "french": "fra_Latn",
    "german": "deu_Latn",
    "spanish": "spa_Latn",
    "chinese": "zho_Hans",
    "japanese": "jpn_Jpan",
    "korean": "kor_Hang",
    "arabic": "arb_Arab",
    "hindi": "hin_Deva"
}
