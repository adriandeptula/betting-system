"""
config.py – Centralna konfiguracja systemu.
Wszystkie parametry w jednym miejscu.

v1.6 zmiany:
  - CLV_CLOSING_HOURS: ile godzin przed meczem kursy traktujemy jako closing
  - OPTUNA_TRIALS: liczba prób tuningu hiperparametrów (0 = wyłączone)
  - DRAW_CLASS_WEIGHT: waga remisów w treningu (>1 = lepiej kalibrowany remis)
"""
import os
from datetime import date as _date


# ── Ligi ────────────────────────────────────────────────────────────────────
LEAGUES = {
    "EPL": {
        "fd_code":  "E0",
        "odds_key": "soccer_epl",
        "name":     "Premier League",
        "country":  "England",
    },
    "BL": {
        "fd_code":  "D1",
        "odds_key": "soccer_germany_bundesliga",
        "name":     "Bundesliga",
        "country":  "Germany",
    },
    "LL": {
        "fd_code":  "SP1",
        "odds_key": "soccer_spain_la_liga",
        "name":     "La Liga",
        "country":  "Spain",
    },
    "SA": {
        "fd_code":  "I1",
        "odds_key": "soccer_italy_serie_a",
        "name":     "Serie A",
        "country":  "Italy",
    },
    "EK": {
        "fd_code":  "P1",
        "odds_key": "soccer_poland_ekstraklasa",
        "name":     "Ekstraklasa",
        "country":  "Poland",
    },
}


# ── Sezony historyczne ───────────────────────────────────────────────────────
def _build_seasons(n_historical: int = 4) -> list[str]:
    today  = _date.today()
    end_yr = today.year + 1 if today.month >= 7 else today.year
    seasons = []
    for end in range(end_yr - n_historical, end_yr + 1):
        s = str(end - 1)[-2:] + str(end)[-2:]
        seasons.append(s)
    return seasons


SEASONS: list[str] = _build_seasons(n_historical=4)


# ── API – The Odds API ───────────────────────────────────────────────────────
ODDS_API_KEYS: list[str] = [
    k for k in [
        os.environ.get("ODDS_API_KEY",   ""),
        os.environ.get("ODDS_API_KEY_2", ""),
        os.environ.get("ODDS_API_KEY_3", ""),
    ] if k
]
ODDS_API_BASE    = "https://api.the-odds-api.com/v4"
ODDS_API_REGIONS = "eu"
ODDS_API_MARKETS = "h2h"


# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ── Model ─────────────────────────────────────────────────────────────────────
FORM_WINDOW        = 8     # Ostatnie N meczów do formy
FORM_HALFLIFE_DAYS = 21    # Półokres zaniku wagi formy [dni]
MIN_EDGE           = 0.05  # Min przewaga nad kursem bukmachera (5 %)
MIN_MODEL_PROB     = 0.40  # Min pewność modelu dla 1X2
KELLY_FRACTION     = 0.25  # Frakcja Kelly (0.25 = bezpieczna)
MAX_BET_PCT        = 0.03  # Max 3 % bankrollu na jeden kupon


# ── Bankroll ──────────────────────────────────────────────────────────────────
_bankroll_raw = os.environ.get("BANKROLL", "1000")
try:
    BANKROLL = float(_bankroll_raw)
except ValueError:
    BANKROLL = 1000.0

if BANKROLL <= 0:
    raise ValueError(
        f"BANKROLL musi być > 0, otrzymano: '{_bankroll_raw}'. "
        "Ustaw zmienną BANKROLL w GitHub Secrets (np. BANKROLL=1000)."
    )


# ── Podatek od wygranych (Polska) ─────────────────────────────────────────────
TAX_THRESHOLD_PLN = 2280.0


# ── Elo rating ────────────────────────────────────────────────────────────────
ELO_START = 1500
ELO_K     = 20


# ── Zakresy kursów ────────────────────────────────────────────────────────────
MIN_ODDS          = 1.50
MAX_ODDS          = 3.20
DC_MIN_ODDS       = 1.20
DC_MAX_ODDS       = 2.00
DC_MIN_MODEL_PROB = 0.55


# ── Kupon – ogólne ────────────────────────────────────────────────────────────
MAX_LEGS         = 3
COUPONS_PER_WEEK = 3


# ── CLV (Closing Line Value) ──────────────────────────────────────────────────
# Ile godzin przed meczem traktujemy aktualne kursy jako "closing odds".
# Codzienny fetch o 06:00 UTC → dla meczów wieczornych (~20:00) to ~14h
# przed kick-offem: wystarczające do pomiaru CLV bez dodatkowych API calls.
CLV_CLOSING_HOURS = 24


# ── Optuna hyperparameter tuning ──────────────────────────────────────────────
# Liczba prób Optuna z expanding window CV (TimeSeriesSplit n_splits=3).
# 30 trials × 3 folds ≈ 10-15 min na GitHub Actions.
# Ustaw 0 żeby wyłączyć tuning i używać domyślnych parametrów XGBoost.
# Ustaw 50-100 lokalnie jeśli masz więcej czasu.
OPTUNA_TRIALS = 30


# ── Waga klasy remis w treningu ───────────────────────────────────────────────
# Remisy są trudne do przewidzenia i rzadsze w danych.
# Waga > 1.0 poprawia kalibrację dla klasy D bez przekalibrowania H/A.
DRAW_CLASS_WEIGHT = 1.5


# ── Ścieżki plików ────────────────────────────────────────────────────────────
DATA_RAW       = "data/raw"
DATA_PROCESSED = "data/processed"
DATA_ODDS      = "data/odds"
DATA_RESULTS   = "data/results"
MODEL_PATH     = "data/model/model.pkl"
