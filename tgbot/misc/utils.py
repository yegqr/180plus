"""
Shared utility functions used across multiple dialog modules.
All functions are pure (no DB/Telegram dependencies) and fully type-annotated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.database.models.questions import Question


def get_question_images(question: "Question") -> list[str]:
    """
    Returns a deduplicated, ordered list of all Telegram file_ids for a question.

    Priority: image_file_id (legacy single-image field) first, then images list.
    Duplicates are removed while preserving insertion order.
    """
    seen: set[str] = set()
    result: list[str] = []

    if question.image_file_id and question.image_file_id not in seen:
        seen.add(question.image_file_id)
        result.append(question.image_file_id)

    for img in (question.images or []):
        if img not in seen:
            seen.add(img)
            result.append(img)

    return result


def build_answer_ui(
    q_type: str,
    correct_answer: dict,
    letters_source: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """
    Returns the three UI element lists needed to render answer widgets:
      choice_variants — list of (label, value) for single-choice buttons
      match_nums      — list of (label, value) for the "number" column of match
      match_letters   — list of (label, value) for the "letter" column of match

    All three are empty lists when a question type doesn't need them.
    This logic was duplicated verbatim in simulation.py and random_mode.py.
    """
    choice_variants: list[tuple[str, str]] = []
    match_nums: list[tuple[str, str]] = []
    match_letters: list[tuple[str, str]] = []

    if q_type == "choice":
        count = int(correct_answer.get("options", 5))
        choice_variants = [(letters_source[i], letters_source[i]) for i in range(count)]

    elif q_type == "match":
        options = str(correct_answer.get("options", "3x5")).lower()
        try:
            n, m = map(int, options.split("x"))
        except (ValueError, AttributeError):
            n, m = 3, 5
        match_nums = [(str(i + 1), str(i + 1)) for i in range(n)]
        match_letters = [(letters_source[i], letters_source[i]) for i in range(m)]

    return choice_variants, match_nums, match_letters


def build_hint_text(q_type: str, active_num: str | None, subject: str) -> str:
    """
    Returns the instructional hint string shown below the question image.
    Duplicated previously in simulation.py and random_mode.py.
    """
    if q_type == "choice":
        return "Обери варіант:"
    if q_type == "match":
        return f"Обери літеру для {active_num}:" if active_num else "Обери цифру:"
    if q_type == "short" and subject == "hist":
        return "✍️ Напиши цифри відповіді (порядок неважливий, наприклад: 123)"
    return "Напиши відповідь у чат:"


def build_wrong_answer_status(
    q_type: str,
    correct_answer: dict,
    user_answer: object,
) -> str:
    """
    Returns an HTML feedback string for an incorrect answer (random-mode review).
    For match: shows each pair with ✅/❌ and the correct letter.
    For other types: shows the correct answer directly.
    """
    if q_type == "match":
        target_pairs = correct_answer.get("pairs", {})
        user_pairs = user_answer if isinstance(user_answer, dict) else {}
        parts: list[str] = []
        for num, correct_letter in sorted(target_pairs.items()):
            user_letter = user_pairs.get(str(num))
            if user_letter == str(correct_letter):
                parts.append(f"<b>{num}-{user_letter}</b> ✅")
            else:
                parts.append(f"<b>{num}-{user_letter or '?'}</b> ❌ (→ {correct_letter})")
        return "😟 <b>Не зовсім правильно:</b>\n" + ", ".join(parts)

    correct = correct_answer.get("answer", "")
    return f"❌ <b>Неправильно.</b> Правильна відповідь: <code>{correct}</code>"


def format_answer_pair(
    q_type: str,
    correct_answer: dict,
    user_ans: object,
) -> tuple[str, str]:
    """
    Returns (user_fmt, correct_fmt) as display strings for answer review.

    Used in both the simulation summary and question-review screens.
    For match questions the pairs are sorted and formatted as "1-А, 2-Б".
    For all other types the raw string value is used.
    """
    if q_type == "match":
        u_fmt = ", ".join(f"{k}-{v}" for k, v in sorted((user_ans or {}).items())) or "немає"
        c_fmt = ", ".join(f"{k}-{v}" for k, v in sorted(correct_answer.get("pairs", {}).items()))
    else:
        u_fmt = str(user_ans) if user_ans is not None else "немає"
        c_fmt = str(correct_answer.get("answer", ""))
    return u_fmt, c_fmt


def format_answer_for_log(user_ans: object) -> str:
    """Converts any user answer to a compact string suitable for DB logging."""
    if isinstance(user_ans, dict):
        return ", ".join(f"{k}-{v}" for k, v in sorted(user_ans.items()))
    return str(user_ans)


def parse_question_caption(caption: str) -> dict:
    """
    Parses an admin photo caption into question metadata.

    Expected format:
        subject | year | session | q_number | q_type | options | answer

    Raises ValueError when the format is invalid.
    Returns a dict with keys:
        subject, year, session, q_number, q_type, correct_answer, weight
    """
    import re

    parts = [p.strip() for p in caption.split("|")]
    if len(parts) != 7:
        raise ValueError(
            f"Expected 7 pipe-separated fields, got {len(parts)}. "
            "Format: subject | year | session | number | type | options | answer"
        )

    subj_str, year_str, sess_str, num_str, type_str, opts_str, ans_str = parts

    from tgbot.misc.constants import SUBJECT_LABELS
    subject = subj_str.lower().strip()
    if subject not in SUBJECT_LABELS:
        raise ValueError(
            f"Unknown subject: {subject!r}. Valid: {', '.join(SUBJECT_LABELS)}"
        )

    q_type = type_str.lower().strip()
    try:
        year = int(year_str)
        q_number = int(num_str)
    except ValueError as exc:
        raise ValueError(f"year and q_number must be integers: {exc}") from exc

    meta: dict = {
        "subject":  subject,
        "year":     year,
        "session":  sess_str.strip(),
        "q_number": q_number,
        "q_type":   q_type,
        "weight":   1,
        "correct_answer": {},
    }

    if q_type == "choice":
        meta["correct_answer"] = {
            "answer":  ans_str.strip().upper(),
            "options": opts_str,
        }
    elif q_type == "short":
        meta["correct_answer"] = {"answer": ans_str.replace(",", ".").strip()}
    elif q_type == "match":
        matches = re.findall(
            r"(\d+)\s*[-]?\s*([а-яА-Яa-zA-ZєЄіІїЇґҐ])", ans_str
        )
        pairs = {num: letter.upper() for num, letter in matches}
        meta["correct_answer"] = {"pairs": pairs, "options": opts_str}
        meta["weight"] = len(pairs)
    else:
        raise ValueError(f"Unknown q_type: {q_type!r}. Expected choice/short/match.")

    return meta
