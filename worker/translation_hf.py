import os
import requests
from ..app.config import settings

HF_API = settings.HF_API_KEY
MODEL = "facebook/nllb-200-1.3B"

def translate_nllb(text: str, source_lang: str = None, target_lang: str = "ru"):
    """
    Calls HuggingFace Inference API for translation.
    """
    if not HF_API:
        raise RuntimeError("HF API key not configured")
    
    url = f"https://api-inference.huggingface.co/models/{MODEL}"
    headers = {"Authorization": f"Bearer {HF_API}"}
    
    payload = {
        "inputs": text,
        "parameters": {
            "src_lang": "eng_Latn",  # English
            "tgt_lang": "rus_Cyrl",  # Russian
        },
        "options": {"use_cache": True, "wait_for_model": True}
    }
    
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    out = resp.json()
    
    if isinstance(out, list) and len(out) > 0:
        return out[0].get('translation_text', str(out[0]))
    
    return str(out)