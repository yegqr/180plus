"""
Tests for pure helpers extracted from admin dialog modules:
  - tgbot/dialogs/admin/daily.py:    _parse_lottery_status
  - tgbot/dialogs/admin/settings.py: _key_preview, _key_source
"""

import pytest

from tgbot.dialogs.admin.daily import _parse_lottery_status
from tgbot.dialogs.admin.settings import _key_preview, _key_source


# ===========================================================================
# _parse_lottery_status
# ===========================================================================

class TestParseLotteryStatus:
    def test_loss_returns_loss_message(self):
        result = _parse_lottery_status("LOSS")
        assert "Програно" in result
        assert "❌" in result

    def test_win_with_time_extracts_time(self):
        result = _parse_lottery_status("WIN(14:30)")
        assert "14:30" in result
        assert "🎯" in result

    def test_win_different_time(self):
        result = _parse_lottery_status("WIN(09:05)")
        assert "09:05" in result

    def test_miss_returns_miss_message(self):
        result = _parse_lottery_status("MISS")
        assert "⌛" in result
        assert "Пропущено" in result

    def test_miss_as_substring(self):
        # "MISS_TODAY" should also match
        result = _parse_lottery_status("MISS_TODAY")
        assert "⌛" in result

    def test_unknown_status_returned_verbatim(self):
        status = "Ще не розіграно"
        result = _parse_lottery_status(status)
        assert result == status

    def test_empty_string_returned_verbatim(self):
        result = _parse_lottery_status("")
        assert result == ""

    def test_win_parens_removed(self):
        result = _parse_lottery_status("WIN(20:00)")
        assert "(" not in result
        assert ")" not in result


# ===========================================================================
# _key_preview
# ===========================================================================

class TestKeyPreview:
    def test_none_returns_dash(self):
        assert _key_preview(None) == "—"

    def test_empty_string_returns_dash(self):
        assert _key_preview("") == "—"

    def test_short_key_shows_ellipsis(self):
        result = _key_preview("AIzaSyABCDEFGH123456")
        assert "..." in result

    def test_starts_with_first_8_chars(self):
        key = "AIzaSyABCDEFGH123456"
        result = _key_preview(key)
        assert result.startswith(key[:8])

    def test_ends_with_last_4_chars(self):
        key = "AIzaSyABCDEFGH123456"
        result = _key_preview(key)
        assert result.endswith(key[-4:])

    def test_middle_is_masked(self):
        key = "AIzaSyABCDEFGH123456"
        result = _key_preview(key)
        # The middle portion (between first 8 and last 4) should not appear
        assert key[8:-4] not in result

    def test_format_is_prefix_dots_suffix(self):
        key = "ABCDEFGHIJKLMNOP"
        result = _key_preview(key)
        assert result == f"{key[:8]}...{key[-4:]}"


# ===========================================================================
# _key_source
# ===========================================================================

class TestKeySource:
    def test_db_key_returns_database(self):
        assert _key_source("db_key_value", None) == "Database"

    def test_config_key_only_returns_config(self):
        assert _key_source(None, "config_key_value") == "Config (.env)"

    def test_no_keys_returns_none_string(self):
        assert _key_source(None, None) == "None"

    def test_db_key_takes_priority_over_config(self):
        # Both present → Database wins
        assert _key_source("db_key", "config_key") == "Database"

    def test_empty_db_key_falls_through_to_config(self):
        # Empty string is falsy
        assert _key_source("", "config_key") == "Config (.env)"

    def test_empty_both_returns_none_string(self):
        assert _key_source("", "") == "None"
