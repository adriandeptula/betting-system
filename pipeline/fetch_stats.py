"""
pipeline/fetch_stats.py
Pobiera dane historyczne z football-data.co.uk (pliki CSV).
Zapisuje połączone dane w data/raw/all_matches.csv
"""
import io
import logging
from pathlib import Path

import pandas as pd
import requests

from config import DATA_RAW, LEAGUES, SEASONS

log = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"

# Kolumny których potrzebujemy (nie wszystkie ligi mają wszystkie)
WANTED_COLS = [
    "Date", "HomeTeam", "AwayTeam",
    "FTHG", "FTAG", "FTR",    # Wyniki
    "HS", "AS",                # Strzały
    "HST", "AST",              # Strzały celne
    "B365H", "B365D", "B365A", # Kursy Bet365 (do backtestów)
]


def download_season(league_code: str, fd_code: str, season: str) -> pd.DataFrame | None:
    """Pobiera jeden sezon jednej ligi jako DataFrame."""
    url = BASE_URL.format(season=season, code=fd_code)
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), on_bad_lines="skip")

        # Zachowaj tylko dostępne kolumny z WANTED_COLS
        available = [c for c in WANTED_COLS if c in df.columns]
        df = df[available].copy()
        df["League"] = league_code
        df["Season"] = season

        # Usuń wiersze bez wyniku
        df = df.dropna(subset=["FTR"])
        df = df[df["FTR"].isin(["H", "D", "A"])]

        log.info(f"✓ {league_code} {season}: {len(df)} meczów")
        return df

    except requests.HTTPError as e:
        log.warning(f"✗ {league_code} {season}: HTTP {e.response.status_code}")
        return None
    except Exception as e:
        log.warning(f"✗ {league_code} {season}: {e}")
        return None


def fetch_all_stats() -> None:
    """Pobiera wszystkie ligi i sezony, zapisuje do all_matches.csv."""
    Path(DATA_RAW).mkdir(parents=True, exist_ok=True)
    frames = []

    for league_code, info in LEAGUES.items():
        for season in SEASONS:
            df = download_season(league_code, info["fd_code"], season)
            if df is not None:
                frames.append(df)

    if not frames:
        log.error("Nie pobrano żadnych danych!")
        return

    combined = pd.concat(frames, ignore_index=True)
    out = f"{DATA_RAW}/all_matches.csv"
    combined.to_csv(out, index=False)
    log.info(f"Zapisano {len(combined)} meczów → {out}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    fetch_all_stats()
