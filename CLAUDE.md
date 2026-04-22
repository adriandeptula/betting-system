# AI Betting System – Instrukcja Projektu dla Claude

Wklej ten plik jako instrukcję systemową w Claude Projects.
Dzięki temu Claude będzie znał pełny kontekst aplikacji bez potrzeby tłumaczenia za każdym razem.

---

## Aktualna wersja: v1.2 ✅

**Co nowego w v1.2 (zaimplementowane):**
- 3 klucze API dla The Odds API (łącznie 1500 req/miesiąc) i API-Football (łącznie 300 req/dzień)
- Double chance markets (1X, X2, 12) – wyprowadzane matematycznie z kursów h2h, zero dodatkowych requestów
- Osobne progi dla double chance: DC_MIN_ODDS=1.20, DC_MAX_ODDS=2.00, DC_MIN_MODEL_PROB=0.55
- Nowe emoji w kuponach Telegram dla double chance: 🏠🤝 / 🤝✈️ / 🏠✈️
- Kupony oczekujące (PENDING) widoczne w każdej odpowiedzi finansowej bota

**Poprzednie wersje:**
- v1.1: kontuzje z API-Football, cechy HST/AST, dual-key API, fuzzy matching
- v1.0: fundament systemu – 5 lig, XGBoost + Platt, value engine, Kelly, Telegram, GitHub Actions

**Następna wersja: v1.3** (Optuna, ensemble XGBoost+LightGBM, Elo, forma ważona)

---

## Czym jest ten projekt

Automatyczny system value bettingu oparty na modelu ML (XGBoost + kalibracja Platta).
Analizuje mecze piłkarskie z 5 lig, identyfikuje zakłady z dodatnią wartością oczekiwaną
i wysyła gotowe kupony na Telegram. Działa w całości na GitHub Actions (0 PLN/miesiąc).

Właściciel używa systemu wyłącznie do użytku własnego.
System nie stawia zakładów automatycznie – tylko sugeruje i wysyła powiadomienia.

---

## Pełna mapa plików

