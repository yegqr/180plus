"""
Integration tests for repository layer.

Uses the in-memory SQLite fixture from conftest.py.
Tests verify actual SQL query behaviour, not just function signatures.
"""

from __future__ import annotations

import pytest

from infrastructure.database.repo.requests import RequestsRepo


# ===========================================================================
# UserRepo
# ===========================================================================

class TestUserRepo:
    async def test_create_new_user(self, repo: RequestsRepo) -> None:
        user = await repo.users.get_or_create_user(
            user_id=100, full_name="Alice", language="uk"
        )
        await repo.session.commit()
        assert user.user_id == 100
        assert user.full_name == "Alice"
        assert user.is_admin is False

    async def test_create_returns_existing_on_conflict(self, repo: RequestsRepo) -> None:
        await repo.users.get_or_create_user(user_id=200, full_name="Bob", language="uk")
        await repo.session.commit()
        user2 = await repo.users.get_or_create_user(
            user_id=200, full_name="Bob Updated", language="uk"
        )
        await repo.session.commit()
        assert user2.user_id == 200
        assert user2.full_name == "Bob Updated"

    async def test_get_user_by_id_existing(self, repo: RequestsRepo) -> None:
        await repo.users.get_or_create_user(user_id=300, full_name="Carol", language="en")
        await repo.session.commit()
        user = await repo.users.get_user_by_id(300)
        assert user is not None
        assert user.full_name == "Carol"

    async def test_get_user_by_id_missing(self, repo: RequestsRepo) -> None:
        user = await repo.users.get_user_by_id(99999)
        assert user is None

    async def test_promote_and_demote_admin(self, repo: RequestsRepo) -> None:
        await repo.users.get_or_create_user(user_id=400, full_name="Dave", language="uk")
        await repo.session.commit()
        await repo.users.promote_admin(400)
        await repo.session.commit()
        user = await repo.users.get_user_by_id(400)
        assert user.is_admin is True
        await repo.users.demote_admin(400)
        await repo.session.commit()
        user = await repo.users.get_user_by_id(400)
        assert user.is_admin is False

    async def test_update_user_settings(self, repo: RequestsRepo) -> None:
        await repo.users.get_or_create_user(user_id=500, full_name="Eve", language="uk")
        await repo.session.commit()
        await repo.users.update_user_settings(500, {"topic_ids": {"math": 1}})
        await repo.session.commit()
        user = await repo.users.get_user_by_id(500)
        assert user.settings == {"topic_ids": {"math": 1}}

    async def test_update_daily_sub(self, repo: RequestsRepo) -> None:
        await repo.users.get_or_create_user(user_id=600, full_name="Frank", language="uk")
        await repo.session.commit()
        await repo.users.update_daily_sub(600, False)
        await repo.session.commit()
        user = await repo.users.get_user_by_id(600)
        assert user.daily_sub is False

    async def test_admin_flag_from_constructor(self, repo: RequestsRepo) -> None:
        user = await repo.users.get_or_create_user(
            user_id=700, full_name="Admin", language="uk", is_admin=True
        )
        await repo.session.commit()
        assert user.is_admin is True


# ===========================================================================
# SettingsRepo
# ===========================================================================

class TestSettingsRepo:
    async def test_get_setting_default(self, repo: RequestsRepo) -> None:
        val = await repo.settings.get_setting("nonexistent_key", "default_val")
        assert val == "default_val"

    async def test_set_and_get_setting(self, repo: RequestsRepo) -> None:
        await repo.settings.set_setting("my_key", "my_value")
        await repo.session.commit()
        val = await repo.settings.get_setting("my_key")
        assert val == "my_value"

    async def test_set_setting_overwrites(self, repo: RequestsRepo) -> None:
        await repo.settings.set_setting("update_key", "v1")
        await repo.session.commit()
        await repo.settings.set_setting("update_key", "v2")
        await repo.session.commit()
        val = await repo.settings.get_setting("update_key")
        assert val == "v2"

    async def test_get_missing_key_returns_none(self, repo: RequestsRepo) -> None:
        val = await repo.settings.get_setting("missing")
        assert val is None


# ===========================================================================
# QuestionRepo
# ===========================================================================

