# AI Betting System – Instrukcja Projektu dla Claude

Wklej ten plik jako instrukcję systemową w Claude Projects.

---

## Aktualna wersja: v1.3 ✅

**Co nowego w v1.3:**
- Forma ważona czasowo (wykładniczy zanik, halflife=21 dni) – nowsze mecze ważą więcej
- Elo rating drużyn (home_elo, away_elo, elo_diff) – siła drużyny z pełnej historii
- Calibration plot zapisywany do data/model/calibration.png
- FORM_WINDOW zwiększony z 5 do 8 meczów
- Usunięto zależność od zewnętrznych API kontuzji
- Łącznie 18 cech (było 15 w v1.2, +3 elo w v1.3)

**Poprzednie wersje:**
- v1.2: 3 klucze API, double chance markets (1X, X2, 12), kupony oczekujące w bocie
- v1.1: strzały celne HST/AST, fuzzy matching w name_mapping
- v1.0: fundament – 5 lig, XGBoost+Platt, value engine, Kelly, Telegram, GitHub Actions

**Następna wersja: v1.4** (Optuna, ensemble XGBoost+LightGBM, osobny model remisów)

---

## Czym jest ten projekt

Automatyczny system value bettingu oparty na modelu ML (XGBoost + kalibracja Platta).
Analizuje mecze piłkarskie z 5 lig, identyfikuje zakłady z dodatnią wartością oczekiwaną
i wysyła gotowe kupony na Telegram. Działa w całości na GitHub Actions (0 PLN/miesiąc).

Właściciel używa systemu wyłącznie do użytku własnego.
System nie stawia zakładów automatycznie – tylko sugeruje i wysyła powiadomienia.

**Uwaga o accuracy:** piłka nożna ma dużą losowość. Nawet najlepsze modele osiągają
~54-58% accuracy dla 1X2. Wartość systemu leży w ROI z value betów, nie accuracy.

---

## Pełna mapa plików

```
betting_system/
│
├── main.py                     ← ORKIESTRATOR. Tryby: fetch | train | coupon | stats | bot | full
├── config.py                   ← WSZYSTKIE parametry. Ligi, klucze API, model, Elo, Kelly.
│                                  [v1.4] Walidacja BANKROLL > 0. TAX_THRESHOLD_PLN=2280.
├── requirements.txt            ← pandas, numpy, scikit-learn, xgboost, requests,
│                                  pytz, rapidfuzz, matplotlib
│
├── pipeline/
│   ├── api_utils.py            ← Multi-key API (3 klucze). Przełącza przy HTTP 401/402/429.
│   ├── fetch_stats.py          ← Pobiera CSV z football-data.co.uk (5 lig)
│   │                              Zapisuje: data/raw/all_matches.csv
│   ├── fetch_odds.py           ← Pobiera kursy z The Odds API (h2h)
│   │                              Zapisuje: data/odds/odds_YYYY-MM-DD.json
│   └── name_mapping.py         ← Mapowanie nazw drużyn + fuzzy matching (rapidfuzz)
│                                  [v1.4] Naprawione kolizje aliasów (Sassuolo/Sampdoria)
│
├── model/
│   ├── features.py             ← [v1.3] Feature engineering walk-forward
│   │                              18 cech: forma ważona(10) + H2H(2) + kursy(3) + Elo(3)
│   │                              FEATURE_COLS – kolejność musi być STAŁA
│   ├── train.py                ← XGBoost + CalibratedClassifierCV. Walk-forward 85/15.
│   │                              [v1.4] _simulate_roi używa kursów z ~5% marżą (nie fair)
│   ├── predict.py              ← Predykcje dla nadchodzących meczów
│   └── evaluate.py             ← [v1.4] Model ROI. Auto-rozliczanie przez The Odds API /scores.
│                                  auto_resolve_pending_coupons() – wywoływana co godzinę przez bota
│                                  update_coupon_results()       – wywoływana w run_stats()
│                                  get_pending_summary()         – stan kuponów oczekujących
│
├── coupon/
│   ├── value_engine.py         ← Value bety dla 1X2 i double chance (1X/X2/12)
│   │                              1X2: edge>5%, kursy 1.50–3.20, prob>40%
│   │                              DC:  edge>5%, kursy 1.20–2.00, prob>55%
│   ├── kelly.py                ← [v1.4] Frakcjonalne Kelly (0.25). Naprawka double-compute.
│   └── builder.py              ← Singiel / podwójny / potrójny (rozłączne mecze)
│                                  Zapisuje: data/results/coupons_history.json
│
├── notify/
│   ├── telegram.py             ← [v1.4] send_message() (publiczne API, dawniej _send).
│   │                              Kupony z numerami #1/#2/#3. DC emojis: 🏠🤝/🤝✈️/🏠✈️
│   ├── finance.py              ← [v1.4] Player ROI. Per-kupon stawki i wypłaty.
│   │                              add_stake(amount, coupon_id) / add_payout(amount, coupon_id)
│   │                              Oddzielony od Model ROI (evaluate.py)
│   └── bot_handler.py          ← [v1.4] Polling + auto-resolve przy każdym poll.
│                                  /stake [nr] [kwota] / /won [nr] [kwota] / /lost [nr]
│
├── data/
│   ├── raw/all_matches.csv
│   ├── odds/odds_*.json
│   ├── results/
│   │   ├── coupons_history.json  ← kupony z result (PENDING/WON/LOST) + resolved_at
│   │   ├── finance.json          ← transakcje gracza per coupon_id
│   │   ├── stats.json            ← Model ROI stats
│   │   └── tg_offset.json
│   └── model/
│       ├── model.pkl
│       └── calibration.png
│
└── .github/workflows/
    ├── daily_fetch.yml         ← env: ODDS_API_KEY, _2, _3
    ├── coupon_gen.yml          ← env: ODDS_API_KEY, _2, _3 + TELEGRAM_* + BANKROLL
    ├── weekly_retrain.yml      ← env: ODDS_API_KEY, _2, _3 + TELEGRAM_* + BANKROLL
    └── bot_polling.yml         ← env: TELEGRAM_* + BANKROLL
```

