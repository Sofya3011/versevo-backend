import requests
from ..config import settings

def deepl_translate(text: str, target_lang: str = "RU", source_lang: str = None) -> str:
    """
    Использует DeepL API для перевода текста.
    text: входной текст
    target_lang: 'RU', 'EN' и т.д.
    """
    url = settings.DEEPL_API_URL
    params = {
        "auth_key": settings.DEEPL_AUTH_KEY,
        "text": text,
        "target_lang": target_lang
    }
    if source_lang:
        params["source_lang"] = source_lang.upper()
    resp = requests.post(url, data=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    # DeepL возвращает list of translations
    translated = " ".join([t["text"] for t in data.get("translations", [])])
    return translated
