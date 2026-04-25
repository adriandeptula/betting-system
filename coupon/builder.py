"""
coupon/builder.py
Buduje kupony bukmacherskie z listy value betów.

Strategia:
  1. Singiel  – najlepszy value bet (największy edge)
  2. Podwójny – 2 kolejne value bety (rozłączne mecze)
  3. Potrójny – 3 kolejne value bety (jeśli wystarczy)

Kupony są rozłączne (każdy mecz max w jednym kuponie).

v1.5 poprawka:
  - parlay_stake(): dzielnik zmieniony z len(legs) na len(individual).
    Gdy któraś noga ma ujemne Kelly (kelly_stake=0, noga pomijana),
    poprzedni kod dzielił przez zbyt dużą liczbę i zaniżał stawkę parlaya.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from config import COUPONS_PER_WEEK, DATA_RESULTS
from coupon.kelly import kelly_stake, parlay_stake

log = logging.getLogger(__name__)


def _ev(legs: list) -> float:
    """Expected Value dla parlaya."""
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
            "legs":           [best],
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
        leg1, leg2 = pool[0], pool[1]
        ev = _ev([leg1, leg2])
        if ev > 0:
            coupons.append({
                "type":           "PODWÓJNY",
                "legs":           [leg1, leg2],
                "total_odds":     round(leg1["bet_odds"] * leg2["bet_odds"], 2),
                "combined_prob":  round(leg1["model_prob"] * leg2["model_prob"], 4),
                "stake":          parlay_stake([leg1, leg2]),
                "expected_value": round(ev, 4),
                "result":         "PENDING",
            })
            used_ids.update([leg1["match_id"], leg2["match_id"]])

    # ── Kupon 3: Potrójny ────────────────────────────────────────────────────
    pool2 = [b for b in value_bets if b["match_id"] not in used_ids]
    if len(pool2) >= 3:
        l1, l2, l3 = pool2[0], pool2[1], pool2[2]
        ev3 = _ev([l1, l2, l3])
        if ev3 > 0:
            coupons.append({
                "type":           "POTRÓJNY",
                "legs":           [l1, l2, l3],
                "total_odds":     round(l1["bet_odds"] * l2["bet_odds"] * l3["bet_odds"], 2),
                "combined_prob":  round(l1["model_prob"] * l2["model_prob"] * l3["model_prob"], 4),
                "stake":          parlay_stake([l1, l2, l3]),
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