---

## Przepływ danych (pipeline)

```
KROK 1 - DANE (daily_fetch, codziennie)
  football-data.co.uk → CSV → data/raw/all_matches.csv
  The Odds API (h2h)  → JSON → data/odds/odds_YYYY-MM-DD.json

KROK 2 - MODEL (weekly_retrain, poniedziałek)
  all_matches.csv
    → features.py (walk-forward: forma ważona + Elo + H2H + kursy)
    → XGBoost + CalibratedClassifierCV
    → model.pkl + calibration.png

KROK 3 - KUPONY (coupon_gen, środa + piątek)
  model.pkl + odds_*.json
    → predict.py (1X2 probs)
    → value_engine.py (1X2 + DC value bets)
    → builder.py → Telegram (kupony z numerami #1, #2, #3...)

KROK 4 - BOT (bot_polling, co godzinę)
  → auto_resolve_pending_coupons() [evaluate.py]
      The Odds API /scores → rozlicza PENDING kupony w coupons_history.json
      (Model ROI automatyczny – niezależny od gracza)
  → getUpdates → bot_handler.py → komendy:
      /stake [nr] [kwota] → finance.json (Player ROI)
      /won [nr] [kwota]   → finance.json
      /lost [nr]          → (stawka już zalogowana przez /stake)

KROK 5 - STATYSTYKI (weekly_retrain, poniedziałek)
  coupons_history.json → evaluate.py  → stats.json     → Telegram (/stats = Model ROI)
  finance.json         → finance.py   → get_summary()  → Telegram (/balance = Player ROI)
```

---

## Cechy modelu v1.3 (18 cech)

### Forma ważona czasowo (10 cech)
Wykładniczy zanik wagi: `w = exp(-ln2 * days_ago / FORM_HALFLIFE_DAYS)`
Przy halflife=21 dni: mecz sprzed 3 tyg. waży 2x mniej niż ostatni.

```python
home_pts_avg, away_pts_avg   # średnia punktów (3/1/0)
home_gf_avg,  away_gf_avg    # średnia goli strzelonych
home_ga_avg,  away_ga_avg    # średnia goli straconych
home_hst_avg, away_hst_avg   # śr. strzałów celnych
home_ast_avg, away_ast_avg   # śr. strzałów celnych przeciwnika
```

### H2H (2 cechy)
```python
h2h_home_win_rate   # % wygranych "gospodarza" w bezpośrednich meczach
h2h_avg_goals       # średnia goli w bezpośrednich meczach
```

### Kursy rynkowe – fair probabilities (3 cechy)
```python
market_prob_h, market_prob_d, market_prob_a  # po usunięciu marży bukmachera
```

