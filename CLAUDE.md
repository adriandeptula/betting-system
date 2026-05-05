# CLAUDE.md — Wytyczne kontekstowe dla AI Betting System v1.6

Ten plik zawiera pełny kontekst systemu dla Claude. Czytaj go przed każdą
modyfikacją kodu — szczególnie przed zmianami w model/features.py, model/train.py,
coupon/kelly.py, model/evaluate.py i pipeline/fetch_clv.py.

---

## Czym jest ten projekt

Automatyczny system value bettingu na piłkę nożną. Stack:
- **ML:** Ensemble XGBoost + LightGBM, każdy kalibrowany osobno (Platt, cv='prefit')
- **Tuning:** Optuna z expanding window CV (TimeSeriesSplit n_splits=3)
- **Infrastruktura:** GitHub Actions (0 PLN/miesiąc, wszystko w chmurze)
- **Powiadomienia:** Telegram Bot API (polling co godzinę)
- **Dane:** football-data.co.uk (historyczne wyniki), The Odds API (aktualne kursy)

**System NIE stawia zakładów automatycznie** — generuje sugestie i wysyła na Telegram.

---

## Aktualna wersja: v1.6

### Co nowego w v1.6

| # | Plik | Zmiana |
|---|------|--------|
| 1 | `pipeline/fetch_clv.py` | NOWY — CLV tracking. Zero dodatkowych API calls. |
| 2 | `model/train.py` | Optuna tuning (OPTUNA_TRIALS=30, TimeSeriesSplit) |
| 3 | `model/train.py` | Ensemble XGBoost + LightGBM z osobną kalibracją Platta |
| 4 | `model/train.py` | sample_weight dla remisów (DRAW_CLASS_WEIGHT=1.5) |
| 5 | `model/predict.py` | Obsługa nowego formatu pkl + backward compat v1.5 |
| 6 | `model/evaluate.py` | CLV statystyki w update_coupon_results() |
| 7 | `notify/telegram.py` | CLV w send_stats() i format_coupon() |
| 8 | `main.py` | run_fetch() wywołuje update_clv() po fetch_all_odds() |
| 9 | `config.py` | CLV_CLOSING_HOURS, OPTUNA_TRIALS, DRAW_CLASS_WEIGHT |
| 10 | `requirements.txt` | lightgbm==4.3.0, optuna==3.6.1 |
| 11 | `.github/workflows/daily_fetch.yml` | git add data/results/ (CLV dane) |
| 12 | `.github/workflows/weekly_retrain.yml` | ODDS_API_KEY w stats step |
| 13 | `tests/test_kelly.py` | +8 testów: TestCLV (5) + TestEnsemblePredict (3) |

### Co naprawiono w v1.5 (historycznie ważne)

| # | Plik | Problem | Naprawa |
|---|------|---------|---------|
| 1 | `model/evaluate.py` | Model ROI przez proporcję całości | Per-kupon WON+LOST |
| 2 | `model/train.py` | `_simulate_roi` zaniżony ROI | `bookmaker_odds = fair_odds / 1.05` |
| 3 | `notify/finance.py` | Błąd domknięcia `cid` | Przepisane |
| 4 | `coupon/kelly.py` | guard odds<=1.0, dzielnik len(legs) | Guard + len(individual) |
| 5 | `model/train.py` | Kalibracja Platta z random k-fold | cv='prefit' temporal |
| 6 | `model/evaluate.py` | days_back=7 hardcoded | Dynamiczny max 14 |
| 7 | `pipeline/fetch_stats.py` | Brak deduplikacji | drop_duplicates() |
| 8 | `pipeline/name_mapping.py` | normalize(None) crash | Guard if not name |
| 9 | `.github/workflows/*.yml` | Race condition git push | concurrency: data-write |
| 10 | `model/features.py` | Elo cross-liga | Elo per liga |
| 11 | `notify/bot_handler.py (polling yml)` | Brak ODDS_API_KEY w env | Dodane |

---

## Architektura — przepływ danych

