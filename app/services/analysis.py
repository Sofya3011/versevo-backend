import os
import re
import json
import requests
from collections import Counter
from typing import List, Dict
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import base64
from io import BytesIO

from ..config import settings

# OpenAI API для крутого анализа
OPENAI_API_KEY = settings.OPENAI_API_KEY

def analyze_with_openai(text: str, prompt: str) -> str:
    """Умный анализ через OpenAI"""
    if not OPENAI_API_KEY:
        return "OpenAI API key not configured"
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "gpt-4",
        "messages": [
            {
                "role": "system", 
                "content": "Ты профессиональный литературный аналитик. Анализируй текст глубоко и точно."
            },
            {
                "role": "user",
                "content": f"{prompt}\n\nТекст для анализа:\n{text[:12000]}"
            }
        ],
        "max_tokens": 2000,
        "temperature": 0.7
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Ошибка анализа: {str(e)}"

def analyze_text(text: str, document_id: int = None, lang_hint: str = None) -> Dict:
    """
    Анализ текста через OpenAI - БЕЗ spacy!
    """
    if not text.strip():
        return {"error": "Текст пустой"}
    
    print("🔍 Начинаем анализ текста через OpenAI...")
    
    try:
        # 1. Краткое содержание
        summary_prompt = "Создай краткое содержание текста на 3-5 предложений."
        summary = analyze_with_openai(text, summary_prompt)
        
        # 2. Персонажи
        characters_prompt = """
        Выдели основных персонажей из текста. Верни в формате JSON:
        {
            "characters": [
                {
                    "name": "имя персонажа", 
                    "role": "роль в сюжете",
                    "importance": "главный/второстепенный"
                }
            ]
        }
        Только JSON.
        """
        characters_result = analyze_with_openai(text, characters_prompt)
        
        # Парсим JSON из ответа
        characters = []
        try:
            json_match = re.search(r'\{.*\}', characters_result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                characters = data.get("characters", [])
        except:
            characters = [{"name": "Не удалось извлечь", "role": "", "importance": ""}]
        
        # 3. Темы
        themes_prompt = "Выдели 3-5 основных тем этого текста."
        themes = analyze_with_openai(text, themes_prompt)
        
        # 4. Тональность
        sentiment_prompt = "Опиши тональность и эмоциональную окраску текста."
        sentiment = analyze_with_openai(text, sentiment_prompt)
        
        # 5. Стиль и язык
        style_prompt = "Проанализируй стиль письма и языковые особенности текста."
        style = analyze_with_openai(text, style_prompt)
        
        # 6. Облако слов
        wordcloud_image = create_wordcloud(text)
        
        result = {
            "summary": summary,
            "characters": characters,
            "themes": themes,
            "sentiment": sentiment,
            "writing_style": style,
            "wordcloud": wordcloud_image,
            "stats": {
                "total_characters": len(text),
                "total_words": len(text.split()),
                "character_count": len(characters)
            },
            "analysis_method": "OpenAI GPT-4"
        }
        
        print("✅ Анализ завершён!")
        return result
        
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}")
        return {"error": f"Ошибка анализа: {str(e)}"}

def create_wordcloud(text: str) -> str:
    """Создание облака слов"""
    try:
        # Очищаем текст
        words = re.findall(r'\b[а-яёa-z]{4,}\b', text.lower())
        filtered_text = ' '.join(words)
        
        # Создаём облако слов
        wordcloud = WordCloud(
            width=800, 
            height=400, 
            background_color='white',
            colormap='viridis',
            max_words=50
        ).generate(filtered_text)
        
        # Сохраняем в base64
        plt.figure(figsize=(10, 5))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis('off')
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{image_base64}"
        
    except Exception as e:
        return f"Ошибка создания облака слов: {str(e)}"