### Elo rating [v1.3] (3 cechy)
```python
home_elo    # rating Elo drużyny domowej (start: 1500, K=20)
away_elo    # rating Elo drużyny gości
elo_diff    # home_elo - away_elo (przewaga domowych)
```

---

## Elo – szczegóły implementacji

```python
# Formuła Elo (build_elo_history w features.py):
E_home = 1 / (1 + 10^((R_away - R_home) / 400))
R_new  = R_old + K * (S - E)
# S: 1.0=wygrana, 0.5=remis, 0.0=przegrana
# K=20 (config.ELO_K), start=1500 (config.ELO_START)

# Elo budowany raz dla całego df (O(n)), nie per mecz
elo_history = build_elo_history(df)
h_elo = _get_elo_before(elo_history, home_team, match_date)
```

---

## Double chance – jak działa (v1.2, niezmienione)

DC obliczane z kursów h2h bez dodatkowych requestów:
```python
dc_1X_market = mh + md   # fair odds = 1/(mh+md)
dc_X2_market = md + ma
dc_12_market = mh + ma
# Edge = (prob_home + prob_draw) - (mh + md)  ← analogicznie jak 1X2
```

Filtry DC: `DC_MIN_ODDS=1.20`, `DC_MAX_ODDS=2.00`, `DC_MIN_MODEL_PROB=0.55`

---

## Zmienne środowiskowe (GitHub Secrets)

```
ODDS_API_KEY       - klucz #1 The Odds API   [WYMAGANY]
ODDS_API_KEY_2     - klucz #2 The Odds API   [ZALECANY]
ODDS_API_KEY_3     - klucz #3 The Odds API   [ZALECANY]
TELEGRAM_TOKEN     - token bota Telegram     [WYMAGANY]
TELEGRAM_CHAT_ID   - Twój chat ID            [WYMAGANY]
BANKROLL           - bankroll w PLN          [WYMAGANY]
```

---

## Parametry modelu (config.py)

| Parametr | Domyślnie | Znaczenie |
|----------|-----------|-----------|
| FORM_WINDOW | 8 | Ostatnie N meczów do formy (v1.3: było 5) |
| FORM_HALFLIFE_DAYS | 21 | Połówka zaniku wagi formy w dniach [v1.3] |
| ELO_START | 1500 | Startowy Elo dla nowych drużyn [v1.3] |
| ELO_K | 20 | Współczynnik K Elo [v1.3] |
| MIN_EDGE | 0.05 | Min przewaga 5% |
| MIN_MODEL_PROB | 0.40 | Min pewność modelu dla 1X2 |
| DC_MIN_MODEL_PROB | 0.55 | Min pewność dla double chance |
| KELLY_FRACTION | 0.25 | Agresywność stawek |
| MAX_BET_PCT | 0.03 | Max 3% bankrollu na kupon |
| MIN_ODDS | 1.50 | Min kurs 1X2 |
| MAX_ODDS | 3.20 | Max kurs 1X2 |
| DC_MIN_ODDS | 1.20 | Min kurs double chance |
| DC_MAX_ODDS | 2.00 | Max kurs double chance |

---

## Ligi i źródła danych

| Kod | Liga | football-data | Odds API |
|-----|------|---------------|----------|
| EPL | Premier League | E0 | soccer_epl |
| BL | Bundesliga | D1 | soccer_germany_bundesliga |
| LL | La Liga | SP1 | soccer_spain_la_liga |
| SA | Serie A | I1 | soccer_italy_serie_a |
| EK | Ekstraklasa | P1 | soccer_poland_ekstraklasa |

---

## Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| /help | Lista komend | /help |
| /stats | Model ROI (jakość predykcji) | /stats |
| /balance | Twój rzeczywisty P&L (Player ROI) | /balance |
| /pending | Lista kuponów oczekujących na wynik | /pending |
| /setbalance X | Ustaw punkt startowy | /setbalance -1500 |
| /stake [nr] X | Stawka na konkretny kupon | /stake 1 100 |
| /won [nr] X | Kupon wygrany, dostałem X PLN | /won 1 350 |
| /lost [nr] | Kupon przegrany | /lost 2 |

**Model ROI** (z /stats) – automatycznie rozliczany przez The Odds API /scores.
Używa sugerowanych stawek Kelly. Mierzy jakość predykcji niezależnie od gracza.

