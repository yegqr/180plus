"""
Tests for pure helpers in infrastructure/database/repo/results.py.
"""

from infrastructure.database.repo.results import _predict_score


class TestPredictScore:
    def test_fewer_than_5_returns_dash(self):
        assert _predict_score([180, 175, 170, 165]) == "-"

    def test_empty_returns_dash(self):
        assert _predict_score([]) == "-"

    def test_exactly_5_returns_int(self):
        result = _predict_score([180, 175, 170, 165, 160])
        assert isinstance(result, int)

    def test_result_is_positive(self):
        result = _predict_score([180, 175, 170, 165, 160])
        assert result > 0

    def test_stable_scores_predict_near_mean(self):
        # All same scores → sigma_norm=0 → prediction = weighted_sum ≈ first score
        scores = [170] * 5
        result = _predict_score(scores)
        # With zero stdev, sigma_norm=0, so prediction = weighted_sum = 170*1.0 = 170
        assert result == 170

    def test_high_variance_lowers_prediction(self):
        stable = [170, 170, 170, 170, 170]
        volatile = [200, 100, 200, 100, 200]
        p_stable = _predict_score(stable)
        p_volatile = _predict_score(volatile)
        # Volatile sequence should predict lower due to variance penalty
        assert p_stable > p_volatile

    def test_more_than_5_scores_uses_5_weights(self):
        # Function only uses last 5 even if more are passed (zip stops at weights length)
        result = _predict_score([180, 175, 170, 165, 160, 155, 150])
        assert isinstance(result, int)
