"""
coupon/kelly.py
Kryterium Kelly do obliczania optymalnych stawek.

Używamy frakcjonalnego Kelly (KELLY_FRACTION = 0.25) dla bezpieczeństwa.
Pełne Kelly jest zbyt agresywne przy niepewności modelu.

v1.5 poprawka:
  - parlay_stake(): base = min(individual) / len(individual)
    Poprzednio był len(legs), co zaniżało stawkę gdy któraś noga
    miała ujemne Kelly (kelly_stake=0) i była pomijana z listy individual.
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
        Zalecana stawka w PLN (zaokrąglona do 5 PLN, min 5 PLN).
        Zwraca 0.0 gdy Kelly jest ujemne (brak wartości).
    """
    if odds <= 1.0:
        return 0.0   # kurs <= 1.0 jest nieprawidłowy (nie ma zysku netto)

    b = odds - 1.0   # zysk netto na jednostkę stawki
    q = 1.0 - prob   # P(przegrana)

    full_kelly = (b * prob - q) / b

    if full_kelly <= 0:
        return 0.0   # ujemne Kelly = brak wartości

    fractional = full_kelly * KELLY_FRACTION
    max_stake  = bankroll * MAX_BET_PCT
    stake      = min(fractional * bankroll, max_stake)
    stake      = max(5.0, stake)
    stake      = round(stake / 5) * 5   # zaokrąglij do 5 PLN

    return float(stake)


def parlay_stake(legs: list, bankroll: float = BANKROLL) -> float:
    """
    Oblicza stawkę na parlay (akumulator).

    Strategia: min indywidualnych stawek Kelly / liczba NÓG Z DODATNIM KELLY.
    Im więcej nóg, tym mniejsza stawka (wyższe ryzyko).

    v1.5 poprawka: dzielnik to len(individual) nie len(legs).
    Nogi z ujemnym Kelly (kelly_stake=0) są pomijane z obliczeń –
    poprzedni kod nieprawidłowo uwzględniał je w dzielniku.
    """
    if not legs:
        return 5.0

    individual = []
    for leg in legs:
        s = kelly_stake(leg["model_prob"], leg["bet_odds"], bankroll)
        if s > 0:
            individual.append(s)

    if not individual:
        return 5.0

    # Dzielnik = liczba nóg z dodatnim Kelly (nie wszystkich nóg)
    base = min(individual) / len(individual)
    base = max(5.0, base)
    return float(round(base / 5) * 5)
