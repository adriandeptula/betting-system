# CLAUDE.md — Wytyczne kontekstowe dla AI Betting System v1.5

Ten plik zawiera pełny kontekst systemu dla Claude. Czytaj go przed każdą
modyfikacją kodu — szczególnie przed zmianami w model/features.py, model/train.py,
coupon/kelly.py i model/evaluate.py.

---

## Czym jest ten projekt

Automatyczny system value bettingu na piłkę nożną. Stack:
- **ML:** XGBoost + kalibracja Platta (Scikit-learn CalibratedClassifierCV)
- **Infrastruktura:** GitHub Actions (0 PLN/miesiąc, wszystko w chmurze)
- **Powiadomienia:** Telegram Bot API (polling co godzinę)
- **Dane:** football-data.co.uk (historyczne wyniki), The Odds API (aktualne kursy)

**System NIE stawia zakładów automatycznie** — generuje sugestie i wysyła na Telegram.
Właściciel sam decyduje czy i ile postawić.

---

## Aktualna wersja: v1.5

### Co naprawiono w v1.5 (KRYTYCZNE — znaj te zmiany)

| # | Plik | Problem | Naprawa |
|---|------|---------|---------|
| 1 | `model/evaluate.py` | Model ROI liczony przez proporcję całości zamiast per kupon | `staked_resolved` śledzi tylko WON+LOST kupony |
| 2 | `model/train.py` | `_simulate_roi`: `0.95/market_p` = fair_odds×0.95 (zaniżony ROI) | `bookmaker_odds = fair_odds / 1.05` |
| 3 | `notify/finance.py` | `pending_player` — błąd domknięcia `cid` + nie w return dict | Przepisane, `pending_player_coupons` w return |
| 4 | `coupon/kelly.py` | guard na `odds <= 1.0` brak, `parlay_stake` dzielił przez `len(legs)` | Guard dodany, dzielnik `len(individual)` |
| 5 | `model/train.py` | Kalibracja Platta z random k-fold (data leakage) | `cv='prefit'` z temporal split |
| 6 | `model/evaluate.py` | `days_back=7` hardcoded (kupony starsze >7 dni nie rozliczane) | `_compute_dynamic_days_back()`, max 14 dni |
| 7 | `pipeline/fetch_stats.py` | Brak deduplikacji po concat (duplikaty meczów) | `drop_duplicates(["Date","HomeTeam","AwayTeam"])` |
| 8 | `pipeline/name_mapping.py` | `normalize(None)` → `AttributeError` | Guard `if not name: return ""` |
| 9 | `.github/workflows/*.yml` | Race condition przy równoległych git push | `concurrency: {group: data-write}` |
| 10 | `model/features.py` | Elo cross-liga (wszystkie ligi w jednej skali) | Elo per liga, `build_elo_history` zwraca `{liga: {team: history}}` |
| 11 | `model/train.py` | Brak logowania feature importance | `_log_feature_importance()` po każdym treningu |
| 12 | `config.py` | SEASONS hardcoded ("2526") — zaśmiecone logi | `_build_seasons()` dynamicznie z daty |

---

## Architektura — przepływ danych

```
KROK 1 — DANE (daily_fetch, codziennie 06:00 UTC)
  football-data.co.uk → CSV → data/raw/all_matches.csv
    (5 lig × 5 sezonów, deduplikacja po concat)
  The Odds API (h2h, eu) → JSON → data/odds/odds_YYYY-MM-DD.json
    (3 klucze z auto-fallback przy 401/402/429)

KROK 2 — MODEL (weekly_retrain, poniedziałek 05:00 UTC)
  all_matches.csv
    → features.py: walk-forward, Elo per liga, forma ważona, H2H
    → train.py: XGBoost (X_base 68%) → Platt (X_cal 17%) → test (15%)
    → model.pkl + calibration.png + feature_importance w logach

KROK 3 — KUPONY (coupon_gen, śr + pt 09:00 UTC)
  model.pkl + odds_*.json
    → predict.py → value_engine.py (1X2 + DC) → builder.py
    → Telegram: kupony #1, #2, #3 z numerami

KROK 4 — BOT (bot_polling, co godzinę)
  auto_resolve_pending_coupons() [days_back dynamiczny]
    → The Odds API /scores → rozlicza PENDING w coupons_history.json
  getUpdates → bot_handler.py:
    /stake [nr] [kwota] → finance.json (Player ROI)
    /won   [nr] [kwota] → finance.json
    /stats              → evaluate.py (Model ROI)

KROK 5 — STATYSTYKI (weekly_retrain, poniedziałek)
  evaluate.py → stats.json → Telegram (/stats = Model ROI)
  finance.py  → get_summary() → Telegram (/balance = Player ROI)
```

