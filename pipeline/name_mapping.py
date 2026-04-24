"""
pipeline/name_mapping.py – Mapowanie nazw drużyn między źródłami danych.

Problem: ta sama drużyna ma różne nazwy w różnych źródłach.
  football-data.co.uk: "Man United"
  The Odds API:        "Manchester United"
  API-Football:        "Manchester Utd"

v1.1: fuzzy matching (rapidfuzz) jako fallback gdy brak ręcznego mapowania.
Nieznane drużyny są logowane z sugestią najbliższego dopasowania.

Jak dodać nowe mapowanie:
  Znajdź w logach linię "Brak mapowania: X" i dodaj wpis do TEAM_MAP poniżej.
"""
import logging

log = logging.getLogger(__name__)

# ── Ręczne mapowania ─────────────────────────────────────────────────────────
# Klucz: nazwa z football-data.co.uk (model trenuje na tej nazwie)
# Wartości: nazwy spotykane w The Odds API i API-Football
#
# Format: "fd_name": ["odds_api_name_1", "odds_api_name_2", ...]

TEAM_MAP: dict[str, list[str]] = {
    # ── Premier League ───────────────────────────────────────────────────────
    "Man United":       ["Manchester United", "Manchester Utd", "Man Utd"],
    "Man City":         ["Manchester City", "Manchester City FC"],
    "Tottenham":        ["Tottenham Hotspur", "Spurs"],
    "Newcastle":        ["Newcastle United", "Newcastle Utd"],
    "Wolves":           ["Wolverhampton Wanderers", "Wolverhampton"],
    "Sheffield United": ["Sheffield Utd"],
    "Nott'm Forest":    ["Nottingham Forest", "Nottm Forest"],
    "Brighton":         ["Brighton & Hove Albion", "Brighton and Hove Albion"],
    "West Ham":         ["West Ham United"],
    "Leicester":        ["Leicester City"],
    "Leeds":            ["Leeds United"],
    "Southampton":      ["Southampton FC"],
    "Brentford":        ["Brentford FC"],
    "Fulham":           ["Fulham FC"],
    "Bournemouth":      ["AFC Bournemouth"],
    "Arsenal":          ["Arsenal FC"],
    "Chelsea":          ["Chelsea FC"],
    "Liverpool":        ["Liverpool FC"],
    "Everton":          ["Everton FC"],
    "Aston Villa":      ["Aston Villa FC"],
    "Crystal Palace":   ["Crystal Palace FC"],

    # ── Bundesliga ───────────────────────────────────────────────────────────
    "Bayern Munich":    ["FC Bayern München", "Bayern München", "Bayern Munchen"],
    "Dortmund":         ["Borussia Dortmund", "BVB", "Borussia Dortmund FC"],
    "Leverkusen":       ["Bayer Leverkusen", "Bayer 04 Leverkusen"],
    "Frankfurt":        ["Eintracht Frankfurt"],
    "Leipzig":          ["RB Leipzig"],
    "Wolfsburg":        ["VfL Wolfsburg"],
    "Freiburg":         ["SC Freiburg"],
    "Monchengladbach":  ["Borussia M'gladbach", "Borussia Mönchengladbach"],
    "Werder Bremen":    ["SV Werder Bremen"],
    "Stuttgart":        ["VfB Stuttgart"],
    "Hoffenheim":       ["TSG 1899 Hoffenheim", "TSG Hoffenheim"],
    "Augsburg":         ["FC Augsburg"],
    "Mainz":            ["1. FSV Mainz 05", "FSV Mainz 05"],
    "Union Berlin":     ["1. FC Union Berlin", "FC Union Berlin"],
    "Cologne":          ["1. FC Köln", "FC Cologne"],
    "Bochum":           ["VfL Bochum"],
    "Darmstadt":        ["SV Darmstadt 98"],
    "Heidenheim":       ["1. FC Heidenheim"],

    # ── La Liga ──────────────────────────────────────────────────────────────
    "Barcelona":        ["FC Barcelona", "Barca"],
    "Real Madrid":      ["Real Madrid CF"],
    "Atletico Madrid":  ["Atlético Madrid", "Atletico de Madrid", "Club Atletico de Madrid"],
    "Sevilla":          ["Sevilla FC"],
    "Valencia":         ["Valencia CF"],
    "Villarreal":       ["Villarreal CF"],
    "Real Sociedad":    ["Real Sociedad de Futbol", "Real Sociedad FC"],
    "Athletic Club":    ["Athletic Bilbao", "Athletic Club de Bilbao"],
    "Osasuna":          ["CA Osasuna"],
    "Getafe":           ["Getafe CF"],
    "Celta Vigo":       ["Celta de Vigo", "RC Celta"],
    "Betis":            ["Real Betis", "Real Betis Balompie"],
    "Rayo Vallecano":   ["Rayo Vallecano de Madrid"],
    "Girona":           ["Girona FC"],
    "Las Palmas":       ["UD Las Palmas"],
    "Mallorca":         ["RCD Mallorca"],
    "Alaves":           ["Deportivo Alaves", "Deportivo Alavés"],
    "Cadiz":            ["Cádiz CF", "Cadiz CF"],
    "Almeria":          ["UD Almería", "UD Almeria"],
    "Granada":          ["Granada CF"],
    "Leganes":          ["CD Leganés"],
    "Valladolid":       ["Real Valladolid"],
    "Espanyol":         ["RCD Espanyol", "Espanyol Barcelona"],

    # ── Serie A ──────────────────────────────────────────────────────────────
    "Juventus":         ["Juventus FC"],
    "Inter":            ["Inter Milan", "FC Internazionale", "Internazionale"],
    "AC Milan":         ["Milan", "AC Milan"],
    "Napoli":           ["SSC Napoli"],
    "Roma":             ["AS Roma"],
    "Lazio":            ["SS Lazio"],
    "Atalanta":         ["Atalanta BC"],
    "Fiorentina":       ["ACF Fiorentina"],
    "Bologna":          ["Bologna FC"],
    "Torino":           ["Torino FC"],
    "Udinese":          ["Udinese Calcio"],
    "Sassuolo":         ["US Sassuolo"],
    "Empoli":           ["Empoli FC"],
    "Monza":            ["AC Monza"],
    "Frosinone":        ["Frosinone Calcio"],
    "Cagliari":         ["Cagliari Calcio"],
    "Lecce":            ["US Lecce"],
    "Salernitana":      ["US Salernitana"],
    "Genoa":            ["Genoa CFC"],
    "Verona":           ["Hellas Verona", "Hellas Verona FC"],
    "Sampdoria":        ["UC Sampdoria"],
    "Parma":            ["Parma Calcio 1913"],
    "Venezia":          ["Venezia FC"],
    "Como":             ["Como 1907"],

    # ── Ekstraklasa ──────────────────────────────────────────────────────────
    "Legia Warsaw":     ["Legia Warszawa", "Legia"],
    "Lech Poznan":      ["Lech Poznań", "Lech"],
    "Rakow":            ["Raków Częstochowa", "Rakow Czestochowa"],
    "Wisla Krakow":     ["Wisła Kraków", "Wisla"],
    "Zaglebie Lubin":   ["Zagłębie Lubin"],
    "Pogon Szczecin":   ["Pogoń Szczecin", "Pogon"],
    "Jagiellonia":      ["Jagiellonia Białystok", "Jagiellonia Bialystok"],
    "Slask Wroclaw":    ["Śląsk Wrocław", "Slask"],
    "Cracovia":         ["MKS Cracovia"],
    "Piast Gliwice":    ["Piast"],
    "Gornik Zabrze":    ["Górnik Zabrze"],
    "Warta Poznan":     ["Warta Poznań"],
    "Widzew Lodz":      ["Widzew Łódź"],
    "LKS Lodz":         ["ŁKS Łódź", "LKS"],
    "Korona Kielce":    ["Korona"],
    "Ruch Chorzow":     ["Ruch Chorzów"],
    "Puszcza Niepolomice": ["Puszcza Niepołomice", "Puszcza"],
    "Stal Mielec":      ["Stal"],
    "Motor Lublin":     ["Motor"],
    "GKS Katowice":     ["GKS"],
    "Nieciecza":        ["Bruk-Bet Termalica", "Termalica Bruk-Bet Nieciecza"],
    "Lechia Gdansk":    ["Lechia Gdańsk", "Lechia"],
    "Wisla Plock":      ["Wisła Płock"],
    "Radomiak":         ["Radomiak Radom"],
    "Arka Gdynia":      ["Arka"],

    # ── Championship (EFL) – pojawia się w The Odds API ──────────────────────
    "Burnley":          ["Burnley FC"],
    "Sunderland":       ["Sunderland AFC"],
    "Sheffield Weds":   ["Sheffield Wednesday"],
    "Middlesbrough":    ["Middlesbrough FC"],
    "Stoke":            ["Stoke City"],
    "West Brom":        ["West Bromwich Albion", "WBA"],
    "QPR":              ["Queens Park Rangers"],
    "Coventry":         ["Coventry City"],
    "Luton":            ["Luton Town"],
    "Watford":          ["Watford FC"],
    "Swansea":          ["Swansea City"],
    "Millwall":         ["Millwall FC"],
    "Bristol City":     ["Bristol City FC"],
    "Preston":          ["Preston North End"],
    "Hull":             ["Hull City"],
    "Blackburn":        ["Blackburn Rovers"],
    "Cardiff":          ["Cardiff City"],
    "Norwich":          ["Norwich City"],
    "Derby":            ["Derby County"],
    "Plymouth":         ["Plymouth Argyle"],
    "Portsmouth":       ["Portsmouth FC"],
    "Oxford United":    ["Oxford Utd"],

    # ── 2. Bundesliga – pojawia się w The Odds API ────────────────────────────
    "Hamburg":          ["Hamburger SV", "HSV"],
    "St Pauli":         ["FC St. Pauli", "St. Pauli"],
    "Hannover":         ["Hannover 96"],
    "Schalke":          ["FC Schalke 04", "Schalke 04"],
    "Kaiserslautern":   ["1. FC Kaiserslautern"],
    "Paderborn":        ["SC Paderborn 07"],
    "Magdeburg":        ["1. FC Magdeburg"],
    "Nuremberg":        ["1. FC Nürnberg", "FC Nurnberg"],
    "Karlsruhe":        ["Karlsruher SC"],
    "Elversberg":       ["SV Elversberg"],
    "Greuther Furth":   ["SpVgg Greuther Fürth"],
    "Braunschweig":     ["Eintracht Braunschweig"],
    "Hertha":           ["Hertha BSC"],

    # ── La Liga 2 – pojawia się w The Odds API ────────────────────────────────
    "Elche":            ["Elche CF"],
    "Levante":          ["Levante UD"],
    "Oviedo":           ["Real Oviedo"],
    "Burgos":           ["Burgos CF"],
    "Racing Santander": ["Racing Club de Santander"],
    "Tenerife":         ["CD Tenerife"],
    "Zaragoza":         ["Real Zaragoza"],
    "Sporting Gijon":   ["Real Sporting de Gijón"],
    "Huesca":           ["SD Huesca"],
    "Albacete":         ["Albacete Balompié"],
    "Mirandes":         ["CD Mirandés"],
    "Castellon":        ["CD Castellón"],
    "Eldense":          ["CD Eldense"],
    "Ferrol":           ["Racing de Ferrol"],
    "Cartagena":        ["FC Cartagena"],

    # ── Serie B – pojawia się w The Odds API ──────────────────────────────────
    "Cremonese":        ["US Cremonese"],
    "Pisa":             ["AC Pisa 1909", "Pisa SC"],
    "Spezia":           ["Spezia Calcio"],
    "Palermo":          ["US Città di Palermo", "Palermo FC"],
    # Uwaga: Sassuolo B i Sampdoria B celowo pominięte – mają identyczne aliasy
    # jak drużyny Serie A ("US Sassuolo", "UC Sampdoria"). Przy zjeździe do Serie B
    # fuzzy matching poprawnie dopasuje do drużyny macierzystej, co jest pożądane
    # (brak danych treningowych dla Serie B – używamy historii z Serie A).
    "Bari":             ["SSC Bari"],
    "Brescia":          ["Brescia Calcio"],
    "Catanzaro":        ["US Catanzaro"],
    "Cesena":           ["Cesena FC"],
    "Cosenza":          ["Cosenza Calcio"],
    "Juve Stabia":      ["SS Juve Stabia"],
    "Mantova":          ["Mantova FC"],
    "Modena":           ["Modena FC"],
    "Salernitana B":    ["US Salernitana 1919"],
    "Sudtirol":         ["FC Südtirol"],
    "Reggiana":         ["AC Reggiana"],
}

