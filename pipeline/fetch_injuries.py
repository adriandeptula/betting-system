"""
pipeline/fetch_injuries.py – Pobiera dane o kontuzjach z API-Football.

Źródło: https://www.api-football.com (RapidAPI)
Endpoint: GET /injuries?league={id}&season={year}

WAŻNE: NIE przekazujemy parametru `date`. Parametr `date` oznacza "kontuzje
dla meczów NA TEN DZIEŃ" – jeśli danego dnia nie ma meczów, API zwraca [].
Bez `date` API zwraca WSZYSTKICH aktualnie niedostępnych zawodników w lidze.

v1.1: obsługa 2 kluczy API (fallback gdy wyczerpany limit).
Darmowy tier: 100 requestów/dzień.
System używa ~5 req/dzień (1 request/liga) → wystarczy z zapasem.

Format wyjściowy (data/injuries/injuries_YYYY-MM-DD.json):
{
  "EPL": [
    {
      "player_name": "Mohamed Salah",
      "player_type": "Injury",
      "team_name": "Liverpool",
      "reason": "Muscle injury",
      "fetched_date": "2026-04-22"
    },
    ...
  ],
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
    fetched_date: str,
) -> list[dict]:
    """
    Pobiera WSZYSTKICH aktualnie niedostępnych zawodników dla danej ligi.
    Nie filtrujemy po dacie meczu – chcemy pełną listę kontuzji i zawieszeń.
    """
    if not config.API_FOOTBALL_KEYS:
        return []

    url = f"{config.API_FOOTBALL_BASE}/injuries"
    # BEZ parametru "date" – zwraca wszystkich niedostępnych graczy w sezonie
    params = {
        "league": league_id,
        "season": season,
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

    if not isinstance(data, dict):
        log.warning(f"API-Football [{league_code}]: nieoczekiwany format {type(data)}")
        return []

    api_errors = data.get("errors", {})
    if api_errors:
        log.warning(f"API-Football [{league_code}]: błędy API = {api_errors}")
        return []

    raw_results = data.get("response", [])
    results_count = data.get("results", 0)

    injuries: list[dict] = []
    for item in raw_results:
        player = item.get("player", {})
        team   = item.get("team", {})

        injuries.append({
            "player_id":    player.get("id", 0),
            "player_name":  player.get("name", ""),
            "player_type":  player.get("type", ""),   # "Injury" | "Suspension"
            "team_id":      team.get("id", 0),
            "team_name":    team.get("name", ""),
            "reason":       player.get("reason", ""),
            "fetched_date": fetched_date,
            "league_code":  league_code,
        })

    # Deduplikacja – jeden gracz może mieć wiele wpisów (jeden per mecz w sezonie)
    seen: set = set()
    unique: list[dict] = []
    for inj in injuries:
        key = (inj["player_id"], inj["team_id"])
        if key not in seen and inj["player_name"]:
            seen.add(key)
            unique.append(inj)

    log.info(
        f"  {league_code}: {len(unique)} niedostępnych zawodników "
        f"(raw: {results_count} wpisów z API)"
    )
    return unique


def fetch_all_injuries(target_date: str | None = None) -> dict[str, list[dict]]:
    """
    Pobiera listę niedostępnych zawodników dla wszystkich lig.

    Parametry
    ---------
    target_date : ISO-format YYYY-MM-DD – tylko do nazwy pliku (domyślnie: dzisiaj)

    Zwraca
    ------
    Slownik {league_code: [kontuzje]}.
    Zapisuje do data/injuries/injuries_{date}.json.
    """
    if not config.API_FOOTBALL_KEYS:
        log.warning(
            "Brak kluczy API-Football – pomijam pobieranie kontuzji. "
            "Ustaw API_FOOTBALL_KEY w GitHub Secrets aby wlaczyc te funkcje."
        )
        return {}

    fetched_date = target_date or date.today().isoformat()
    all_injuries: dict[str, list[dict]] = {}

    for league_code, league_cfg in config.LEAGUES.items():
        league_id = league_cfg.get("apifootball_id")
        if league_id is None:
            log.warning(f"Brak apifootball_id dla ligi {league_code} – pominiam")
            continue

        injuries = _fetch_injuries_for_league(
            league_id=league_id,
            league_code=league_code,
            season=config.CURRENT_SEASON,
            fetched_date=fetched_date,
        )
        all_injuries[league_code] = injuries

    os.makedirs(config.DATA_INJURIES, exist_ok=True)
    out_path = os.path.join(config.DATA_INJURIES, f"injuries_{fetched_date}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_injuries, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in all_injuries.values())
    log.info(f"Zapisano {total} niedostepnych zawodnikow → {out_path}")
    return all_injuries


def load_latest_injuries() -> dict[str, list[dict]]:
    """
    Wczytuje najnowszy plik kontuzji z dysku.
    Zwraca {} jesli brak pliku (kontuzje sa opcjonalna cecha).
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
        total = sum(len(v) for v in data.values())
        log.info(f"Wczytano kontuzje z {files[0]} ({total} zawodnikow)")
        return data
    except Exception as exc:
        log.warning(f"Blad wczytywania kontuzji: {exc}")
        return {}
