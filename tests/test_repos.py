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


# ===========================================================================
# MaterialRepo
# ===========================================================================

class TestMaterialRepo:
    async def test_get_by_subject_returns_none_when_missing(self, repo: RequestsRepo) -> None:
        result = await repo.materials.get_by_subject("math")
        assert result is None

    async def test_update_creates_new_row(self, repo: RequestsRepo) -> None:
        await repo.materials.update_materials("math", ["file_id_1"])
        await repo.session.commit()
        material = await repo.materials.get_by_subject("math")
        assert material is not None
        assert "file_id_1" in material.images

    async def test_update_upserts_existing_row(self, repo: RequestsRepo) -> None:
        await repo.materials.update_materials("math", ["file_id_1"])
        await repo.session.commit()
        await repo.materials.update_materials("math", ["file_id_1", "file_id_2"])
        await repo.session.commit()
        material = await repo.materials.get_by_subject("math")
        assert material.images == ["file_id_1", "file_id_2"]

    async def test_update_multiple_subjects_independently(self, repo: RequestsRepo) -> None:
        await repo.materials.update_materials("math", ["a"])
        await repo.materials.update_materials("ukr", ["b"])
        await repo.session.commit()
        assert (await repo.materials.get_by_subject("math")).images == ["a"]
        assert (await repo.materials.get_by_subject("ukr")).images == ["b"]

    async def test_clear_empties_images(self, repo: RequestsRepo) -> None:
        await repo.materials.update_materials("math", ["file_id_1", "file_id_2"])
        await repo.session.commit()
        await repo.materials.clear_materials("math")
        await repo.session.commit()
        material = await repo.materials.get_by_subject("math")
        assert material.images == []

    async def test_clear_nonexistent_subject_is_noop(self, repo: RequestsRepo) -> None:
        await repo.materials.clear_materials("nonexistent")  # should not raise


# ===========================================================================
# ResultRepo
# ===========================================================================

