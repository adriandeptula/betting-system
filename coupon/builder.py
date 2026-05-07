"""
coupon/builder.py
Buduje kupony bukmacherskie z listy value betów.

Strategia:
  1. Singiel  – najlepszy value bet (największy edge)
  2. Podwójny – 2 kolejne value bety (rozłączne mecze)
  3. Potrójny – 3 kolejne value bety (jeśli wystarczy)

Kupony są rozłączne (każdy mecz max w jednym kuponie).

v1.6:
  - _slim_leg(): przechowuje tylko 11 pól niezbędnych do rozliczania,
    wyświetlania i CLV. Usuwa 9 zbędnych pól (odds_home/draw/away,
    prob_home/draw/away, market_prob_home/draw/away, expected_value)
    które nigdy nie były odczytywane po zapisie.
    Redukuje rozmiar coupons_history.json o ~45%.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from config import COUPONS_PER_WEEK, DATA_RESULTS
from coupon.kelly import kelly_stake, parlay_stake

log = logging.getLogger(__name__)


def _slim_leg(vb: dict) -> dict:
    """
    Tworzy odchudzoną reprezentację nogi z value_bet dict.

    Zachowane pola:
      - rozliczanie (evaluate.py):  match_id, home_team, away_team,
                                    league_code, bet_outcome
      - wyświetlanie (telegram.py): home_team, away_team, league_code,
                                    bet_label, bet_odds, model_prob,
                                    market_prob, edge
      - CLV (fetch_clv.py):        match_id, home_team, away_team,
                                    bet_outcome, bet_odds
      - info o czasie:              commence_time

    Odrzucone (zbędne po wyborze zakładu):
      odds_home/draw/away, prob_home/draw/away,
      market_prob_home/draw/away, expected_value
    """
    return {
        "match_id":      vb.get("match_id", ""),
        "home_team":     vb.get("home_team", ""),
        "away_team":     vb.get("away_team", ""),
        "league_code":   vb.get("league_code", ""),
        "commence_time": vb.get("commence_time", ""),
        "bet_outcome":   vb.get("bet_outcome", ""),
        "bet_label":     vb.get("bet_label", ""),
        "bet_odds":      vb.get("bet_odds", 0.0),
        "model_prob":    vb.get("model_prob", 0.0),
        "market_prob":   vb.get("market_prob", 0.0),
        "edge":          vb.get("edge", 0.0),
    }


def _ev(legs: list) -> float:
    """Expected Value dla parlaya (używa oryginalnych value_bet dicts)."""
    combined_prob = 1.0
    combined_odds = 1.0
    for leg in legs:
        combined_prob *= leg["model_prob"]
        combined_odds *= leg["bet_odds"]
    return (combined_prob * combined_odds) - 1.0


def build_coupons(value_bets: list) -> list:
    """
    Buduje zestaw kuponów z listy value betów.

    Args:
        value_bets: posortowana lista z value_engine.py

    Returns:
        Lista kuponów (max COUPONS_PER_WEEK)
    """
    if not value_bets:
        log.warning("Brak value betów – nie tworzę kuponów.")
        return []

    coupons  = []
    used_ids: set = set()

    # ── Kupon 1: Singiel ─────────────────────────────────────────────────────
    best  = value_bets[0]
    stake = kelly_stake(best["model_prob"], best["bet_odds"])
    if stake > 0:
        coupons.append({
            "type":           "SINGIEL",
            "legs":           [_slim_leg(best)],
            "total_odds":     round(best["bet_odds"], 2),
            "combined_prob":  round(best["model_prob"], 4),
            "stake":          stake,
            "expected_value": round(best["expected_value"], 4),
            "result":         "PENDING",
        })
        used_ids.add(best["match_id"])

    # ── Kupon 2: Podwójny ────────────────────────────────────────────────────
    pool = [b for b in value_bets if b["match_id"] not in used_ids]
    if len(pool) >= 2:
        vb1, vb2 = pool[0], pool[1]
        ev = _ev([vb1, vb2])
        if ev > 0:
            coupons.append({
                "type":           "PODWÓJNY",
                "legs":           [_slim_leg(vb1), _slim_leg(vb2)],
                "total_odds":     round(vb1["bet_odds"] * vb2["bet_odds"], 2),
                "combined_prob":  round(vb1["model_prob"] * vb2["model_prob"], 4),
                "stake":          parlay_stake([vb1, vb2]),
                "expected_value": round(ev, 4),
                "result":         "PENDING",
            })
            used_ids.update([vb1["match_id"], vb2["match_id"]])

    # ── Kupon 3: Potrójny ────────────────────────────────────────────────────
    pool2 = [b for b in value_bets if b["match_id"] not in used_ids]
    if len(pool2) >= 3:
        vb1, vb2, vb3 = pool2[0], pool2[1], pool2[2]
        ev3 = _ev([vb1, vb2, vb3])
        if ev3 > 0:
            coupons.append({
                "type":           "POTRÓJNY",
                "legs":           [_slim_leg(vb1), _slim_leg(vb2), _slim_leg(vb3)],
                "total_odds":     round(vb1["bet_odds"] * vb2["bet_odds"] * vb3["bet_odds"], 2),
                "combined_prob":  round(vb1["model_prob"] * vb2["model_prob"] * vb3["model_prob"], 4),
                "stake":          parlay_stake([vb1, vb2, vb3]),
                "expected_value": round(ev3, 4),
                "result":         "PENDING",
            })

    coupons = coupons[:COUPONS_PER_WEEK]
    log.info(f"Zbudowano {len(coupons)} kuponów")
    return coupons


def save_coupons(coupons: list) -> None:
    """Zapisuje kupony do pliku historii wyników."""
    Path(DATA_RESULTS).mkdir(parents=True, exist_ok=True)
    history_path = f"{DATA_RESULTS}/coupons_history.json"

    history: list = []
    if Path(history_path).exists():
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)

    history.append({
        "date":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "coupons": coupons,
    })

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    log.info(f"Zapisano kupony → {history_path}")
