"""
Pure scoring functions for NMT question types.

All functions are framework-agnostic:
  - no Telegram/aiogram imports
  - no database imports
  - no async — fully synchronous and instantly testable

These functions are the single source of truth for answer evaluation.
Both the Telegram dialog layer and the future REST API layer call these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnswerResult:
    """Scoring result for a single question."""
    points_earned: int
    max_points: int
    is_correct: bool        # True only when full credit awarded


@dataclass
class SimulationScore:
    """Aggregate result of a full simulation session."""
    total_score: int
    total_max: int
    logs_data: list[dict] = field(default_factory=list)
    """List of dicts ready to pass to repo.logs.add_logs_batch()."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compare_float(user: str, correct: str) -> bool:
    """Returns True when both strings represent the same float value."""
    try:
        return float(user.replace(",", ".")) == float(correct.replace(",", "."))
    except (ValueError, AttributeError):
        return False


def _compare_digits_flexible(user: str, correct: str) -> bool:
    """
    Flexible digit comparison for mova/eng/hist short answers.
    Treats the answer as a set of digits (order-independent).
    """
    if user.isdigit() and correct.isdigit():
        return sorted(user) == sorted(correct)
    return False


# ---------------------------------------------------------------------------
# Simulation scoring  (used by simulation.py)
# ---------------------------------------------------------------------------

def check_simulation_answer(
    q_type: str,
    q_number: int,
    correct_answer: dict[str, Any],
    user_answer: Any,
    subject: str,
) -> AnswerResult:
    """
    Scores a single answer according to official NMT simulation rules.

    History has special per-question-number scoring:
      - Q 1-20:  choice    (1 pt)
      - Q 21-24: match     (4 pts, 1 per pair)
      - Q 25-27: sequence  (3 pts, 1 per digit in correct position)
      - Q 28-30: cluster   (3 pts, intersection of digit sets)

    All other subjects:
      - choice: 1 pt
      - short:  2 pts
      - match:  1 pt per matched pair
    """
    if subject == "hist":
        return _score_history(q_type, q_number, correct_answer, user_answer)
    return _score_standard(q_type, correct_answer, user_answer, subject)


def _score_history(
    q_type: str,
    q_number: int,
    correct_answer: dict,
    user_answer: Any,
) -> AnswerResult:
    num = q_number

    if 1 <= num <= 20:
        q_max = 1
        c_ans = str(correct_answer.get("answer", "")).strip().upper()
        pts = 1 if (user_answer and str(user_answer).strip().upper() == c_ans) else 0
        return AnswerResult(pts, q_max, pts == q_max)

    if 21 <= num <= 24:
        q_max = 4
        target = correct_answer.get("pairs", {})
        pts = 0
        if isinstance(user_answer, dict):
            for k, v in user_answer.items():
                if target.get(str(k)) == str(v):
                    pts += 1
        return AnswerResult(pts, q_max, pts == q_max)

    if 25 <= num <= 30:
        q_max = 3
        pts = 0
        if user_answer:
            if isinstance(user_answer, dict):
                target = correct_answer.get("pairs", {})
                for k, v in user_answer.items():
                    if target.get(str(k)) == str(v):
                        pts += 1
                pts = min(3, pts)
            else:
                c_str = str(correct_answer.get("answer", ""))
                c_digits = [c for c in c_str if c.isdigit()]
                if not c_digits and "pairs" in correct_answer:
                    c_digits = [
                        str(k) for k in sorted(correct_answer["pairs"].keys())
                        if str(k).isdigit()
                    ]
                u_digits = [c for c in str(user_answer) if c.isdigit()]

                if 25 <= num <= 27:
                    # Sequence: 1 pt per digit in the correct position
                    for i in range(min(len(u_digits), len(c_digits))):
                        if u_digits[i] == c_digits[i]:
                            pts += 1
                else:
                    # Cluster (28-30): intersection of digit sets
                    pts = len(set(c_digits) & set(u_digits))

        return AnswerResult(pts, q_max, pts == q_max)

    # Fallback for unexpected question numbers
    q_max = 1
    pts = 1 if (user_answer and str(user_answer).strip() ==
                str(correct_answer.get("answer", "")).strip()) else 0
    return AnswerResult(pts, q_max, pts == q_max)


def _score_standard(
    q_type: str,
    correct_answer: dict,
    user_answer: Any,
    subject: str,
) -> AnswerResult:
    if q_type == "choice":
        q_max = 1
        if user_answer and (
            str(user_answer).strip().upper() ==
            str(correct_answer.get("answer", "")).strip().upper()
        ):
            return AnswerResult(1, q_max, True)
        return AnswerResult(0, q_max, False)

    if q_type == "short":
        q_max = 2
        if not user_answer:
            return AnswerResult(0, q_max, False)

        u_str = str(user_answer).strip()
        c_str = str(correct_answer.get("answer", "")).strip()

        is_correct = _compare_float(u_str, c_str) or u_str == c_str
        if not is_correct and subject in ("mova", "eng"):
            is_correct = _compare_digits_flexible(u_str, c_str)

        pts = q_max if is_correct else 0
        return AnswerResult(pts, q_max, is_correct)

    if q_type == "match":
        target = correct_answer.get("pairs", {})
        q_max = len(target)
        pts = 0
        if isinstance(user_answer, dict):
            for n, ltr in user_answer.items():
                if target.get(str(n)) == str(ltr):
                    pts += 1
        return AnswerResult(pts, q_max, pts == q_max)

    # Unknown type — treat as unanswered
    return AnswerResult(0, 0, False)


