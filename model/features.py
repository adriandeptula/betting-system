"""
model/features.py – Feature engineering dla modelu XGBoost.

Metodologia: walk-forward (bez data leakage).
  Dla każdego meczu cechy liczone są TYLKO z danych historycznych
  (mecze które odbyły się PRZED datą tego meczu).

Cechy (v1.1):
  Forma (ostatnie FORM_WINDOW meczów):
    - home_pts_avg, away_pts_avg             – średnia punktów (3/1/0)
    - home_gf_avg, away_gf_avg               – średnia goli strzelonych
    - home_ga_avg, away_ga_avg               – średnia goli straconych
    - home_hst_avg, away_hst_avg             – śr. strzałów celnych [v1.1]
    - home_ast_avg, away_ast_avg             – śr. strzałów celnych przeciwnika [v1.1]

  H2H (ostatnie 5 bezpośrednich meczów):
    - h2h_home_win_rate                      – % wygranych drużyny domowej
    - h2h_avg_goals                          – średnia goli w meczu

  Kursy rynkowe (fair, po usunięciu marży bukmachera):
    - market_prob_h, market_prob_d, market_prob_a

  Kontuzje [v1.1] (opcjonalne – gdy dostępne z API-Football):
    - home_injury_score                      – ułamek kontuzjowanych graczy
    - away_injury_score

Funkcja remove_margin() usuwa marżę bukmachera z kursów.
Funkcja compute_features() tworzy feature matrix dla treningu modelu.
Funkcja compute_features_upcoming() tworzy cechy dla nadchodzących meczów.
"""
import logging
from typing import Any

import numpy as np
import pandas as pd

import config
from pipeline.name_mapping import normalize

log = logging.getLogger(__name__)

# Cechy zwracane przez compute_features() – kolejność musi być ZAWSZE ta sama
FEATURE_COLS = [
    "home_pts_avg",
    "away_pts_avg",
    "home_gf_avg",
    "away_gf_avg",
    "home_ga_avg",
    "away_ga_avg",
    "home_hst_avg",     # v1.1
    "away_hst_avg",     # v1.1
    "home_ast_avg",     # v1.1
    "away_ast_avg",     # v1.1
    "h2h_home_win_rate",
    "h2h_avg_goals",
    "market_prob_h",
    "market_prob_d",
    "market_prob_a",
    "home_injury_score",  # v1.1 (0.0 gdy brak danych)
    "away_injury_score",  # v1.1 (0.0 gdy brak danych)
]


# ── Usuwanie marży bukmachera ─────────────────────────────────────────────────

def remove_margin(odds_h: float, odds_d: float, odds_a: float) -> tuple[float, float, float]:
    """
    Normalizuje kursy 1X2 usuwając marżę bukmachera (overround).

    Np. kursy 2.0 / 3.5 / 3.8 mają marżę ~6%.
    Po normalizacji suma prawdopodobieństw = 1.0.

    Zwraca (prob_h, prob_d, prob_a) – fair probabilities.
    """
    try:
        raw_h = 1.0 / odds_h
        raw_d = 1.0 / odds_d
        raw_a = 1.0 / odds_a
        total = raw_h + raw_d + raw_a
        if total <= 0:
            return 1 / 3, 1 / 3, 1 / 3
        return raw_h / total, raw_d / total, raw_a / total
    except (ZeroDivisionError, TypeError):
        return 1 / 3, 1 / 3, 1 / 3


# ── Pomocnicze funkcje formy ──────────────────────────────────────────────────

def _get_team_history(df: pd.DataFrame, team: str, before_date: pd.Timestamp, n: int) -> pd.DataFrame:
    """Ostatnie n meczów drużyny (home lub away) przed daną datą."""
    mask = (
        ((df["HomeTeam"] == team) | (df["AwayTeam"] == team))
        & (df["Date"] < before_date)
    )
    return df[mask].sort_values("Date").tail(n)


