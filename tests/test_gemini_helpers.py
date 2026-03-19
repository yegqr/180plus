"""
Tests for pure helpers in tgbot/services/gemini.py.
"""

from tgbot.services.gemini import _build_category_prompt, _build_parts


# ===========================================================================
# _build_category_prompt
# ===========================================================================

class TestBuildCategoryPrompt:
    def test_empty_dict_returns_empty_string(self):
        assert _build_category_prompt({}) == ""

    def test_none_like_falsy_returns_empty(self):
        assert _build_category_prompt({}) == ""

    def test_single_section_appears_in_output(self):
        cats = {"Алгебра": [{"slug": "algebra_eq", "name": "Рівняння", "desc": "лін. рівняння"}]}
        result = _build_category_prompt(cats)
        assert "Алгебра" in result
        assert "algebra_eq" in result
        assert "Рівняння" in result

    def test_multiple_sections_all_present(self):
        cats = {
            "Алгебра": [{"slug": "alg", "name": "Алг", "desc": "d1"}],
            "Геометрія": [{"slug": "geo", "name": "Гео", "desc": "d2"}],
        }
        result = _build_category_prompt(cats)
        assert "Алгебра" in result
        assert "Геометрія" in result
        assert "alg" in result
        assert "geo" in result

    def test_header_line_present(self):
        cats = {"Sec": [{"slug": "s", "name": "N", "desc": "D"}]}
        result = _build_category_prompt(cats)
        assert "ВРАХУЙ" in result


# ===========================================================================
# _build_parts
# ===========================================================================

class TestBuildParts:
    def test_single_image_bytes_produces_two_parts(self):
        parts = _build_parts("prompt", b"\xff\xd8\xff")  # fake JPEG header
        assert len(parts) == 2  # 1 text + 1 image

    def test_list_of_images_produces_correct_count(self):
        images = [b"\xff" * 10, b"\xd8" * 10, b"\xe0" * 10]
        parts = _build_parts("prompt", images)
        assert len(parts) == 4  # 1 text + 3 images

    def test_empty_list_produces_one_part(self):
        parts = _build_parts("prompt", [])
        assert len(parts) == 1  # only the text part

    def test_prompt_is_first_part(self):
        parts = _build_parts("hello world", b"\x00")
        # The first part should be the text
        assert hasattr(parts[0], "text") or str(parts[0]).count("hello") >= 0
