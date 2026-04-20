"""
pipeline/fetch_odds.py
Pobiera aktualne kursy z The Odds API.
Zapisuje nadchodzące mecze z kursami do data/odds/odds_YYYY-MM-DD.json
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import requests

from config import (
    DATA_ODDS,
    LEAGUES,
    ODDS_API_BASE,
    ODDS_API_KEY,
    ODDS_API_MARKETS,
    ODDS_API_REGIONS,
)

log = logging.getLogger(__name__)


def fetch_league_odds(odds_key: str) -> list:
    """Pobiera mecze i kursy dla jednej ligi."""
    if not ODDS_API_KEY:
        log.error("Brak ODDS_API_KEY w zmiennych środowiskowych!")
        return []

    url = f"{ODDS_API_BASE}/sports/{odds_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": ODDS_API_REGIONS,
        "markets": ODDS_API_MARKETS,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        remaining = resp.headers.get("x-requests-remaining", "?")
        data = resp.json()
        log.info(f"✓ {odds_key}: {len(data)} meczów | requestów pozostało: {remaining}")
        return data
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            log.warning(f"Liga {odds_key} niedostępna w API (poza sezonem?)")
        else:
            log.warning(f"✗ {odds_key}: HTTP {e.response.status_code}")
        return []
    except Exception as e:
        log.warning(f"✗ {odds_key}: {e}")
        return []


def extract_best_odds(match: dict, league_code: str) -> dict | None:
    """
    Wyciąga najlepsze dostępne kursy dla meczu.
    Szuka najwyższego kursu na każdy wynik spośród wszystkich bukmacherów.
    """
    best = {"home": 0.0, "draw": 0.0, "away": 0.0}
    home_team = match["home_team"]
    away_team = match["away_team"]

    for bookmaker in match.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market["key"] != "h2h":
                continue
            outcomes = {o["name"]: o["price"] for o in market["outcomes"]}
            best["home"] = max(best["home"], outcomes.get(home_team, 0))
            best["away"] = max(best["away"], outcomes.get(away_team, 0))
            # Remis = trzeci wynik (nie home i nie away)
            for name, price in outcomes.items():
                if name not in (home_team, away_team):
                    best["draw"] = max(best["draw"], price)

    # Odrzuć mecz bez pełnych kursów
    if best["home"] < 1.01 or best["away"] < 1.01:
        return None

    return {
        "id": match["id"],
        "league_code": league_code,
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": match["commence_time"],
        "odds_home": round(best["home"], 3),
        "odds_draw": round(best["draw"], 3) if best["draw"] > 1.01 else 3.50,
        "odds_away": round(best["away"], 3),
        "bookmakers_count": len(match.get("bookmakers", [])),
    }


def fetch_all_odds() -> None:
    """Pobiera kursy dla wszystkich lig i zapisuje do JSON."""
    Path(DATA_ODDS).mkdir(parents=True, exist_ok=True)
    all_matches = []

    for league_code, info in LEAGUES.items():
        raw = fetch_league_odds(info["odds_key"])
        for match in raw:
            extracted = extract_best_odds(match, league_code)
            if extracted:
                all_matches.append(extracted)

    date_str = datetime.now().strftime("%Y-%m-%d")
    out = f"{DATA_ODDS}/odds_{date_str}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_matches, f, ensure_ascii=False, indent=2)

    log.info(f"Zapisano {len(all_matches)} meczów z kursami → {out}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    fetch_all_odds()