def _calc_form(history: pd.DataFrame, team: str) -> dict[str, float]:
    """
    Oblicza cechy formy z ostatnich meczów drużyny.
    Zwraca słownik cech z prefiksem (bez prefiksu home_/away_).
    """
    if history.empty:
        return {
            "pts_avg": 1.0,      # domyślne środkowe wartości
            "gf_avg":  1.2,
            "ga_avg":  1.2,
            "hst_avg": 4.0,      # śr. strzały celne w Premier League ~4.5
            "ast_avg": 4.0,
        }

    pts_list, gf_list, ga_list, hst_list, ast_list = [], [], [], [], []

    for _, row in history.iterrows():
        is_home = row["HomeTeam"] == team

        # Punkty
        ftr = row["FTR"]
        if is_home:
            pts = 3 if ftr == "H" else (1 if ftr == "D" else 0)
            gf  = row["FTHG"]
            ga  = row["FTAG"]
            hst = row.get("HST", np.nan)
            ast = row.get("AST", np.nan)
        else:
            pts = 3 if ftr == "A" else (1 if ftr == "D" else 0)
            gf  = row["FTAG"]
            ga  = row["FTHG"]
            hst = row.get("AST", np.nan)   # przeciwnik strzelał
            ast = row.get("HST", np.nan)

        pts_list.append(pts)
        gf_list.append(float(gf) if not pd.isna(gf) else np.nan)
        ga_list.append(float(ga) if not pd.isna(ga) else np.nan)
        hst_list.append(float(hst) if not pd.isna(hst) else np.nan)
        ast_list.append(float(ast) if not pd.isna(ast) else np.nan)

    def _mean_or_default(lst: list, default: float) -> float:
        vals = [v for v in lst if not np.isnan(v)]
        return float(np.mean(vals)) if vals else default

    return {
        "pts_avg":  _mean_or_default(pts_list,  1.0),
        "gf_avg":   _mean_or_default(gf_list,   1.2),
        "ga_avg":   _mean_or_default(ga_list,   1.2),
        "hst_avg":  _mean_or_default(hst_list,  4.0),
        "ast_avg":  _mean_or_default(ast_list,  4.0),
    }


def _calc_h2h(df: pd.DataFrame, home: str, away: str, before_date: pd.Timestamp, n: int = 5) -> dict[str, float]:
    """Oblicza statystyki H2H (ostatnie n meczów między dwiema drużynami)."""
    mask = (
        (
            ((df["HomeTeam"] == home) & (df["AwayTeam"] == away))
            | ((df["HomeTeam"] == away) & (df["AwayTeam"] == home))
        )
        & (df["Date"] < before_date)
    )
    h2h = df[mask].sort_values("Date").tail(n)

    if h2h.empty:
        return {"h2h_home_win_rate": 0.40, "h2h_avg_goals": 2.5}

    home_wins, total_goals, count = 0, 0, 0
    for _, row in h2h.iterrows():
        count += 1
        total_goals += float(row["FTHG"]) + float(row["FTAG"])
        # "home" w kontekście bieżącego meczu
        if row["HomeTeam"] == home and row["FTR"] == "H":
            home_wins += 1
        elif row["AwayTeam"] == home and row["FTR"] == "A":
            home_wins += 1

    return {
        "h2h_home_win_rate": home_wins / count,
        "h2h_avg_goals":     total_goals / count,
    }


# ── Kontuzje ──────────────────────────────────────────────────────────────────

def _calc_injury_score(
    injuries_by_league: dict[str, list[dict]],
    league_code: str,
    team_name: str,
    squad_size: int = 25,
) -> float:
    """
    Oblicza wskaźnik kontuzji: ułamek niedostępnych graczy (0.0–1.0).
    0.0 oznacza brak danych lub brak kontuzji.
    Wyższy = więcej graczy niedostępnych (negatywne dla drużyny).
    """
    league_injuries = injuries_by_league.get(league_code, [])
    if not league_injuries:
        return 0.0

    # Normalizuj nazwę drużyny
    norm_team = normalize(team_name, source="injury_score")
    count = sum(
        1 for inj in league_injuries
        if normalize(inj.get("team_name", ""), source="injury_score") == norm_team
    )
    return min(count / squad_size, 1.0)


# ── Główne funkcje publiczne ──────────────────────────────────────────────────

