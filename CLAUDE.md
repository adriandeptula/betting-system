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
- Łącznie 18 cech (było 17: -2 injury_score, +3 elo)

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
│
├── model/
│   ├── features.py             ← [v1.3] Feature engineering walk-forward
│   │                              NOWE: forma ważona czasowo + Elo rating
│   │                              18 cech: forma(10) + H2H(2) + kursy(3) + Elo(3)
│   │                              FEATURE_COLS – kolejność musi być stała
│   ├── train.py                ← XGBoost + CalibratedClassifierCV. Walk-forward 85/15.
│   │                              [v1.3] Zapisuje calibration.png do data/model/
│   ├── predict.py              ← Predykcje dla nadchodzących meczów
│   └── evaluate.py             ← ROI z historii kuponów + get_pending_summary()
│
├── coupon/
│   ├── value_engine.py         ← Value bety dla 1X2 i double chance (1X/X2/12)
│   │                              1X2: edge>5%, kursy 1.50–3.20, prob>40%
│   │                              DC:  edge>5%, kursy 1.20–2.00, prob>55%
│   ├── kelly.py                ← Frakcjonalne Kelly (0.25). Stawki zaokr. do 5 PLN.
│   └── builder.py              ← Singiel / podwójny / potrójny (rozłączne mecze)
│                                  Zapisuje: data/results/coupons_history.json
│
├── notify/
│   ├── telegram.py             ← Formatowanie kuponów. DC emojis: 🏠🤝/🤝✈️/🏠✈️
│   ├── finance.py              ← P&L tracking + format_summary_message(pending)
│   └── bot_handler.py          ← Polling Telegram + komendy + pending w odpowiedziach
│
├── data/
│   ├── raw/all_matches.csv
│   ├── odds/odds_*.json
│   ├── results/
│   │   ├── coupons_history.json
│   │   ├── finance.json
│   │   ├── stats.json
│   │   └── tg_offset.json
│   └── model/
│       ├── model.pkl
│       └── calibration.png     ← [v1.3] Nowy: wykres jakości kalibracji
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
    → predict.py (1X2 probs + Elo)
    → value_engine.py (1X2 + DC value bets)
    → builder.py → Telegram

KROK 4 - BOT (bot_polling, co godzinę)
  Telegram getUpdates → bot_handler.py → komendy → finance.py + pending → odpowiedź

KROK 5 - STATYSTYKI (weekly_retrain, poniedziałek)
  coupons_history.json + finance.json → evaluate.py → stats.json → Telegram
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

| Komenda | Opis |
|---------|------|
| /help | Lista komend |
| /stats | ROI i historia kuponów |
| /balance | Status finansowy P&L + kupony oczekujące |
| /setbalance X | Ustaw punkt startowy |
| /stake X | Zaloguj wpłatę |
| /payout X | Zaloguj wypłatę |
| /won X | Kupon wygrany |
| /lost | Kupon przegrany |

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

### v1.3 ✅ (obecna)
Forma ważona czasowo + Elo + calibration plot

### v1.4 (następna) – Zaawansowany model
- Hyperparameter tuning (Optuna)
- Ensemble XGBoost + LightGBM
- Osobny mini-model dla remisów
- Elo z uwzględnieniem siły harmonogramu (SOS)

### v1.5 – Over/under + lepsza selekcja
- Totals market (over/under gole)
- Round-robin kupony
- CLV tracking
- Automatyczne rozliczanie wyników

### v2.0 – Nowe sporty
- Tenis ATP/WTA
- NBA (basketball-reference.com)
- Siatkówka PlusLiga

### v2.1 – Monitoring
- Dashboard GitHub Pages
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
3. data/raw/all_matches.csv istnieje? Jeśli nie: `python main.py fetch`
4. data/model/model.pkl istnieje? Jeśli nie: `python main.py train`
5. data/odds/odds_YYYY-MM-DD.json z dzisiaj? Jeśli nie: `python main.py fetch`
6. GitHub Secrets → ODDS_API_KEY i TELEGRAM_* ustawione?
7. Telegram → /start do bota
8. Logi "Wszystkie klucze wyczerpane"? → sprawdź limity 3 kont The Odds API