---

## Cechy modelu (18 — kolejność STAŁA w FEATURE_COLS)

```python
FEATURE_COLS = [
    # Forma ważona czasowo (wykładniczy zanik halflife=21 dni)
    "home_pts_avg",   "away_pts_avg",    # punkty (3/1/0)
    "home_gf_avg",    "away_gf_avg",     # gole strzelone
    "home_ga_avg",    "away_ga_avg",     # gole stracone
    "home_hst_avg",   "away_hst_avg",    # strzały celne
    "home_ast_avg",   "away_ast_avg",    # strzały celne przeciwnika
    # H2H
    "h2h_home_win_rate",                 # % wygranych drużyny domowej
    "h2h_avg_goals",                     # średnia goli
    # Fair probabilities (po remove_margin)
    "market_prob_h",  "market_prob_d",  "market_prob_a",
    # Elo per liga
    "home_elo",       "away_elo",        "elo_diff",
]
```

**NIGDY nie zmieniaj kolejności FEATURE_COLS bez pełnego retrainingu modelu.**
Pkl zawiera listę cech użytą przy treningu — muszą pasować do inferencji.

---

## Kluczowe niezmienne założenia

### 1. Walk-forward (brak data leakage)
Cechy dla każdego meczu liczone **wyłącznie z danych przed datą meczu**.
`build_elo_history()` — O(n), wykonywany raz przed pętlą.
`_get_team_history()` — filtruje `df["Date"] < before_date`.

### 2. Kalibracja Platta — temporal split
```python
# Poprawny porządek chronologiczny (v1.5):
X_base (68% danych) → base.fit()
X_cal  (17% danych) → CalibratedClassifierCV(base, cv="prefit").fit()
X_test (15% danych) → ewaluacja
```
**NIGDY** nie używaj `cv=5` z domyślnym k-fold dla danych czasowych.

### 3. Elo per liga
`build_elo_history(df)` zwraca `{liga_kod: {druzyna: [(date, elo)]}}`.
`_get_elo_before(history, team, date, league)` — wymagany parametr `league`.
Bez `league` (stara sygnatura) zwróci `ELO_START` — nie crashuje, ale da złe cechy.

### 4. Model ROI — stawki per kupon
```python
# v1.5 — poprawne:
if result == "WON":
    stats["staked_resolved"] += model_stake
    stats["total_model_return"] += model_stake * odds
elif result == "LOST":
    stats["staked_resolved"] += model_stake

# BŁĄD v1.4 (nie wracaj do tego):
# staked_resolved = total_staked * (resolved / total_coupons)
```

### 5. Symulacja ROI — kurs bukmachera
```python
# v1.5 — poprawne:
fair_odds      = 1.0 / market_p          # market_p to fair prob
bookmaker_odds = fair_odds / 1.05        # ~5% overround

# BŁĄD v1.4 (nie wracaj do tego):
# approx_odds = 0.95 / market_p          # = fair_odds * 0.95 — za niski
```

---

## Krytyczne zależności między plikami

```
config.py
  └─ używany przez WSZYSTKIE moduły (LEAGUES, SEASONS, ELO_*, KELLY_*, ścieżki)

model/features.py (FEATURE_COLS)
  ├─ importowany przez model/train.py (trening)
  └─ importowany przez model/predict.py (inferencja)
  ⚠️  Zmiana FEATURE_COLS = konieczny retrain + zmiana w obu miejscach

pipeline/name_mapping.py (normalize)
  ├─ używany przez model/predict.py (normalizacja nazw z API)
  └─ używany przez model/evaluate.py (normalizacja przy rozliczaniu)
  ⚠️  Dodanie nowej drużyny: tylko TEAM_MAP, _REVERSE budowany automatycznie

coupon/kelly.py
  ├─ używany przez coupon/builder.py
  ⚠️  Zmiana KELLY_FRACTION/MAX_BET_PCT: w config.py, nie w kelly.py
```

---

## Format plików danych

### data/results/coupons_history.json
```json
[
  {
    "date": "2025-04-25 09:00",
    "coupons": [
      {
        "type": "SINGIEL",
        "legs": [
          {
            "match_id": "abc123",
            "home_team": "Man City",
            "away_team": "Arsenal",
            "league_code": "EPL",
            "bet_outcome": "H",
            "bet_odds": 2.10,
            "model_prob": 0.55,
            "market_prob": 0.48,
            "edge": 0.07
          }
        ],
        "total_odds": 2.10,
        "combined_prob": 0.55,
        "stake": 30.0,
        "expected_value": 0.155,
        "result": "PENDING",
        "resolved_at": null
      }
    ]
  }
]
```

