"""
SimulationService — encapsulates scoring and DB persistence for simulation finish.

Separates business logic from the aiogram-dialog handler so it can be
tested and reused without a full dialog context.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from infrastructure.database.models import User
from infrastructure.database.repo.requests import RequestsRepo
from tgbot.misc.nmt_scoring import get_nmt_score
from tgbot.services.scoring import score_simulation


@dataclass
class SimulationResult:
    raw_score: int
    max_score: int
    nmt_score: int
    nmt_text: str
    duration: int


async def finish_simulation(
    repo: RequestsRepo,
    user: User,
    q_ids: list,
    answers: dict,
    session_id: str,
    year: int,
    start_time: float,
    end_time: float,
) -> SimulationResult:
    """
    Scores the simulation, persists results and action logs to DB.

    Does NOT commit — the caller (middleware) owns the transaction.
    Returns a SimulationResult with all display-ready values.
    """
    subject = user.selected_subject

    questions_data = await _load_questions_data(repo, q_ids)
    sim_result = score_simulation(questions_data, answers, subject, session_id, user.user_id)

    duration = int(end_time - start_time)
    nmt_val = get_nmt_score(subject, sim_result.total_score, max_possible=sim_result.total_max)
    nmt_score = nmt_val or 0
    nmt_text = f"<b>{nmt_score}</b>" if nmt_val else "Не склав (менше 100)"

    if answers:
        await repo.results.save_result(
            user_id=user.user_id,
            subject=subject,
            year=year,
            session_name=session_id,
            raw_score=sim_result.total_score,
            nmt_score=nmt_score,
            duration=duration,
        )
        if sim_result.logs_data:
            await repo.logs.add_logs_batch(sim_result.logs_data)

    return SimulationResult(
        raw_score=sim_result.total_score,
        max_score=sim_result.total_max,
        nmt_score=nmt_score,
        nmt_text=nmt_text,
        duration=duration,
    )


async def _load_questions_data(repo: RequestsRepo, q_ids: list) -> list[dict]:
    """Batch-fetches questions and returns scoring-ready dicts."""
    int_ids = [int(q) for q in q_ids]
    questions = await repo.questions.get_questions_by_ids(int_ids)
    return [
        {
            "id": q.id,
            "q_number": q.q_number,
            "q_type": q.q_type,
            "correct_answer": q.correct_answer,
        }
        for q in questions
    ]
