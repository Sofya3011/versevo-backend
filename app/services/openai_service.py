# services/openai_service.py
import openai
import os
import json
import time
from typing import Dict, Any
from datetime import datetime

class OpenAIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        openai.api_key = self.api_key
        self.client = openai.OpenAI(api_key=self.api_key)
        
    def analyze_text(self, text: str, analysis_type: str = "full") -> Dict[str, Any]:
        """
        Основной метод анализа текста через OpenAI
        """
        try:
            start_time = time.time()
            
            # Если текст слишком длинный, берем только первые 6000 символов
            if len(text) > 6000:
                text = text[:3000] + "\n...\n" + text[-3000:]
                print(f"⚠️ Текст обрезан до 6000 символов для анализа")
            
            prompt = self._create_prompt(text, analysis_type)
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-1106",  # Можно использовать gpt-4 если нужно
                messages=[
                    {"role": "system", "content": "Ты - эксперт по анализу текстов. Ты говоришь на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=1500
            )
            
            processing_time = time.time() - start_time
            
            # Парсим JSON ответ
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Добавляем метаданные
            result.update({
                "model_used": response.model,
                "processing_time": round(processing_time, 2),
                "token_count": response.usage.total_tokens if hasattr(response, 'usage') else 0,
                "created_at": datetime.now().isoformat()
            })
            
            return result
            
        except openai.RateLimitError:
            print("❌ Rate limit exceeded. Waiting...")
            time.sleep(10)
            return self._get_fallback_response()
        except openai.APIError as e:
            print(f"❌ OpenAI API Error: {e}")
            return self._get_fallback_response()
        except json.JSONDecodeError as e:
            print(f"❌ JSON Parse Error: {e}")
            print(f"Raw response: {content[:200]}...")
            return self._get_fallback_response()
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return self._get_fallback_response()
    
    def _create_prompt(self, text: str, analysis_type: str) -> str:
        """Создаем промпт в зависимости от типа анализа"""
        
        base_prompt = f"""
ПРОАНАЛИЗИРУЙ ЭТОТ ТЕКСТ И ВЕРНИ ОТВЕТ ТОЛЬКО В ФОРМАТЕ JSON:

ТЕКСТ ДЛЯ АНАЛИЗА:
{text}

"""

        if analysis_type == "full":
            prompt = base_prompt + """
ТРЕБУЕМЫЙ ФОРМАТ JSON:
{
  "summary": "Краткое содержание текста (3-4 предложения)",
  "themes": "Основные темы текста через запятую",
  "sentiment": "Общая тональность текста (позитивная, негативная, нейтральная, смешанная)",
  "writing_style": "Стиль письма (формальный, разговорный, академический, художественный и т.д.)",
  "key_points": ["Ключевой момент 1", "Ключевой момент 2", "Ключевой момент 3"],
  "characters": [
    {"name": "Имя персонажа 1", "role": "Роль в тексте", "importance": "высокая/средняя/низкая"},
    {"name": "Имя персонажа 2", "role": "Роль в тексте", "importance": "высокая/средняя/низкая"}
  ]
}

ПРАВИЛА:
1. ВСЕ ответы должны быть НА РУССКОМ языке
2. Если персонажей нет - верни пустой массив
3. Будь точным и объективным
4. Не добавляй никакого текста кроме JSON
"""
        elif analysis_type == "quick":
            prompt = base_prompt + """
ТРЕБУЕМЫЙ ФОРМАТ JSON:
{
  "summary": "Очень краткое содержание (1-2 предложения)",
  "themes": "1-2 основные темы",
  "sentiment": "Тональность"
}
"""
        else:
            prompt = base_prompt + """
ТРЕБУЕМЫЙ ФОРМАТ JSON:
{
  "summary": "Краткое содержание",
  "themes": "Основные темы",
  "sentiment": "Тональность"
}
"""
        
        return prompt
    
    def _get_fallback_response(self) -> Dict[str, Any]:
        """Резервный ответ если OpenAI не работает"""
        return {
            "summary": "Анализ временно недоступен. Используется локальная обработка.",
            "themes": "Тематика не определена",
            "sentiment": "Нейтральная",
            "writing_style": "Не определен",
            "key_points": ["Анализ в процессе разработки"],
            "characters": [],
            "model_used": "fallback",
            "processing_time": 0.1,
            "token_count": 0,
            "created_at": datetime.now().isoformat(),
            "fallback": True
        }
    
    def extract_quotes(self, text: str, max_quotes: int = 5) -> List[str]:
        """Извлекает значимые цитаты из текста"""
        try:
            prompt = f"""
ИЗВЛЕКИ {max_quotes} САМЫХ ЗНАЧИМЫХ ЦИТАТ ИЗ ТЕКСТА:

ТЕКСТ:
{text[:4000]}  # Ограничиваем для экономии токенов

ВЕРНИ ТОЛЬКО JSON В ФОРМАТЕ:
{{
  "quotes": ["Цитата 1", "Цитата 2", "Цитата 3"]
}}

ПРАВИЛА:
1. Цитаты должны быть точными фразами из текста
2. Не изменяй оригинальный текст
3. Выбирай цитаты, которые лучше всего отражают суть
4. Максимум {max_quotes} цитат
"""
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                max_tokens=800
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("quotes", [])
            
        except Exception as e:
            print(f"❌ Ошибка извлечения цитат: {e}")
            return [
                "Цитаты временно недоступны",
                "Попробуйте позже"
            ]
