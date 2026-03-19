"""
Tests for tgbot/services/daily.py (pure helpers only).
"""

from datetime import datetime

import pytest

from tgbot.misc.constants import DAILY_WINDOW_START_HOUR, DAILY_WINDOW_END_HOUR
from tgbot.services.daily import _build_daily_keyboard, _pick_send_time


# ===========================================================================
# _pick_send_time
# ===========================================================================

class TestPickSendTime:
    """_pick_send_time must always return a time inside the daily window or None."""

    def _window_open(self) -> datetime:
        """Returns 'now' in the middle of the window."""
        mid = (DAILY_WINDOW_START_HOUR + DAILY_WINDOW_END_HOUR) // 2
        return datetime.now().replace(hour=mid, minute=0, second=0, microsecond=0)

    def _window_over(self) -> datetime:
        """Returns 'now' after the window ends."""
        return datetime.now().replace(hour=DAILY_WINDOW_END_HOUR + 1, minute=0, second=0, microsecond=0)

    def test_returns_datetime_during_window(self):
        result = _pick_send_time(self._window_open())
        assert isinstance(result, datetime)

    def test_result_is_in_future_relative_to_now(self):
        now = self._window_open()
        result = _pick_send_time(now)
        assert result is not None
        assert result >= now

    def test_result_within_window_hours(self):
        now = self._window_open()
        result = _pick_send_time(now)
        assert result is not None
        assert DAILY_WINDOW_START_HOUR <= result.hour < DAILY_WINDOW_END_HOUR + 1

    def test_returns_none_when_window_over(self):
        result = _pick_send_time(self._window_over())
        assert result is None

    def test_multiple_calls_all_valid(self):
        """Randomness check: 20 calls should all yield valid times."""
        now = self._window_open()
        for _ in range(20):
            result = _pick_send_time(now)
            assert result is not None
            assert result >= now


# ===========================================================================
# _build_daily_keyboard
# ===========================================================================

class TestBuildDailyKeyboard:
    class _Q:
        def __init__(self, q_id: int, q_type: str):
            self.id = q_id
            self.q_type = q_type

    def test_choice_has_five_option_buttons(self):
        q = self._Q(1, "choice")
        kb = _build_daily_keyboard(q)
        # First row = answer buttons
        first_row = kb.inline_keyboard[0]
        assert len(first_row) == 5

    def test_choice_callback_contains_question_id(self):
        q = self._Q(42, "choice")
        kb = _build_daily_keyboard(q)
        for btn in kb.inline_keyboard[0]:
            assert "42" in btn.callback_data

    def test_choice_has_home_button(self):
        q = self._Q(1, "choice")
        kb = _build_daily_keyboard(q)
        all_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "daily:menu:home" in all_cbs

    def test_non_choice_has_input_and_show_answer(self):
        q = self._Q(7, "short")
        kb = _build_daily_keyboard(q)
        all_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert any("INPUT" in cb for cb in all_cbs)
        assert any("SHOW_ANSWER" in cb for cb in all_cbs)

    def test_non_choice_has_home_button(self):
        q = self._Q(7, "short")
        kb = _build_daily_keyboard(q)
        all_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "daily:menu:home" in all_cbs