```
KROK 1 — DANE (daily_fetch, codziennie 06:00 UTC)
  football-data.co.uk → CSV → data/raw/all_matches.csv
    (5 lig × 5 sezonów, deduplikacja po concat)
  The Odds API (h2h, eu) → JSON → data/odds/odds_YYYY-MM-DD.json
    (3 klucze z auto-fallback przy 401/402/429)
  fetch_clv.update_clv() ← kluczowe v1.6
    używa już pobranego pliku odds_*.json (ZERO dodatkowych API calls)
    dla PENDING kuponów w oknie CLV_CLOSING_HOURS → zapisuje closing_odds + clv_pct

KROK 2 — MODEL (weekly_retrain, poniedziałek 05:00 UTC)
  all_matches.csv
    → features.py: walk-forward, Elo per liga, forma ważona, H2H
    → Optuna (TimeSeriesSplit n=3, OPTUNA_TRIALS=30) → best_params_xgb
    → XGBoost(best_params) + DRAW_CLASS_WEIGHT → Platt (X_cal 17%)
    → LightGBM(best_params) + DRAW_CLASS_WEIGHT → Platt (X_cal 17%)
    → model.pkl (model_type="ensemble") + calibration.png

KROK 3 — KUPONY (coupon_gen, śr + pt 09:00 UTC)
  model.pkl + odds_*.json
    → predict.py: proba = mean([xgb.predict_proba(X), lgb.predict_proba(X)])
    → value_engine.py (1X2 + DC) → builder.py
    → Telegram: kupony #1, #2, #3 z numerami

KROK 4 — BOT (bot_polling, co godzinę)
  auto_resolve_pending_coupons() [days_back dynamiczny]
    → The Odds API /scores → rozlicza PENDING w coupons_history.json
  getUpdates → bot_handler.py:
    /stake /won /lost → finance.json (Player ROI)
    /stats → update_coupon_results() (Model ROI + CLV)

KROK 5 — STATYSTYKI (weekly_retrain, poniedziałek)
  evaluate.py → stats.json + CLV summary → Telegram (/stats)
  finance.py  → get_summary() → Telegram (/balance)
```

---

## CLV — jak działa (v1.6, kluczowy feature)

**CLV = (bet_odds / closing_odds − 1) × 100%**

- `bet_odds`: kurs w momencie generowania kuponu (z The Odds API w środę/piątek)
- `closing_odds`: kurs ~24h przed meczem (z codziennego fetchu o 06:00)
- Dodatnie CLV długoterminowo → model ma realny edge nad rynkiem

**Implementacja zero-cost:**
```python
# fetch_clv.update_clv() wywoływana przez run_fetch() KAŻDEGO dnia:
# 1. Wczytuje odds_*.json (już pobrany przez fetch_all_odds())
# 2. Szuka PENDING kuponów z commence_time < now + CLV_CLOSING_HOURS
# 3. Zapisuje closing_odds + clv_pct do coupons_history.json
# Nigdy nie nadpisuje raz zapisanego CLV (pierwsze trafienie = final)
```

**Ważne szczegóły:**
- `CLV_CLOSING_HOURS = 24` — codzienny fetch o 06:00 UTC trafia w okno 24h
  dla większości meczów wieczornych (kick-off ~19-21 UTC)
- Double chance closing_odds obliczane z `remove_margin(h, d, a)` tak jak w value_engine
- CLV pokazywany w Telegramie gdy znany (`format_coupon`), w statystykach od 5+ nóg

**Nie nadpisuj closing_odds:**
```python
# Poprawnie — pierwsze trafienie blokuje wartość:
if leg.get("closing_odds") is not None:
    continue
```

---

## Ensemble — jak działa (v1.6)

**Dlaczego osobna kalibracja przed uśrednieniem:**
Uśrednianie nieskalibrowanych probabilities = błędne EV.
Każdy model ma swoją krzywą kalibracji. Platt po treningu bazy zapewnia
że prob_xgb i prob_lgb są na tej samej skali przed uśrednieniem.

```python
# Poprawny porządek v1.6:
base_xgb.fit(X_base, y_base, sample_weight=w)
cal_xgb = CalibratedClassifierCV(base_xgb, cv="prefit").fit(X_cal, y_cal)

base_lgb.fit(X_base, y_base, sample_weight=w)
cal_lgb = CalibratedClassifierCV(base_lgb, cv="prefit").fit(X_cal, y_cal)

proba = np.mean([cal_xgb.predict_proba(X), cal_lgb.predict_proba(X)], axis=0)
```