```
betting_system/
│
├── main.py                     ← ORKIESTRATOR. Tu zaczyna się każde uruchomienie.
│                                  Tryby: fetch | train | coupon | stats | bot | full
│
├── config.py                   ← WSZYSTKIE parametry. Zmieniaj tylko tutaj.
│                                  Ligi (z apifootball_id), klucze API (listy z env),
│                                  progi modelu, Kelly, kursy 1X2 i double chance.
│
├── requirements.txt            ← pandas, numpy, scikit-learn, xgboost, requests,
│                                  pytz, rapidfuzz
│
├── pipeline/
│   ├── api_utils.py            ← Mechanizm multi-key API (do 3 kluczy).
│   │                              Funkcja api_get() próbuje kolejno każdy klucz.
│   │                              Przy HTTP 401/402/429 przełącza na następny.
│   ├── fetch_stats.py          ← Pobiera CSV z football-data.co.uk (5 lig, 4 sezony)
│   │                              Zachowuje HST/AST (strzały celne)
│   │                              Zapisuje: data/raw/all_matches.csv
│   ├── fetch_odds.py           ← Pobiera JSON z The Odds API (aktualne kursy h2h)
│   │                              Double chance NIE wymaga osobnego fetcha –
│   │                              obliczane są w value_engine.py z kursów h2h.
│   │                              Zapisuje: data/odds/odds_YYYY-MM-DD.json
│   ├── fetch_injuries.py       ← Pobiera kontuzje z API-Football
│   │                              Opcjonalne: bez klucza po prostu pomija (no-op)
│   │                              Zapisuje: data/injuries/injuries_YYYY-MM-DD.json
│   └── name_mapping.py         ← Słownik mapowań nazw drużyn między źródłami.
│                                  Fuzzy matching z rapidfuzz jako fallback.
│
├── model/
│   ├── features.py             ← Feature engineering (walk-forward, bez data leakage)
│   │                              Cechy: forma, H2H, kursy rynkowe, kontuzje, HST/AST
│   │                              STAŁE: FEATURE_COLS – lista w ustalonej kolejności
│   ├── train.py                ← XGBoost multiclass (H/D/A) + CalibratedClassifierCV
│   │                              Walk-forward split 85/15. Brier Score jako metryka.
│   │                              Zapisuje: data/model/model.pkl
│   ├── predict.py              ← Wczytuje model, generuje predykcje dla nadchodzących meczów
│   └── evaluate.py             ← ROI z historii kuponów + get_pending_summary()
│
├── coupon/
│   ├── value_engine.py         ← [v1.2] Filtruje value bety dla 1X2 ORAZ double chance.
│   │                              1X2: edge>5%, kursy 1.50–3.20, prob>40%
│   │                              DC:  edge>5%, kursy 1.20–2.00, prob>55%
│   │                              DC odds/probs wyprowadzane z h2h (0 extra requestów)
│   ├── kelly.py                ← Frakcjonalne Kelly (0.25). Stawki w PLN, zaokr. do 5.
│   └── builder.py              ← Buduje singiel / podwójny / potrójny (rozłączne mecze)
│                                  Zapisuje: data/results/coupons_history.json
│
├── notify/
│   ├── telegram.py             ← [v1.2] Formatowanie kuponów z emojis dla DC outcomes:
│   │                              1X=🏠🤝, X2=🤝✈️, 12=🏠✈️
│   ├── finance.py              ← Śledzenie finansów P&L + format_summary_message(pending)
│   └── bot_handler.py          ← Polling Telegram + komendy + pending w każdej odpowiedzi
│
├── data/
│   ├── raw/all_matches.csv
│   ├── odds/odds_*.json
│   ├── injuries/injuries_*.json
│   ├── results/
│   │   ├── coupons_history.json
│   │   ├── finance.json
│   │   ├── stats.json
│   │   └── tg_offset.json
│   └── model/model.pkl
│
└── .github/workflows/
    ├── daily_fetch.yml         ← env: ODDS_API_KEY, _2, _3 + API_FOOTBALL_KEY, _2, _3
    ├── coupon_gen.yml          ← env: ODDS_API_KEY, _2, _3 + API_FOOTBALL_KEY, _2, _3
    ├── weekly_retrain.yml      ← env: ODDS_API_KEY, _2, _3 + API_FOOTBALL_KEY, _2, _3
    └── bot_polling.yml         ← env: tylko TELEGRAM_* i BANKROLL (bez kluczy API)
```

---

## Przepływ danych (pipeline)

```
KROK 1 - DANE (daily_fetch, codziennie)
  football-data.co.uk → CSV → data/raw/all_matches.csv
  The Odds API (h2h)  → JSON → data/odds/odds_YYYY-MM-DD.json
  API-Football        → JSON → data/injuries/injuries_YYYY-MM-DD.json (opcjonalne)

KROK 2 - MODEL (weekly_retrain, poniedziałek)
  all_matches.csv + injuries/*.json → features.py (walk-forward) → XGBoost → model.pkl

KROK 3 - KUPONY (coupon_gen, środa + piątek)
  model.pkl + odds_*.json + injuries_*.json
    → predict.py (1X2 probs)
    → value_engine.py (1X2 candidates + DC candidates wyprowadzone z h2h)
    → builder.py → Telegram

KROK 4 - BOT (bot_polling, co godzinę)
  Telegram getUpdates → bot_handler.py → komendy → finance.py + pending → odpowiedź

KROK 5 - STATYSTYKI (weekly_retrain, poniedziałek)
  coupons_history.json + finance.json → evaluate.py → stats.json → Telegram
```

---

## Double chance – jak działa (v1.2)

Double chance NIE pobiera osobnych kursów z API. Zamiast tego:

