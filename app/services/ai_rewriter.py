import os
import requests
from ..config import settings
from typing import Optional

OPENAI_API_KEY = settings.OPENAI_API_KEY
HF_API_KEY = settings.HF_API_KEY

def rewrite_with_openai(prompt: str, model: str = "gpt-4o-mini", max_tokens: int = 1500) -> str:
    import openai
    openai.api_key = OPENAI_API_KEY
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[{"role":"user","content": prompt}],
        max_tokens=max_tokens,
        temperature=0.8,
    )
    return resp.choices[0].message.content

def rewrite_with_hf(model_id: str, inputs: str) -> str:
    # Uses HuggingFace Inference API (requires HF_API_KEY)
    url = f"https://api-inference.huggingface.co/models/{model_id}"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {"inputs": inputs, "parameters": {"max_new_tokens": 1024, "temperature": 0.7}}
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    out = resp.json()
    # response can be text or list
    if isinstance(out, dict) and "generated_text" in out:
        return out["generated_text"]
    if isinstance(out, list) and len(out) > 0 and "generated_text" in out[0]:
        return out[0]["generated_text"]
    return str(out)

def beautify_translation(text: str, mode: str = "artistic") -> str:
    """
    mode: 'artistic' or 'official'
    Strategy:
      - If OPENAI_API_KEY provided => use OpenAI
      - Else if HF_API_KEY provided => use HF model (e.g. 'bigscience/bloom' or other)
      - Else return input text (fallback)
    """
    prompt = f"""You are an expert editor. Rewrite the following translated text to be a { 'beautiful literary' if mode=='artistic' else 'concise formal business' } translation.
Make the result natural, coherent, preserving meaning, fix logic gaps and avoid abrupt transitions. Output only the rewritten text.

Text:
{text}
"""
    if OPENAI_API_KEY:
        try:
            return rewrite_with_openai(prompt)
        except Exception as e:
            print("OpenAI rewrite failed:", e)
    if HF_API_KEY:
        try:
            # recommend a model like "bigcode/starcoder" or "tiiuae/falcon-7b-instruct" depending on account
            hf_model = "tiiuae/falcon-7b-instruct"  # example; replace if not available
            return rewrite_with_hf(hf_model, prompt)
        except Exception as e:
            print("HF rewrite failed:", e)
    # Fallback naive: return text with minor formatting
    return text.strip()
