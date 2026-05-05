# 🤖 AI Betting System — v1.6

System automatyczny do generowania value betów oparty na XGBoost + LightGBM ensemble z kalibracją Platta.
Działa w 100% na GitHub Actions. Koszt: **0 zł/miesiąc**.

---

## Spis treści

1. [Jak to działa](#jak-to-działa)
2. [Pierwsze uruchomienie](#pierwsze-uruchomienie)
3. [Harmonogram](#harmonogram)
4. [Śledzenie finansów i komendy Telegram](#śledzenie-finansów-i-komendy-telegram)
5. [Zarządzanie bankrollem](#zarządzanie-bankrollem)
6. [Parametry modelu](#parametry-modelu)
7. [Mapa plików](#mapa-plików)
8. [Plan rozwoju](#plan-rozwoju)
9. [Debug checklist](#debug-checklist)

---

## Jak to działa

```
Co tydzień automatycznie:

PON  05:00 → Pobierz dane → Retrenuj ensemble → Wyślij statystyki ROI + CLV
CODZ 06:00 → Pobierz dane + kursy → Zapisz CLV dla kuponów w oknie 24h
ŚR   09:00 → Generuj kupony → Wyślij na Telegram
PT   09:00 → Generuj kupony → Wyślij na Telegram
CO H 00:00 → Bot: komendy + auto-rozliczanie kuponów
```

**Źródła danych:**
- football-data.co.uk — historyczne wyniki 5 lig (EPL, Bundesliga, La Liga, Serie A, Ekstraklasa)
- The Odds API — aktualne kursy z ~40 bukmacherów europejskich

**Model:** Ensemble XGBoost + LightGBM, każdy kalibrowany osobno (Platt, cv='prefit')

**Tuning:** Optuna z expanding window CV (TimeSeriesSplit n_splits=3, 30 prób)

**Cechy modelu (18 cech):**
- Forma ważona czasowo (wykładniczy zanik halflife=21 dni)
- Elo rating **per liga** (osobna skala, brak cross-league noise)
- Statystyki: gole, strzały celne HST/AST, H2H
- Fair probabilities (kursy po usunięciu marży bukmachera)

**CLV tracking (v1.6):**
- Zero dodatkowych wywołań API
- Closing odds zapisywane z codziennego fetchu (~24h przed meczem)
- CLV = (bet_odds / closing_odds − 1) × 100%. Cel: avg CLV > 0%

**Obsługiwane typy zakładów:** 1X2 i Double Chance (1X, X2, 12)

**Stawki:** Frakcjonalne kryterium Kelly (25% pełnego Kelly)

**CI/CD:** GitHub Actions z concurrency groups — brak race condition

---

## Pierwsze uruchomienie

### KROK 1: Stwórz konta na The Odds API

1. **https://the-odds-api.com** → **Get API Key** → zarejestruj się
2. Zalecane: 2-3 konta (różne emaile) — free tier: 500 req/miesiąc/konto

---

### KROK 2: Stwórz bota Telegram

1. Telegram → **@BotFather** → `/newbot` → skopiuj TOKEN
2. **@userinfobot** → `/start` → skopiuj swój Chat ID
3. Wyszukaj swojego bota → `/start` (aktywacja)

---

### KROK 3: Prywatne repozytorium GitHub

GitHub → **+** → **New repository** → **Private**

---

### KROK 4: Wgraj kod

```bash
git clone https://github.com/TWOJA_NAZWA/betting-system.git
cd betting-system
git add .
git commit -m "feat: v1.6 initial setup"
git push origin main
```

---

### KROK 5: Ustaw GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret:**

| Nazwa | Wartość | Wymagany |
|-------|---------|---------|
| `ODDS_API_KEY` | klucz #1 z The Odds API | ✅ Tak |
| `ODDS_API_KEY_2` | klucz #2 | ⚡ Zalecany |
| `ODDS_API_KEY_3` | klucz #3 | ⚡ Zalecany |
| `TELEGRAM_TOKEN` | token bota | ✅ Tak |
| `TELEGRAM_CHAT_ID` | Twój chat ID | ✅ Tak |
| `BANKROLL` | bankroll w PLN, np. `1000` | ✅ Tak |

---

### KROK 6: Pierwsze uruchomienie

```
Actions → "Daily Data Fetch"  → Run workflow   (~3-5 min)
Actions → "Weekly Retrain"    → Run workflow   (~15-20 min z Optuna)
Actions → "Generate Coupons"  → Run workflow   (~2 min)
```

> ⚠️ Pierwszy retrain z Optuna trwa dłużej (~15-20 min). Kolejne tyle samo —
> GitHub Actions cache pip przyspiesza instalację zależności.

---

### KROK 7: Weryfikacja

W logach Actions sprawdź:
- ✅ Dane pobrane (X meczów, deduplikacja OK)
- ✅ Optuna: najlepszy log_loss zalogowany (30 prób)
- ✅ Ensemble: XGBoost + LightGBM wytrenowane i skalibrowane
- ✅ Feature importance zalogowane (top-8)
- ✅ Calibration plot zapisany → data/model/calibration.png
- ✅ Value bety znalezione
- ✅ Kupony wysłane na Telegram

---

## Harmonogram

| Dzień | Godzina UTC | Akcja |
|-------|-------------|-------|
| Pon–Niedz | 06:00 | Pobierz dane + kursy + zapisz CLV |
| Poniedziałek | 05:00 | Retrenuj ensemble (Optuna) + statystyki |
| Środa | 09:00 | Generuj kupony (mecze środkowe) |
| Piątek | 09:00 | Generuj kupony (mecze weekendowe) |
| Co godzinę | — | Bot: komendy + auto-rozliczanie |

---

## Śledzenie finansów i komendy Telegram

### Dwa niezależne systemy ROI

**Model ROI** (`/stats`) — jakość predykcji ensemble. Auto-rozliczany przez
The Odds API. Używa sugerowanych stawek Kelly. **Od v1.6: zawiera statystyki CLV.**

**Player ROI** (`/balance`) — Twój rzeczywisty P&L. Per-kupon.

### CLV w praktyce

```
Śr/Pt: system generuje kupony z kursami (np. Man City H @ 2.10)

Każdego dnia 06:00: daily_fetch zapisuje closing_odds dla kuponów
  w oknie 24h przed meczem (np. Man City H closing @ 2.05)
  CLV = (2.10 / 2.05 - 1) × 100 = +2.4% ← model pobił rynek!

Telegram: kupon pokazuje CLV gdy już znany
  🟢 CLV: +2.4%  (kurs otwarcia: 2.10 → closing: 2.05)

/stats (poniedziałek): raport CLV ze wszystkich zakładów
  📐 Closing Line Value (CLV)
  🟢 Średnie CLV: +1.8%
  ✅ Dodatnie CLV: 64% zakładów
```

### Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| `/help` | Lista komend | `/help` |
| `/stats` | Model ROI + CLV | `/stats` |
| `/balance` | Player ROI (Twój P&L) | `/balance` |
| `/pending` | Kupony czekające | `/pending` |
| `/setbalance X` | Ustaw punkt startowy | `/setbalance -1500` |
| `/stake [nr] X` | Zaloguj stawkę | `/stake 1 100` |
| `/won [nr] X` | Kupon wygrany | `/won 1 350` |
| `/lost [nr]` | Kupon przegrany | `/lost 2` |

---

## Zarządzanie bankrollem

1. Nigdy nie stawiaj więcej niż sugeruje Kelly
2. Bankroll = odłożona kwota — nie pieniądze potrzebne do życia
3. Zacznij od małych stawek — weryfikuj przez 50+ zakładów
4. Monitoruj CLV — jeśli avg CLV < 0% przez dłuższy czas, model traci edge

**Kiedy zatrzymać:**
- ROI < -15% po 50+ zakładach → sprawdź model
- Avg CLV < -2% przez 4 tygodnie → sprawdź dane i cechy
- Seria 10 przegranych z rzędu → sprawdź dane wejściowe

---

## Parametry modelu

| Parametr | Domyślnie | Znaczenie |
|----------|-----------|-----------|
| `FORM_WINDOW` | 8 | Ostatnie N meczów do formy |
| `FORM_HALFLIFE_DAYS` | 21 | Półokres zaniku wagi formy [dni] |
| `ELO_START` | 1500 | Startowy Elo dla nowych drużyn |
| `ELO_K` | 20 | Współczynnik K Elo |
| `MIN_EDGE` | 0.05 | Min przewaga 5% |
| `MIN_MODEL_PROB` | 0.40 | Min pewność modelu dla 1X2 |
| `DC_MIN_MODEL_PROB` | 0.55 | Min pewność dla double chance |
| `KELLY_FRACTION` | 0.25 | Agresywność stawek |
| `MAX_BET_PCT` | 0.03 | Max 3% bankrollu na kupon |
| `MIN_ODDS` | 1.50 | Min kurs 1X2 |
| `MAX_ODDS` | 3.20 | Max kurs 1X2 |
| `DC_MIN_ODDS` | 1.20 | Min kurs double chance |
| `DC_MAX_ODDS` | 2.00 | Max kurs double chance |
| `CLV_CLOSING_HOURS` | 24 | Okno closing odds [h] |
| `OPTUNA_TRIALS` | 30 | Próby tuningu (0 = wyłączone) |
| `DRAW_CLASS_WEIGHT` | 1.5 | Waga remisów w treningu |

---

## Mapa plików

```
betting_system/
│
├── main.py                     ← Orkiestrator. Tryby: fetch|train|coupon|stats|bot|full
│                                  [v1.6] run_fetch() wywołuje update_clv()
├── config.py                   ← Wszystkie parametry.
│                                  [v1.6] CLV_CLOSING_HOURS, OPTUNA_TRIALS, DRAW_CLASS_WEIGHT
├── requirements.txt            ← [v1.6] lightgbm==4.3.0, optuna==3.6.1
│
├── pipeline/
│   ├── api_utils.py            ← Multi-key API, auto-fallback
│   ├── fetch_stats.py          ← CSV z football-data.co.uk + deduplikacja
│   ├── fetch_odds.py           ← Kursy z The Odds API (h2h)
│   ├── fetch_clv.py            ← [v1.6] NOWY — CLV tracking. Zero API calls.
│   │                              update_clv(): zapisuje closing_odds + clv_pct
│   │                              get_clv_summary(): statystyki CLV
│   └── name_mapping.py         ← Mapowanie nazw + fuzzy matching + guard na None
│
├── model/
│   ├── features.py             ← 18 cech, walk-forward, Elo per liga (bez zmian)
│   ├── train.py                ← [v1.6] Optuna + ensemble XGB+LGB + draw weight
│   │                              _tune_hyperparams(): TimeSeriesSplit CV
│   │                              _fit_and_calibrate_xgb/lgb(): osobna kalibracja
│   ├── predict.py              ← [v1.6] Obsługa ensemble pkl + backward compat v1.5
│   └── evaluate.py             ← [v1.6] CLV statystyki w update_coupon_results()
│
├── coupon/
│   ├── value_engine.py         ← Value bety 1X2 + DC (bez zmian)
│   ├── kelly.py                ← Frakcjonalne Kelly (bez zmian)
│   └── builder.py              ← Singiel/podwójny/potrójny (bez zmian)
│
├── notify/
│   ├── telegram.py             ← [v1.6] CLV w send_stats() i format_coupon()
│   ├── finance.py              ← Player ROI (bez zmian)
│   └── bot_handler.py          ← Polling + auto-resolve (bez zmian)
│
├── tests/
│   └── test_kelly.py           ← [v1.6] 41 testów (+8: TestCLV + TestEnsemblePredict)
│
└── .github/workflows/
    ├── daily_fetch.yml         ← [v1.6] git add data/results/ (CLV dane)
    ├── coupon_gen.yml          ← bez zmian
    ├── weekly_retrain.yml      ← [v1.6] ODDS_API_KEY w stats step
    └── bot_polling.yml         ← [v1.5.1] ODDS_API_KEY dodane
```

---

## Historia wersji

### v1.6 ✅ (obecna) — Ensemble + CLV + Optuna

**Nowe funkcje:**
- `pipeline/fetch_clv.py` — CLV tracking bez dodatkowych API calls
- `model/train.py` — Optuna hyperparameter tuning z TimeSeriesSplit CV
- `model/train.py` — Ensemble XGBoost + LightGBM z osobną kalibracją Platta
- `model/train.py` — sample_weight dla remisów (DRAW_CLASS_WEIGHT=1.5)
- `model/predict.py` — obsługa ensemble pkl + backward compat v1.5
- `notify/telegram.py` — CLV w raportach i kuponach
- `tests/test_kelly.py` — +8 testów (41 łącznie)

### v1.5.1 ✅
Naprawiono brakujące ODDS_API_KEY w bot_polling.yml — auto-resolve kuponów zaczął działać.

### v1.5 ✅
Optuna (zapowiedź), Elo per liga, temporal Platt, dynamiczny days_back,
deduplikacja CSV, 33 testy, SEASONS dynamiczne, feature importance.

### v1.4 ✅
Auto-rozliczanie kuponów, Player ROI, per-kupon komendy, publiczne send_message().

### v1.3 ✅
Forma ważona czasowo, Elo rating, calibration plot, FORM_WINDOW=8.

### v1.2 ✅
3 klucze API, double chance markets (1X, X2, 12), kupony oczekujące.

### v1.1 ✅
Strzały celne HST/AST, fuzzy matching name_mapping.

### v1.0 ✅
Fundament: 5 lig, XGBoost+Platt, value engine, Kelly, Telegram, GitHub Actions.

---

## Plan rozwoju

### v1.7 — Over/Under + CLV monitoring
- Totals market (over/under gole) — model Poissona
- Alert degradacji: avg CLV < -2% przez 4 tygodnie → wiadomość Telegram
- Forma ważona osobno dom/wyjazd
- Elo SOS (Strength of Schedule)

### v2.0 — Nowe sporty
- Tenis ATP/WTA
- NBA — tylko z advanced stats

### v2.1 — Dashboard
- GitHub Pages: ROI, CLV trend, historia kuponów
- Raport PDF na email

---

## Debug checklist

1. Actions → zielony checkmark?
2. Logi → szukaj `ERROR` lub `WARNING`
3. `data/raw/all_matches.csv` istnieje? → `python main.py fetch`
4. `data/model/model.pkl` istnieje? → `python main.py train`
5. `data/odds/odds_YYYY-MM-DD.json` z dzisiaj? → `python main.py fetch`
6. GitHub Secrets → ODDS_API_KEY, TELEGRAM_*, BANKROLL ustawione?
7. BANKROLL > 0? System rzuci `ValueError` przy BANKROLL=0.
8. Telegram → `/start` do bota, `/help`
9. Kupony wciąż PENDING po >7 dniach? → sprawdź logi auto-resolve (bot_polling)
10. CLV = null dla starych kuponów? → normalnie, closing_odds zapisywane tylko raz
11. Optuna trwa za długo? → ustaw `OPTUNA_TRIALS=0` w config.py (domyślne params)
12. LightGBM błąd instalacji? → sprawdź `pip install lightgbm==4.3.0`
13. Testy → `cd betting_system && BANKROLL=1000 python -m pytest tests/ -v`

---

## Typowe błędy

| Błąd | Przyczyna | Rozwiązanie |
|------|-----------|-------------|
| `Brak kluczy API` | Secret nie ustawiony | GitHub Secrets |
| `Wszystkie klucze wyczerpane` | Limit 3 kont | Poczekaj do resetu miesiąca |
| `Za mało danych < 200` | Pierwsze uruchomienie | `fetch` → `train` |
| `Brak value betów` | Model konserwatywny | Obniż `MIN_EDGE` do 0.04 |
| `model.pkl not found` | Nie wytrenowany | `python main.py train` |
| `Brak mapowania: X` | Nowa drużyna | Dodaj do `name_mapping.py` |
| `Bot nie odpowiada` | Zły token/chat ID | Sprawdź Secrets, `/start` |
| `lightgbm ImportError` | Brak biblioteki | `pip install lightgbm==4.3.0` |
| `optuna ImportError` | Brak biblioteki | `pip install optuna==3.6.1` |
| `Nieznany format modelu` | Stary pkl + nowy kod | `python main.py train` |
| `CLV zawsze null` | Kupony za daleko w czasie | Normalnie — CLV zapisze się ~24h przed meczem |

---

## Ważne zastrzeżenia

System generuje sugestie zakładów wyłącznie na potrzeby własne właściciela.
Stawiaj wyłącznie w legalnych, licencjonowanych serwisach (w Polsce: licencja MF).

Hazard może uzależniać. Graj odpowiedzialnie.
**www.uzaleznienia.info** | Infolinia: **801 889 880**
