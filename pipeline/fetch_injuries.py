"""
pipeline/fetch_injuries.py – Pobiera dane o kontuzjach z API-Football.

Źródło: https://www.api-football.com (RapidAPI)
Endpoint: GET /injuries?league={id}&season={year}&date={YYYY-MM-DD}

v1.1: obsługa 2 kluczy API (fallback gdy wyczerpany limit).
Darmowy tier: 100 requestów/dzień.
System używa ~10 req/dzień (1 request/liga + bufor) → wystarczy z zapasem.

Format wyjściowy (data/injuries/injuries_YYYY-MM-DD.json):
{
  "EPL": [
    {
      "player_name": "Mohamed Salah",
      "player_type": "Injury",        # lub "Suspension"
      "team_name": "Liverpool",
      "reason": "Muscle injury",
      "date": "2025-01-10"
    },
    ...
  ],
  "BL": [...],
  ...
}

Zapisuje: data/injuries/injuries_YYYY-MM-DD.json
"""
import json
import logging
import os
from datetime import date

import config
from pipeline.api_utils import api_get

log = logging.getLogger(__name__)


def _fetch_injuries_for_league(
    league_id: int,
    league_code: str,
    season: int,
    fetch_date: str,
) -> list[dict]:
    """
    Pobiera kontuzje i zawieszenia dla jednej ligi na konkretny dzień.
    Zwraca ustandaryzowaną listę słowników lub [] przy błędzie / braku kluczy.
    """
    if not config.API_FOOTBALL_KEYS:
        return []

    url = f"{config.API_FOOTBALL_BASE}/injuries"
    params = {
        "league": league_id,
        "season": season,
        "date": fetch_date,
    }
    headers = {
        "x-rapidapi-host": config.API_FOOTBALL_HOST,
    }

    try:
        data, _ = api_get(
            url=url,
            keys=config.API_FOOTBALL_KEYS,
            params=params,
            headers=headers,
            key_header="x-rapidapi-key",
        )
    except RuntimeError as exc:
        log.error(f"API-Football [{league_code}]: {exc}")
        return []

    # Sprawdź czy API zwróciło błąd wewnętrzny
    if not isinstance(data, dict):
        log.warning(f"API-Football [{league_code}]: nieoczekiwany format {type(data)}")
        return []

    api_errors = data.get("errors", {})
    if api_errors:
        log.warning(f"API-Football [{league_code}]: błędy API = {api_errors}")
        return []

    raw_results = data.get("response", [])
    injuries: list[dict] = []

    for item in raw_results:
        player = item.get("player", {})
        team   = item.get("team",   {})
        reason = item.get("reason", {})

        injuries.append({
            "player_name": player.get("name", ""),
            "player_type": reason.get("type", ""),    # "Injury" | "Suspension"
            "team_name":   team.get("name", ""),
            "reason":      reason.get("reason", ""),
            "date":        fetch_date,
            "league_code": league_code,
        })

    log.info(f"  {league_code}: {len(injuries)} kontuzji/zawieszeń na {fetch_date}")
    return injuries


def fetch_all_injuries(target_date: str | None = None) -> dict[str, list[dict]]:
    """
    Pobiera kontuzje dla wszystkich lig.

    Parametry
    ---------
    target_date : ISO-format YYYY-MM-DD (domyślnie: dzisiaj)

    Zwraca
    ------
    Słownik {league_code: [kontuzje]}.
    Zapisuje do data/injuries/injuries_{date}.json.
    """
    if not config.API_FOOTBALL_KEYS:
        log.warning(
            "Brak kluczy API-Football – pomijam pobieranie kontuzji. "
            "Ustaw API_FOOTBALL_KEY w GitHub Secrets aby włączyć tę funkcję."
        )
        return {}

    fetch_date = target_date or date.today().isoformat()
    all_injuries: dict[str, list[dict]] = {}

    for league_code, league_cfg in config.LEAGUES.items():
        league_id = league_cfg.get("apifootball_id")
        if league_id is None:
            log.warning(f"Brak apifootball_id dla ligi {league_code} – pomiń")
            continue

        injuries = _fetch_injuries_for_league(
            league_id=league_id,
            league_code=league_code,
            season=config.CURRENT_SEASON,
            fetch_date=fetch_date,
        )
        all_injuries[league_code] = injuries

    # Zapisz wyniki
    os.makedirs(config.DATA_INJURIES, exist_ok=True)
    out_path = os.path.join(config.DATA_INJURIES, f"injuries_{fetch_date}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_injuries, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in all_injuries.values())
    log.info(f"✓ Zapisano {total} kontuzji/zawieszeń → {out_path}")
    return all_injuries


def load_latest_injuries() -> dict[str, list[dict]]:
    """
    Wczytuje najnowszy plik kontuzji z dysku.
    Zwraca {} jeśli brak pliku (kontuzje są opcjonalną cechą).
    """
    if not os.path.isdir(config.DATA_INJURIES):
        return {}

    files = sorted(
        [f for f in os.listdir(config.DATA_INJURIES) if f.startswith("injuries_")],
        reverse=True,
    )
    if not files:
        return {}

    path = os.path.join(config.DATA_INJURIES, files[0])
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        log.info(f"Wczytano kontuzje z {files[0]}")
        return data
    except Exception as exc:
        log.warning(f"Błąd wczytywania kontuzji: {exc}")
        return {}
