import requests

def translate_text(text, target_lang="ru"):
    """Бесплатный перевод через LibreTranslate"""
    try:
        response = requests.post(
            "https://libretranslate.com/translate",
            json={
                "q": text,
                "source": "auto", 
                "target": target_lang,
                "format": "text"
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json()["translatedText"]
        return f"Ошибка перевода"
    except Exception as e:
        return f"Ошибка: {str(e)}"
