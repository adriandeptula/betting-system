"""
pipeline/fetch_odds.py – Pobiera aktualne kursy z The Odds API.

Źródło: https://the-odds-api.com
Rynek: h2h (1X2), regiony europejskie.

v1.1: obsługa 2 kluczy API (fallback gdy wyczerpany limit).
Darmowy tier: 500 requestów/miesiąc (~16/dzień).
Przy 5 ligach x 2 wywołania = ~10 req/dzień → wystarczy z zapasem.

Zapisuje: data/odds/odds_YYYY-MM-DD.json
"""
import json
import logging
import os
from datetime import date

import config
from pipeline.api_utils import api_get

log = logging.getLogger(__name__)


def fetch_odds_for_league(odds_key: str) -> list[dict]:
    """
    Pobiera mecze i kursy dla jednej ligi.
    Zwraca listę eventów lub [] przy błędzie.
    """
    url = f"{config.ODDS_API_BASE}/sports/{odds_key}/odds"
    params = {
        "regions": config.ODDS_API_REGIONS,
        "markets": config.ODDS_API_MARKETS,
        "oddsFormat": "decimal",
    }

    try:
        data, used_key = api_get(
            url=url,
            keys=config.ODDS_API_KEYS,
            params=params,
            key_param="apiKey",
        )
    except RuntimeError as exc:
        log.error(f"The Odds API [{odds_key}]: {exc}")
        return []

    if not isinstance(data, list):
        log.warning(f"Nieoczekiwany format odpowiedzi dla {odds_key}: {type(data)}")
        return []

    log.info(f"  {odds_key}: {len(data)} meczów z kursami")
    return data


def fetch_all_odds() -> None:
    """Pobiera kursy dla wszystkich lig i zapisuje do jednego pliku JSON."""
    if not config.ODDS_API_KEYS:
        log.error(
            "Brak kluczy The Odds API! "
            "Ustaw ODDS_API_KEY (i opcjonalnie ODDS_API_KEY_2) w GitHub Secrets."
        )
        return

    all_events: list[dict] = []

    for league_code, league_cfg in config.LEAGUES.items():
        odds_key = league_cfg["odds_key"]
        events = fetch_odds_for_league(odds_key)
        # Wzbogać każdy event o nasz wewnętrzny kod ligi
        for ev in events:
            ev["_league_code"] = league_code
        all_events.extend(events)

    if not all_events:
        log.warning("Nie pobrano żadnych kursów. Sprawdź klucze API i dostępność lig.")
        return

    os.makedirs(config.DATA_ODDS, exist_ok=True)
    today = date.today().isoformat()
    out_path = os.path.join(config.DATA_ODDS, f"odds_{today}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"✓ Zapisano {len(all_events)} eventów z kursami → {out_path}")
