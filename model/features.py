"""
model/features.py
Feature engineering – buduje cechy dla modelu ML z danych historycznych.

Kluczowe cechy:
- Forma drużyn (ostatnie N meczów)
- Head-to-head (historia bezpośrednich starć)
- Uczciwe prawdopodobieństwa rynkowe (po usunięciu marży bukmachera)
"""
import logging

import numpy as np
import pandas as pd

from config import FORM_WINDOW

log = logging.getLogger(__name__)

# Wszystkie kolumny cech używane przez model
FEATURE_COLS = [
    "league_encoded",
    "home_form_pts",   "home_form_gf",  "home_form_ga",  "home_form_wins",
    "away_form_pts",   "away_form_gf",  "away_form_ga",  "away_form_wins",
    "pts_diff",        "gf_diff",       "ga_diff",
    "h2h_home_wins",   "h2h_draws",     "h2h_away_wins",
    "market_prob_home","market_prob_draw","market_prob_away",
]


def remove_margin(odds_h: float, odds_d: float, odds_a: float) -> tuple[float, float, float]:
    """
    Usuwa marżę bukmachera i zwraca uczciwe prawdopodobieństwa.

    Przykład: kursy 2.10 / 3.40 / 3.60 → suma implikowanych = 1.048
    Po normalizacji: uczciwe prob = implikowane / 1.048
    """
    if odds_h <= 1.0 or odds_d <= 1.0 or odds_a <= 1.0:
        return 0.45, 0.27, 0.28  # domyślne dla ligi europejskiej

    raw_h = 1.0 / odds_h
    raw_d = 1.0 / odds_d
    raw_a = 1.0 / odds_a
    total = raw_h + raw_d + raw_a  # > 1.0 o wartość marży

    return raw_h / total, raw_d / total, raw_a / total


def _form(df_league: pd.DataFrame, team: str,
          before_date: pd.Timestamp, n: int = FORM_WINDOW) -> dict:
    """Oblicza statystyki formy drużyny z ostatnich N meczów."""
    h_mask = (df_league["HomeTeam"] == team) & (df_league["Date"] < before_date)
    a_mask = (df_league["AwayTeam"] == team) & (df_league["Date"] < before_date)

    games = pd.concat([df_league[h_mask], df_league[a_mask]])
    games = games.sort_values("Date").tail(n)

    if games.empty:
        return {"form_pts": 1.0, "form_gf": 1.3, "form_ga": 1.3,
                "form_wins": 0.33, "games_count": 0}

    pts = gf = ga = wins = draws = 0
    for _, r in games.iterrows():
        is_home = r["HomeTeam"] == team
        gf += r["FTHG"] if is_home else r["FTAG"]
        ga += r["FTAG"] if is_home else r["FTHG"]
        res = r["FTR"]
        if (is_home and res == "H") or (not is_home and res == "A"):
            pts += 3; wins += 1
        elif res == "D":
            pts += 1; draws += 1

    n_g = len(games)
    return {
        "form_pts":   pts / n_g,
        "form_gf":    gf / n_g,
        "form_ga":    ga / n_g,
        "form_wins":  wins / n_g,
        "games_count": n_g,
    }


def _h2h(df_league: pd.DataFrame, home: str, away: str,
         before_date: pd.Timestamp, n: int = 5) -> dict:
    """Head-to-head statystyki."""
    mask = (
        ((df_league["HomeTeam"] == home) & (df_league["AwayTeam"] == away)) |
        ((df_league["HomeTeam"] == away) & (df_league["AwayTeam"] == home))
    ) & (df_league["Date"] < before_date)

    games = df_league[mask].tail(n)
    if games.empty:
        return {"h2h_home_wins": 0.40, "h2h_draws": 0.27, "h2h_away_wins": 0.33}

    hw = dr = aw = 0
    for _, r in games.iterrows():
        if r["HomeTeam"] == home:
            if r["FTR"] == "H": hw += 1
            elif r["FTR"] == "D": dr += 1
            else: aw += 1
        else:
            if r["FTR"] == "A": hw += 1
            elif r["FTR"] == "D": dr += 1
            else: aw += 1

    n_g = len(games)
    return {
        "h2h_home_wins": hw / n_g,
        "h2h_draws":     dr / n_g,
        "h2h_away_wins": aw / n_g,
    }


def build_features(df_hist: pd.DataFrame, upcoming: list[dict],
                   league_codes: dict | None = None) -> pd.DataFrame:
    """
    Buduje DataFrame z cechami dla nadchodzących meczów.

    Args:
        df_hist: historyczne mecze (all_matches.csv)
        upcoming: lista słowników z meczami i kursami
        league_codes: opcjonalne enkodowanie lig {kod: int}

    Returns:
        DataFrame z kolumnami FEATURE_COLS + meta (match_id, team names, itp.)
    """
    df = df_hist.copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTR"])
    df = df[df["FTR"].isin(["H", "D", "A"])]
    df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce").fillna(0)
    df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce").fillna(0)

    if league_codes is None:
        league_codes = {c: i for i, c in enumerate(sorted(df["League"].unique()))}

    now = pd.Timestamp.now()
    rows = []

    for match in upcoming:
        home  = match["home_team"]
        away  = match["away_team"]
        lcode = match.get("league_code", "EPL")
        df_lg = df[df["League"] == lcode]

        hf  = _form(df_lg, home, now)
        af  = _form(df_lg, away, now)
        h2h = _h2h(df_lg, home, away, now)

        mh, md, ma = remove_margin(
            match.get("odds_home", 2.0),
            match.get("odds_draw", 3.5),
            match.get("odds_away", 3.5),
        )

        rows.append({
            # Meta
            "match_id":      match.get("id", f"{home}_vs_{away}"),
            "home_team":     home,
            "away_team":     away,
            "league_code":   lcode,
            "commence_time": match.get("commence_time", ""),
            "odds_home":     match.get("odds_home", 2.0),
            "odds_draw":     match.get("odds_draw", 3.5),
            "odds_away":     match.get("odds_away", 3.5),
            # Cechy modelu
            "league_encoded":    league_codes.get(lcode, 0),
            "home_form_pts":     hf["form_pts"],
            "home_form_gf":      hf["form_gf"],
            "home_form_ga":      hf["form_ga"],
            "home_form_wins":    hf["form_wins"],
            "away_form_pts":     af["form_pts"],
            "away_form_gf":      af["form_gf"],
            "away_form_ga":      af["form_ga"],
            "away_form_wins":    af["form_wins"],
            "pts_diff":          hf["form_pts"] - af["form_pts"],
            "gf_diff":           hf["form_gf"]  - af["form_gf"],
            "ga_diff":           hf["form_ga"]  - af["form_ga"],
            "h2h_home_wins":     h2h["h2h_home_wins"],
            "h2h_draws":         h2h["h2h_draws"],
            "h2h_away_wins":     h2h["h2h_away_wins"],
            "market_prob_home":  mh,
            "market_prob_draw":  md,
            "market_prob_away":  ma,
        })

    return pd.DataFrame(rows)