def compute_features(
    df: pd.DataFrame,
    injuries: dict[str, list[dict]] | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Tworzy feature matrix (X) i wektor etykiet (y) dla treningu modelu.

    Metoda walk-forward: cechy dla każdego meczu liczone są tylko z danych
    historycznych (mecze przed datą danego meczu).

    Parametry
    ---------
    df       : DataFrame z all_matches.csv (posortowany po Date)
    injuries : opcjonalne dane o kontuzjach {league_code: [kontuzje]}

    Zwraca
    ------
    (X, y) – feature matrix i etykiety (0=H, 1=D, 2=A)
    """
    if injuries is None:
        injuries = {}

    # Upewnij się że Date to datetime
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    # Mapuj wyniki na liczby
    result_map = {"H": 0, "D": 1, "A": 2}

    rows: list[dict[str, Any]] = []
    labels: list[int] = []

    for idx, match in df.iterrows():
        home = str(match["HomeTeam"])
        away = str(match["AwayTeam"])
        date = match["Date"]
        league = str(match.get("league", ""))

        # Kursy rynkowe (Bet365 jako bazowe)
        odds_h = match.get("B365H", np.nan)
        odds_d = match.get("B365D", np.nan)
        odds_a = match.get("B365A", np.nan)

        if pd.isna(odds_h) or pd.isna(odds_d) or pd.isna(odds_a):
            # Brak kursów – pomiń mecz
            continue

        ftr = match.get("FTR")
        if ftr not in result_map:
            continue

        # Forma
        home_hist = _get_team_history(df, home, date, config.FORM_WINDOW)
        away_hist = _get_team_history(df, away, date, config.FORM_WINDOW)

        home_form = _calc_form(home_hist, home)
        away_form = _calc_form(away_hist, away)

        # H2H
        h2h = _calc_h2h(df, home, away, date)

        # Kursy → fair probabilities
        prob_h, prob_d, prob_a = remove_margin(odds_h, odds_d, odds_a)

        # Kontuzje (v1.1)
        home_inj = _calc_injury_score(injuries, league, home)
        away_inj = _calc_injury_score(injuries, league, away)

        row = {
            "home_pts_avg":      home_form["pts_avg"],
            "away_pts_avg":      away_form["pts_avg"],
            "home_gf_avg":       home_form["gf_avg"],
            "away_gf_avg":       away_form["gf_avg"],
            "home_ga_avg":       home_form["ga_avg"],
            "away_ga_avg":       away_form["ga_avg"],
            "home_hst_avg":      home_form["hst_avg"],
            "away_hst_avg":      away_form["hst_avg"],
            "home_ast_avg":      home_form["ast_avg"],
            "away_ast_avg":      away_form["ast_avg"],
            "h2h_home_win_rate": h2h["h2h_home_win_rate"],
            "h2h_avg_goals":     h2h["h2h_avg_goals"],
            "market_prob_h":     prob_h,
            "market_prob_d":     prob_d,
            "market_prob_a":     prob_a,
            "home_injury_score": home_inj,
            "away_injury_score": away_inj,
        }

        rows.append(row)
        labels.append(result_map[ftr])

    X = pd.DataFrame(rows, columns=FEATURE_COLS)
    y = pd.Series(labels, name="result")

    log.info(
        f"compute_features: {len(X)} rekordów, "
        f"cechy={list(X.columns)[:5]}... "
        f"rozkład: H={labels.count(0)} D={labels.count(1)} A={labels.count(2)}"
    )
    return X, y


def compute_features_upcoming(
    upcoming: list[dict],
    history_df: pd.DataFrame,
    injuries: dict[str, list[dict]] | None = None,
) -> pd.DataFrame:
    """
    Tworzy cechy dla nadchodzących meczów (bez etykiet).

    Parametry
    ---------
    upcoming    : lista słowników z kluczami:
                  home_team, away_team, date (pd.Timestamp), league,
                  odds_h, odds_d, odds_a
    history_df  : historyczny DataFrame z all_matches.csv
    injuries    : opcjonalne dane o kontuzjach

    Zwraca
    ------
    DataFrame z cechami (FEATURE_COLS) w tej samej kolejności co trening.
    """
    if injuries is None:
        injuries = {}

    history_df = history_df.copy()
    # history_df["Date"] musi być timezone-naive (dane z CSV nie mają strefy)
    history_df["Date"] = pd.to_datetime(history_df["Date"]).dt.tz_localize(None)

    rows: list[dict[str, Any]] = []

    for match in upcoming:
        home   = str(match["home_team"])
        away   = str(match["away_team"])
        # Zdejmij strefę czasową jeśli istnieje – daty z The Odds API mają UTC (+00:00)
        raw_date = pd.Timestamp(match["date"])
        date = raw_date.tz_localize(None) if raw_date.tzinfo is None else raw_date.tz_convert("UTC").tz_localize(None)
        league = str(match.get("league", ""))

        odds_h = float(match.get("odds_h", 2.0))
        odds_d = float(match.get("odds_d", 3.5))
        odds_a = float(match.get("odds_a", 4.0))

        home_hist = _get_team_history(history_df, home, date, config.FORM_WINDOW)
        away_hist = _get_team_history(history_df, away, date, config.FORM_WINDOW)

        home_form = _calc_form(home_hist, home)
        away_form = _calc_form(away_hist, away)

        h2h  = _calc_h2h(history_df, home, away, date)
        prob_h, prob_d, prob_a = remove_margin(odds_h, odds_d, odds_a)

        home_inj = _calc_injury_score(injuries, league, home)
        away_inj = _calc_injury_score(injuries, league, away)

        rows.append({
            "home_pts_avg":      home_form["pts_avg"],
            "away_pts_avg":      away_form["pts_avg"],
            "home_gf_avg":       home_form["gf_avg"],
            "away_gf_avg":       away_form["gf_avg"],
            "home_ga_avg":       home_form["ga_avg"],
            "away_ga_avg":       away_form["ga_avg"],
            "home_hst_avg":      home_form["hst_avg"],
            "away_hst_avg":      away_form["hst_avg"],
            "home_ast_avg":      home_form["ast_avg"],
            "away_ast_avg":      away_form["ast_avg"],
            "h2h_home_win_rate": h2h["h2h_home_win_rate"],
            "h2h_avg_goals":     h2h["h2h_avg_goals"],
            "market_prob_h":     prob_h,
            "market_prob_d":     prob_d,
            "market_prob_a":     prob_a,
            "home_injury_score": home_inj,
            "away_injury_score": away_inj,
        })

    return pd.DataFrame(rows, columns=FEATURE_COLS)
