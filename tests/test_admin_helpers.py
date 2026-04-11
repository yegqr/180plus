"""
Tests for pure helpers extracted from admin dialog modules:
  - tgbot/dialogs/admin/settings.py: _key_preview, _key_source
"""

import pytest

from tgbot.dialogs.admin.settings import _key_preview, _key_source


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
