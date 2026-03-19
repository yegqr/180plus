"""
Sanity tests for tgbot/misc/constants.py

These tests guard against accidental removal or corruption of constants that
the rest of the codebase depends on at import time.
"""

import pytest

from tgbot.misc.constants import (
    ALBUM_WAIT_SECONDS,
    BROADCAST_SEND_DELAY,
    DAILY_CHALLENGE_SUBJECTS,
    DAILY_WINDOW_END_HOUR,
    DAILY_WINDOW_START_HOUR,
    ENG_LETTERS,
    GEMINI_SEMAPHORE_LIMIT,
    JOIN_REQUEST_DELAY,
    QUESTION_HISTORY_LIMIT,
    SUBJECT_FULL_NAMES,
    SUBJECT_LABELS,
    TG_CAPTION_SAFE_LIMIT,
    TG_TEXT_SAFE_LIMIT,
    UKR_LETTERS,
)


class TestSubjectConstants:
    EXPECTED_SUBJECTS = {"math", "hist", "mova", "eng", "physics"}

    def test_subject_labels_keys(self):
        assert set(SUBJECT_LABELS.keys()) == self.EXPECTED_SUBJECTS

    def test_subject_labels_all_non_empty(self):
        for slug, label in SUBJECT_LABELS.items():
            assert isinstance(label, str) and label, f"SUBJECT_LABELS[{slug!r}] is empty"

    def test_subject_full_names_keys(self):
        assert set(SUBJECT_FULL_NAMES.keys()) == self.EXPECTED_SUBJECTS

    def test_daily_challenge_subjects_subset(self):
        assert set(DAILY_CHALLENGE_SUBJECTS).issubset(self.EXPECTED_SUBJECTS)
        assert len(DAILY_CHALLENGE_SUBJECTS) > 0


class TestLetterConstants:
    def test_ukr_letters_contains_а(self):
        assert "А" in UKR_LETTERS

    def test_ukr_letters_uppercase(self):
        assert UKR_LETTERS == UKR_LETTERS.upper()

    def test_ukr_letters_no_duplicates(self):
        assert len(UKR_LETTERS) == len(set(UKR_LETTERS))

    def test_eng_letters_contains_a(self):
        assert "A" in ENG_LETTERS

    def test_eng_letters_uppercase(self):
        assert ENG_LETTERS == ENG_LETTERS.upper()

    def test_eng_letters_26(self):
        assert len(ENG_LETTERS) == 26


class TestNumericConstants:
    def test_broadcast_send_delay_positive(self):
        assert BROADCAST_SEND_DELAY > 0

    def test_album_wait_seconds_positive(self):
        assert ALBUM_WAIT_SECONDS > 0

    def test_join_request_delay_positive(self):
        assert JOIN_REQUEST_DELAY > 0

    def test_gemini_semaphore_limit_at_least_1(self):
        assert GEMINI_SEMAPHORE_LIMIT >= 1

    def test_daily_window_order(self):
        assert DAILY_WINDOW_START_HOUR < DAILY_WINDOW_END_HOUR

    def test_daily_window_valid_hours(self):
        assert 0 <= DAILY_WINDOW_START_HOUR < 24
        assert 0 < DAILY_WINDOW_END_HOUR <= 24

    def test_question_history_limit_positive(self):
        assert QUESTION_HISTORY_LIMIT > 0

    def test_tg_caption_limit_less_than_text_limit(self):
        assert TG_CAPTION_SAFE_LIMIT < TG_TEXT_SAFE_LIMIT

    def test_tg_limits_reasonable(self):
        # Telegram caption hard limit is 1024; our safe limit must be below
        assert TG_CAPTION_SAFE_LIMIT < 1024
        # Telegram message hard limit is 4096; our safe limit must be below
        assert TG_TEXT_SAFE_LIMIT < 4096
