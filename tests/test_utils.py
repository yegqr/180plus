"""
Tests for tgbot/misc/utils.py
"""

import pytest

from tgbot.misc.utils import (
    build_answer_ui,
    build_hint_text,
    build_wrong_answer_status,
    format_answer_for_log,
    format_answer_pair,
    get_question_images,
    parse_question_caption,
)
from tgbot.misc.constants import UKR_LETTERS, ENG_LETTERS


# ===========================================================================
# get_question_images
# ===========================================================================

class TestGetQuestionImages:
    """get_question_images must return a deduplicated ordered list of file_ids."""

    class _Q:
        """Minimal mock of the Question model."""
        def __init__(self, image_file_id=None, images=None):
            self.image_file_id = image_file_id
            self.images = images

    def test_single_image_via_images_list(self):
        q = self._Q(image_file_id="id1", images=["id1"])
        assert get_question_images(q) == ["id1"]

    def test_multiple_images(self):
        q = self._Q(image_file_id="id1", images=["id1", "id2", "id3"])
        assert get_question_images(q) == ["id1", "id2", "id3"]

    def test_deduplication(self):
        q = self._Q(image_file_id="id1", images=["id1", "id1", "id2"])
        result = get_question_images(q)
        assert result.count("id1") == 1
        assert "id2" in result

    def test_fallback_to_image_file_id(self):
        """If images is empty/None, fall back to image_file_id."""
        q = self._Q(image_file_id="primary", images=[])
        assert get_question_images(q) == ["primary"]

    def test_empty_question(self):
        q = self._Q(image_file_id=None, images=[])
        assert get_question_images(q) == []

    def test_none_images_field(self):
        q = self._Q(image_file_id="only", images=None)
        assert get_question_images(q) == ["only"]

    def test_order_preserved(self):
        q = self._Q(image_file_id="a", images=["a", "b", "c"])
        assert get_question_images(q) == ["a", "b", "c"]


# ===========================================================================
# format_answer_for_log
# ===========================================================================

class TestFormatAnswerForLog:
    def test_string_passthrough(self):
        assert format_answer_for_log("А") == "А"

    def test_dict_match_answer(self):
        result = format_answer_for_log({"1": "А", "2": "Б"})
        # Should be "1-А, 2-Б" (sorted keys)
        assert "1-А" in result
        assert "2-Б" in result

    def test_none_becomes_empty_or_none_string(self):
        result = format_answer_for_log(None)
        assert result == "" or result == "None"

    def test_int_converted(self):
        result = format_answer_for_log(42)
        assert result == "42"


# ===========================================================================
# parse_question_caption
# ===========================================================================

class TestParseQuestionCaption:
    def test_choice_full(self):
        cap = "math | 2024 | main | 1 | choice | 5 | А"
        meta = parse_question_caption(cap)
        assert meta["subject"] == "math"
        assert meta["year"] == 2024
        assert meta["session"] == "main"
        assert meta["q_number"] == 1
        assert meta["q_type"] == "choice"
        assert meta["correct_answer"]["answer"] == "А"
        assert meta["correct_answer"]["options"] == "5"  # stored as string

    def test_match_full(self):
        cap = "physics | 2024 | main | 2 | match | 3x5 | 1А 2Б 3Д"
        meta = parse_question_caption(cap)
        assert meta["q_type"] == "match"
        pairs = meta["correct_answer"]["pairs"]
        assert pairs["1"] == "А"
        assert pairs["2"] == "Б"
        assert pairs["3"] == "Д"

    def test_short_dot(self):
        cap = "physics | 2024 | main | 3 | short | - | 4.5"
        meta = parse_question_caption(cap)
        assert meta["q_type"] == "short"
        assert meta["correct_answer"]["answer"] == "4.5"

    def test_short_comma_normalized(self):
        cap = "physics | 2024 | main | 3 | short | - | 4,5"
        meta = parse_question_caption(cap)
        # comma should be normalized to dot in storage
        assert "4" in str(meta["correct_answer"]["answer"])

    def test_invalid_subject_raises(self):
        cap = "invalidsubj | 2024 | main | 1 | choice | 5 | А"
        with pytest.raises(ValueError):
            parse_question_caption(cap)

    def test_missing_fields_raises(self):
        cap = "math | 2024 | main | 1 | choice"
        with pytest.raises(ValueError):
            parse_question_caption(cap)

    def test_invalid_year_raises(self):
        cap = "math | notayear | main | 1 | choice | 5 | А"
        with pytest.raises(ValueError):
            parse_question_caption(cap)

    def test_invalid_q_number_raises(self):
        cap = "math | 2024 | main | notanumber | choice | 5 | А"
        with pytest.raises(ValueError):
            parse_question_caption(cap)

    def test_weight_extracted(self):
        cap = "math | 2024 | main | 1 | choice | 5 | А"
        meta = parse_question_caption(cap)
        assert "weight" in meta

    def test_extra_spaces_handled(self):
        cap = "  math  |  2024  |  main  |  1  |  choice  |  5  |  А  "
        meta = parse_question_caption(cap)
        assert meta["subject"] == "math"
        assert meta["year"] == 2024


# ===========================================================================
# build_answer_ui
# ===========================================================================

