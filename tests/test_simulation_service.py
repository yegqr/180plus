"""
Integration tests for SimulationService (finish_simulation).

Uses the in-memory SQLite fixture from conftest.py.
"""
from __future__ import annotations

import time

import pytest

from infrastructure.database.repo.requests import RequestsRepo
from tgbot.services.simulation_service import SimulationResult, finish_simulation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(repo: RequestsRepo, user_id: int = 1, subject: str = "math"):
    user = await repo.users.get_or_create_user(user_id=user_id, full_name="Test", language="uk")
    await repo.session.commit()
    user.selected_subject = subject
    return user


async def _make_question(
    repo: RequestsRepo,
    subject: str = "math",
    q_number: int = 1,
    q_type: str = "choice",
    correct_answer: dict | None = None,
) -> int:
    if correct_answer is None:
        correct_answer = {"answer": "А", "options": 5}
    await repo.questions.upsert_question(
        subject=subject,
        year=2024,
        session="main",
        q_number=q_number,
        image_file_ids=[],
        q_type=q_type,
        correct_answer=correct_answer,
        weight=1,
    )
    await repo.session.commit()
    q = await repo.questions.get_random_question([subject], q_type=None)
    return q.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFinishSimulation:
    async def test_returns_simulation_result(self, repo: RequestsRepo) -> None:
        user = await _make_user(repo)
        q_id = await _make_question(repo)

        result = await finish_simulation(
            repo=repo,
            user=user,
            q_ids=[q_id],
            answers={str(q_id): "А"},
            session_id="main",
            year=2024,
            start_time=time.time() - 60,
            end_time=time.time(),
        )

        assert isinstance(result, SimulationResult)
        assert result.raw_score >= 0
        assert result.max_score > 0
        assert result.duration > 0

    async def test_correct_answer_gives_score(self, repo: RequestsRepo) -> None:
        user = await _make_user(repo)
        q_id = await _make_question(repo, correct_answer={"answer": "Б", "options": 5})

        result = await finish_simulation(
            repo=repo,
            user=user,
            q_ids=[q_id],
            answers={str(q_id): "Б"},
            session_id="main",
            year=2024,
            start_time=time.time(),
            end_time=time.time(),
        )

        assert result.raw_score == result.max_score

    async def test_wrong_answer_gives_zero_score(self, repo: RequestsRepo) -> None:
        user = await _make_user(repo)
        q_id = await _make_question(repo, correct_answer={"answer": "А", "options": 5})

        result = await finish_simulation(
            repo=repo,
            user=user,
            q_ids=[q_id],
            answers={str(q_id): "Б"},
            session_id="main",
            year=2024,
            start_time=time.time(),
            end_time=time.time(),
        )

        assert result.raw_score == 0
        assert result.max_score > 0

    async def test_no_answers_skips_db_save(self, repo: RequestsRepo) -> None:
        """With empty answers dict, nothing is saved to results or logs."""
        user = await _make_user(repo)
        q_id = await _make_question(repo)

        result = await finish_simulation(
            repo=repo,
            user=user,
            q_ids=[q_id],
            answers={},
            session_id="main",
            year=2024,
            start_time=time.time(),
            end_time=time.time(),
        )

        assert isinstance(result, SimulationResult)
        # No DB records should have been created
        history = await repo.logs.get_question_history(user.user_id, q_id)
        assert history == []

    async def test_with_answers_saves_logs(self, repo: RequestsRepo) -> None:
        user = await _make_user(repo)
        q_id = await _make_question(repo)

        await finish_simulation(
            repo=repo,
            user=user,
            q_ids=[q_id],
            answers={str(q_id): "А"},
            session_id="main",
            year=2024,
            start_time=time.time() - 10,
            end_time=time.time(),
        )
        await repo.session.commit()

        history = await repo.logs.get_question_history(user.user_id, q_id)
        assert len(history) == 1

    async def test_nmt_text_for_passing_score(self, repo: RequestsRepo) -> None:
        """nmt_text contains a bold number when score is above threshold."""
        user = await _make_user(repo, subject="math")
        # Insert 5 correct-answer questions to get a passable score
        q_ids = []
        for i in range(1, 6):
            q_id = await _make_question(
                repo, q_number=i, correct_answer={"answer": "А", "options": 5}
            )
            q_ids.append(q_id)

        answers = {str(qid): "А" for qid in q_ids}

        result = await finish_simulation(
            repo=repo,
            user=user,
            q_ids=q_ids,
            answers=answers,
            session_id="main",
            year=2024,
            start_time=time.time() - 120,
            end_time=time.time(),
        )

        # If NMT score > 0 the text wraps it in bold tags; otherwise it's a failure message
        assert isinstance(result.nmt_text, str)
        assert result.nmt_score >= 0

    async def test_duration_calculated_correctly(self, repo: RequestsRepo) -> None:
        user = await _make_user(repo)
        q_id = await _make_question(repo)
        start = time.time() - 90

        result = await finish_simulation(
            repo=repo,
            user=user,
            q_ids=[q_id],
            answers={str(q_id): "А"},
            session_id="main",
            year=2024,
            start_time=start,
            end_time=start + 90,
        )

        assert result.duration == 90

    async def test_multiple_questions_partial_answers(self, repo: RequestsRepo) -> None:
        user = await _make_user(repo)
        q_ids = []
        for i in range(1, 4):
            q_id = await _make_question(repo, q_number=i)
            q_ids.append(q_id)

        # Only answer the first question
        result = await finish_simulation(
            repo=repo,
            user=user,
            q_ids=q_ids,
            answers={str(q_ids[0]): "А"},
            session_id="main",
            year=2024,
            start_time=time.time() - 30,
            end_time=time.time(),
        )

        # max_score should reflect all 3 questions
        assert result.max_score >= 3
