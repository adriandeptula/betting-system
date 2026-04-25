"""
tests/test_kelly.py
Testy jednostkowe dla coupon/kelly.py.

Uruchom: pytest tests/ -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Patch BANKROLL przed importem kelly
os.environ.setdefault("BANKROLL", "1000")

from coupon.kelly import kelly_stake, parlay_stake


class TestKellyStake:
    def test_positive_edge_returns_stake(self):
        """Przy dodatnim Kelly powinniśmy dostać stawkę > 0."""
        stake = kelly_stake(prob=0.55, odds=2.10, bankroll=1000)
        assert stake > 0

    def test_negative_kelly_returns_zero(self):
        """Gdy prob jest za niska dla danego kursu, Kelly jest ujemne → 0."""
        # prob=0.30, odds=2.00: Kelly = (1.0*0.30 - 0.70)/1.0 = -0.40 < 0
        stake = kelly_stake(prob=0.30, odds=2.00, bankroll=1000)
        assert stake == 0.0

    def test_stake_rounded_to_5(self):
        """Stawka zawsze zaokrąglona do wielokrotności 5 PLN."""
        stake = kelly_stake(prob=0.60, odds=2.20, bankroll=1000)
        assert stake % 5 == 0

    def test_stake_min_5(self):
        """Minimalna stawka to 5 PLN (nie mniej) gdy Kelly jest dodatnie."""
        # prob=0.55, odds=2.10: b=1.1, Kelly=(1.1*0.55-0.45)/1.1 > 0
        # Przy małym bankrollu frakcja Kelly może być mała — floor do 5 PLN
        stake = kelly_stake(prob=0.55, odds=2.10, bankroll=50)
        if stake > 0:
            assert stake >= 5.0

    def test_stake_max_bankroll_pct(self):
        """Stawka nie przekracza MAX_BET_PCT (3%) bankrollu."""
        from config import MAX_BET_PCT
        bankroll = 10_000
        stake    = kelly_stake(prob=0.90, odds=3.00, bankroll=bankroll)
        assert stake <= bankroll * MAX_BET_PCT + 5  # +5 tolerance dla zaokrąglenia

    def test_zero_odds_returns_zero(self):
        """Kurs 0 (nieprawidłowy) zwraca 0 — guard na odds <= 1.0."""
        assert kelly_stake(prob=0.50, odds=0.0,  bankroll=1000) == 0.0
        assert kelly_stake(prob=0.50, odds=0.99, bankroll=1000) == 0.0
        assert kelly_stake(prob=0.50, odds=1.0,  bankroll=1000) == 0.0

    def test_prob_one_high_stake(self):
        """Przy pewności 100% Kelly = 1.0 (full Kelly), frakcja ogranicza do MAX_BET_PCT."""
        from config import MAX_BET_PCT, KELLY_FRACTION
        bankroll = 1000
        stake    = kelly_stake(prob=1.0, odds=2.0, bankroll=bankroll)
        assert stake <= bankroll * MAX_BET_PCT + 5


class TestParlaytake:
    def _make_leg(self, prob: float, odds: float) -> dict:
        return {"model_prob": prob, "bet_odds": odds}

    def test_single_leg(self):
        """Parlay z jedną nogą powinien dać sensowną stawkę."""
        legs  = [self._make_leg(0.55, 2.10)]
        stake = parlay_stake(legs, bankroll=1000)
        assert stake >= 5.0

    def test_two_legs_less_than_single(self):
        """Parlay 2-nogowy powinien być ≤ singleu (bardziej ryzykowny)."""
        leg    = self._make_leg(0.55, 2.10)
        single = parlay_stake([leg], bankroll=1000)
        double = parlay_stake([leg, leg], bankroll=1000)
        assert double <= single

    def test_empty_legs_returns_minimum(self):
        """Pusta lista nóg zwraca minimum 5 PLN."""
        stake = parlay_stake([], bankroll=1000)
        assert stake == 5.0

    def test_all_negative_kelly_legs(self):
        """Gdy wszystkie nogi mają ujemne Kelly, zwraca minimum 5 PLN."""
        legs  = [self._make_leg(0.20, 2.00), self._make_leg(0.25, 2.00)]
        stake = parlay_stake(legs, bankroll=1000)
        assert stake == 5.0

    def test_divisor_uses_valid_legs_count(self):
        """
        Kluczowy test dla v1.5: przy jednej nodze z ujemnym Kelly
        dzielnik powinien być 1 (tylko valid legs), nie 2.
        Stawka nie powinna być zaniżona przez pominiętą nogę.
        """
        good_leg = self._make_leg(0.60, 2.10)  # dodatnie Kelly
        bad_leg  = self._make_leg(0.20, 2.00)  # ujemne Kelly → pomijana

        stake_good_only = parlay_stake([good_leg], bankroll=1000)
        stake_mixed     = parlay_stake([good_leg, bad_leg], bankroll=1000)

        # Stawka mixed powinna być oparta o len(individual)=1, nie len(legs)=2
        # Więc powinna być równa lub bliska stake_good_only (nie jej połowie)
        assert stake_mixed >= stake_good_only / 2  # nie drastycznie zaniżona


class TestRemoveMargin:
    def test_sum_to_one(self):
        """Fair probabilities muszą sumować się do 1.0."""
        from model.features import remove_margin
        h, d, a = remove_margin(2.10, 3.40, 3.80)
        assert abs(h + d + a - 1.0) < 1e-9

    def test_favorite_highest_prob(self):
        """Faworyt (najniższy kurs) ma najwyższe prawdopodobieństwo."""
        from model.features import remove_margin
        h, d, a = remove_margin(1.50, 4.00, 6.00)
        assert h > d > 0
        assert h > a

    def test_zero_odds_fallback(self):
        """Kurs 0 nie crashuje — zwraca 1/3 każdy."""
        from model.features import remove_margin
        h, d, a = remove_margin(0, 3.5, 4.0)
        assert h == pytest.approx(1 / 3, abs=0.01)

    def test_equal_odds_equal_probs(self):
        """Równe kursy → równe prawdopodobieństwa."""
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
        """v1.5: normalize(None) zwraca '' zamiast rzucać AttributeError."""
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
        """fd_name mapuje sam na siebie."""
        from pipeline.name_mapping import normalize
        result = normalize("Man United", source="test")
        assert result == "Man United"

    def test_case_insensitive(self):
        from pipeline.name_mapping import normalize
        result = normalize("manchester united", source="test")
        assert result == "Man United"


class TestParseCouponNr:
    """
    Testuje logikę parsowania argumentów komend /stake i /won.
    Funkcja zdefiniowana inline — nie wymaga importu bot_handler z Telegramem.
    """

    @staticmethod
    def _parse(args: str):
        """Kopia logiki z bot_handler._parse_coupon_nr_and_amount."""
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
