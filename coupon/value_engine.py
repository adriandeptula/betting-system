"""
coupon/value_engine.py
Identyfikuje value bety – zakłady gdzie model widzi wyższą
szansę wygranej niż sugeruje kurs bukmachera.

Value bet: model_prob > market_prob + MIN_EDGE
"""
import logging

from config import MAX_ODDS, MIN_EDGE, MIN_MODEL_PROB, MIN_ODDS

log = logging.getLogger(__name__)


def find_value_bets(predictions: list) -> list:
    """
    Skanuje predykcje w poszukiwaniu value betów.

    Args:
        predictions: lista słowników z predict_matches()

    Returns:
        Lista value betów posortowana malejąco po edge.
    """
    value_bets = []

    for match in predictions:
        candidates = [
            {
                "outcome":      "H",
                "label":        "Wygrana gospodarza",
                "model_prob":   match["prob_home"],
                "market_prob":  match["market_prob_home"],
                "odds":         match["odds_home"],
            },
            {
                "outcome":      "D",
                "label":        "Remis",
                "model_prob":   match["prob_draw"],
                "market_prob":  match["market_prob_draw"],
                "odds":         match["odds_draw"],
            },
            {
                "outcome":      "A",
                "label":        "Wygrana gościa",
                "model_prob":   match["prob_away"],
                "market_prob":  match["market_prob_away"],
                "odds":         match["odds_away"],
            },
        ]

        for c in candidates:
            edge = c["model_prob"] - c["market_prob"]
            odds = c["odds"]

            # ── Filtry jakości ────────────────────────────────────────────
            if edge < MIN_EDGE:
                continue                          # Zbyt mały edge
            if odds < MIN_ODDS or odds > MAX_ODDS:
                continue                          # Poza zakresem kursów
            if c["model_prob"] < MIN_MODEL_PROB:
                continue                          # Za mała pewność modelu
            if c["market_prob"] <= 0:
                continue                          # Brak danych rynkowych

            ev = (c["model_prob"] * odds) - 1.0  # Expected Value

            vb = {
                **match,
                "bet_outcome":  c["outcome"],
                "bet_label":    c["label"],
                "bet_odds":     odds,
                "model_prob":   c["model_prob"],
                "market_prob":  c["market_prob"],
                "edge":         edge,
                "expected_value": ev,
            }
            value_bets.append(vb)

            log.info(
                f"✓ VALUE BET: {match['home_team']} vs {match['away_team']} "
                f"[{c['outcome']}] kurs={odds:.2f} "
                f"model={c['model_prob']:.0%} rynek={c['market_prob']:.0%} "
                f"edge=+{edge:.1%} EV=+{ev:.1%}"
            )

    # Sortuj: najpierw największy edge
    value_bets.sort(key=lambda x: x["edge"], reverse=True)

    log.info(f"Znaleziono {len(value_bets)} value betów z {len(predictions)} meczów")
    return value_bets
