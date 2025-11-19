import requests
import os
from typing import Literal

HF_API_KEY = os.getenv("HF_API_KEY")

# Модель NLLB 600M
NLLB_MODEL = "facebook/nllb-200-distilled-600M"

LANG_MAP = {
    "en": "eng_Latn",
    "ru": "rus_Cyrl",
    "de": "deu_Latn",
    "fr": "fra_Latn",
    "es": "spa_Latn",
    "it": "ita_Latn",
    "zh": "zho_Hans",
    "ar": "arb_Arab",
    "uk": "ukr_Cyrl",
    "pl": "pol_Latn",
}

def translate_text_nllb(text: str, source: str, target: str) -> str:
    """
    Перевод текста через HF Inference API.
    HuggingFace сам масштабирует модель, backend не весит больше 700 MB.
    """

    if source not in LANG_MAP or target not in LANG_MAP:
        raise ValueError("Unsupported language code for NLLB")

    payload = {
        "inputs": text,
        "parameters": {
            "src_lang": LANG_MAP[source],
            "tgt_lang": LANG_MAP[target],
            "max_length": 2048
        }
    }

    headers = {
        "Authorization": f"Bearer {HF_API_KEY}"
    }

    response = requests.post(
        f"https://api-inference.huggingface.co/models/{NLLB_MODEL}",
        json=payload,
        headers=headers,
        timeout=120
    )

    if response.status_code != 200:
        raise Exception(f"HF translation error: {response.status_code} {response.text}")

    result = response.json()

    if isinstance(result, list) and "translation_text" in result[0]:
        return result[0]["translation_text"]

    return result
