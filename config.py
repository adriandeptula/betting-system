"""
config.py – Centralna konfiguracja systemu.
Wszystkie parametry w jednym miejscu.

v1.5 zmiany:
  - SEASONS obliczane dynamicznie na podstawie daty (koniec hardcoded "2526")
  - TAX_THRESHOLD_PLN udokumentowany
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
# Obliczane dynamicznie: ostatnie 5 sezonów + bieżący.
# Format football-data.co.uk: "2425" = sezon 2024/25.
# Sezon piłkarski zaczyna się w lipcu/sierpniu.
def _build_seasons(n_historical: int = 4) -> list[str]:
    today   = _date.today()
    # Jeśli jesteśmy po lipcu — bieżący sezon kończy się w przyszłym roku
    end_yr  = today.year + 1 if today.month >= 7 else today.year
    seasons = []
    for end in range(end_yr - n_historical, end_yr + 1):
        s = str(end - 1)[-2:] + str(end)[-2:]
        seasons.append(s)
    return seasons


SEASONS: list[str] = _build_seasons(n_historical=4)


# ── API – The Odds API ───────────────────────────────────────────────────────
# 3 klucze (3 konta) – system automatycznie przełącza się na kolejny
# gdy bieżący wyczerpie limit requestów (darmowy tier: 500/miesiąc/konto).
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
# 12 % podatek od gier wliczony w overround – remove_margin() go eliminuje.
# 10 % podatek zryczałtowany: pobierany gdy jednorazowa wygrana > 2280 PLN.
# Przy obecnych parametrach (BANKROLL ≤ 15 000 PLN, MAX_BET_PCT=3 %,
# MAX_ODDS=3.20) max wygrana ≈ 30 * 3.20 = 96 PLN – próg nieosiągalny.
# Dla bankrollu > 15 000 PLN uwzględnij korektę w kelly_stake (v1.5 TODO).
TAX_THRESHOLD_PLN = 2280.0


# ── Elo rating ────────────────────────────────────────────────────────────────
ELO_START = 1500  # Startowy rating dla nowych drużyn
ELO_K     = 20    # Współczynnik K (standard piłka nożna)
# Elo obliczany OSOBNO per liga — unikamy cross-league contamination.
# Każda liga ma niezależną skalę ratingów, co jest poprawne dopóki
# drużyny nie grają między ligami (puchar UEFA – v2.0).


# ── Zakresy kursów ────────────────────────────────────────────────────────────
MIN_ODDS          = 1.50  # Min kurs na nogę 1X2
MAX_ODDS          = 3.20  # Max kurs 1X2 (unikamy longshots)
DC_MIN_ODDS       = 1.20  # Min kurs double chance
DC_MAX_ODDS       = 2.00  # Max kurs double chance
DC_MIN_MODEL_PROB = 0.55  # Min pewność dla double chance


# ── Kupon – ogólne ────────────────────────────────────────────────────────────
MAX_LEGS         = 3  # Max nogi w jednym parlayach
COUPONS_PER_WEEK = 3  # Ile kuponów tygodniowo


# ── Ścieżki plików ────────────────────────────────────────────────────────────
DATA_RAW       = "data/raw"
DATA_PROCESSED = "data/processed"
DATA_ODDS      = "data/odds"
DATA_RESULTS   = "data/results"
MODEL_PATH     = "data/model/model.pkl"
