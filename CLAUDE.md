# AI Betting System – Instrukcja Projektu dla Claude

Wklej ten plik jako instrukcję systemową w Claude Projects.
Dzięki temu Claude będzie znał pełny kontekst aplikacji bez potrzeby tłumaczenia za każdym razem.

---

## Aktualna wersja: v1.1 ✅

**Co nowego w v1.1 (zaimplementowane):**
- Integracja API-Football: kontuzje i zawieszenia jako cecha modelu
- Nowe cechy modelu: strzały celne HST (home shots on target) i AST
- Podwójne klucze API z automatycznym fallbackiem dla The Odds API i API-Football
- Fuzzy matching w name_mapping.py przy użyciu rapidfuzz
- Nowy plik: `pipeline/api_utils.py` (centralny mechanizm dual-key)
- Nowy plik: `pipeline/fetch_injuries.py` (pobieranie kontuzji)
- Nowy katalog danych: `data/injuries/`

**Następna wersja: v1.2** (hyperparameter tuning, ensemble, forma ważona, Elo)

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
│                                  progi modelu, Kelly, kursy.
│
├── requirements.txt            ← pandas, numpy, scikit-learn, xgboost, requests,
│                                  pytz, rapidfuzz
│
├── pipeline/
│   ├── api_utils.py            ← [v1.1 NOWY] Mechanizm dual-key API.
│   │                              Funkcja api_get() próbuje kolejno każdy klucz.
│   │                              Przy HTTP 401/402/429 przełącza na następny.
│   ├── fetch_stats.py          ← Pobiera CSV z football-data.co.uk (5 lig, 4 sezony)
│   │                              Zachowuje HST/AST (strzały celne) [v1.1]
│   │                              Zapisuje: data/raw/all_matches.csv
│   ├── fetch_odds.py           ← Pobiera JSON z The Odds API (aktualne kursy)
│   │                              Używa api_utils.api_get() z dual-key fallback [v1.1]
│   │                              Zapisuje: data/odds/odds_YYYY-MM-DD.json
│   ├── fetch_injuries.py       ← [v1.1 NOWY] Pobiera kontuzje z API-Football
│   │                              Używa api_utils.api_get() z dual-key fallback
│   │                              Opcjonalne: bez klucza po prostu pomija (no-op)
│   │                              Zapisuje: data/injuries/injuries_YYYY-MM-DD.json
│   └── name_mapping.py         ← Słownik mapowań nazw drużyn między źródłami.
│                                  [v1.1] fuzzy matching z rapidfuzz jako fallback.
│                                  Gdy pojawi się "brak mapowania" w logach – dodaj tu.
│
├── model/
│   ├── features.py             ← Feature engineering (walk-forward, bez data leakage)
│   │                              [v1.1] Nowe cechy: home/away_hst_avg, home/away_ast_avg
│   │                              [v1.1] Nowe cechy: home/away_injury_score
│   │                              FUNKCJA: remove_margin() usuwa marżę bukmachera
│   │                              STAŁE: FEATURE_COLS – lista w ustalonej kolejności
│   ├── train.py                ← XGBoost multiclass (H/D/A) + CalibratedClassifierCV
│   │                              Walk-forward split 85/15. Brier Score jako metryka.
│   │                              Symulacja ROI na danych testowych przy każdym treningu.
│   │                              Zapisuje: data/model/model.pkl
│   ├── predict.py              ← Wczytuje model, generuje predykcje dla nadchodzących meczów
│   │                              Wczytuje też injuries przez fetch_injuries.load_latest_injuries()
│   └── evaluate.py             ← Oblicza ROI z historii kuponów, aktualizuje stats.json
│
├── coupon/
│   ├── value_engine.py         ← Filtr: edge > MIN_EDGE, kursy 1.50-3.20, prob > 40%
│   │                              Edge = model_prob - market_prob (po usunięciu marży)
│   ├── kelly.py                ← Frakcjonalne Kelly (0.25). Stawki w PLN, zaokr. do 5.
│   └── builder.py              ← Buduje singiel / podwójny / potrójny (rozłączne mecze)
│                                  Zapisuje: data/results/coupons_history.json
│
├── notify/
│   ├── telegram.py             ← Formatowanie i wysyłka wiadomości (HTML parse_mode)
│   │                              Funkcje: send_coupons(), send_stats(), send_alert()
│   ├── finance.py              ← Śledzenie finansów P&L
│   │                              Dane: data/results/finance.json
│   │                              Funkcje: set_initial_balance(), add_stake(),
│   │                                       add_payout(), get_summary()
│   └── bot_handler.py          ← Dwukierunkowa komunikacja Telegram (polling getUpdates)
│                                  Komendy: /stats /balance /setbalance /stake /payout
│                                           /won /lost /help
│
├── data/
│   ├── raw/all_matches.csv     ← Historyczne mecze (generowane przez fetch)
│   ├── odds/odds_*.json        ← Kursy z danego dnia
│   ├── injuries/               ← [v1.1 NOWY] Kontuzje z API-Football
│   │   └── injuries_*.json     ← {league_code: [{player_name, team_name, reason, ...}]}
│   ├── results/
│   │   ├── coupons_history.json ← Historia kuponów (date, type, legs, stake, result)
│   │   ├── finance.json         ← Historia transakcji finansowych
│   │   ├── stats.json           ← Bieżące statystyki ROI
│   │   └── tg_offset.json       ← Offset Telegram polling (nie modyfikuj ręcznie)
│   └── model/model.pkl         ← Wytrenowany model + metadane (Liga codes, features)
│
└── .github/workflows/
    ├── daily_fetch.yml         ← Cron: codziennie 06:00 UTC - pobierz dane
    ├── coupon_gen.yml          ← Cron: środa + piątek 09:00 UTC - generuj kupony
    ├── weekly_retrain.yml      ← Cron: poniedziałek 05:00 UTC - retrain + stats
    └── bot_polling.yml         ← Cron: co godzinę - sprawdź komendy Telegram
