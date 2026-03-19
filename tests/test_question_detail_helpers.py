"""
Tests for pure display helpers in tgbot/dialogs/admin/question_detail.py.
"""

from tgbot.dialogs.admin.question_detail import (
    _format_answer_text,
    _resolve_categories_text,
    _truncate_explanation,
)
from tgbot.misc.constants import TG_CAPTION_SAFE_LIMIT, TG_TEXT_SAFE_LIMIT


# ===========================================================================
# _format_answer_text
# ===========================================================================

class TestFormatAnswerText:
    def test_choice_includes_answer_and_options(self):
        result = _format_answer_text("choice", {"answer": "Б", "options": "5"})
        assert "Б" in result
        assert "5" in result

    def test_match_formats_pairs(self):
        result = _format_answer_text("match", {"pairs": {"1": "А", "2": "Б"}})
        assert "1-А" in result
        assert "2-Б" in result

    def test_short_returns_answer_string(self):
        result = _format_answer_text("short", {"answer": "42.5"})
        assert result == "42.5"

    def test_unknown_type_falls_back_to_str(self):
        result = _format_answer_text("unknown", {"key": "val"})
        assert isinstance(result, str)

    def test_empty_match_pairs(self):
        result = _format_answer_text("match", {"pairs": {}})
        assert result == ""


# ===========================================================================
# _resolve_categories_text
# ===========================================================================

class TestResolveCategoriesText:
    def test_none_returns_dash(self):
        assert _resolve_categories_text(None) == "—"

    def test_empty_list_returns_dash(self):
        assert _resolve_categories_text([]) == "—"

    def test_unknown_slug_returned_as_is(self):
        # A slug that is not in CATEGORIES should just be returned raw
        result = _resolve_categories_text(["nonexistent_slug_xyz"])
        assert "nonexistent_slug_xyz" in result

    def test_returns_string(self):
        result = _resolve_categories_text(["nonexistent_slug_xyz"])
        assert isinstance(result, str)


# ===========================================================================
# _truncate_explanation
# ===========================================================================

class TestTruncateExplanation:
    def test_short_text_unchanged(self):
        text = "short explanation"
        result = _truncate_explanation(text, "ans", show_image=False, is_long_text=False)
        assert result == text

    def test_very_long_no_image_gets_truncated(self):
        long_text = "A" * (TG_TEXT_SAFE_LIMIT + 500)
        result = _truncate_explanation(long_text, "ans", show_image=False, is_long_text=False)
        assert len(result) <= TG_TEXT_SAFE_LIMIT + 200  # truncated + ellipsis
        assert "довгий" in result

    def test_caption_mode_truncates_to_limit(self):
        ans = "А (з 5)"
        # Create explanation that pushes over caption limit
        long_expl = "B" * TG_CAPTION_SAFE_LIMIT
        result = _truncate_explanation(long_expl, ans, show_image=True, is_long_text=True)
        assert "обрізано" in result

    def test_caption_mode_short_text_unchanged(self):
        result = _truncate_explanation("ok", "ans", show_image=True, is_long_text=False)
        assert result == "ok"