```python
# Z kursów h2h (już pobranych) → fair probs po usunięciu marży:
mh = market_prob_home  # np. 0.50
md = market_prob_draw  # np. 0.25
ma = market_prob_away  # np. 0.25

# Double chance probs:
dc_1X_market = mh + md        # 0.75 → fair odds = 1/0.75 = 1.33
dc_X2_market = md + ma        # 0.50 → fair odds = 1/0.50 = 2.00
dc_12_market = mh + ma        # 0.75 → fair odds = 1/0.75 = 1.33

# Edge = model_prob - market_prob (tak samo jak przy 1X2)
dc_1X_model = prob_home + prob_draw  # np. 0.82
edge_1X = 0.82 - 0.75 = +0.07  ← value bet!
```

Filtry dla double chance (osobne od 1X2):
- `DC_MIN_ODDS = 1.20`, `DC_MAX_ODDS = 2.00`
- `DC_MIN_MODEL_PROB = 0.55` (wyższy niż 0.40 dla 1X2, bo DC jest z natury bardziej pewne)
- `MIN_EDGE = 0.05` (ten sam co 1X2)

---

## Multi-key API (v1.1+, rozszerzony w v1.2)

Każde API obsługuje teraz **3 klucze** w GitHub Secrets:
```
ODDS_API_KEY, ODDS_API_KEY_2, ODDS_API_KEY_3
API_FOOTBALL_KEY, API_FOOTBALL_KEY_2, API_FOOTBALL_KEY_3
```

W config.py lista budowana dynamicznie (puste klucze pomijane):
```python
ODDS_API_KEYS = [k for k in [env("ODDS_API_KEY"), env("ODDS_API_KEY_2"), env("ODDS_API_KEY_3")] if k]
```

Mechanizm w api_utils.py: przy HTTP 401/402/429 przełącza na następny klucz z listy.

Pojemność przy 3 kontach:
- The Odds API: 1500 req/miesiąc (wystarczy na 5 lig + zapas ~3x)
- API-Football: 300 req/dzień (wystarczy na 15+ lig)

---

## Zmienne środowiskowe (GitHub Secrets)

```
ODDS_API_KEY       - klucz #1 The Odds API              [WYMAGANY]
ODDS_API_KEY_2     - klucz #2 The Odds API              [ZALECANY]
ODDS_API_KEY_3     - klucz #3 The Odds API              [ZALECANY]
TELEGRAM_TOKEN     - token bota Telegram                 [WYMAGANY]
TELEGRAM_CHAT_ID   - Twój chat ID                       [WYMAGANY]
BANKROLL           - bankroll w PLN, np. "1000"          [WYMAGANY]
API_FOOTBALL_KEY   - klucz #1 API-Football (opcjonalny) [OPCJONALNY]
API_FOOTBALL_KEY_2 - klucz #2 API-Football              [OPCJONALNY]
API_FOOTBALL_KEY_3 - klucz #3 API-Football              [OPCJONALNY]
```

---

## Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| /help | Lista komend | /help |
| /stats | ROI i historia kuponów | /stats |
| /balance | Status finansowy P&L + kupony oczekujące | /balance |
| /setbalance X | Ustaw punkt startowy | /setbalance -1500 |
| /stake X | Zaloguj wpłatę na zakłady | /stake 100 |
| /payout X | Zaloguj wypłatę wygranej | /payout 500 |
| /won X | Kupon wygrany + kwota | /won 350 |
| /lost | Kupon przegrany | /lost |

Każda odpowiedź finansowa (/stake, /won, /lost, /balance, /setbalance, /payout)
automatycznie pokazuje sekcję kuponów PENDING z zakresem worst/best case.

---

## Parametry modelu (config.py)