class TestResultRepo:
    async def _setup_user(self, repo: RequestsRepo) -> None:
        await repo.users.get_or_create_user(user_id=1, full_name="Test", language="uk")
        await repo.session.commit()

    async def test_save_and_get_last_session_result(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.results.save_result(1, "math", 2024, "s1", 30, 160, 3600)
        await repo.session.commit()
        result = await repo.results.get_last_session_result(1, "math", "s1")
        assert result is not None
        assert result.raw_score == 30
        assert result.nmt_score == 160

    async def test_get_last_session_result_returns_none_when_missing(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        result = await repo.results.get_last_session_result(1, "math", "s1")
        assert result is None

    async def test_get_last_session_result_excludes_zero_score(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.results.save_result(1, "math", 2024, "s1", 0, 0, 3600)
        await repo.session.commit()
        result = await repo.results.get_last_session_result(1, "math", "s1")
        assert result is None  # raw_score > 0 filter

    async def test_get_completed_sessions_requires_duration_900(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.results.save_result(1, "math", 2024, "short", 10, 100, 899)
        await repo.session.commit()
        await repo.results.save_result(1, "math", 2024, "valid", 10, 100, 900)
        await repo.session.commit()
        sessions = await repo.results.get_completed_sessions(1, "math", 2024)
        assert "short" not in sessions
        assert "valid" in sessions

    async def test_get_completed_sessions_empty_for_unknown_user(self, repo: RequestsRepo) -> None:
        sessions = await repo.results.get_completed_sessions(999, "math", 2024)
        assert sessions == set()

    async def test_get_completed_sessions_subject_isolation(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.results.save_result(1, "math", 2024, "s1", 10, 100, 1800)
        await repo.session.commit()
        await repo.results.save_result(1, "ukr", 2024, "s1", 10, 100, 1800)
        await repo.session.commit()
        math_sessions = await repo.results.get_completed_sessions(1, "math", 2024)
        ukr_sessions = await repo.results.get_completed_sessions(1, "ukr", 2024)
        assert "s1" in math_sessions
        assert "s1" in ukr_sessions

    async def test_get_all_results_for_export_filters(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.results.save_result(1, "math", 2024, "zero_score", 0, 0, 3600)
        await repo.session.commit()
        await repo.results.save_result(1, "math", 2024, "too_short", 10, 150, 200)
        await repo.session.commit()
        await repo.results.save_result(1, "math", 2024, "valid", 20, 160, 3600)
        await repo.session.commit()
        export = await repo.results.get_all_results_for_export()
        sessions = [r.session for r in export]
        assert "zero_score" not in sessions
        assert "too_short" not in sessions
        assert "valid" in sessions

    async def test_save_random_result(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.results.save_random_result(1, "math", question_id=42, points=1)
        await repo.session.commit()  # should not raise


# ===========================================================================
# StatsRepo
# ===========================================================================

class TestStatsRepo:
    async def _setup_user(self, repo: RequestsRepo, user_id: int = 1) -> None:
        await repo.users.get_or_create_user(user_id=user_id, full_name="Test", language="uk")
        await repo.session.commit()

    async def test_add_join_stat(self, repo: RequestsRepo) -> None:
        await repo.stats.add_join_stat(user_id=1, source="telegram")
        await repo.session.commit()  # should not raise

    async def test_get_weekly_stats_current_week(self, repo: RequestsRepo) -> None:
        await repo.stats.add_join_stat(user_id=1, source="telegram")
        await repo.stats.add_join_stat(user_id=2, source="telegram")
        await repo.stats.add_join_stat(user_id=3, source="vk")
        await repo.session.commit()
        stats = await repo.stats.get_weekly_stats(week_offset=0)
        by_source = {s["source"]: s["count"] for s in stats}
        assert by_source.get("telegram") == 2
        assert by_source.get("vk") == 1

    async def test_get_weekly_stats_last_week_empty(self, repo: RequestsRepo) -> None:
        await repo.stats.add_join_stat(user_id=1, source="telegram")
        await repo.session.commit()
        stats = await repo.stats.get_weekly_stats(week_offset=1)
        assert stats == []

    async def test_get_content_stats_empty(self, repo: RequestsRepo) -> None:
        stats = await repo.stats.get_content_stats()
        assert stats == []

    async def test_get_daily_activity_stats_empty(self, repo: RequestsRepo) -> None:
        stats = await repo.stats.get_daily_activity_stats()
        assert stats["total_sims"] == 0
        assert stats["total_rand"] == 0
        assert stats["simulations"] == {}
        assert stats["random"] == {}

    async def test_get_daily_activity_stats_with_data(self, repo: RequestsRepo) -> None:
        await self._setup_user(repo)
        await repo.results.save_result(1, "math", 2024, "s1", 10, 150, 3600)
        await repo.results.save_random_result(1, "ukr", question_id=5, points=1)
        await repo.session.commit()
        stats = await repo.stats.get_daily_activity_stats()
        assert stats["simulations"].get("math") == 1
        assert stats["random"].get("ukr") == 1
        assert stats["total_sims"] == 1
        assert stats["total_rand"] == 1


# ===========================================================================
# UserRepo — additional coverage
# ===========================================================================

class TestUserRepoExtra:
    async def _create_user(self, repo: RequestsRepo, user_id: int, **kwargs) -> None:
        await repo.users.get_or_create_user(
            user_id=user_id, full_name=f"User{user_id}", language="uk", **kwargs
        )
        await repo.session.commit()

    async def test_get_active_stats_empty(self, repo: RequestsRepo) -> None:
        stats = await repo.users.get_active_stats()
        assert stats == {"total": 0, "today": 0, "week": 0}

    async def test_get_active_stats_counts_users(self, repo: RequestsRepo) -> None:
        await self._create_user(repo, 1)
        await self._create_user(repo, 2)
        stats = await repo.users.get_active_stats()
        assert stats["total"] == 2
        assert stats["today"] == 2
        assert stats["week"] == 2

    async def test_get_users_for_broadcast_all(self, repo: RequestsRepo) -> None:
        await self._create_user(repo, 1)
        await self._create_user(repo, 2)
        user_ids = await repo.users.get_users_for_broadcast("all")
        assert 1 in user_ids
        assert 2 in user_ids

    async def test_get_users_for_broadcast_active_today(self, repo: RequestsRepo) -> None:
        await self._create_user(repo, 1)
        user_ids = await repo.users.get_users_for_broadcast("active_today")
        assert 1 in user_ids

    async def test_get_users_for_broadcast_daily_challenge(self, repo: RequestsRepo) -> None:
        await self._create_user(repo, 1)
        user_ids = await repo.users.get_users_for_broadcast("daily_challenge")
        assert 1 in user_ids

    async def test_update_subject(self, repo: RequestsRepo) -> None:
        await self._create_user(repo, 1)
        await repo.users.update_subject(1, "ukr")
        await repo.session.commit()
        user = await repo.users.get_user_by_id(1)
        assert user.selected_subject == "ukr"
