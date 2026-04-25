"""
model/features.py – Feature engineering dla modelu XGBoost.

Metodologia: walk-forward (bez data leakage).
  Dla każdego meczu cechy liczone są TYLKO z danych historycznych
  (mecze które odbyły się PRZED datą tego meczu).

Cechy (v1.5):
  Forma ważona czasowo (wykładniczy zanik, halflife=FORM_HALFLIFE_DAYS):
    home_pts_avg, away_pts_avg   – średnia punktów (3/1/0)
    home_gf_avg,  away_gf_avg    – średnia goli strzelonych
    home_ga_avg,  away_ga_avg    – średnia goli straconych
    home_hst_avg, away_hst_avg   – śr. strzałów celnych
    home_ast_avg, away_ast_avg   – śr. strzałów celnych przeciwnika

  H2H (ostatnie 5 bezpośrednich meczów):
    h2h_home_win_rate            – % wygranych drużyny domowej
    h2h_avg_goals                – średnia goli w meczu

  Kursy rynkowe (fair, po usunięciu marży bukmachera):
    market_prob_h, market_prob_d, market_prob_a

  Elo rating per liga (v1.5: osobno na każdą ligę – brak cross-league contamination):
    home_elo                     – rating Elo drużyny domowej
    away_elo                     – rating Elo drużyny gości
    elo_diff                     – różnica (home_elo - away_elo)

Zmiany v1.5 vs v1.3/v1.4:
  - Elo per liga (było: wszystkie ligi razem) – eliminuje cross-league noise
  - _get_elo_before przyjmuje parametr league
  - Poprawka: build_elo_history zwraca {league: {team: [(date, elo)]}}
"""
import logging
import math
from typing import Any

import numpy as np
import pandas as pd

import config
from pipeline.name_mapping import normalize

log = logging.getLogger(__name__)

# Cechy zwracane przez compute_features() – kolejność musi być ZAWSZE ta sama.
# NIGDY nie zmieniaj kolejności bez pełnego retraining modelu.
FEATURE_COLS = [
    "home_pts_avg",
    "away_pts_avg",
    "home_gf_avg",
    "away_gf_avg",
    "home_ga_avg",
    "away_ga_avg",
    "home_hst_avg",
    "away_hst_avg",
    "home_ast_avg",
    "away_ast_avg",
    "h2h_home_win_rate",
    "h2h_avg_goals",
    "market_prob_h",
    "market_prob_d",
    "market_prob_a",
    "home_elo",
    "away_elo",
    "elo_diff",
]


# ── Usuwanie marży bukmachera ─────────────────────────────────────────────────

