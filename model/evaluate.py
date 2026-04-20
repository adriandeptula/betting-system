"""
model/evaluate.py
Oblicza ROI i śledzi wyniki kuponów w czasie.
Uruchamiaj raz w tygodniu po rozegraniu meczów.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from config import DATA_RESULTS, ODDS_API_BASE, ODDS_API_KEY

log = logging.getLogger(__name__)


def fetch_results(league_key: str, days_back: int = 7) -> list:
    """Pobiera wyniki meczów z ostatnich N dni z The Odds API."""
    if not ODDS_API_KEY:
        return []

    url = f"{ODDS_API_BASE}/sports/{league_key}/scores"
    params = {
        "apiKey": ODDS_API_KEY,
        "daysFrom": days_back,
        "dateFormat": "iso",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning(f"Błąd pobierania wyników {league_key}: {e}")
        return []


def update_coupon_results() -> dict:
    """
    Sprawdza wyniki kuponów i oblicza ROI.
    Aktualizuje historię kuponów.
    """
    history_path = f"{DATA_RESULTS}/coupons_history.json"
    if not Path(history_path).exists():
        log.info("Brak historii kuponów.")
        return {}

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    stats = {
        "total_coupons":  0,
        "won":            0,
        "lost":           0,
        "pending":        0,
        "total_staked":   0.0,
        "total_return":   0.0,
        "roi":            0.0,
    }

    for entry in history:
        for coupon in entry.get("coupons", []):
            stats["total_coupons"] += 1
            staked = coupon.get("stake", 0)
            stats["total_staked"] += staked
            result = coupon.get("result", "PENDING")

            if result == "WON":
                stats["won"] += 1
                stats["total_return"] += staked * coupon.get("total_odds", 1)
            elif result == "LOST":
                stats["lost"] += 1
            else:
                stats["pending"] += 1

    resolved = stats["won"] + stats["lost"]
    if resolved > 0 and stats["total_staked"] > 0:
        staked_resolved = stats["total_staked"] * (resolved / stats["total_coupons"])
        stats["roi"] = ((stats["total_return"] - staked_resolved) / staked_resolved * 100
                        if staked_resolved > 0 else 0.0)

    log.info("─── STATYSTYKI KUPONÓW ──────────────────────────")
    log.info(f"Łącznie:       {stats['total_coupons']}")
    log.info(f"Wygrane:       {stats['won']}")
    log.info(f"Przegrane:     {stats['lost']}")
    log.info(f"Oczekujące:    {stats['pending']}")
    log.info(f"ROI:           {stats['roi']:.1f}%")
    log.info("─────────────────────────────────────────────────")

    # Zapisz statystyki
    stats_path = f"{DATA_RESULTS}/stats.json"
    stats["updated_at"] = datetime.now().isoformat()
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    update_coupon_results()