# ---------------------------------------------------------------------------
# Random-mode scoring  (used by random_mode.py)
# ---------------------------------------------------------------------------

def check_random_answer(
    q_type: str,
    correct_answer: dict[str, Any],
    user_answer: Any,
    subject: str,
) -> AnswerResult:
    """
    Scores a single answer in random-practice mode.

    Differences from simulation scoring:
      - No question-number-based special cases.
      - History short answers award 3 pts (not 2).
      - Match is fully-correct-only for is_correct flag (partial pts still returned).
    """
    if q_type == "choice":
        q_max = 1
        if user_answer and (
            str(user_answer).strip().upper() ==
            str(correct_answer.get("answer", "")).strip().upper()
        ):
            return AnswerResult(1, q_max, True)
        return AnswerResult(0, q_max, False)

    if q_type == "short":
        q_max = 3 if subject == "hist" else 2
        if not user_answer:
            return AnswerResult(0, q_max, False)

        u_str = str(user_answer).strip()
        c_str = str(correct_answer.get("answer", "")).strip()

        is_correct = _compare_float(u_str, c_str) or u_str == c_str
        if not is_correct and subject in ("hist", "mova", "eng"):
            is_correct = _compare_digits_flexible(u_str, c_str)

        pts = q_max if is_correct else 0
        return AnswerResult(pts, q_max, is_correct)

    if q_type == "match":
        target = correct_answer.get("pairs", {})
        q_max = len(target)
        pts = 0
        if isinstance(user_answer, dict):
            for n, ltr in target.items():
                if user_answer.get(str(n)) == str(ltr):
                    pts += 1
        is_correct = pts == q_max
        return AnswerResult(pts, q_max, is_correct)

    return AnswerResult(0, 0, False)


# ---------------------------------------------------------------------------
# Correctness check for display (summary / review views)
# ---------------------------------------------------------------------------

def is_answer_correct_for_display(
    q_type: str,
    correct_answer: dict[str, Any],
    user_answer: Any,
    subject: str,
) -> bool:
    """
    Simplified correctness check used for the summary error list and review view.
    Returns True only when the answer is fully correct.
    """
    if q_type == "choice":
        return bool(user_answer) and (
            str(user_answer).strip().upper() ==
            str(correct_answer.get("answer", "")).strip().upper()
        )

    if q_type == "short":
        if not user_answer:
            return False
        u_str = str(user_answer).strip()
        c_str = str(correct_answer.get("answer", "")).strip()
        ok = _compare_float(u_str, c_str) or u_str == c_str
        if not ok and subject in ("hist", "mova", "eng"):
            ok = _compare_digits_flexible(u_str, c_str)
        return ok

    if q_type == "match":
        target = correct_answer.get("pairs", {})
        if not isinstance(user_answer, dict) or len(user_answer) != len(target):
            return False
        return all(target.get(k) == v for k, v in user_answer.items())

    return False


# ---------------------------------------------------------------------------
# Full simulation scoring (used by simulation.py on_finish)
# ---------------------------------------------------------------------------

def score_simulation(
    questions_data: list[dict[str, Any]],
    answers: dict[str, Any],
    subject: str,
    session_id: str,
    user_id: int,
) -> SimulationScore:
    """
    Scores an entire simulation session.

    Args:
        questions_data: list of dicts, each with keys:
            id, q_number, q_type, correct_answer
        answers: mapping of str(q_id) → user_answer
        subject: subject slug (e.g. "math", "hist")
        session_id: session name string (stored in logs)
        user_id: Telegram user ID (stored in logs)

    Returns:
        SimulationScore with total_score, total_max, and logs_data ready for DB.
    """
    total_score = 0
    total_max = 0
    logs_data: list[dict] = []

    for q_data in questions_data:
        q_id = q_data["id"]
        user_ans = answers.get(str(q_id))
        result = check_simulation_answer(
            q_type=q_data["q_type"],
            q_number=q_data["q_number"],
            correct_answer=q_data["correct_answer"],
            user_answer=user_ans,
            subject=subject,
        )

        total_score += result.points_earned
        total_max += result.max_points

        if user_ans is not None:
            log_ans = (
                ", ".join(f"{k}-{v}" for k, v in sorted(user_ans.items()))
                if isinstance(user_ans, dict)
                else str(user_ans)
            )
            logs_data.append({
                "user_id":     user_id,
                "question_id": q_id,
                "answer":      log_ans,
                "is_correct":  result.is_correct,
                "mode":        "simulation",
                "session_id":  session_id,
            })

    return SimulationScore(
        total_score=total_score,
        total_max=total_max,
        logs_data=logs_data,
    )
