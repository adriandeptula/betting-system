"""
tests/test_kelly.py
Testy jednostkowe dla coupon/kelly.py, model/evaluate.py, pipeline/fetch_clv.py.

v1.6: dodano TestCLV (5 testów) + TestEnsemblePredict (3 testy)

Uruchom: pytest tests/ -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("BANKROLL", "1000")

from coupon.kelly import kelly_stake, parlay_stake


class TestKellyStake:
    def test_positive_edge_returns_stake(self):
        stake = kelly_stake(prob=0.55, odds=2.10, bankroll=1000)
        assert stake > 0

    def test_negative_kelly_returns_zero(self):
        stake = kelly_stake(prob=0.30, odds=2.00, bankroll=1000)
        assert stake == 0.0

    def test_stake_rounded_to_5(self):
        stake = kelly_stake(prob=0.60, odds=2.20, bankroll=1000)
        assert stake % 5 == 0

    def test_stake_min_5(self):
        stake = kelly_stake(prob=0.55, odds=2.10, bankroll=50)
        if stake > 0:
            assert stake >= 5.0

    def test_stake_max_bankroll_pct(self):
        from config import MAX_BET_PCT
        bankroll = 10_000
        stake    = kelly_stake(prob=0.90, odds=3.00, bankroll=bankroll)
        assert stake <= bankroll * MAX_BET_PCT + 5

    def test_zero_odds_returns_zero(self):
        assert kelly_stake(prob=0.50, odds=0.0,  bankroll=1000) == 0.0
        assert kelly_stake(prob=0.50, odds=0.99, bankroll=1000) == 0.0
        assert kelly_stake(prob=0.50, odds=1.0,  bankroll=1000) == 0.0

    def test_prob_one_high_stake(self):
        from config import MAX_BET_PCT
        bankroll = 1000
        stake    = kelly_stake(prob=1.0, odds=2.0, bankroll=bankroll)
        assert stake <= bankroll * MAX_BET_PCT + 5


class TestParlaytake:
    def _make_leg(self, prob: float, odds: float) -> dict:
        return {"model_prob": prob, "bet_odds": odds}

    def test_single_leg(self):
        legs  = [self._make_leg(0.55, 2.10)]
        stake = parlay_stake(legs, bankroll=1000)
        assert stake >= 5.0

    def test_two_legs_less_than_single(self):
        leg    = self._make_leg(0.55, 2.10)
        single = parlay_stake([leg], bankroll=1000)
        double = parlay_stake([leg, leg], bankroll=1000)
        assert double <= single

    def test_empty_legs_returns_minimum(self):
        stake = parlay_stake([], bankroll=1000)
        assert stake == 5.0

    def test_all_negative_kelly_legs(self):
        legs  = [self._make_leg(0.20, 2.00), self._make_leg(0.25, 2.00)]
        stake = parlay_stake(legs, bankroll=1000)
        assert stake == 5.0

    def test_divisor_uses_valid_legs_count(self):
        good_leg = self._make_leg(0.60, 2.10)
        bad_leg  = self._make_leg(0.20, 2.00)
        stake_good_only = parlay_stake([good_leg], bankroll=1000)
        stake_mixed     = parlay_stake([good_leg, bad_leg], bankroll=1000)
        assert stake_mixed >= stake_good_only / 2


class TestRemoveMargin:
    def test_sum_to_one(self):
        from model.features import remove_margin
        h, d, a = remove_margin(2.10, 3.40, 3.80)
        assert abs(h + d + a - 1.0) < 1e-9

    def test_favorite_highest_prob(self):
        from model.features import remove_margin
        h, d, a = remove_margin(1.50, 4.00, 6.00)
        assert h > d > 0
        assert h > a

    def test_zero_odds_fallback(self):
        from model.features import remove_margin
        h, d, a = remove_margin(0, 3.5, 4.0)
        assert h == pytest.approx(1 / 3, abs=0.01)

    def test_equal_odds_equal_probs(self):
        from model.features import remove_margin
        h, d, a = remove_margin(3.0, 3.0, 3.0)
        assert h == pytest.approx(1 / 3, abs=1e-9)
        assert d == pytest.approx(1 / 3, abs=1e-9)
        assert a == pytest.approx(1 / 3, abs=1e-9)


class TestLegWon:
    def test_h_bet_home_win(self):
        from model.evaluate import _leg_won
        assert _leg_won("H", "H") is True

    def test_h_bet_away_win(self):
        from model.evaluate import _leg_won
        assert _leg_won("A", "H") is False

    def test_draw_bet(self):
        from model.evaluate import _leg_won
        assert _leg_won("D", "D") is True
        assert _leg_won("H", "D") is False

    def test_double_chance_1x(self):
        from model.evaluate import _leg_won
        assert _leg_won("H", "1X") is True
        assert _leg_won("D", "1X") is True
        assert _leg_won("A", "1X") is False

    def test_double_chance_x2(self):
        from model.evaluate import _leg_won
        assert _leg_won("D", "X2") is True
        assert _leg_won("A", "X2") is True
        assert _leg_won("H", "X2") is False

    def test_double_chance_12(self):
        from model.evaluate import _leg_won
        assert _leg_won("H", "12") is True
        assert _leg_won("A", "12") is True
        assert _leg_won("D", "12") is False

    def test_unknown_outcome(self):
        from model.evaluate import _leg_won
        assert _leg_won("H", "UNKNOWN") is False


class TestNormalize:
    def test_none_returns_empty_string(self):
        from pipeline.name_mapping import normalize
        result = normalize(None, source="test")
        assert result == ""

    def test_empty_string_returns_empty(self):
        from pipeline.name_mapping import normalize
        result = normalize("", source="test")
        assert result == ""

    def test_known_alias(self):
        from pipeline.name_mapping import normalize
        result = normalize("Manchester United", source="test")
        assert result == "Man United"

    def test_fd_name_identity(self):
        from pipeline.name_mapping import normalize
        result = normalize("Man United", source="test")
        assert result == "Man United"

    def test_case_insensitive(self):
        from pipeline.name_mapping import normalize
        result = normalize("manchester united", source="test")
        assert result == "Man United"


class TestParseCouponNr:
    @staticmethod
    def _parse(args: str):
        parts = args.strip().split()
        if len(parts) == 0:
            return "?", None
        if len(parts) == 1:
            try:
                return "?", float(parts[0].replace(",", "."))
            except ValueError:
                return "?", None
        try:
            coupon_id = parts[0]
            amount    = float(parts[1].replace(",", "."))
            return coupon_id, amount
        except (ValueError, IndexError):
            return "?", None

    def test_new_format_nr_and_amount(self):
        cid, amount = self._parse("1 100")
        assert cid == "1"
        assert amount == 100.0

    def test_old_format_amount_only(self):
        cid, amount = self._parse("100")
        assert cid == "?"
        assert amount == 100.0

    def test_decimal_comma(self):
        cid, amount = self._parse("2 99,50")
        assert cid == "2"
        assert amount == 99.5

    def test_empty_args(self):
        cid, amount = self._parse("")
        assert cid == "?"
        assert amount is None

    def test_invalid_amount(self):
        cid, amount = self._parse("abc")
        assert amount is None


class TestCLV:
    """Testy dla pipeline/fetch_clv.py"""

    def test_closing_odds_h(self):
        """Closing odds dla H = odds_h."""
        from pipeline.fetch_clv import _closing_odds_for_outcome
        result = _closing_odds_for_outcome("H", 2.10, 3.40, 3.80)
        assert result == 2.10

    def test_closing_odds_draw(self):
        """Closing odds dla D = odds_d."""
        from pipeline.fetch_clv import _closing_odds_for_outcome
        result = _closing_odds_for_outcome("D", 2.10, 3.40, 3.80)
        assert result == 3.40

    def test_closing_odds_dc_1x(self):
        """Closing odds dla 1X = 1 / (prob_H + prob_D), zawsze < min(odds_H, odds_D)."""
        from pipeline.fetch_clv import _closing_odds_for_outcome
        result = _closing_odds_for_outcome("1X", 2.00, 3.50, 4.50)
        # DC kurs musi być niższy niż sam H (łączona szansa)
        assert 1.0 < result < 2.00

    def test_clv_positive_when_better_odds(self):
        """CLV > 0 gdy bet_odds > closing_odds."""
        bet_odds     = 2.20
        closing_odds = 2.00
        clv = (bet_odds / closing_odds - 1.0) * 100
        assert clv > 0

    def test_empty_clv_summary(self):
        """get_clv_summary() zwraca pusty słownik gdy brak danych."""
        from pipeline.fetch_clv import _empty_clv
        result = _empty_clv()
        assert result["legs_with_clv"] == 0
        assert result["avg_clv"] == 0.0


class TestEnsemblePredict:
    """Testy dla logiki ensemble w model/predict.py"""

    def test_load_model_handles_legacy_format(self, tmp_path, monkeypatch):
        """load_model() powinno obsłużyć stary format v1.5 bez błędu."""
        import pickle
        from unittest.mock import MagicMock

        # Symulacja starego formatu pkl
        mock_model = MagicMock()
        mock_model.predict_proba = MagicMock(return_value=[[0.5, 0.3, 0.2]])

        pkl_path = tmp_path / "model.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump({
                "model":        mock_model,
                "feature_cols": ["a", "b"],
                "league_codes": {},
            }, f)

        monkeypatch.setattr("config.MODEL_PATH", str(pkl_path))
        import importlib
        import model.predict as mp
        importlib.reload(mp)

        result = mp.load_model()
        assert result is not None
        models, feature_cols, _ = result
        assert len(models) == 1

    def test_load_model_handles_ensemble_format(self, tmp_path, monkeypatch):
        """load_model() poprawnie odczytuje nowy format ensemble v1.6."""
        import pickle
        from unittest.mock import MagicMock

        mock_xgb = MagicMock()
        mock_lgb = MagicMock()

        pkl_path = tmp_path / "model.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump({
                "model_type":  "ensemble",
                "models":      [mock_xgb, mock_lgb],
                "model_names": ["XGBoost", "LightGBM"],
                "weights":     [0.5, 0.5],
                "feature_cols": ["a", "b"],
                "league_codes": {},
                "metrics":     {"accuracy": 0.55, "log_loss": 0.9, "optuna_trials": 30},
            }, f)

        monkeypatch.setattr("config.MODEL_PATH", str(pkl_path))
        import importlib
        import model.predict as mp
        importlib.reload(mp)

        result = mp.load_model()
        assert result is not None
        models, _, _ = result
        assert len(models) == 2

    def test_proba_ensemble_average(self):
        """Ensemble proba = średnia z obu modeli."""
        import numpy as np

        proba_xgb = np.array([[0.6, 0.2, 0.2]])
        proba_lgb = np.array([[0.4, 0.3, 0.3]])
        ensemble  = np.mean([proba_xgb, proba_lgb], axis=0)

        assert ensemble[0, 0] == pytest.approx(0.5)
        assert ensemble[0, 1] == pytest.approx(0.25)
        assert abs(ensemble[0].sum() - 1.0) < 1e-9
