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
    },
    "BL": {
        "fd_code": "D1",
        "odds_key": "soccer_germany_bundesliga",
        "name": "Bundesliga",
        "country": "Germany",
    },
    "LL": {
        "fd_code": "SP1",
        "odds_key": "soccer_spain_la_liga",
        "name": "La Liga",
        "country": "Spain",
    },
    "SA": {
        "fd_code": "I1",
        "odds_key": "soccer_italy_serie_a",
        "name": "Serie A",
        "country": "Italy",
    },
    "EK": {
        "fd_code": "P1",
        "odds_key": "soccer_poland_ekstraklasa",
        "name": "Ekstraklasa",
        "country": "Poland",
    },
}

# Sezony historyczne do pobrania (format football-data.co.uk)
SEASONS = ["2122", "2223", "2324", "2425", "2526"]

# ── API – The Odds API ───────────────────────────────────────────────────────
# 3 klucze (3 konta) – system automatycznie przełącza się na kolejny
# gdy bieżący wyczerpie limit requestów (darmowy tier: 500/miesiąc/konto)
# Łącznie: 1500 req/miesiąc z 3 kontami
ODDS_API_KEYS = [
    k for k in [
        os.environ.get("ODDS_API_KEY", ""),
        os.environ.get("ODDS_API_KEY_2", ""),
        os.environ.get("ODDS_API_KEY_3", ""),
    ] if k
]
ODDS_API_BASE    = "https://api.the-odds-api.com/v4"
ODDS_API_REGIONS = "eu"
ODDS_API_MARKETS = "h2h"

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Model ─────────────────────────────────────────────────────────────────────
FORM_WINDOW          = 8      # Ostatnie N meczów do obliczania formy (v1.3: 5→8)
FORM_HALFLIFE_DAYS   = 21     # Półokres zaniku wagi formy [v1.3]: mecz 3 tyg. temu
                               # waży 2x mniej niż z ostatniego tygodnia
MIN_EDGE             = 0.05   # Minimalna przewaga nad kursem bukmachera (5%)
MIN_MODEL_PROB       = 0.40   # Minimalna pewność modelu dla 1X2 (40%)
KELLY_FRACTION       = 0.25   # Frakcja Kelly (0.25 = bezpieczna)
MAX_BET_PCT          = 0.03   # Max 3% bankrollu na jeden kupon
BANKROLL             = float(os.environ.get("BANKROLL", "1000"))  # PLN

# ── Elo rating [v1.3] ────────────────────────────────────────────────────────
ELO_START = 1500   # Startowy rating dla nowych drużyn
ELO_K     = 20     # Współczynnik K – czułość na wyniki
                    # 20 = standard dla piłki nożnej
                    # Wyższy K → szybsza adaptacja, większe wahania

# ── Kupon – zakresy kursów ────────────────────────────────────────────────────
# 1X2 (wynik meczu)
MIN_ODDS         = 1.50  # Min kurs na nogę 1X2
MAX_ODDS         = 3.20  # Max kurs 1X2 (unikamy longshots)

# Double chance (1X, X2, 12) – kursy są z natury niższe
DC_MIN_ODDS      = 1.20  # Min kurs na nogę double chance
DC_MAX_ODDS      = 2.00  # Max kurs double chance
DC_MIN_MODEL_PROB = 0.55  # Min pewność modelu dla double chance

# ── Kupon – ogólne ────────────────────────────────────────────────────────────
MAX_LEGS         = 3     # Max nogi w jednym parlayach
COUPONS_PER_WEEK = 3     # Ile kuponów tygodniowo

# ── Ścieżki plików ────────────────────────────────────────────────────────────
DATA_RAW       = "data/raw"
DATA_PROCESSED = "data/processed"
DATA_ODDS      = "data/odds"
DATA_RESULTS   = "data/results"
MODEL_PATH     = "data/model/model.pkl"
