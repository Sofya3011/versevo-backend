from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import spacy
import nltk
from langdetect import detect, LangDetectError
import requests
import time
import asyncio
from typing import Dict, List, Optional

# Инициализация FastAPI
app = FastAPI(title="Versevo Backend")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация NLP моделей
try:
    nlp = spacy.load("xx_ent_wiki_sm")
except OSError:
    from spacy.cli import download
    download("xx_ent_wiki_sm")
    nlp = spacy.load("xx_ent_wiki_sm")

# Загрузка NLTK данных
def download_nltk_data():
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)

download_nltk_data()

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

class HFTranslationService:
    def __init__(self, api_key: str):
        self.api_key = api_key
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
    
    async def _translate_with_retry(self, text: str, target_lang: str, source_lang: str, max_retries: int = 3) -> str:
        """Повторные попытки перевода"""
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(5 * (attempt + 1))  # Используем asyncio.sleep вместо time.sleep
                
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

# Инициализация сервиса перевода (нужно будет добавить API key в настройки)
# translator = HFTranslationService(api_key="your_hf_api_key_here")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Versevo Backend is running"}

@app.post("/analyze/{document_id}")
async def analyze_document(document_id: int, text: str):
    """Анализ документа"""
    try:
        # Определяем язык
        try:
            language = detect(text)
        except LangDetectError:
            language = "unknown"
        
        # Извлекаем сущности (персонажи)
        doc = nlp(text)
        persons = [ent.text for ent in doc.ents if ent.label_ == "PER"]
        
        # Считаем частотность персонажей
        person_counts = {}
        for person in persons:
            person_counts[person] = person_counts.get(person, 0) + 1
        
        # Простой суммаризатор
        sentences = nltk.sent_tokenize(text)
        summary = " ".join(sentences[:3]) if len(sentences) >= 3 else " ".join(sentences)
        
        return {
            "document_id": document_id,
            "language": language,
            "persons": [{"name": name, "count": count} for name, count in person_counts.items()],
            "summary": summary,
            "wordcloud": f"/static/wordcloud_{document_id}.png",
            "graph": f"/static/graph_{document_id}.png"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/translate/nllb")
async def translate_text(text: str, source: str = "en", target: str = "ru"):
    """Перевод текста через NLLB"""
    try:
        # Конвертируем языковые коды в формат NLLB
        source_nllb = NLLB_LANGUAGES.get(source, "eng_Latn")
        target_nllb = NLLB_LANGUAGES.get(target, "rus_Cyrl")
        
        # Здесь нужно инициализировать translator с реальным API key
        # translated = await translator.translate(text, target_nllb, source_nllb)
        
        # Временный заглушка
        translated = f"[Перевод] {text}"
        
        return {"translated": translated, "source": source, "target": target}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@app.get("/documents")
async def get_documents():
    """Получение списка документов"""
    # Заглушка - нужно подключить базу данных
    return [
        {
            "id": 1,
            "filename": "Пример документа.txt",
            "content": "Это тестовый документ для проверки работы приложения.",
            "language": "ru"
        }
    ]

@app.get("/document/{document_id}")
async def get_document(document_id: int):
    """Получение конкретного документа"""
    # Заглушка - нужно подключить базу данных
    return {
        "id": document_id,
        "filename": f"Документ {document_id}.txt",
        "content": "Содержимое документа...",
        "language": "ru"
    }

# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