def remove_margin(odds_h: float, odds_d: float, odds_a: float) -> tuple[float, float, float]:
    """
    Normalizuje kursy 1X2 usuwając marżę bukmachera (overround).
    Zwraca (prob_h, prob_d, prob_a) – fair probabilities sumujące się do 1.0.
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


# ── Elo rating per liga ───────────────────────────────────────────────────────

# Typ zwracany: {liga_kod: {nazwa_druzyny: [(data, elo_po_meczu), ...]}}
EloHistory = dict[str, dict[str, list[tuple[pd.Timestamp, float]]]]


def build_elo_history(df: pd.DataFrame) -> EloHistory:
    """
    Buduje historię ratingów Elo OSOBNO dla każdej ligi (walk-forward, O(n)).

    Kalkulacja per liga eliminuje cross-league contamination — drużyny z EPL
    i Ekstraklasy zaczynają od tego samego startowego ratingu 1500, ale nigdy
    nie grają między sobą, więc wspólna skala nie miałaby sensu.

    Formuła Elo:
      E_home = 1 / (1 + 10^((R_away - R_home) / 400))
      R_new  = R_old + K * (S - E)
      S: 1.0=wygrana, 0.5=remis, 0.0=przegrana

    Parametry
    ---------
    df : DataFrame z all_matches.csv posortowany po Date, z kolumną 'league'

    Zwraca
    ------
    {liga_kod: {drużyna: [(data, elo)]}}
    """
    # elo[liga][druzyna] = bieżący rating
    elo: dict[str, dict[str, float]] = {}
    history: EloHistory = {}

    for _, row in df.sort_values("Date").iterrows():
        home   = str(row["HomeTeam"])
        away   = str(row["AwayTeam"])
        date   = row["Date"]
        ftr    = row.get("FTR", "")
        league = str(row.get("league", "UNKNOWN"))

        if ftr not in ("H", "D", "A"):
            continue

        elo.setdefault(league, {})
        history.setdefault(league, {})

        ra = elo[league].get(home, config.ELO_START)
        rb = elo[league].get(away, config.ELO_START)

        ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        sa = 1.0 if ftr == "H" else (0.5 if ftr == "D" else 0.0)
        sb = 1.0 - sa

        elo[league][home] = ra + config.ELO_K * (sa - ea)
        elo[league][away] = rb + config.ELO_K * (sb - eb)

        history[league].setdefault(home, []).append((date, elo[league][home]))
        history[league].setdefault(away, []).append((date, elo[league][away]))

    total_teams = sum(len(v) for v in history.values())
    log.info(
        f"Elo: obliczono historię dla {total_teams} drużyn "
        f"w {len(history)} ligach: {list(history.keys())}"
    )
    return history


def _get_elo_before(
    history: EloHistory,
    team: str,
    before_date: pd.Timestamp,
    league: str = "UNKNOWN",
) -> float:
    """
    Zwraca ostatni rating Elo drużyny w danej lidze przed podaną datą.
    Jeśli brak historii (nowa drużyna lub nowa liga) – zwraca ELO_START.
    """
    league_hist = history.get(league, {})
    entries     = league_hist.get(team, [])
    relevant    = [e for d, e in entries if d < before_date]
    return relevant[-1] if relevant else float(config.ELO_START)


# ── Forma ważona czasowo ──────────────────────────────────────────────────────

def _weighted_mean(
    values: list[float],
    dates: list[pd.Timestamp],
    reference_date: pd.Timestamp,
    default: float,
) -> float:
    """
    Oblicza średnią ważoną wykładniczo – nowsze mecze mają wyższą wagę.

    Waga(d) = exp(-ln2 * days_ago / FORM_HALFLIFE_DAYS)

    Przy halflife=21 dni:
      mecz z ostatniego tygodnia  → waga ~1.0
      mecz sprzed 3 tyg.          → waga ~0.5
      mecz sprzed 6 tyg.          → waga ~0.25
    """
    if not values:
        return default

    ln2 = math.log(2)
    hl  = config.FORM_HALFLIFE_DAYS
    weights = [
        math.exp(-ln2 * max(0, (reference_date - d).days) / hl)
        for d in dates
    ]
    total_w = sum(weights)
    if total_w <= 0:
        return default
    return sum(v * w for v, w in zip(values, weights)) / total_w


def _get_team_history(
    df: pd.DataFrame, team: str, before_date: pd.Timestamp, n: int
) -> pd.DataFrame:
    """Ostatnie n meczów drużyny (home lub away) przed daną datą."""
    mask = (
        ((df["HomeTeam"] == team) | (df["AwayTeam"] == team))
        & (df["Date"] < before_date)
    )
    return df[mask].sort_values("Date").tail(n)


def _calc_form(
    history: pd.DataFrame,
    team: str,
    reference_date: pd.Timestamp,
) -> dict[str, float]:
    """
    Oblicza cechy formy z ostatnich meczów drużyny (ważone czasowo).
    Zwraca słownik z pts_avg, gf_avg, ga_avg, hst_avg, ast_avg.
    """
    if history.empty:
        return {
            "pts_avg": 1.0,
            "gf_avg":  1.2,
            "ga_avg":  1.2,
            "hst_avg": 4.0,
            "ast_avg": 4.0,
        }

    pts_list, gf_list, ga_list, hst_list, ast_list = [], [], [], [], []
    dates: list[pd.Timestamp] = []

    for _, row in history.iterrows():
        is_home = row["HomeTeam"] == team
        ftr     = row["FTR"]

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
            hst = row.get("AST", np.nan)
            ast = row.get("HST", np.nan)

        pts_list.append(float(pts))
        gf_list.append(float(gf)   if not pd.isna(gf)   else np.nan)
        ga_list.append(float(ga)   if not pd.isna(ga)   else np.nan)
        hst_list.append(float(hst) if not pd.isna(hst)  else np.nan)
        ast_list.append(float(ast) if not pd.isna(ast)  else np.nan)
        dates.append(row["Date"])

    def wmean(vals: list, default: float) -> float:
        pairs = [(v, d) for v, d in zip(vals, dates) if not np.isnan(v)]
        if not pairs:
            return default
        vs, ds = zip(*pairs)
        return _weighted_mean(list(vs), list(ds), reference_date, default)

    return {
        "pts_avg":  wmean(pts_list,  1.0),
        "gf_avg":   wmean(gf_list,   1.2),
        "ga_avg":   wmean(ga_list,   1.2),
        "hst_avg":  wmean(hst_list,  4.0),
        "ast_avg":  wmean(ast_list,  4.0),
    }


def _calc_h2h(
    df: pd.DataFrame,
    home: str,
    away: str,
    before_date: pd.Timestamp,
    n: int = 5,
) -> dict[str, float]:
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
        count       += 1
        total_goals += float(row["FTHG"]) + float(row["FTAG"])
        if row["HomeTeam"] == home and row["FTR"] == "H":
            home_wins += 1
        elif row["AwayTeam"] == home and row["FTR"] == "A":
            home_wins += 1

    return {
        "h2h_home_win_rate": home_wins / count,
        "h2h_avg_goals":     total_goals / count,
    }


# ── Główne funkcje publiczne ──────────────────────────────────────────────────

def compute_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Tworzy feature matrix (X) i wektor etykiet (y) dla treningu modelu.

    Walk-forward: cechy dla każdego meczu liczone z danych historycznych
    PRZED datą danego meczu. Elo budowany raz na całym df (O(n)).

    Parametry
    ---------
    df : DataFrame z all_matches.csv

    Zwraca
    ------
    (X, y) – feature matrix (18 cech) i etykiety (0=H, 1=D, 2=A)
    """
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    # Elo per liga – O(n), wykonywany raz
    elo_history = build_elo_history(df)

    result_map = {"H": 0, "D": 1, "A": 2}
    rows:   list[dict[str, Any]] = []
    labels: list[int] = []

    for _, match in df.iterrows():
        home   = str(match["HomeTeam"])
        away   = str(match["AwayTeam"])
        date   = match["Date"]
        league = str(match.get("league", "UNKNOWN"))

        odds_h = match.get("B365H", np.nan)
        odds_d = match.get("B365D", np.nan)
        odds_a = match.get("B365A", np.nan)

        if pd.isna(odds_h) or pd.isna(odds_d) or pd.isna(odds_a):
            continue

        ftr = match.get("FTR")
        if ftr not in result_map:
            continue

        home_hist = _get_team_history(df, home, date, config.FORM_WINDOW)
        away_hist = _get_team_history(df, away, date, config.FORM_WINDOW)

        home_form = _calc_form(home_hist, home, date)
        away_form = _calc_form(away_hist, away, date)

        h2h                       = _calc_h2h(df, home, away, date)
        prob_h, prob_d, prob_a    = remove_margin(odds_h, odds_d, odds_a)

        h_elo = _get_elo_before(elo_history, home, date, league)
        a_elo = _get_elo_before(elo_history, away, date, league)

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
            "home_elo":          h_elo,
            "away_elo":          a_elo,
            "elo_diff":          h_elo - a_elo,
        })
        labels.append(result_map[ftr])

    X = pd.DataFrame(rows, columns=FEATURE_COLS)
    y = pd.Series(labels, name="result")

    log.info(
        f"compute_features: {len(X)} rekordów, "
        f"rozkład: H={labels.count(0)} D={labels.count(1)} A={labels.count(2)}"
    )
    return X, y


