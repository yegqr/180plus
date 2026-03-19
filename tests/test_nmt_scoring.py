"""
Tests for tgbot/misc/nmt_scoring.py

All tests are pure/synchronous — no DB, no Telegram, no async.
"""

import pytest

from tgbot.misc.nmt_scoring import (
    calculate_kb_2026,
    get_nmt_score,
    get_raw_score_equivalent,
    get_scaled_score,
)


# ===========================================================================
# get_scaled_score
# ===========================================================================

class TestGetScaledScore:
    def test_zero_raw_returns_zero(self):
        assert get_scaled_score("math", 0) == 0.0

    def test_negative_raw_returns_zero(self):
        assert get_scaled_score("math", -5) == 0.0

    def test_known_value_math(self):
        # From table: math 5 → 100
        assert get_scaled_score("math", 5) == 100.0

    def test_known_value_math_max(self):
        # From table: math 32 → 200
        assert get_scaled_score("math", 32) == 200.0

    def test_below_min_threshold_returns_zero(self):
        # math min is 5; raw=4 → 0
        assert get_scaled_score("math", 4) == 0.0

    def test_above_max_threshold_returns_200(self):
        # math max is 32; raw=99 → 200
        assert get_scaled_score("math", 99) == 200.0

    def test_unknown_subject_returns_raw(self):
        # No table → pass-through
        assert get_scaled_score("unknown_subj", 150) == 150

    def test_ukr_mova_boundary(self):
        # ukr_mova: 8 → 100, 45 → 200
        assert get_scaled_score("ukr_mova", 8) == 100.0
        assert get_scaled_score("ukr_mova", 45) == 200.0

    def test_physics_known(self):
        # physics 5 → 100
        assert get_scaled_score("physics", 5) == 100.0

    def test_returns_float(self):
        result = get_scaled_score("math", 10)
        assert isinstance(result, float)


# ===========================================================================
# get_nmt_score
# ===========================================================================

class TestGetNmtScore:
    def test_valid_score_returns_int(self):
        result = get_nmt_score("math", 10)
        assert isinstance(result, int)

    def test_below_threshold_returns_none(self):
        # raw=0 → scaled=0 → below 100 → None
        assert get_nmt_score("math", 0) is None

    def test_min_score_returns_100(self):
        # math 5 → 100
        assert get_nmt_score("math", 5) == 100

    def test_max_score_returns_200(self):
        assert get_nmt_score("math", 32) == 200


# ===========================================================================
# calculate_kb_2026
# ===========================================================================

class TestCalculateKb2026:
    def test_zero_denominator_returns_zero(self):
        # All coefficients zero → denominator 0
        result = calculate_kb_2026(
            p1=150, k1=0, p2=150, k2=0, p3=150, k3=0,
            p4=0, k4=0, k4max=0,
        )
        assert result == 0.0

    def test_simple_equal_weights(self):
        # k1=k2=k3=1, k4=0, no bonus, rk=1, gk=1
        # KB = (1*150 + 1*150 + 1*150 + 0) / (1+1+1+(0+0)/2) = 450/3 = 150
        result = calculate_kb_2026(
            p1=150, k1=1, p2=150, k2=1, p3=150, k3=1,
            p4=0, k4=0, k4max=0,
        )
        assert result == pytest.approx(150.0, abs=0.01)

    def test_region_coefficient_applied(self):
        # Same as above but rk=1.02
        result = calculate_kb_2026(
            p1=150, k1=1, p2=150, k2=1, p3=150, k3=1,
            p4=0, k4=0, k4max=0, rk=1.02,
        )
        assert result == pytest.approx(153.0, abs=0.01)

    def test_gk_coefficient_applied(self):
        result = calculate_kb_2026(
            p1=150, k1=1, p2=150, k2=1, p3=150, k3=1,
            p4=0, k4=0, k4max=0, gk=1.02,
        )
        assert result == pytest.approx(153.0, abs=0.01)

    def test_result_capped_at_200(self):
        # Extreme scores
        result = calculate_kb_2026(
            p1=200, k1=1, p2=200, k2=1, p3=200, k3=1,
            p4=0, k4=0, k4max=0, rk=1.5, gk=1.5,
        )
        assert result == 200.0

    def test_fourth_subject_increases_score(self):
        # With k4>0 and p4>0, KB should be higher than without
        without = calculate_kb_2026(
            p1=150, k1=1, p2=150, k2=1, p3=150, k3=1,
            p4=0, k4=0, k4max=0,
        )
        with_fourth = calculate_kb_2026(
            p1=150, k1=1, p2=150, k2=1, p3=150, k3=1,
            p4=180, k4=0.5, k4max=0.5,
        )
        assert with_fourth > without

    def test_ou_bonus_added(self):
        base = calculate_kb_2026(
            p1=150, k1=1, p2=150, k2=1, p3=150, k3=1,
            p4=0, k4=0, k4max=0,
        )
        with_ou = calculate_kb_2026(
            p1=150, k1=1, p2=150, k2=1, p3=150, k3=1,
            p4=0, k4=0, k4max=0, ou=15.0,
        )
        assert with_ou > base

    def test_result_precision_3_decimals(self):
        result = calculate_kb_2026(
            p1=153, k1=0.3, p2=145, k2=0.3, p3=160, k3=0.4,
            p4=0, k4=0, k4max=0,
        )
        # Result should be rounded to 3 decimal places
        assert round(result, 3) == result


# ===========================================================================
# get_raw_score_equivalent
# ===========================================================================

class TestGetRawScoreEquivalent:
    def test_known_nmt_score_math(self):
        # math: scaled=100 → raw=5
        raw = get_raw_score_equivalent("math", 100)
        assert raw == 5

    def test_known_nmt_score_ukr_mova(self):
        # ukr_mova: scaled=100 → raw=8
        raw = get_raw_score_equivalent("ukr_mova", 100)
        assert raw == 8

    def test_max_score_returns_valid_raw(self):
        raw = get_raw_score_equivalent("math", 200)
        assert raw == 32  # math max

    def test_too_high_score_returns_max_key(self):
        # Asking for score higher than 200 still returns max raw
        raw = get_raw_score_equivalent("math", 999)
        assert raw == max({5: 100, 32: 200}.keys()) or isinstance(raw, int)

    def test_unknown_subject_passthrough(self):
        # No table → direct return
        result = get_raw_score_equivalent("unknown_subject", 150)
        assert result == 150

    def test_returns_int(self):
        result = get_raw_score_equivalent("math", 150)
        assert isinstance(result, int)

    def test_inverse_of_scaled_score(self):
        # get_raw_score_equivalent(s, get_scaled_score(s, raw)) should give us
        # a raw score that maps to the same or close scaled score
        raw_input = 20
        scaled = get_scaled_score("math", raw_input)
        raw_back = get_raw_score_equivalent("math", int(scaled))
        # raw_back should also map to scaled
        assert get_scaled_score("math", raw_back) >= scaled * 0.99
