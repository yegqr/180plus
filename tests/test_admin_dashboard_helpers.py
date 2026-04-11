"""
Tests for tgbot/dialogs/admin/dashboard.py pure helpers:
  _fmt_week, _fmt_content, _fmt_daily_activity
"""

import pytest

from tgbot.dialogs.admin.dashboard import _fmt_content, _fmt_daily_activity, _fmt_week


# ===========================================================================
# _fmt_week
# ===========================================================================

class TestFmtWeek:
    def test_empty_list_returns_placeholder(self):
        assert _fmt_week([]) == "— порожньо —"

    def test_single_row(self):
        result = _fmt_week([{"source": "direct", "count": 5}])
        assert "direct" in result
        assert "5" in result

    def test_multiple_rows_joined_by_newline(self):
        data = [
            {"source": "link_a", "count": 10},
            {"source": "link_b", "count": 3},
        ]
        result = _fmt_week(data)
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_bullet_prefix(self):
        result = _fmt_week([{"source": "x", "count": 1}])
        assert result.startswith("•")

    def test_preserves_order(self):
        data = [
            {"source": "first", "count": 1},
            {"source": "second", "count": 2},
        ]
        result = _fmt_week(data)
        assert result.index("first") < result.index("second")


# ===========================================================================
# _fmt_content
# ===========================================================================

class TestFmtContent:
    def test_empty_list_returns_placeholder(self):
        assert _fmt_content([]) == "— порожньо —"

    def test_single_subject(self):
        result = _fmt_content([{"subject": "math", "count": 42}])
        assert "math" in result
        assert "42" in result

    def test_multiple_subjects(self):
        data = [
            {"subject": "math", "count": 100},
            {"subject": "hist", "count": 80},
        ]
        result = _fmt_content(data)
        assert "math" in result
        assert "hist" in result
        assert len(result.split("\n")) == 2

    def test_bullet_prefix(self):
        result = _fmt_content([{"subject": "eng", "count": 50}])
        assert result.startswith("•")


# ===========================================================================
# _fmt_daily
# ===========================================================================

class TestFmtDailyActivity:
    def _empty_activity(self) -> dict:
        return {"simulations": {}, "random": {}}

    def test_no_activity_returns_placeholder(self):
        result = _fmt_daily_activity(self._empty_activity())
        assert "активності не було" in result

    def test_sim_only_subject(self):
        activity = {"simulations": {"math": 5}, "random": {}}
        result = _fmt_daily_activity(activity)
        assert "MATH" in result
        assert "5" in result

    def test_rand_only_subject(self):
        activity = {"simulations": {}, "random": {"hist": 3}}
        result = _fmt_daily_activity(activity)
        assert "HIST" in result
        assert "3" in result

    def test_both_sim_and_rand(self):
        activity = {"simulations": {"math": 7}, "random": {"math": 4}}
        result = _fmt_daily_activity(activity)
        assert "7" in result
        assert "4" in result

    def test_subjects_sorted_alphabetically(self):
        activity = {
            "simulations": {"physics": 1, "eng": 2},
            "random": {},
        }
        result = _fmt_daily_activity(activity)
        assert result.index("ENG") < result.index("PHYSICS")

    def test_zero_rand_when_only_sim(self):
        activity = {"simulations": {"math": 5}, "random": {}}
        result = _fmt_daily_activity(activity)
        assert "0" in result

    def test_multiple_subjects_each_on_own_line(self):
        activity = {
            "simulations": {"math": 1, "hist": 2},
            "random": {"math": 0, "hist": 0},
        }
        result = _fmt_daily_activity(activity)
        assert len(result.split("\n")) == 2
