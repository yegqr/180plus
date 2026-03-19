import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-3-flash-preview" # Using 2.0 Flash as per request (closest to 3-preview)
        
    async def generate_explanation(self, image_bytes: bytes | list[bytes], question_text: str = "", subject: str = "math") -> dict:
        """
        Generates explanation AND categorizes the question.
        Returns a dict: {"explanation": str, "categories": list[str]}
        """
        from tgbot.misc.categories import CATEGORIES
        
        # Get categories for this subject
        subj_categories = CATEGORIES.get(subject, {})
        category_prompt = ""
        if subj_categories:
            category_prompt = "ВРАХУЙ ЦІ КАТЕГОРІЇ (може бути декілька):\n"
            for section, cats in subj_categories.items():
                category_prompt += f"--- {section} ---\n"
                for c in cats:
                     category_prompt += f"- {c['slug']}: {c['name']} ({c['desc']})\n"
        
        prompt = (
            f"Question Text: {question_text}\n"
            f"Subject: {subject}\n\n"
            "Ти — крутий викладач. Твій стиль — професіоналізм + гумор. 😎\n"
            "ТВОЄ ЗАВДАННЯ:\n"
            "1. Пояснити розв'язання (Explanation).\n"
            "2. Визначити категорію(ї) завдання (Categories).\n\n"
            
            f"{category_prompt}\n\n"
            
            "ВАЖЛИВО: Поверни ВІДПОВІДЬ ВИКЛЮЧНО У ФОРМАТІ JSON!\n"
            "Приклад JSON:\n"
            "{\n"
            '  "explanation": "Тут текст пояснення з емодзі...",\n'
            '  "categories": ["math_equations", "math_text_problems"]\n'
            "}\n\n"
            
            "Вимоги до пояснення:\n"
            "- Одразу до суті.\n"
            "- ЖОДНОГО Markdown (*, #). Тільки текст та емодзі.\n"
            "- Структура: '🤡 TL;DR', '🚀 Розбір', '🧐 Чому інші - крінж?'\n"
        )

        try:
            import asyncio
            import json
            
            def _sync_generate():
                parts = [types.Part.from_text(text=prompt)]
                if isinstance(image_bytes, list):
                    for img in image_bytes:
                        parts.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))
                else:
                    parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[types.Content(role="user", parts=parts)],
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        response_mime_type="application/json"
                    )
                )
                return response.text

            loop = asyncio.get_running_loop()
            result_text = await loop.run_in_executor(None, _sync_generate)
            
            try:
                # Cleanup json markdown if present
                clean_text = result_text.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_text)
            except:
                logger.error(f"JSON Parse Error: {result_text}")
                return {"explanation": result_text, "categories": []}

        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return {"explanation": "⚠️ Не вдалося згенерувати пояснення.", "categories": []}
