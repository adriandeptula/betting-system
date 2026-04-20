"""
coupon/kelly.py
Kryterium Kelly do obliczania optymalnych stawek.

Używamy frakcjonalnego Kelly (KELLY_FRACTION = 0.25) dla bezpieczeństwa.
Pełne Kelly jest zbyt agresywne przy niepewności modelu.
"""
from config import BANKROLL, KELLY_FRACTION, MAX_BET_PCT


def kelly_stake(prob: float, odds: float, bankroll: float = BANKROLL) -> float:
    """
    Oblicza optymalną stawkę wg frakcjonalnego kryterium Kelly.

    Args:
        prob:     prawdopodobieństwo wygranej wg modelu
        odds:     kurs bukmachera (decimal, np. 2.10)
        bankroll: dostępny bankroll w PLN

    Returns:
        Zalecana stawka w PLN (zaokrąglona do 5 PLN, min 5 PLN)
    """
    b = odds - 1.0           # Zysk netto na jednostkę stawki
    q = 1.0 - prob           # P(przegrana)

    full_kelly = (b * prob - q) / b

    if full_kelly <= 0:
        return 0.0           # Ujemne Kelly = brak wartości

    fractional = full_kelly * KELLY_FRACTION
    max_stake   = bankroll * MAX_BET_PCT
    stake       = min(fractional * bankroll, max_stake)
    stake       = max(5.0, stake)          # minimum 5 PLN
    stake       = round(stake / 5) * 5    # zaokrąglij do 5 PLN

    return float(stake)


def parlay_stake(legs: list, bankroll: float = BANKROLL) -> float:
    """
    Oblicza stawkę na parlay (akumulator).
    Używa min indywidualnych stawek Kelly podzielonych przez ilość nóg.

    Im więcej nóg, tym mniejsza stawka (wyższe ryzyko).
    """
    if not legs:
        return 5.0

    individual = [
        kelly_stake(leg["model_prob"], leg["bet_odds"], bankroll)
        for leg in legs
        if kelly_stake(leg["model_prob"], leg["bet_odds"], bankroll) > 0
    ]

    if not individual:
        return 5.0

    # Konserwatywnie: min stawka / liczba nóg
    base = min(individual) / len(legs)
    base = max(5.0, base)
    return float(round(base / 5) * 5)
