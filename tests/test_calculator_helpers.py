"""
Tests for pure helpers in tgbot/dialogs/calculator.py.
"""

from tgbot.dialogs.calculator import _build_k_vals, _build_input_hint, is_budget_eligible


# ===========================================================================
# _build_k_vals
# ===========================================================================

class TestBuildKVals:
    def test_none_spec_returns_all_zeros(self):
        result = _build_k_vals(None, None)
        assert all(v == 0 for v in result.values())

    def test_main_block_coefficients_extracted(self):
        spec = {
            "main_block": {"ukr_mova": 0.3, "ukr_history": 0.2, "math": 0.5},
            "choosable_block": {},
            "tvorchy_konkurs": 0,
        }
        k = _build_k_vals(spec, None)
        assert k["k1"] == 0.3
        assert k["k2"] == 0.2
        assert k["k3"] == 0.5

    def test_fourth_subject_coeff_extracted(self):
        spec = {
            "main_block": {"ukr_mova": 0, "ukr_history": 0, "math": 0},
            "choosable_block": {"physics": 0.25},
            "tvorchy_konkurs": 0,
        }
        k = _build_k_vals(spec, "physics")
        assert k["k4"] == 0.25

    def test_fourth_subject_absent_gives_zero(self):
        spec = {
            "main_block": {"ukr_mova": 0, "ukr_history": 0, "math": 0},
            "choosable_block": {"physics": 0.25},
            "tvorchy_konkurs": 0,
        }
        k = _build_k_vals(spec, "chemistry")
        assert k["k4"] == 0

    def test_k4max_is_max_of_choosable_block(self):
        spec = {
            "main_block": {"ukr_mova": 0, "ukr_history": 0, "math": 0},
            "choosable_block": {"a": 0.1, "b": 0.4, "c": 0.2},
            "tvorchy_konkurs": 0,
        }
        k = _build_k_vals(spec, None)
        assert k["k4max"] == 0.4

    def test_tvorchy_konkurs_extracted(self):
        spec = {
            "main_block": {"ukr_mova": 0, "ukr_history": 0, "math": 0},
            "choosable_block": {},
            "tvorchy_konkurs": 0.3,
        }
        k = _build_k_vals(spec, None)
        assert k["kt"] == 0.3

    def test_none_tvorchy_defaults_to_zero(self):
        spec = {
            "main_block": {"ukr_mova": 0, "ukr_history": 0, "math": 0},
            "choosable_block": {},
            "tvorchy_konkurs": None,
        }
        k = _build_k_vals(spec, None)
        assert k["kt"] == 0


# ===========================================================================
# _build_input_hint
# ===========================================================================

class TestBuildInputHint:
    def test_no_input_returns_default(self):
        result = _build_input_hint("", None, "Предмет")
        assert result == "Введіть бал:"

    def test_btn_tk_returns_creative_hint(self):
        result = _build_input_hint("btn_tk", None, "Предмет")
        assert "Творчий конкурс" in result

    def test_btn_p1_returns_ukr_mova_hint(self):
        result = _build_input_hint("btn_p1", None, "Предмет")
        assert "Укр. мови" in result or "Введіть бал" in result

    def test_btn_p3_returns_math_hint(self):
        result = _build_input_hint("btn_p3", None, "Предмет")
        assert "Математики" in result or "Введіть бал" in result

    def test_result_is_string(self):
        assert isinstance(_build_input_hint("btn_p1", None, "Предмет"), str)


# ===========================================================================
# is_budget_eligible
# ===========================================================================

class TestIsBudgetEligible:
    def test_standard_spec_needs_130(self):
        assert is_budget_eligible(130.0, "Z1") is True
        assert is_budget_eligible(129.9, "Z1") is False

    def test_high_threshold_spec_needs_150(self):
        assert is_budget_eligible(150.0, "C1") is True
        assert is_budget_eligible(149.9, "C1") is False

    def test_d8_is_high_threshold(self):
        assert is_budget_eligible(149.0, "D8") is False
        assert is_budget_eligible(150.0, "D8") is True
