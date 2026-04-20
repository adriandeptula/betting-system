"""
pipeline/name_mapping.py
Ujednolicanie nazw drużyn między football-data.co.uk a The Odds API.

Problem: te same drużyny mają różne nazwy w różnych źródłach.
Rozwiązanie: słownik mapowań + fuzzy matching jako fallback.
"""
from difflib import SequenceMatcher

# Format: "nazwa z football-data.co.uk" → "nazwa z The Odds API"
TEAM_NAME_MAP: dict[str, str] = {
    # ── Premier League ───────────────────────────────────────────────────────
    "Man United":       "Manchester United",
    "Man City":         "Manchester City",
    "Wolves":           "Wolverhampton Wanderers",
    "Tottenham":        "Tottenham Hotspur",
    "Nott'm Forest":    "Nottingham Forest",
    "Newcastle":        "Newcastle United",
    "West Ham":         "West Ham United",
    "Brighton":         "Brighton and Hove Albion",
    "Leicester":        "Leicester City",
    "Leeds":            "Leeds United",
    "Norwich":          "Norwich City",
    "Brentford":        "Brentford",
    "Fulham":           "Fulham",
    "Bournemouth":      "AFC Bournemouth",
    "Sheffield United": "Sheffield United",
    "Luton":            "Luton Town",
    "Burnley":          "Burnley",
    "Ipswich":          "Ipswich Town",

    # ── Bundesliga ───────────────────────────────────────────────────────────
    "Leverkusen":       "Bayer 04 Leverkusen",
    "Bayern Munich":    "FC Bayern München",
    "Dortmund":         "Borussia Dortmund",
    "Frankfurt":        "Eintracht Frankfurt",
    "Werder":           "Werder Bremen",
    "Hoffenheim":       "TSG 1899 Hoffenheim",
    "Mainz":            "1. FSV Mainz 05",
    "Augsburg":         "FC Augsburg",
    "Heidenheim":       "1. FC Heidenheim 1846",
    "Monchengladbach":  "Borussia Mönchengladbach",
    "Freiburg":         "SC Freiburg",
    "Stuttgart":        "VfB Stuttgart",
    "RB Leipzig":       "RB Leipzig",
    "Wolfsburg":        "VfL Wolfsburg",
    "Darmstadt":        "SV Darmstadt 98",
    "Cologne":          "1. FC Köln",
    "Union Berlin":     "1. FC Union Berlin",
    "Bochum":           "VfL Bochum",
    "Hamburg":          "Hamburger SV",

    # ── La Liga ──────────────────────────────────────────────────────────────
    "Ath Madrid":       "Atletico Madrid",
    "Ath Bilbao":       "Athletic Club",
    "Betis":            "Real Betis",
    "Sociedad":         "Real Sociedad",
    "Vallecano":        "Rayo Vallecano",
    "Alaves":           "Deportivo Alavés",
    "Espanol":          "RCD Espanyol",
    "La Coruna":        "Deportivo La Coruña",
    "Vallodolid":       "Real Valladolid",
    "Celta":            "Celta Vigo",
    "Leganes":          "CD Leganés",

    # ── Serie A ──────────────────────────────────────────────────────────────
    "Inter":            "Inter Milan",
    "Verona":           "Hellas Verona",
    "Spal":             "SPAL",
    "Chievo":           "Chievo Verona",
    "CrotoneFC":        "FC Crotone",

    # ── Ekstraklasa ──────────────────────────────────────────────────────────
    "Legia":            "Legia Warszawa",
    "Lech":             "Lech Poznań",
    "Wisla":            "Wisła Kraków",
    "Wisla Krakow":     "Wisła Kraków",
    "Pogon":            "Pogoń Szczecin",
    "Pogon Szczecin":   "Pogoń Szczecin",
    "Rakow":            "Raków Częstochowa",
    "Rakow Czestochowa":"Raków Częstochowa",
    "Gornik":           "Górnik Zabrze",
    "Slask":            "Śląsk Wrocław",
    "Zaglebie":         "Zagłębie Lubin",
    "Cracovia":         "Cracovia Kraków",
    "Jagiellonia":      "Jagiellonia Białystok",
    "Piast":            "Piast Gliwice",
    "Korona":           "Korona Kielce",
    "Warta":            "Warta Poznań",
    "Stal Mielec":      "Stal Mielec",
    "Widzew":           "Widzew Łódź",
}

# Odwrotne mapowanie (Odds API → football-data)
_REVERSE_MAP: dict[str, str] = {v: k for k, v in TEAM_NAME_MAP.items()}

# Połączony słownik dla szybkiego sprawdzenia
_ALL_KNOWN: set[str] = set(TEAM_NAME_MAP.keys()) | set(_REVERSE_MAP.keys())


def normalize(name: str) -> str:
    """
    Normalizuje nazwę drużyny do formatu The Odds API.
    Jeśli nie znajdzie w słowniku, zwraca oryginalną nazwę.
    """
    if name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[name]
    # Już jest w formacie docelowym?
    if name in _REVERSE_MAP:
        return name
    return name


def fuzzy_match(name: str, candidates: list[str], threshold: float = 0.75) -> str | None:
    """
    Fuzzy matching jako fallback gdy bezpośrednie mapowanie zawodzi.
    Używaj ostrożnie – niska wartość threshold może dać błędne wyniki.
    """
    best_ratio = 0.0
    best_match = None
    normalized = normalize(name).lower()

    for candidate in candidates:
        ratio = SequenceMatcher(None, normalized, candidate.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = candidate

    return best_match if best_ratio >= threshold else None


def match_teams(fd_team: str, odds_teams: list[str]) -> str:
    """
    Próbuje dopasować nazwę drużyny z football-data do listy nazw z Odds API.
    Kolejność prób: bezpośrednie mapowanie → fuzzy matching → oryginalna nazwa.
    """
    # 1. Bezpośrednie mapowanie
    mapped = normalize(fd_team)
    if mapped in odds_teams:
        return mapped

    # 2. Fuzzy matching
    fuzzy = fuzzy_match(fd_team, odds_teams)
    if fuzzy:
        return fuzzy

    # 3. Fallback
    return fd_team