# ── Wewnętrzny słownik odwrotny (wartość → klucz) ────────────────────────────
_REVERSE: dict[str, str] = {}
for _fd_name, _aliases in TEAM_MAP.items():
    _REVERSE[_fd_name.lower()] = _fd_name  # fd_name też mapuje sam na siebie
    for _alias in _aliases:
        _REVERSE[_alias.lower()] = _fd_name

# ── Cache dla fuzzy match ────────────────────────────────────────────────────
_FUZZY_CACHE: dict[str, str | None] = {}

# Wszystkie znane nazwy fd (lewy słupek mapowania)
_ALL_FD_NAMES: list[str] = list(TEAM_MAP.keys())


def _fuzzy_match(name: str, threshold: int = 80) -> str | None:
    """
    Próbuje dopasować `name` do jednej z znanych nazw fd-name przy użyciu
    rapidfuzz. Wymaga zainstalowanej biblioteki rapidfuzz (requirements.txt).

    Zwraca dopasowaną fd-name lub None jeśli score < threshold.
    """
    if name in _FUZZY_CACHE:
        return _FUZZY_CACHE[name]

    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        log.debug("rapidfuzz nie jest zainstalowany – fuzzy matching niedostępny")
        _FUZZY_CACHE[name] = None
        return None

    # Szukaj w fd_names ORAZ aliasach (spłaszczone do jednej listy)
    all_names = list(_REVERSE.keys())
    result = process.extractOne(
        name.lower(),
        all_names,
        scorer=fuzz.token_sort_ratio,
    )

    if result is None or result[1] < threshold:
        _FUZZY_CACHE[name] = None
        return None

    matched_lower = result[0]
    fd_name = _REVERSE.get(matched_lower)
    _FUZZY_CACHE[name] = fd_name
    return fd_name