class TestBuildAnswerUI:
    def test_choice_returns_variants_only(self):
        ca = {"answer": "А", "options": "5"}
        variants, nums, letters = build_answer_ui("choice", ca, UKR_LETTERS)
        assert len(variants) == 5
        assert nums == []
        assert letters == []

    def test_choice_label_and_value_equal(self):
        ca = {"answer": "А", "options": "3"}
        variants, _, _ = build_answer_ui("choice", ca, UKR_LETTERS)
        for label, value in variants:
            assert label == value

    def test_choice_uses_letters_source(self):
        ca = {"answer": "A", "options": "4"}
        variants, _, _ = build_answer_ui("choice", ca, ENG_LETTERS)
        assert variants[0] == (ENG_LETTERS[0], ENG_LETTERS[0])
        assert variants[3] == (ENG_LETTERS[3], ENG_LETTERS[3])

    def test_choice_default_options(self):
        # No "options" key → defaults to 5
        variants, _, _ = build_answer_ui("choice", {}, UKR_LETTERS)
        assert len(variants) == 5

    def test_match_returns_nums_and_letters(self):
        ca = {"pairs": {"1": "А", "2": "Б"}, "options": "2x3"}
        _, nums, letters = build_answer_ui("match", ca, UKR_LETTERS)
        assert len(nums) == 2
        assert len(letters) == 3

    def test_match_nums_are_string_ints(self):
        ca = {"pairs": {}, "options": "3x5"}
        _, nums, _ = build_answer_ui("match", ca, UKR_LETTERS)
        assert nums == [("1", "1"), ("2", "2"), ("3", "3")]

    def test_match_default_options_on_bad_format(self):
        ca = {"pairs": {}, "options": "bad"}
        _, nums, letters = build_answer_ui("match", ca, UKR_LETTERS)
        assert len(nums) == 3
        assert len(letters) == 5

    def test_short_returns_all_empty(self):
        variants, nums, letters = build_answer_ui("short", {"answer": "42"}, UKR_LETTERS)
        assert variants == []
        assert nums == []
        assert letters == []


# ===========================================================================
# build_hint_text
# ===========================================================================

class TestBuildHintText:
    def test_choice_hint(self):
        assert build_hint_text("choice", None, "math") == "Обери варіант:"

    def test_match_no_active_num(self):
        assert build_hint_text("match", None, "math") == "Обери цифру:"

    def test_match_with_active_num(self):
        result = build_hint_text("match", "2", "math")
        assert "2" in result
        assert "літеру" in result

    def test_short_hist_subject(self):
        result = build_hint_text("short", None, "hist")
        assert "цифри" in result

    def test_short_other_subject(self):
        result = build_hint_text("short", None, "math")
        assert "відповідь" in result.lower()


# ===========================================================================
# build_wrong_answer_status
# ===========================================================================

class TestBuildWrongAnswerStatus:
    def test_choice_shows_correct_answer(self):
        ca = {"answer": "Б", "options": "5"}
        result = build_wrong_answer_status("choice", ca, "А")
        assert "Б" in result
        assert "Неправильно" in result

    def test_short_shows_correct_answer(self):
        ca = {"answer": "42"}
        result = build_wrong_answer_status("short", ca, "99")
        assert "42" in result

    def test_match_correct_pair_gets_checkmark(self):
        ca = {"pairs": {"1": "А", "2": "Б"}}
        user_ans = {"1": "А", "2": "В"}
        result = build_wrong_answer_status("match", ca, user_ans)
        assert "✅" in result   # pair 1 is correct
        assert "❌" in result   # pair 2 is wrong

    def test_match_shows_correct_letter_for_wrong_pair(self):
        ca = {"pairs": {"1": "А"}}
        user_ans = {"1": "Б"}
        result = build_wrong_answer_status("match", ca, user_ans)
        assert "А" in result
        assert "Б" in result

    def test_match_missing_pair_shows_question_mark(self):
        ca = {"pairs": {"1": "А", "2": "Б"}}
        user_ans = {}  # user didn't answer pair 2
        result = build_wrong_answer_status("match", ca, user_ans)
        assert "?" in result


# ===========================================================================
# format_answer_pair
# ===========================================================================

class TestFormatAnswerPair:
    def test_choice_returns_user_and_correct(self):
        u, c = format_answer_pair("choice", {"answer": "Б"}, "А")
        assert u == "А"
        assert c == "Б"

    def test_short_returns_strings(self):
        u, c = format_answer_pair("short", {"answer": "42"}, "99")
        assert u == "99"
        assert c == "42"

    def test_none_user_answer_shows_none_string(self):
        u, c = format_answer_pair("choice", {"answer": "А"}, None)
        assert u == "немає"
        assert c == "А"

    def test_match_sorts_pairs(self):
        ca = {"pairs": {"2": "Б", "1": "А"}}
        u, c = format_answer_pair("match", ca, {"2": "В", "1": "А"})
        assert u.startswith("1-")
        assert c.startswith("1-")

    def test_match_correct_pairs_formatted(self):
        ca = {"pairs": {"1": "А", "2": "Б"}}
        _, c = format_answer_pair("match", ca, {})
        assert "1-А" in c
        assert "2-Б" in c

    def test_match_empty_user_shows_none(self):
        ca = {"pairs": {"1": "А"}}
        u, _ = format_answer_pair("match", ca, {})
        assert u == "немає"