def compute_features_upcoming(
    upcoming: list[dict],
    history_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Tworzy cechy dla nadchodzących meczów (bez etykiet).

    Parametry
    ---------
    upcoming    : lista słowników z kluczami:
                  home_team, away_team, date (pd.Timestamp),
                  league, odds_h, odds_d, odds_a
    history_df  : historyczny DataFrame z all_matches.csv

    Zwraca
    ------
    DataFrame z cechami (FEATURE_COLS) w tej samej kolejności co trening.
    """
    history_df = history_df.copy()
    history_df["Date"] = pd.to_datetime(history_df["Date"]).dt.tz_localize(None)

    elo_history = build_elo_history(history_df)

    rows: list[dict[str, Any]] = []

    for match in upcoming:
        home     = str(match["home_team"])
        away     = str(match["away_team"])
        league   = str(match.get("league", "UNKNOWN"))
        raw_date = pd.Timestamp(match["date"])
        date     = (
            raw_date.tz_localize(None)
            if raw_date.tzinfo is None
            else raw_date.tz_convert("UTC").tz_localize(None)
        )

        odds_h = float(match.get("odds_h", 2.0))
        odds_d = float(match.get("odds_d", 3.5))
        odds_a = float(match.get("odds_a", 4.0))

        home_hist = _get_team_history(history_df, home, date, config.FORM_WINDOW)
        away_hist = _get_team_history(history_df, away, date, config.FORM_WINDOW)

        home_form = _calc_form(home_hist, home, date)
        away_form = _calc_form(away_hist, away, date)

        h2h                    = _calc_h2h(history_df, home, away, date)
        prob_h, prob_d, prob_a = remove_margin(odds_h, odds_d, odds_a)

        h_elo = _get_elo_before(elo_history, home, date, league)
        a_elo = _get_elo_before(elo_history, away, date, league)

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
            "home_elo":          h_elo,
            "away_elo":          a_elo,
            "elo_diff":          h_elo - a_elo,
        })

    return pd.DataFrame(rows, columns=FEATURE_COLS)