class TestQuestionRepo:
    async def _insert_question(
        self, repo: RequestsRepo, subject: str = "math", q_number: int = 1
    ) -> None:
        await repo.questions.upsert_question(
            subject=subject,
            year=2024,
            session="main",
            q_number=q_number,
            image_file_ids=["file123"],
            q_type="choice",
            correct_answer={"answer": "А", "options": 5},
            weight=1,
        )
        await repo.session.commit()

    async def test_upsert_creates_question(self, repo: RequestsRepo) -> None:
        await self._insert_question(repo)
        q = await repo.questions.get_random_question(["math"])
        assert q is not None
        assert q.subject == "math"

    async def test_upsert_updates_existing(self, repo: RequestsRepo) -> None:
        await self._insert_question(repo)
        await repo.questions.upsert_question(
            subject="math", year=2024, session="main", q_number=1,
            image_file_ids=["new_file"], q_type="short",
            correct_answer={"answer": "42"}, weight=2,
        )
        await repo.session.commit()
        q = await repo.questions.get_random_question(["math"], q_type=None)
        assert q.q_type == "short"

    async def test_get_questions_by_ids_batch(self, repo: RequestsRepo) -> None:
        for i in range(1, 4):
            await self._insert_question(repo, q_number=i)
        all_qs = await repo.questions.get_questions_by_ids([1, 2, 3])
        assert len(all_qs) == 3

    async def test_get_questions_by_ids_empty(self, repo: RequestsRepo) -> None:
        result = await repo.questions.get_questions_by_ids([])
        assert result == []

    async def test_get_unique_years(self, repo: RequestsRepo) -> None:
        await self._insert_question(repo)
        years = await repo.questions.get_unique_years("math")
        assert 2024 in years

    async def test_delete_question(self, repo: RequestsRepo) -> None:
        await self._insert_question(repo)
        q = await repo.questions.get_random_question(["math"])
        assert q is not None
        await repo.questions.delete_question(q.id)
        await repo.session.commit()
        q_after = await repo.questions.get_question_by_id(q.id)
        assert q_after is None

    async def test_update_explanation(self, repo: RequestsRepo) -> None:
        await self._insert_question(repo)
        q = await repo.questions.get_random_question(["math"])
        await repo.questions.update_explanation(q.id, "Test explanation")
        await repo.session.commit()
        q_updated = await repo.questions.get_question_by_id(q.id)
        assert q_updated.explanation == "Test explanation"


# ===========================================================================
# LogsRepo
# ===========================================================================

class TestLogsRepo:
    async def _setup_user(self, repo: RequestsRepo, user_id: int = 1) -> None:
        await repo.users.get_or_create_user(user_id=user_id, full_name="Test", language="uk")
        await repo.session.commit()

    async def test_add_log(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.logs.add_log(
            user_id=1, question_id=10, answer="А", is_correct=True, mode="random"
        )
        await repo.session.commit()
        history = await repo.logs.get_question_history(1, 10)
        assert "А" in history

    async def test_add_logs_batch(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        logs = [
            {"user_id": 1, "question_id": i, "answer": "А",
             "is_correct": True, "mode": "simulation", "session_id": "s1"}
            for i in range(1, 4)
        ]
        await repo.logs.add_logs_batch(logs)
        await repo.session.commit()
        history = await repo.logs.get_question_history(1, 1)
        assert len(history) == 1

    async def test_empty_batch_is_noop(self, repo: RequestsRepo) -> None:
        await repo.logs.add_logs_batch([])  # should not raise

    async def test_get_failures_count(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.logs.add_log(user_id=1, question_id=20, answer="Б", is_correct=False, mode="random")
        await repo.logs.add_log(user_id=1, question_id=20, answer="А", is_correct=True, mode="random")
        await repo.session.commit()
        count = await repo.logs.get_question_failures_count(1, 20)
        assert count == 1

    async def test_question_history_order(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        for ans in ["А", "Б", "В"]:
            await repo.logs.add_log(user_id=1, question_id=30, answer=ans, is_correct=False, mode="random")
        await repo.session.commit()
        history = await repo.logs.get_question_history(1, 30, limit=2)
        assert len(history) == 2


# ===========================================================================
# JoinRequestsRepo
# ===========================================================================

class TestJoinRequestsRepo:
    async def test_add_and_get_requests(self, repo: RequestsRepo) -> None:
        await repo.join_requests.add_request(user_id=1, chat_id=-100)
        await repo.session.commit()
        requests = await repo.join_requests.get_all_requests()
        assert (1, -100) in requests

    async def test_add_duplicate_is_ignored(self, repo: RequestsRepo) -> None:
        await repo.join_requests.add_request(user_id=2, chat_id=-100)
        await repo.join_requests.add_request(user_id=2, chat_id=-100)
        await repo.session.commit()
        requests = await repo.join_requests.get_all_requests()
        assert requests.count((2, -100)) == 1

    async def test_delete_request(self, repo: RequestsRepo) -> None:
        await repo.join_requests.add_request(user_id=3, chat_id=-200)
        await repo.session.commit()
        await repo.join_requests.delete_request(3, -200)
        await repo.session.commit()
        requests = await repo.join_requests.get_all_requests()
        assert (3, -200) not in requests

    async def test_clear_all(self, repo: RequestsRepo) -> None:
        await repo.join_requests.add_request(user_id=4, chat_id=-300)
        await repo.join_requests.add_request(user_id=5, chat_id=-300)
        await repo.session.commit()
        await repo.join_requests.clear_all()
        await repo.session.commit()
        requests = await repo.join_requests.get_all_requests()
        assert requests == []
