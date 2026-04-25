"""
pipeline/fetch_stats.py – Pobiera historyczne wyniki meczów z football-data.co.uk.

Źródło: https://www.football-data.co.uk/data.php
Format CSV: mecze z wynikami, kursami, statystykami strzałów itp.

Pobierane kolumny:
  Date, HomeTeam, AwayTeam
  FTHG, FTAG, FTR          – wynik końcowy (gole i rezultat H/D/A)
  HS, AS                    – strzały ogółem
  HST, AST                  – strzały celne (v1.1)
  B365H, B365D, B365A       – kursy Bet365

Zapisuje: data/raw/all_matches.csv

v1.5 poprawka:
  - Deduplikacja po concat: drop_duplicates(subset=["Date","HomeTeam","AwayTety"]).
    Football-data.co.uk przy aktualizacjach sezonu może generować duplikaty
    meczów z pogranicza sezonów. Duplikaty zafałszowałyby Elo i formę.
"""
import io
import logging
import os

import pandas as pd
import requests

import config

log = logging.getLogger(__name__)

_REQUIRED_COLS = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]

_KEEP_COLS = [
    "Date", "HomeTeam", "AwayTeam",
    "FTHG", "FTAG", "FTR",
    "HS",   "AS",
    "HST",  "AST",
    "B365H", "B365D", "B365A",
]

_FD_BASE = "https://www.football-data.co.uk/mmz4281"


def _fetch_csv(fd_code: str, season: str) -> pd.DataFrame | None:
    """Pobiera jeden CSV i zwraca DataFrame lub None przy błędzie."""
    url = f"{_FD_BASE}/{season}/{fd_code}.csv"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning(f"Nie udało się pobrać {url}: {exc}")
        return None

    try:
        df = pd.read_csv(
            io.StringIO(resp.content.decode("latin-1")),
            on_bad_lines="skip",
        )
    except Exception as exc:
        log.warning(f"Błąd parsowania CSV {url}: {exc}")
        return None

    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        log.warning(f"Brakuje kolumn {missing} w {url} – pomijam")
        return None

    existing = [c for c in _KEEP_COLS if c in df.columns]
    df       = df[existing].copy()

    df = df.dropna(subset=["FTHG", "FTAG", "FTR"])
    df = df[df["FTR"].isin(["H", "D", "A"])]

    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date"])

    league_code = next(
        (k for k, v in config.LEAGUES.items() if v["fd_code"] == fd_code),
        fd_code,
    )
    df["league"] = league_code
    df["season"] = season

    log.info(f"  {league_code} {season}: {len(df)} meczów")
    return df


def fetch_all_stats() -> None:
    """
    Pobiera wszystkie ligi i sezony, łączy, deduplikuje i zapisuje all_matches.csv.

    v1.5: deduplikacja po concat chroni przed podwójnym liczeniem meczów
    z pogranicza sezonów co zafałszowałoby Elo i formę drużyn.
    """
    frames: list[pd.DataFrame] = []

    for league_code, league_cfg in config.LEAGUES.items():
        fd_code = league_cfg["fd_code"]
        for season in config.SEASONS:
            df = _fetch_csv(fd_code, season)
            if df is not None and not df.empty:
                frames.append(df)

    if not frames:
        log.error("Nie pobrano żadnych danych! Sprawdź połączenie z internetem.")
        return

    all_matches = pd.concat(frames, ignore_index=True)

    # Deduplikacja: ten sam mecz mógł pojawić się w dwóch sezonach CSV
    before_dedup = len(all_matches)
    all_matches  = all_matches.drop_duplicates(
        subset=["Date", "HomeTeam", "AwayTeam"]
    ).reset_index(drop=True)
    after_dedup  = len(all_matches)

    if before_dedup != after_dedup:
        log.info(f"Deduplikacja: usunięto {before_dedup - after_dedup} duplikatów")

    all_matches = all_matches.sort_values("Date").reset_index(drop=True)

    os.makedirs(config.DATA_RAW, exist_ok=True)
    out_path = os.path.join(config.DATA_RAW, "all_matches.csv")
    all_matches.to_csv(out_path, index=False)

    has_hst = all_matches["HST"].notna().sum() if "HST" in all_matches.columns else 0
    pct     = has_hst / max(len(all_matches), 1) * 100

    log.info(
        f"✓ Zapisano {len(all_matches)} meczów → {out_path}\n"
        f"  Sezony: {config.SEASONS}\n"
        f"  Strzały celne (HST/AST): {has_hst}/{len(all_matches)} ({pct:.0f}% pokrycie)"
    )