```

---

## Przepływ danych (pipeline)

```
KROK 1 - DANE (daily_fetch, codziennie)
  football-data.co.uk → CSV → data/raw/all_matches.csv  (z HST/AST v1.1)
  The Odds API        → JSON → data/odds/odds_YYYY-MM-DD.json
  API-Football        → JSON → data/injuries/injuries_YYYY-MM-DD.json  [v1.1, opcjonalne]

KROK 2 - MODEL (weekly_retrain, poniedziałek)
  all_matches.csv + injuries/*.json → features.py (walk-forward) → XGBoost → model.pkl

KROK 3 - KUPONY (coupon_gen, środa + piątek)
  model.pkl + odds_*.json + injuries_*.json → predict.py → value_engine.py → builder.py → Telegram
  Po wysłaniu: bot pyta "Ile wpłaciłeś?" → czeka na /stake X

KROK 4 - BOT (bot_polling, co godzinę)
  Telegram getUpdates → bot_handler.py → komendy → finance.py → odpowiedź Telegram

KROK 5 - STATYSTYKI (weekly_retrain, poniedziałek)
  coupons_history.json + finance.json → evaluate.py → stats.json → Telegram
```

---

## Kluczowe decyzje projektowe

### Dual-key API (v1.1)
Każde API ma 2 klucze w GitHub Secrets (np. ODDS_API_KEY + ODDS_API_KEY_2).
Mechanizm w pipeline/api_utils.py:
- Próbuje klucz #1
- Przy HTTP 401/402/429 (limit wyczerpany) przełącza na klucz #2
- Klucze trzymane jako lista w config.py: ODDS_API_KEYS = [key1, key2]
- Jeśli brak klucza #2, działa na jednym (brak błędu)

### API-Football jest opcjonalne
fetch_injuries.py przy braku klucza zwraca {} bez błędu.
features.py przy braku danych o kontuzjach ustawia injury_score = 0.0.
System działa normalnie bez tej funkcji – kontuzje to dodatkowe ulepszenie.

### Fuzzy matching w name_mapping (v1.1)
rapidfuzz jako fallback przy braku ręcznego mapowania.
Threshold: 80 punktów (token_sort_ratio).
Fuzzy cache zapobiega wielokrotnemu przeliczaniu.
Zawsze lepiej dodać ręczne mapowanie do TEAM_MAP niż polegać na fuzzy.

### Multiclass zamiast binary
Piłka nożna ma 3 wyniki (H/D/A). Model binarny byłby błędny.
XGBClassifier z num_class=3, predict_proba() zwraca [P(H), P(D), P(A)].

### Kalibracja Platta (CalibratedClassifierCV)
XGBoost bez kalibracji daje złe prawdopodobieństwa.
Kalibracja koryguje je tak że model.predict_proba() = rzeczywiste prawdopodobieństwa.
BEZ KALIBRACJI Kelly criterion daje błędne stawki i grozi ruiną bankrollu.

### Walk-forward split (nie random)
Dane sportowe są chronologiczne. Random split = data leakage.
Zawsze trenuj na przeszłości, testuj na przyszłości. Split: 85% train, 15% test.

### remove_margin() w features
Kursy bukmachera mają marżę (~5%). Suma implikowanych prob > 1.0.
Bez normalizacji edge wyglądałby większy niż jest. remove_margin() naprawia to.

### Frakcjonalne Kelly = 0.25
Pełne Kelly zakłada idealny model. Nasz model jest probabilistyczny, nie pewny.
0.25 Kelly = 4x bezpieczniejsze przy akceptowalnym zwrocie.

### Polling zamiast webhook
Webhook wymaga publicznego URL (serwer). Polling przez GitHub Actions = 0 PLN.
Opóźnienie: max 60 minut. Wystarczające dla zakładów sportowych.

---

## Zmienne środowiskowe (GitHub Secrets)

```
ODDS_API_KEY       - klucz #1 The Odds API (the-odds-api.com)  [WYMAGANY]
ODDS_API_KEY_2     - klucz #2 The Odds API (drugie konto)      [ZALECANY – fallback]
TELEGRAM_TOKEN     - token bota (@BotFather na Telegramie)     [WYMAGANY]
TELEGRAM_CHAT_ID   - Twój chat ID (@userinfobot na Telegramie) [WYMAGANY]
BANKROLL           - bankroll w PLN, np. "1000"                 [WYMAGANY]
API_FOOTBALL_KEY   - klucz #1 API-Football (v1.1, opcjonalny)  [OPCJONALNY]
API_FOOTBALL_KEY_2 - klucz #2 API-Football (drugie konto)      [OPCJONALNY – fallback]
```

---

## Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| /help | Lista komend | /help |
| /stats | ROI i historia kuponów | /stats |
| /balance | Pełny status finansowy P&L | /balance |
| /setbalance X | Ustaw punkt startowy | /setbalance -1500 |
| /stake X | Zaloguj wpłatę na zakłady | /stake 100 |
| /payout X | Zaloguj wypłatę wygranej | /payout 500 |
| /won X | Kupon wygrany + kwota | /won 350 |
| /lost | Kupon przegrany | /lost |

Komendy są przetwarzane co godzinę (bot_polling.yml), nie natychmiastowo.

---

## Finanse - jak działa tracking P&L

```
Punkt startowy (/setbalance):
  Ustawiasz raz. Może być ujemny np. -1500 oznacza że zaczynasz ze stratą 1500 PLN.

Przepływ typowego kuponu:
  1. Bot wysyła kupony (środa/piątek) → pyta "Ile wpłaciłeś?" → /stake 100
  2. Mecze się rozgrywają (1-3 dni)
  3. Poniedziałek: bot pyta "Wygrałeś?" → /won 350 lub /lost
  4. /balance pokazuje aktualny całościowy wynik

Wzór całościowego wyniku:
  overall = initial_balance + suma_wyplat - suma_wplat
  roi     = (suma_wyplat - suma_wplat) / suma_wplat × 100%
```

---

## Parametry modelu (config.py)

| Parametr | Domyślnie | Znaczenie i kiedy zmienić |
|----------|-----------|---------------------------|
| MIN_EDGE | 0.05 | Min przewaga 5%. Obniż do 0.04 jeśli mało kuponów. |
| MIN_MODEL_PROB | 0.40 | Min pewność 40%. Obniż do 0.35 dla większej liczby zakładów. |
| KELLY_FRACTION | 0.25 | Agresywność stawek. 0.1=ultra-ostrożny, 0.5=ryzykowny. |
| MAX_BET_PCT | 0.03 | Max 3% bankrollu na kupon. Nie przekraczaj 0.05. |
| MIN_ODDS | 1.50 | Min kurs na nogę. |
| MAX_ODDS | 3.20 | Max kurs. Powyżej = zbyt niepewne. |
| FORM_WINDOW | 5 | Ile ostatnich meczów do liczenia formy. |
| MAX_LEGS | 3 | Max nogi w parlayach. Nie zwiększaj powyżej 3. |
| CURRENT_SEASON | 2024 | Rok sezonu dla API-Football. Aktualizuj co rok. |

---

## Ligi i źródła danych

| Kod | Liga | football-data | Odds API | API-Football ID |
|-----|------|---------------|----------|-----------------|
| EPL | Premier League | E0 | soccer_epl | 39 |
| BL | Bundesliga | D1 | soccer_germany_bundesliga | 78 |
| LL | La Liga | SP1 | soccer_spain_la_liga | 140 |
| SA | Serie A | I1 | soccer_italy_serie_a | 135 |
| EK | Ekstraklasa | P1 | soccer_poland_ekstraklasa | 106 |

Sezony: 2021/22, 2022/23, 2023/24, 2024/25

---

## Typowe błędy i rozwiązania

| Błąd w logach | Przyczyna | Rozwiązanie |
|---------------|-----------|-------------|
| Brak kluczy API | Secret nie ustawiony | GitHub → Settings → Secrets |
| Wszystkie klucze wyczerpane | Oba konta osiągnęły limit | Poczekaj do resetu (1 dzień/miesiąc) |
| Za mało danych < 200 | Pierwsze uruchomienie | python main.py fetch, potem train |
| Liga X niedostępna | Przerwa sezonowa | Normalny stan |
| Brak value betów | Model zbyt konserwatywny | Obniż MIN_EDGE do 0.04 |
| model.pkl not found | Nie wytrenowany | python main.py train |
| Brak mapowania: X | Nowa drużyna w lidze | Dodaj do name_mapping.py → TEAM_MAP |
| Bot nie odpowiada | Zły token lub chat ID | Sprawdź Secrets, /start do bota |
| API-Football errors | Limit dzienny 100 req | Poczekaj do północy lub użyj klucza #2 |
| rapidfuzz not found | Nie zainstalowany | pip install rapidfuzz==3.9.3 |

---

## Gdzie wpisywać wyniki meczów

Nie ma ręcznego wpisywania wyników meczów do modelu.
Model ocenia mecze probabilistycznie na podstawie historycznych statystyk.

Wyniki historyczne są pobierane automatycznie przez fetch_stats.py
z football-data.co.uk z opóźnieniem 1-2 dni.

Wyniki finansowe kuponów wpisujesz przez Telegram komendami /won lub /lost.

---

## Metryki sukcesu

System DZIAŁA jeśli po 50+ zakładach:
- ROI > 0% (jakikolwiek zysk)
- ROI > 5% = bardzo dobry wynik
- Model accuracy > baseline (baseline ~46% = zawsze typuj gospodarza)

System WYMAGA KOREKTY jeśli:
- ROI < -10% po 50+ zakładach
- Accuracy < baseline przez 2+ tygodnie
- Brak value betów przez 2 tygodnie

---

## Plan rozwoju

### v1.1 (obecna) ✅
- Dane o kontuzjach z API-Football (100 req/dzień/konto)
- Cechy HST/AST (strzały celne)
- Dual-key z automatycznym fallbackiem dla wszystkich API
- Fuzzy matching w name_mapping.py

### v1.2 (następna)
- Hyperparameter tuning (Optuna)
- Ensemble XGBoost + LightGBM
- Feature: forma ważona wagą czasową
- Feature: Elo rating drużyn
- Closing Line Value tracking

### v1.3
- Round-robin kupony (z 4 value betów kombinacje 2-nożne)
- Filtry korelacji przy budowaniu parlayów
- Automatyczne rozliczanie wyników przez API scores

### v2.0
- Tenis ATP/WTA (dane: Jeff Sackmann GitHub, darmowe)
- NBA (dane: basketball-reference)
- Siatkówka PlusLiga

### v2.1
- Dashboard GitHub Pages (wykres ROI, historia kuponów)
- Tygodniowy raport PDF na email

---

## Czego system NIE robi

- Automatyczne stawianie zakładów (nielegalne bez licencji)
- Live/in-play betting (wymaga WebSocket + płatne API)
- Arbitraż (inna strategia)
- Prognozowanie remisów osobno (planowane v1.2)

---

## Szybki debug checklist

1. Actions → czy workflow zakończył się bez błędu (zielony checkmark)?
2. Logi workflow → szukaj ERROR lub WARNING
3. Czy data/raw/all_matches.csv istnieje? Jeśli nie: uruchom fetch
4. Czy data/model/model.pkl istnieje? Jeśli nie: uruchom train
5. Czy data/odds/odds_YYYY-MM-DD.json z dzisiaj istnieje? Jeśli nie: uruchom fetch
6. GitHub Secrets → czy ODDS_API_KEY i TELEGRAM_* są ustawione?
7. Telegram → napisz /start do bota (aktywacja)
8. [v1.1] Czy data/injuries/ istnieje? Jeśli nie i masz API-Football key – uruchom fetch
9. [v1.1] Logi "Wszystkie klucze wyczerpane"? → sprawdź limity obu kont API