**Format pkl v1.6:**
```python
{
    "model_type":      "ensemble",
    "models":          [cal_xgb, cal_lgb],   # lista skalibrowanych modeli
    "model_names":     ["XGBoost", "LightGBM"],
    "weights":         [0.5, 0.5],            # równe wagi (na razie)
    "feature_cols":    FEATURE_COLS,
    "league_codes":    {...},
    "best_params_xgb": {...},                 # wynik Optuna
    "metrics":         {...},
}
```

**Backward compat:** predict.py obsługuje stary format `{"model": ...}` z v1.5.

---

## Optuna — szczegóły (v1.6)

```python
# Expanding window CV (TimeSeriesSplit n_splits=3):
# Fold 1: train=[0:33%],  val=[33:50%]
# Fold 2: train=[0:50%],  val=[50:67%]
# Fold 3: train=[0:67%],  val=[67:83%]   ← (na X_train_full = 85% danych)
#
# Metryka: mean(log_loss) — niższy = lepszy kalibracja
# n_trials=30 → ~10-15 min na GitHub Actions (ubuntu-latest)
# Ustaw OPTUNA_TRIALS=0 żeby wyłączyć i używać domyślnych parametrów
```

**Nie uruchamiaj Optuna z k-fold random:**
`TimeSeriesSplit` jest obowiązkowy dla danych chronologicznych.
Random k-fold = data leakage w tuningu = false confidence parametrów.

---

## sample_weight dla remisów (v1.6)

```python
# DRAW_CLASS_WEIGHT = 1.5 (config.py)
w = np.where(y == 1, DRAW_CLASS_WEIGHT, 1.0)
model.fit(X, y, sample_weight=w)
```

Remisy (klasa 1) są najtrudniejsze do predykcji i historycznie niedokalibrowane.
Waga 1.5 poprawia kalibrację dla D bez znaczącego pogorszenia H/A.
Jeśli brier_score dla remisów jest wysoki po retreningu → rozważ zwiększenie do 2.0.

---

## Cechy modelu (18 — kolejność STAŁA)

```python
FEATURE_COLS = [
    "home_pts_avg",   "away_pts_avg",
    "home_gf_avg",    "away_gf_avg",
    "home_ga_avg",    "away_ga_avg",
    "home_hst_avg",   "away_hst_avg",
    "home_ast_avg",   "away_ast_avg",
    "h2h_home_win_rate", "h2h_avg_goals",
    "market_prob_h",  "market_prob_d",  "market_prob_a",
    "home_elo",       "away_elo",        "elo_diff",
]
```

**NIGDY nie zmieniaj kolejności FEATURE_COLS bez pełnego retrainingu.**

---

## Kluczowe niezmienne założenia (z v1.5, nadal obowiązują)

### Walk-forward (brak data leakage)
Cechy dla każdego meczu liczone wyłącznie z danych przed datą meczu.

### Kalibracja Platta — temporal split
```python
X_base (68%) → base.fit()
X_cal  (17%) → CalibratedClassifierCV(base, cv="prefit").fit()
X_test (15%) → ewaluacja
```
NIGDY nie używaj cv=5 z domyślnym k-fold dla danych czasowych.

### Elo per liga
build_elo_history(df) zwraca {liga_kod: {druzyna: [(date, elo)]}}.

### Model ROI — stawki per kupon (nie proporcja całości)
```python
if result == "WON":
    stats["staked_resolved"] += model_stake
    stats["total_model_return"] += model_stake * odds
elif result == "LOST":
    stats["staked_resolved"] += model_stake
```

### Symulacja ROI — kurs bukmachera
```python
fair_odds      = 1.0 / market_p
bookmaker_odds = fair_odds / 1.05
```

---

## Format danych

### data/results/coupons_history.json (v1.6 — rozszerzony)
```json
{
  "date": "2025-04-25 09:00",
  "coupons": [{
    "type": "SINGIEL",
    "legs": [{
      "match_id":      "abc123",
      "home_team":     "Man City",
      "away_team":     "Arsenal",
      "league_code":   "EPL",
      "bet_outcome":   "H",
      "bet_odds":      2.10,
      "model_prob":    0.55,
      "market_prob":   0.48,
      "edge":          0.07,
      "closing_odds":  2.05,       ← v1.6: zapisane przez fetch_clv.update_clv()
      "clv_pct":       2.44,       ← v1.6: (2.10/2.05 - 1)*100
      "clv_at":        "2025-04-26T06:12:33+00:00"
    }],
    "total_odds":  2.10,
    "stake":       30.0,
    "result":      "WON",
    "resolved_at": "2025-04-26T..."
  }]
}
```

