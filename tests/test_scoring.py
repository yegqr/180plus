"""
Tests for tgbot/services/scoring.py

All tests are pure/synchronous — no DB, no Telegram, no async.
"""

import pytest

from tgbot.services.scoring import (
    AnswerResult,
    SimulationScore,
    _compare_digits_flexible,
    _compare_float,
    check_random_answer,
    check_simulation_answer,
    is_answer_correct_for_display,
    score_simulation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _choice(answer: str = "А", options: int = 5) -> dict:
    return {"answer": answer, "options": options}


def _short(answer: str) -> dict:
    return {"answer": answer}


def _match(pairs: dict) -> dict:
    return {"pairs": pairs}


# ===========================================================================
# check_simulation_answer — standard subjects
# ===========================================================================

class TestSimulationChoice:
    def test_correct(self):
        r = check_simulation_answer("choice", 1, _choice("А"), "А", "math")
        assert r == AnswerResult(1, 1, True)

    def test_wrong(self):
        r = check_simulation_answer("choice", 1, _choice("А"), "Б", "math")
        assert r == AnswerResult(0, 1, False)

    def test_case_insensitive(self):
        r = check_simulation_answer("choice", 1, _choice("А"), "а", "math")
        assert r == AnswerResult(1, 1, True)

    def test_none_answer(self):
        r = check_simulation_answer("choice", 1, _choice("А"), None, "math")
        assert r == AnswerResult(0, 1, False)

    def test_whitespace_stripped(self):
        r = check_simulation_answer("choice", 1, _choice("А"), " А ", "math")
        assert r == AnswerResult(1, 1, True)


class TestSimulationShort:
    def test_correct_integer_string(self):
        r = check_simulation_answer("short", 1, _short("4"), "4", "math")
        assert r == AnswerResult(2, 2, True)

    def test_correct_float_dot(self):
        r = check_simulation_answer("short", 1, _short("4.5"), "4.5", "math")
        assert r == AnswerResult(2, 2, True)

    def test_correct_float_comma(self):
        r = check_simulation_answer("short", 1, _short("4.5"), "4,5", "math")
        assert r == AnswerResult(2, 2, True)

    def test_wrong_float(self):
        r = check_simulation_answer("short", 1, _short("4.5"), "3.5", "math")
        assert r == AnswerResult(0, 2, False)

    def test_none_answer(self):
        r = check_simulation_answer("short", 1, _short("4.5"), None, "math")
        assert r == AnswerResult(0, 2, False)

    def test_mova_digit_set_correct(self):
        # mova allows flexible digit comparison: sorted digits match
        r = check_simulation_answer("short", 1, _short("123"), "321", "mova")
        assert r == AnswerResult(2, 2, True)

    def test_mova_digit_set_wrong(self):
        r = check_simulation_answer("short", 1, _short("123"), "124", "mova")
        assert r == AnswerResult(0, 2, False)


class TestSimulationMatch:
    def test_all_correct(self):
        pairs = {"1": "А", "2": "Б", "3": "В"}
        r = check_simulation_answer("match", 1, _match(pairs), {"1": "А", "2": "Б", "3": "В"}, "math")
        assert r == AnswerResult(3, 3, True)

    def test_partial_correct(self):
        pairs = {"1": "А", "2": "Б", "3": "В"}
        r = check_simulation_answer("match", 1, _match(pairs), {"1": "А", "2": "Х", "3": "В"}, "math")
        assert r == AnswerResult(2, 3, False)

    def test_none_answer(self):
        pairs = {"1": "А", "2": "Б"}
        r = check_simulation_answer("match", 1, _match(pairs), None, "math")
        assert r == AnswerResult(0, 2, False)

    def test_wrong_type_answer(self):
        pairs = {"1": "А"}
        r = check_simulation_answer("match", 1, _match(pairs), "А", "math")
        assert r == AnswerResult(0, 1, False)


class TestSimulationUnknownType:
    def test_unknown_returns_zero(self):
        r = check_simulation_answer("unknown_type", 1, {}, "anything", "math")
        assert r == AnswerResult(0, 0, False)


# ===========================================================================
# check_simulation_answer — history special rules
# ===========================================================================

class TestSimulationHistory:
    # Q1-20: choice, 1 pt
    def test_q1_choice_correct(self):
        r = check_simulation_answer("choice", 1, _choice("А"), "А", "hist")
        assert r == AnswerResult(1, 1, True)

    def test_q20_choice_correct(self):
        r = check_simulation_answer("choice", 20, _choice("Б"), "Б", "hist")
        assert r == AnswerResult(1, 1, True)

    def test_q1_choice_wrong(self):
        r = check_simulation_answer("choice", 1, _choice("А"), "Б", "hist")
        assert r == AnswerResult(0, 1, False)

    # Q21-24: match, 4 pts (1 per pair)
    def test_q21_match_all_correct(self):
        pairs = {"1": "А", "2": "Б", "3": "В", "4": "Г"}
        r = check_simulation_answer("match", 21, _match(pairs), pairs, "hist")
        assert r == AnswerResult(4, 4, True)

    def test_q21_match_partial(self):
        pairs = {"1": "А", "2": "Б", "3": "В", "4": "Г"}
        user = {"1": "А", "2": "Б", "3": "Х", "4": "Г"}
        r = check_simulation_answer("match", 21, _match(pairs), user, "hist")
        assert r == AnswerResult(3, 4, False)

    def test_q24_match_max_4(self):
        pairs = {"1": "А", "2": "Б"}
        r = check_simulation_answer("match", 24, _match(pairs), pairs, "hist")
        assert r.max_points == 4

    # Q25-27: sequence, 3 pts
    def test_q25_sequence_all_correct(self):
        correct = _short("123")
        r = check_simulation_answer("short", 25, correct, "123", "hist")
        assert r == AnswerResult(3, 3, True)

    def test_q25_sequence_partial(self):
        # Position 0 correct (1==1), position 1 wrong (2≠3), position 2 wrong (3≠2)
        correct = _short("123")
        r = check_simulation_answer("short", 25, correct, "132", "hist")
        assert r.points_earned == 1
        assert r.max_points == 3

    def test_q27_sequence_none(self):
        r = check_simulation_answer("short", 27, _short("123"), None, "hist")
        assert r == AnswerResult(0, 3, False)

    # Q28-30: cluster, 3 pts
    def test_q28_cluster_full_overlap(self):
        correct = _short("123")
        r = check_simulation_answer("short", 28, correct, "123", "hist")
        assert r == AnswerResult(3, 3, True)

    def test_q28_cluster_partial_overlap(self):
        # correct digits {1,2,3}, user digits {1,2,4} → overlap = {1,2} → 2 pts
        correct = _short("123")
        r = check_simulation_answer("short", 28, correct, "124", "hist")
        assert r.points_earned == 2

    def test_q30_cluster_no_overlap(self):
        correct = _short("123")
        r = check_simulation_answer("short", 30, correct, "456", "hist")
        assert r.points_earned == 0


# ===========================================================================
# check_random_answer
# ===========================================================================

class TestRandomChoice:
    def test_correct(self):
        r = check_random_answer("choice", _choice("А"), "А", "math")
        assert r == AnswerResult(1, 1, True)

    def test_wrong(self):
        r = check_random_answer("choice", _choice("А"), "Б", "math")
        assert r == AnswerResult(0, 1, False)


class TestRandomShort:
    def test_math_2pts(self):
        r = check_random_answer("short", _short("4.5"), "4.5", "math")
        assert r == AnswerResult(2, 2, True)

    def test_hist_3pts(self):
        r = check_random_answer("short", _short("4"), "4", "hist")
        assert r == AnswerResult(3, 3, True)

    def test_hist_wrong(self):
        r = check_random_answer("short", _short("4"), "5", "hist")
        assert r == AnswerResult(0, 3, False)

    def test_comma_notation(self):
        r = check_random_answer("short", _short("4.5"), "4,5", "math")
        assert r == AnswerResult(2, 2, True)


class TestRandomMatch:
    def test_all_correct_is_correct_true(self):
        pairs = {"1": "А", "2": "Б"}
        r = check_random_answer("match", _match(pairs), {"1": "А", "2": "Б"}, "math")
        assert r.is_correct is True

    def test_partial_is_correct_false(self):
        pairs = {"1": "А", "2": "Б"}
        r = check_random_answer("match", _match(pairs), {"1": "А", "2": "Х"}, "math")
        assert r.is_correct is False
        assert r.points_earned == 1


# ===========================================================================
# is_answer_correct_for_display
# ===========================================================================

class TestCorrectForDisplay:
    def test_choice_correct(self):
        assert is_answer_correct_for_display("choice", _choice("А"), "А", "math") is True

    def test_choice_wrong(self):
        assert is_answer_correct_for_display("choice", _choice("А"), "Б", "math") is False

    def test_short_float(self):
        assert is_answer_correct_for_display("short", _short("4.5"), "4,5", "math") is True

    def test_short_wrong(self):
        assert is_answer_correct_for_display("short", _short("4.5"), "3.5", "math") is False

    def test_match_all_correct(self):
        pairs = {"1": "А", "2": "Б"}
        assert is_answer_correct_for_display("match", _match(pairs), {"1": "А", "2": "Б"}, "math") is True

    def test_match_partial_is_false(self):
        pairs = {"1": "А", "2": "Б"}
        assert is_answer_correct_for_display("match", _match(pairs), {"1": "А", "2": "Х"}, "math") is False

    def test_unknown_type_false(self):
        assert is_answer_correct_for_display("unknown", {}, "anything", "math") is False

    def test_none_answer_false(self):
        assert is_answer_correct_for_display("choice", _choice("А"), None, "math") is False


# ===========================================================================
# score_simulation (integration of scoring logic)
# ===========================================================================

class TestScoreSimulation:
    def _make_questions(self):
        return [
            {"id": 1, "q_number": 1, "q_type": "choice",  "correct_answer": _choice("А")},
            {"id": 2, "q_number": 2, "q_type": "short",   "correct_answer": _short("4.5")},
            {"id": 3, "q_number": 3, "q_type": "match",   "correct_answer": _match({"1": "А", "2": "Б"})},
        ]

    def test_all_correct(self):
        qs = self._make_questions()
        answers = {"1": "А", "2": "4.5", "3": {"1": "А", "2": "Б"}}
        result = score_simulation(qs, answers, "math", "main", user_id=42)
        assert result.total_score == 1 + 2 + 2   # choice=1, short=2, match=2
        assert result.total_max == 1 + 2 + 2
        assert len(result.logs_data) == 3

    def test_all_wrong(self):
        qs = self._make_questions()
        answers = {"1": "Б", "2": "0", "3": {"1": "Х", "2": "Х"}}
        result = score_simulation(qs, answers, "math", "main", user_id=42)
        assert result.total_score == 0

    def test_unanswered_not_logged(self):
        qs = self._make_questions()
        answers = {"1": "А"}  # only answered Q1
        result = score_simulation(qs, answers, "math", "main", user_id=42)
        assert len(result.logs_data) == 1
        assert result.logs_data[0]["question_id"] == 1

    def test_logs_contain_required_keys(self):
        qs = self._make_questions()
        answers = {"1": "А"}
        result = score_simulation(qs, answers, "math", "ses1", user_id=99)
        log = result.logs_data[0]
        assert log["user_id"] == 99
        assert log["session_id"] == "ses1"
        assert log["mode"] == "simulation"
        assert log["is_correct"] is True

    def test_returns_simulation_score_type(self):
        qs = self._make_questions()
        result = score_simulation(qs, {}, "math", "s", user_id=1)
        assert isinstance(result, SimulationScore)

    def test_history_subject_uses_q_number_rules(self):
        """Q21 in hist uses match-4pts rule, not standard match."""
        qs = [
            {"id": 21, "q_number": 21, "q_type": "match",
             "correct_answer": _match({"1": "А", "2": "Б", "3": "В", "4": "Г"})}
        ]
        answers = {"21": {"1": "А", "2": "Б", "3": "В", "4": "Г"}}
        result = score_simulation(qs, answers, "hist", "main", user_id=1)
        assert result.total_max == 4
        assert result.total_score == 4


# ===========================================================================
# _compare_float
# ===========================================================================

class TestCompareFloat:
    def test_equal_dot_notation(self):
        assert _compare_float("4.5", "4.5") is True

    def test_comma_vs_dot(self):
        assert _compare_float("4,5", "4.5") is True

    def test_both_comma(self):
        assert _compare_float("4,5", "4,5") is True

    def test_not_equal(self):
        assert _compare_float("3.5", "4.5") is False

    def test_invalid_user_returns_false(self):
        assert _compare_float("abc", "4.5") is False

    def test_invalid_correct_returns_false(self):
        assert _compare_float("4.5", "xyz") is False

    def test_none_user_returns_false(self):
        # AttributeError on None.replace → caught
        assert _compare_float(None, "4.5") is False  # type: ignore[arg-type]

    def test_both_invalid_returns_false(self):
        assert _compare_float("abc", "xyz") is False

    def test_integer_strings(self):
        assert _compare_float("4", "4.0") is True


# ===========================================================================
# _compare_digits_flexible
# ===========================================================================

class TestCompareDigitsFlexible:
    def test_same_order_correct(self):
        assert _compare_digits_flexible("123", "123") is True

    def test_different_order_correct(self):
        assert _compare_digits_flexible("321", "123") is True

    def test_different_digits_wrong(self):
        assert _compare_digits_flexible("124", "123") is False

    def test_non_digit_user_returns_false(self):
        assert _compare_digits_flexible("abc", "123") is False

    def test_non_digit_correct_returns_false(self):
        assert _compare_digits_flexible("123", "abc") is False

    def test_mixed_alpha_digit_user_false(self):
        assert _compare_digits_flexible("1a3", "123") is False

    def test_empty_strings(self):
        # "".isdigit() is False → False
        assert _compare_digits_flexible("", "") is False

    def test_different_length_wrong(self):
        assert _compare_digits_flexible("12", "123") is False


# ===========================================================================
# _score_history Q25-30 dict-answer path (untested branch)
# ===========================================================================

class TestSimulationHistoryDictAnswer:
    """
    Q25-30 when user_answer is a dict (pairs) instead of a digit string.
    This exercises the `isinstance(user_answer, dict)` branch in _score_history.
    """

    def test_q25_dict_all_pairs_correct(self):
        # dict path: counts matching pairs, capped at 3
        pairs = {"1": "А", "2": "Б", "3": "В"}
        r = check_simulation_answer("short", 25, _match(pairs), {"1": "А", "2": "Б", "3": "В"}, "hist")
        assert r == AnswerResult(3, 3, True)

    def test_q25_dict_partial_pairs(self):
        pairs = {"1": "А", "2": "Б", "3": "В"}
        r = check_simulation_answer("short", 25, _match(pairs), {"1": "А", "2": "Х", "3": "В"}, "hist")
        assert r.points_earned == 2
        assert r.max_points == 3

    def test_q25_dict_no_correct_pairs(self):
        pairs = {"1": "А", "2": "Б", "3": "В"}
        r = check_simulation_answer("short", 25, _match(pairs), {"1": "Х", "2": "Х", "3": "Х"}, "hist")
        assert r.points_earned == 0

    def test_q28_dict_all_pairs_correct(self):
        # Same dict path applies for cluster questions (28-30)
        pairs = {"1": "А", "2": "Б", "3": "В"}
        r = check_simulation_answer("short", 28, _match(pairs), {"1": "А", "2": "Б", "3": "В"}, "hist")
        assert r == AnswerResult(3, 3, True)

    def test_q30_dict_capped_at_3_even_if_more_pairs(self):
        # 4 correct pairs → still max 3 pts
        pairs = {"1": "А", "2": "Б", "3": "В", "4": "Г"}
        r = check_simulation_answer("short", 30, _match(pairs), {"1": "А", "2": "Б", "3": "В", "4": "Г"}, "hist")
        assert r.points_earned == 3
        assert r.max_points == 3

    def test_q27_dict_empty_user_answer(self):
        pairs = {"1": "А", "2": "Б", "3": "В"}
        r = check_simulation_answer("short", 27, _match(pairs), {}, "hist")
        # empty dict is falsy → user_answer branch not entered → 0 pts
        assert r.points_earned == 0
