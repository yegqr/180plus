from __future__ import annotations

import asyncio
import json
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_EMPTY_RESULT: dict = {"explanation": "⚠️ Не вдалося згенерувати пояснення.", "categories": []}


def _build_category_prompt(subj_categories: dict) -> str:
    """Formats the subject's category list into a prompt block."""
    if not subj_categories:
        return ""
    lines = ["ВРАХУЙ ЦІ КАТЕГОРІЇ (може бути декілька):"]
    for section, cats in subj_categories.items():
        lines.append(f"--- {section} ---")
        for c in cats:
            lines.append(f"- {c['slug']}: {c['name']} ({c['desc']})")
    return "\n".join(lines)


def _build_parts(prompt: str, image_bytes: bytes | list[bytes]) -> list:
    """Assembles the Gemini Content parts list from a prompt and one or more images."""
    parts = [types.Part.from_text(text=prompt)]
    images = image_bytes if isinstance(image_bytes, list) else [image_bytes]
    for img in images:
        parts.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))
    return parts


class GeminiService:
    def __init__(self, api_key: str) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-3-flash-preview"

    async def generate_explanation(
        self,
        image_bytes: bytes | list[bytes],
        question_text: str = "",
        subject: str = "math",
    ) -> dict:
        """Generates an explanation and category tags for a question image.

        Returns a dict: {"explanation": str, "categories": list[str]}
        """
        from tgbot.misc.categories import CATEGORIES

        subj_categories = CATEGORIES.get(subject, {})
        category_prompt = _build_category_prompt(subj_categories)

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
            parts = _build_parts(prompt, image_bytes)

            def _sync_generate() -> str:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[types.Content(role="user", parts=parts)],
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        response_mime_type="application/json",
                    ),
                )
                return response.text

            result_text = await asyncio.get_running_loop().run_in_executor(None, _sync_generate)

            clean = result_text.replace("```json", "").replace("```", "").strip()
            try:
                return json.loads(clean)
            except (json.JSONDecodeError, ValueError):
                logger.error(f"JSON Parse Error: {result_text}")
                return {"explanation": result_text, "categories": []}

        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return _EMPTY_RESULT