---

## Testy jednostkowe

Plik: `tests/test_kelly.py` — 41 testów (było 33), wszystkie powinny być zielone.

```bash
cd betting_system
BANKROLL=1000 python -m pytest tests/ -v
```

**Pokrycie v1.6:**
- `TestKellyStake` (7) — bez zmian
- `TestParlaytake` (5) — bez zmian
- `TestRemoveMargin` (4) — bez zmian
- `TestLegWon` (7) — bez zmian
- `TestNormalize` (5) — bez zmian
- `TestParseCouponNr` (5) — bez zmian
- `TestCLV` (5) — NOWE: closing_odds, DC, formuła CLV, empty summary
- `TestEnsemblePredict` (3) — NOWE: legacy pkl, ensemble pkl, averaging

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

---

## Ligi i kody

| Kod | Liga | fd_code | odds_key |
|-----|------|---------|----------|
| EPL | Premier League | E0 | soccer_epl |
| BL | Bundesliga | D1 | soccer_germany_bundesliga |
| LL | La Liga | SP1 | soccer_spain_la_liga |
| SA | Serie A | I1 | soccer_italy_serie_a |
| EK | Ekstraklasa | P1 | soccer_poland_ekstraklasa |

---

## GitHub Actions — concurrency

Wszystkie 4 workflow współdzielą grupę `data-write`:
```yaml
concurrency:
  group: data-write
  cancel-in-progress: false
```
**Nie usuwaj tego** — bez tego równoległe joby nadpisują wzajemnie dane w git.

---

## Nowe parametry config.py (v1.6)

| Parametr | Domyślnie | Znaczenie |
|----------|-----------|-----------|
| `CLV_CLOSING_HOURS` | 24 | Ile h przed meczem kurs uznajemy za closing |
| `OPTUNA_TRIALS` | 30 | Liczba prób Optuna (0 = wyłączone) |
| `DRAW_CLASS_WEIGHT` | 1.5 | Waga remisów w sample_weight |

---

## Czego NIE robić przy modyfikacjach

**Nie uśredniaj nieskalibrowanych modeli:**
Każdy model MUSI mieć własny Platt przed uśrednieniem.
`np.mean([base_xgb.predict_proba(X), base_lgb.predict_proba(X)])` = BŁĄD.
`np.mean([cal_xgb.predict_proba(X), cal_lgb.predict_proba(X)])` = POPRAWNIE.

**Nie używaj random k-fold w Optuna ani kalibracji:**
TimeSeriesSplit i cv='prefit' są obowiązkowe dla danych czasowych.

**Nie nadpisuj closing_odds:**
Raz zapisana wartość CLV jest finalna. `if leg.get("closing_odds") is not None: continue`.

**Nie zmieniaj kolejności FEATURE_COLS bez pełnego retrainingu.**

**Przy zmianie logiki Kelly:**
`BANKROLL=1000 python -m pytest tests/test_kelly.py -v` przed commitem.

---

## Plan rozwoju

### v1.6 ✅ (obecna)
Ensemble XGB+LGB, Optuna, CLV tracking, draw class weight, 41 testów.

### v1.7 — Over/Under + monitoring CLV
- Totals market (over/under gole) — model Poissona, +1 req/liga
- CLV monitoring: alert gdy avg CLV < -2% przez 4 tygodnie (degradacja)
- Forma ważona osobno dla meczów domowych i wyjazdowych
- Elo z uwzględnieniem siły harmonogramu (SOS)

### v2.0 — Nowe sporty
- Tenis ATP/WTA (dane: tennis-data.co.uk, Jeff Sackmann był aktualny do ~IV 2026)
- Przy dodaniu: Elo musi być per sport/liga (już gotowe w v1.5+)

### v2.1 — Monitoring i UX
- Dashboard GitHub Pages: wykres ROI, historia kuponów, CLV trend
- Cotygodniowy raport PDF na email