**Player ROI** (z /balance) – rzeczywisty P&L gracza z finance.json.
Stawki i wypłaty per kupon, wprowadzane ręcznie przez /stake i /won.

---

## Typowe błędy i rozwiązania

| Błąd w logach | Przyczyna | Rozwiązanie |
|---------------|-----------|-------------|
| Brak kluczy API | Secret nie ustawiony | GitHub → Settings → Secrets |
| Wszystkie klucze wyczerpane | Limit 3 kont | Poczekaj do resetu |
| Za mało danych < 200 | Pierwsze uruchomienie | python main.py fetch, potem train |
| Brak value betów | Model konserwatywny | Obniż MIN_EDGE do 0.04 |
| model.pkl not found | Nie wytrenowany | python main.py train |
| Brak mapowania: X | Nowa drużyna | Dodaj do name_mapping.py → TEAM_MAP |
| Bot nie odpowiada | Zły token lub chat ID | Sprawdź Secrets, /start do bota |

---

## Plan rozwoju

### v1.3 ✅
Forma ważona czasowo + Elo + calibration plot

### v1.4 ✅ (obecna)
- Bugfixy: kelly_stake double-compute, kolizje name_mapping, walidacja BANKROLL
- Auto-rozliczanie kuponów przez The Odds API /scores
- Rozdzielenie Model ROI (evaluate.py) od Player ROI (finance.py)
- Per-kupon komendy: /stake [nr] [kwota], /won [nr] [kwota], /lost [nr]
- Realistyczna symulacja ROI w train.py (~5% marża bukmachera)
- Publiczne API send_message() w telegram.py
- Usunięto fetch_injuries.py (darmowe API bez danych bieżącego sezonu)

> **UWAGA Elo cross-liga:** build_elo_history buduje rating dla wszystkich lig razem.
> Nie wpływa negatywnie dopóki predykcje są per liga. Rozdzielić Elo per liga
> w v2.0 przy dodaniu nowych sportów / porównań cross-liga.

> **UWAGA podatek 10%:** pobierany od wygranych > 2280 PLN.
> Przy BANKROLL < 15 000 PLN próg nieosiągalny. Dla większych bankrolli
> uwzględnić korektę w kelly_stake (v1.5 TODO, patrz config.py TAX_THRESHOLD_PLN).

### v1.5 – Model + CLV
- Hyperparameter tuning (Optuna, n_trials=100)
- Ensemble XGBoost + LightGBM z uśrednianiem prawdopodobieństw
- CLV tracking: porównanie kursów z momentu generowania z closing odds
- class_weight dla remisów (D: 1.5 vs H/A: 1.0)
- Elo osobno per liga

### v1.6 – Over/under + lepsza selekcja
- Totals market (over/under gole) – model Poissona
- CLV monitoring + alert degradacji modelu
- Forma ważona dom/wyjazd osobno
- Elo SOS (Strength of Schedule)

### v2.0 – Nowe sporty
- Tenis ATP/WTA (tennis-data.co.uk, Jeff Sackmann GitHub)
- Siatkówka PlusLiga
- NBA – tylko z dostępem do advanced stats

### v2.1 – Monitoring
- Dashboard GitHub Pages (ROI, CLV trend, historia)
- Raport PDF na email

---

## Czego system NIE robi

- Automatyczne stawianie zakładów (nielegalne bez licencji)
- Live/in-play betting
- Arbitraż
- Over/under (planowane v1.5)

---

## Szybki debug checklist

1. Actions → zielony checkmark?
2. Logi → szukaj ERROR lub WARNING
3. `data/raw/all_matches.csv` istnieje? Jeśli nie: `python main.py fetch`
4. `data/model/model.pkl` istnieje? Jeśli nie: `python main.py train`
5. `data/odds/odds_YYYY-MM-DD.json` z dzisiaj? Jeśli nie: `python main.py fetch`
6. GitHub Secrets → ODDS_API_KEY i TELEGRAM_* i BANKROLL ustawione?
7. BANKROLL > 0? System rzuci ValueError przy BANKROLL=0.
8. Telegram → /start do bota, potem /help
9. Logi "Wszystkie klucze wyczerpane"? → sprawdź limity 3 kont The Odds API
10. Kupony wciąż PENDING po tygodniu? → sprawdź logi auto-resolve, może mecz był odwołany