| Parametr | Domyślnie | Znaczenie |
|----------|-----------|-----------|
| MIN_EDGE | 0.05 | Min przewaga 5%. Obniż do 0.04 jeśli mało kuponów. |
| MIN_MODEL_PROB | 0.40 | Min pewność modelu dla 1X2. |
| DC_MIN_MODEL_PROB | 0.55 | Min pewność modelu dla double chance. |
| KELLY_FRACTION | 0.25 | Agresywność stawek. 0.1=ultra-ostrożny, 0.5=ryzykowny. |
| MAX_BET_PCT | 0.03 | Max 3% bankrollu na kupon. |
| MIN_ODDS | 1.50 | Min kurs na nogę 1X2. |
| MAX_ODDS | 3.20 | Max kurs 1X2. |
| DC_MIN_ODDS | 1.20 | Min kurs dla double chance. |
| DC_MAX_ODDS | 2.00 | Max kurs double chance. |
| FORM_WINDOW | 5 | Ostatnie N meczów do formy. |
| CURRENT_SEASON | 2025 | Rok sezonu dla API-Football. Aktualizuj co rok. |

---

## Ligi i źródła danych

| Kod | Liga | football-data | Odds API | API-Football ID |
|-----|------|---------------|----------|-----------------|
| EPL | Premier League | E0 | soccer_epl | 39 |
| BL | Bundesliga | D1 | soccer_germany_bundesliga | 78 |
| LL | La Liga | SP1 | soccer_spain_la_liga | 140 |
| SA | Serie A | I1 | soccer_italy_serie_a | 135 |
| EK | Ekstraklasa | P1 | soccer_poland_ekstraklasa | 106 |

---

## Typowe błędy i rozwiązania

| Błąd w logach | Przyczyna | Rozwiązanie |
|---------------|-----------|-------------|
| Brak kluczy API | Secret nie ustawiony | GitHub → Settings → Secrets |
| Wszystkie klucze wyczerpane | Wszystkie 3 konta osiągnęły limit | Poczekaj do resetu lub dodaj klucz #4 |
| Za mało danych < 200 | Pierwsze uruchomienie | python main.py fetch, potem train |
| Brak value betów | Model zbyt konserwatywny | Obniż MIN_EDGE do 0.04 |
| model.pkl not found | Nie wytrenowany | python main.py train |
| Brak mapowania: X | Nowa drużyna w lidze | Dodaj do name_mapping.py → TEAM_MAP |
| Bot nie odpowiada | Zły token lub chat ID | Sprawdź Secrets, /start do bota |
| rapidfuzz not found | Nie zainstalowany | pip install rapidfuzz==3.9.3 |

---

## Plan rozwoju

### v1.0 ✅ → v1.1 ✅ → v1.2 ✅ (obecna)
Szczegóły w README.md

### v1.3 (następna) – Lepszy model
- Hyperparameter tuning (Optuna)
- Ensemble XGBoost + LightGBM
- Forma ważona czasowo
- Elo rating drużyn
- Osobny mini-model dla remisów

### v1.4 – Over/under + lepsza selekcja kuponów
- Totals market (over/under gole) — wymaga nowego modelu regresji
- Round-robin kupony
- CLV tracking
- Automatyczne rozliczanie przez API scores

### v2.0 – Nowe sporty
- Tenis ATP/WTA: źródło danych DO USTALENIA w 2026
  (Tennis Abstract API lub sofascore; Jeff Sackmann nieaktualne)
- NBA (basketball-reference.com)
- Siatkówka PlusLiga

### v2.1 – Monitoring
- Dashboard GitHub Pages
- Raport PDF na email
- API-Football premium: rozważyć przy v2.0+ gdy potrzeba >300 req/dzień

---

## Czego system NIE robi

- Automatyczne stawianie zakładów (nielegalne bez licencji)
- Live/in-play betting
- Arbitraż
- Over/under (planowane v1.4)

---

## Szybki debug checklist

1. Actions → zielony checkmark?
2. Logi → szukaj ERROR lub WARNING
3. data/raw/all_matches.csv istnieje? Jeśli nie: `python main.py fetch`
4. data/model/model.pkl istnieje? Jeśli nie: `python main.py train`
5. data/odds/odds_YYYY-MM-DD.json z dzisiaj? Jeśli nie: `python main.py fetch`
6. GitHub Secrets → ODDS_API_KEY i TELEGRAM_* ustawione?
7. Telegram → /start do bota
8. Logi "Wszystkie klucze wyczerpane"? → sprawdź limity wszystkich 3 kont