def normalize(name: str, source: str = "unknown") -> str:
    """
    Normalizuje nazwę drużyny do standardowej formy z football-data.co.uk.

    Przepływ:
      1. Szukaj w ręcznym słowniku (dokładne dopasowanie, case-insensitive)
      2. Jeśli nie znaleziono – próbuj fuzzy match (rapidfuzz)
      3. Jeśli nadal nie znaleziono – zwróć oryginalną nazwę i zaloguj ostrzeżenie

    Parametry
    ---------
    name   : nazwa drużyny do znormalizowania
    source : skąd pochodzi nazwa (do lepszych logów)

    Zwraca
    ------
    Znormalizowana nazwa (fd-name) lub oryginalna nazwa przy braku dopasowania.
    """
    key = name.strip().lower()

    # 1. Dokładne dopasowanie
    if key in _REVERSE:
        return _REVERSE[key]

    # 2. Fuzzy match
    fuzzy_result = _fuzzy_match(name)
    if fuzzy_result is not None:
        log.debug(
            f"Fuzzy match [{source}]: '{name}' → '{fuzzy_result}' "
            "(dodaj do TEAM_MAP dla pewności)"
        )
        return fuzzy_result

    # 3. Brak dopasowania
    log.warning(
        f"Brak mapowania [{source}]: '{name}'. "
        f"Dodaj do pipeline/name_mapping.py → TEAM_MAP"
    )
    return name


def normalize_batch(
    names: list[str],
    source: str = "unknown",
) -> list[str]:
    """Normalizuje listę nazw drużyn naraz."""
    return [normalize(n, source) for n in names]
