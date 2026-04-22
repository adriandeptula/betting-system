"""
coupon/value_engine.py
Identyfikuje value bety – zakłady gdzie model widzi wyższą
szansę wygranej niż sugeruje kurs bukmachera.

Value bet: model_prob > market_prob + MIN_EDGE

v1.2: double chance markets (1X, X2, 12) wyprowadzane z kursów h2h.
  Nie wymagają dodatkowych requestów do The Odds API.
  Kursy i prawdopodobieństwa rynkowe liczone ze znormalizowanych h2h.
  Osobny zakres kursów: DC_MIN_ODDS / DC_MAX_ODDS (niższy niż 1X2).
"""
import logging

from config import (
    DC_MIN_MODEL_PROB,
    DC_MIN_ODDS,
    DC_MAX_ODDS,
    MAX_ODDS,
    MIN_EDGE,
    MIN_MODEL_PROB,
    MIN_ODDS,
)

log = logging.getLogger(__name__)


def _dc_odds(market_prob: float) -> float:
    """Oblicza fair odds dla double chance z prawdopodobieństwa rynkowego."""
    if market_prob <= 0:
        return 0.0
    return round(1.0 / market_prob, 2)


def find_value_bets(predictions: list) -> list:
    """
    Skanuje predykcje w poszukiwaniu value betów.
    Sprawdza zarówno 1X2 jak i double chance (1X, X2, 12).

    Args:
        predictions: lista słowników z predict_matches()

    Returns:
        Lista value betów posortowana malejąco po edge.
    """
    value_bets = []

    for match in predictions:
        mh = match["market_prob_home"]
        md = match["market_prob_draw"]
        ma = match["market_prob_away"]

        # ── Kandydaci 1X2 ────────────────────────────────────────────────────
        candidates_1x2 = [
            {
                "outcome":    "H",
                "label":      "Wygrana gospodarza",
                "model_prob": match["prob_home"],
                "market_prob": mh,
                "odds":       match["odds_home"],
                "min_odds":   MIN_ODDS,
                "max_odds":   MAX_ODDS,
                "min_prob":   MIN_MODEL_PROB,
            },
            {
                "outcome":    "D",
                "label":      "Remis",
                "model_prob": match["prob_draw"],
                "market_prob": md,
                "odds":       match["odds_draw"],
                "min_odds":   MIN_ODDS,
                "max_odds":   MAX_ODDS,
                "min_prob":   MIN_MODEL_PROB,
            },
            {
                "outcome":    "A",
                "label":      "Wygrana gościa",
                "model_prob": match["prob_away"],
                "market_prob": ma,
                "odds":       match["odds_away"],
                "min_odds":   MIN_ODDS,
                "max_odds":   MAX_ODDS,
                "min_prob":   MIN_MODEL_PROB,
            },
        ]

        # ── Kandydaci double chance (wyprowadzone z h2h, 0 dodatkowych req) ──
        candidates_dc = [
            {
                "outcome":    "1X",
                "label":      "Gospodarz lub remis",
                "model_prob": match["prob_home"] + match["prob_draw"],
                "market_prob": mh + md,
                "odds":       _dc_odds(mh + md),
                "min_odds":   DC_MIN_ODDS,
                "max_odds":   DC_MAX_ODDS,
                "min_prob":   DC_MIN_MODEL_PROB,
            },
            {
                "outcome":    "X2",
                "label":      "Remis lub gość",
                "model_prob": match["prob_draw"] + match["prob_away"],
                "market_prob": md + ma,
                "odds":       _dc_odds(md + ma),
                "min_odds":   DC_MIN_ODDS,
                "max_odds":   DC_MAX_ODDS,
                "min_prob":   DC_MIN_MODEL_PROB,
            },
            {
                "outcome":    "12",
                "label":      "Gospodarz lub gość (bez remisu)",
                "model_prob": match["prob_home"] + match["prob_away"],
                "market_prob": mh + ma,
                "odds":       _dc_odds(mh + ma),
                "min_odds":   DC_MIN_ODDS,
                "max_odds":   DC_MAX_ODDS,
                "min_prob":   DC_MIN_MODEL_PROB,
            },
        ]

        for c in candidates_1x2 + candidates_dc:
            edge = c["model_prob"] - c["market_prob"]
            odds = c["odds"]

            # ── Filtry jakości ────────────────────────────────────────────────
            if edge < MIN_EDGE:
                continue                          # Zbyt mały edge
            if odds <= 0 or odds < c["min_odds"] or odds > c["max_odds"]:
                continue                          # Poza zakresem kursów
            if c["model_prob"] < c["min_prob"]:
                continue                          # Za mała pewność modelu
            if c["market_prob"] <= 0:
                continue                          # Brak danych rynkowych

            ev = (c["model_prob"] * odds) - 1.0  # Expected Value

            vb = {
                **match,
                "bet_outcome":    c["outcome"],
                "bet_label":      c["label"],
                "bet_odds":       odds,
                "model_prob":     c["model_prob"],
                "market_prob":    c["market_prob"],
                "edge":           edge,
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