### data/results/finance.json
```json
{
  "initial_balance": -500.0,
  "transactions": [
    {
      "date": "2025-04-25 10:30",
      "type": "stake",
      "amount": -100.0,
      "coupon_id": "1",
      "note": "Stawka na kupon #1"
    }
  ]
}
```

---

## Testy jednostkowe

Plik: `tests/test_kelly.py` — 33 testy, wszystkie zielone.

```bash
cd betting_system
BANKROLL=1000 python -m pytest tests/ -v
```

**Pokrycie testami:**
- `TestKellyStake` (7 testów) — kelly_stake: dodatnie, ujemne, zaokrąglenie, max, guard
- `TestParlaytake` (5 testów) — parlay_stake: single, double, empty, all-negative, divisor fix
- `TestRemoveMargin` (4 testy) — suma=1, faworyt, zero, równe
- `TestLegWon` (7 testów) — H/D/A + wszystkie double chance + unknown
- `TestNormalize` (5 testów) — None guard, empty, alias, identity, case
- `TestParseCouponNr` (5 testów) — nowy format, stary, przecinek, empty, invalid

**Przy każdej zmianie logiki biznesowej** (kelly, features, evaluate) dodaj test.

---

## Zmienne środowiskowe

| Zmienna | Gdzie | Wymagana |
|---------|-------|---------|
| `ODDS_API_KEY` | GitHub Secrets | ✅ |
| `ODDS_API_KEY_2` | GitHub Secrets | ⚡ Zalecana |
| `ODDS_API_KEY_3` | GitHub Secrets | ⚡ Zalecana |
| `TELEGRAM_TOKEN` | GitHub Secrets | ✅ |
| `TELEGRAM_CHAT_ID` | GitHub Secrets | ✅ |
| `BANKROLL` | GitHub Secrets | ✅ (>0, float) |

Lokalnie: `export BANKROLL=1000` lub prefix przed pytest.

---

## Ligi i kody

| Kod | Liga | fd_code | odds_key |
|-----|------|---------|----------|
| EPL | Premier League | E0 | soccer_epl |
| BL | Bundesliga | D1 | soccer_germany_bundesliga |
| LL | La Liga | SP1 | soccer_spain_la_liga |
| SA | Serie A | I1 | soccer_italy_serie_a |
| EK | Ekstraklasa | P1 | soccer_poland_ekstraklasa |

Sezony: obliczane dynamicznie przez `_build_seasons()` w config.py.
Format: `"2425"` = sezon 2024/25. Nowy sezon zaczyna się w lipcu.

---

## GitHub Actions — concurrency

Wszystkie 4 workflow współdzielą grupę `data-write`:
```yaml
concurrency:
  group: data-write
  cancel-in-progress: false
```
**Nie usuwaj tego** — bez tego równoległe joby nadpisują wzajemnie dane w git.
`cancel-in-progress: false` = czekaj na zakończenie, nie anuluj.

---

## Czego system NIE robi (i nie powinien robić)

- ❌ Automatyczne stawianie zakładów
- ❌ Live/in-play betting
- ❌ Arbitraż
- ❌ Zarządzanie kontem bukmachera
- ❌ Przechowywanie danych osobowych użytkownika

---

## Typowe pułapki przy modyfikacjach

**Przy zmianie FEATURE_COLS:**
Retrain jest obowiązkowy. Plik model.pkl zawiera listę cech — niezgodność
między treningiem a inferencją spowoduje ciche błędy (złe predykcje bez wyjątku).

**Przy dodaniu nowej ligi:**
1. Dodaj do `config.py → LEAGUES`
2. Dodaj drużyny do `pipeline/name_mapping.py → TEAM_MAP`
3. Uruchom `python main.py fetch && python main.py train`

**Przy zmianie logiki Kelly:**
Uruchom `BANKROLL=1000 python -m pytest tests/test_kelly.py -v` zanim zcommitujesz.

**Przy zmianie `_build_result_lookups` (evaluate.py):**
Sprawdź czy `results_by_teams` używa znormalizowanych nazw (lowercase po normalize()).
Niezgodność powoduje ciche PENDING — kupony nigdy nie są rozliczane.

**Przy podniesieniu v1.x → v2.0 (nowe sporty):**
Elo musi być osobno per sport (tennis_ATP, football_EPL, etc.).
`build_elo_history()` już obsługuje per-liga — wystarczy upewnić się że
kolumna `league` w danych jest unikalna per sport.
