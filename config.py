"""
config.py – Centralna konfiguracja systemu.
Wszystkie parametry w jednym miejscu.
"""
import os

# ── Ligi ────────────────────────────────────────────────────────────────────
LEAGUES = {
    "EPL": {
        "fd_code": "E0",
        "odds_key": "soccer_epl",
        "name": "Premier League",
        "country": "England",
        "apifootball_id": 39,
    },
    "BL": {
        "fd_code": "D1",
        "odds_key": "soccer_germany_bundesliga",
        "name": "Bundesliga",
        "country": "Germany",
        "apifootball_id": 78,
    },
    "LL": {
        "fd_code": "SP1",
        "odds_key": "soccer_spain_la_liga",
        "name": "La Liga",
        "country": "Spain",
        "apifootball_id": 140,
    },
    "SA": {
        "fd_code": "I1",
        "odds_key": "soccer_italy_serie_a",
        "name": "Serie A",
        "country": "Italy",
        "apifootball_id": 135,
    },
    "EK": {
        "fd_code": "P1",
        "odds_key": "soccer_poland_ekstraklasa",
        "name": "Ekstraklasa",
        "country": "Poland",
        "apifootball_id": 106,
    },
}

# Sezony historyczne do pobrania (format football-data.co.uk)
SEASONS = ["2122", "2223", "2324", "2425"]

# Aktualny sezon dla API-Football (format YYYY)
CURRENT_SEASON = 2024

# ── API – The Odds API ───────────────────────────────────────────────────────
# 2 klucze (2 konta) – system automatycznie przełącza się na drugi
# gdy pierwszy wyczerpie limit requestów (darmowy tier: 500/miesiąc)
ODDS_API_KEYS = [
    k for k in [
        os.environ.get("ODDS_API_KEY", ""),
        os.environ.get("ODDS_API_KEY_2", ""),
    ] if k
]
ODDS_API_BASE    = "https://api.the-odds-api.com/v4"
ODDS_API_REGIONS = "eu"
ODDS_API_MARKETS = "h2h"

# ── API – API-Football ───────────────────────────────────────────────────────
# 2 klucze (2 konta) – system automatycznie przełącza się na drugi
# gdy pierwszy wyczerpie limit requestów (darmowy tier: 100/dzień)
API_FOOTBALL_KEYS = [
    k for k in [
        os.environ.get("API_FOOTBALL_KEY", ""),
        os.environ.get("API_FOOTBALL_KEY_2", ""),
    ] if k
]
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
API_FOOTBALL_HOST = "v3.football.api-sports.io"

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Model ─────────────────────────────────────────────────────────────────────
FORM_WINDOW     = 5      # Ostatnie N meczów do obliczania formy
MIN_EDGE        = 0.05   # Minimalna przewaga nad kursem bukmachera (5%)
MIN_MODEL_PROB  = 0.40   # Minimalna pewność modelu (40%)
KELLY_FRACTION  = 0.25   # Frakcja Kelly (0.25 = bezpieczna)
MAX_BET_PCT     = 0.03   # Max 3% bankrollu na jeden kupon
BANKROLL        = float(os.environ.get("BANKROLL", "1000"))  # PLN

# ── Kupon ─────────────────────────────────────────────────────────────────────
MAX_LEGS         = 3     # Max nogi w jednym parlayach
MIN_ODDS         = 1.50  # Min kurs na nogę
MAX_ODDS         = 3.20  # Max kurs na nogę (unikamy longshots)
COUPONS_PER_WEEK = 3     # Ile kuponów tygodniowo

# ── Ścieżki plików ────────────────────────────────────────────────────────────
DATA_RAW       = "data/raw"
DATA_PROCESSED = "data/processed"
DATA_ODDS      = "data/odds"
DATA_INJURIES  = "data/injuries"
DATA_RESULTS   = "data/results"
MODEL_PATH     = "data/model/model.pkl"
