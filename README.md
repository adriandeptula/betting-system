# 🤖 AI Betting System — v1.5

System automatyczny do generowania value betów oparty na XGBoost + kalibracja Platta.
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

PON  05:00 → Pobierz świeże dane → Retrenuj model → Wyślij statystyki ROI
COD  06:00 → Pobierz dane (wyniki + kursy)
ŚR   09:00 → Generuj kupony → Wyślij na Telegram
PT   09:00 → Generuj kupony → Wyślij na Telegram
CO H 00:00 → Bot sprawdza komendy Telegram i auto-rozlicza kupony
```

**Źródła danych:**
- football-data.co.uk — historyczne wyniki 5 lig (EPL, Bundesliga, La Liga, Serie A, Ekstraklasa)
- The Odds API — aktualne kursy z ~40 bukmacherów europejskich

**Model:** XGBoost + kalibracja Platta (3 klasy: H/D/A)

**Cechy modelu (v1.5 — 18 cech):**
- Forma ważona czasowo (wykładniczy zanik halflife=21 dni, nowsze mecze ważą więcej)
- Elo rating **per liga** (osobna skala dla każdej ligi — brak cross-league noise)
- Statystyki: gole, strzały celne HST/AST, H2H
- Fair probabilities (kursy po usunięciu marży bukmachera)

**Kalibracja Platta:** temporal split (cv='prefit') — eliminuje data leakage w kalibracji.

**Obsługiwane typy zakładów:** 1X2 i Double Chance (1X, X2, 12)

**Stawki:** Frakcjonalne kryterium Kelly (25% pełnego Kelly)

**Klucze API:** The Odds API obsługuje **3 klucze** z automatycznym przełączaniem

**CI/CD:** GitHub Actions z concurrency groups — brak race condition przy równoległych jobach

---

## Pierwsze uruchomienie

### KROK 1: Stwórz konta na The Odds API

1. Wejdź na **https://the-odds-api.com** → **Get API Key** → zarejestruj się
2. Skopiuj klucz API
3. Zalecane: załóż 2-3 konta (różne emaile) — free tier: 500 req/miesiąc/konto

---

### KROK 2: Stwórz bota Telegram

**2a. Utwórz bota:**
1. Otwórz Telegram → wyszukaj **@BotFather**
2. Napisz `/newbot` → podaj nazwę i username (musi kończyć się na `bot`)
3. Skopiuj **TOKEN**

**2b. Pobierz swój Chat ID:**
1. Wyszukaj **@userinfobot** → napisz `/start`
2. Skopiuj swoje **ID** (liczba, np. `123456789`)

**2c. Aktywuj bota:** wyszukaj bota po username → napisz `/start`

---

### KROK 3: Utwórz prywatne repozytorium GitHub

1. GitHub → **+** → **New repository** → ustaw **Private**
2. **NIE** zaznaczaj "Initialize repository"

---

### KROK 4: Wgraj kod

```bash
git clone https://github.com/TWOJA_NAZWA/betting-system.git
cd betting-system
# Skopiuj wszystkie pliki projektu tutaj
git add .
git commit -m "feat: v1.5 initial setup"
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

> ⚠️ Nigdy nie wpisuj kluczy bezpośrednio w kod!

---

### KROK 6: Pierwsze uruchomienie

```
Actions → "Daily Data Fetch" → Run workflow   (czekaj ~3-5 min)
Actions → "Weekly Retrain"   → Run workflow   (czekaj ~5-10 min)
Actions → "Generate Coupons" → Run workflow   (sprawdź Telegram po ~2 min)
```

---

### KROK 7: Weryfikacja

W logach Actions sprawdź:
- ✅ Dane pobrane (X meczów historycznych, deduplikacja OK)
- ✅ Elo obliczone dla X drużyn w Y ligach (osobno per liga)
- ✅ Model wytrenowany (accuracy > baseline ~45%)
- ✅ Feature importance zalogowane (top-8 cech)
- ✅ Calibration plot zapisany do data/model/calibration.png
- ✅ Value bety znalezione
- ✅ Kupony wysłane na Telegram

---

## Harmonogram

| Dzień | Godzina UTC | Akcja |
|-------|-------------|-------|
| Pon–Niedz | 06:00 | Pobierz dane + kursy |
| Poniedziałek | 05:00 | Retrenuj model + statystyki ROI |
| Środa | 09:00 | Generuj kupony (mecze środkowe) |
| Piątek | 09:00 | Generuj kupony (mecze weekendowe) |
| Co godzinę | — | Bot: komendy + auto-rozliczanie |

> UTC → dodaj +1h (CET) lub +2h (CEST latem)

**Concurrency:** wszystkie joby współdzielą grupę `data-write` — drugi job czeka
na zakończenie pierwszego zamiast powodować konflikt git push.

---

## Śledzenie finansów i komendy Telegram

### Dwa niezależne systemy ROI

**Model ROI** (`/stats`) — jakość predykcji modelu. Kupony auto-rozliczane przez
The Odds API. Używa sugerowanych stawek Kelly. Niezależny od gracza.

**Player ROI** (`/balance`) — Twój rzeczywisty P&L. Stawki i wypłaty per kupon,
wprowadzane ręcznie przez /stake i /won.

### Przepływ

```
1. Śr/Pt: bot wysyła kupony z numerami (#1, #2, #3...)
   → /stake 1 100   postaw 100 PLN na kupon #1
   → /stake 2 50    postaw 50 PLN na kupon #2
   → /stake 3 0     nie gram na kupon #3

2. Mecze rozgrywają się → bot AUTO-ROZLICZA Model ROI przez API
   (days_back dynamiczny — działa nawet po >7 dniach przerwy Actions)

3. Gdy wiesz wynik u swojego bukmachera:
   → /won 1 350     kupon #1 wygrał, dostałem 350 PLN
   → /lost 2        kupon #2 przegrał

4. /balance  → Twój rzeczywisty P&L
   /stats    → Model ROI (jakość predykcji)
```

### Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| `/help` | Lista komend | `/help` |
| `/stats` | Model ROI | `/stats` |
| `/balance` | Player ROI (Twój P&L) | `/balance` |
| `/pending` | Kupony czekające na wynik | `/pending` |
| `/setbalance X` | Ustaw punkt startowy | `/setbalance -1500` |
| `/stake [nr] X` | Zaloguj stawkę | `/stake 1 100` |
| `/won [nr] X` | Kupon wygrany | `/won 1 350` |
| `/lost [nr]` | Kupon przegrany | `/lost 2` |

---

## Zarządzanie bankrollem

**Zasady:**
1. Nigdy nie stawiaj więcej niż sugeruje Kelly — to górna granica, nie cel
2. Bankroll = odłożona kwota — nie używaj pieniędzy potrzebnych do życia
3. Zacznij od małych stawek — weryfikuj system przez 50+ zakładów
4. Co miesiąc analizuj ROI

**Kiedy zatrzymać:**
- ROI < -15% po 50+ zakładach → sprawdź model
- Seria 10 przegranych z rzędu → sprawdź dane wejściowe
- Bukmacher ogranicza konto → zmień bukmachera

---

## Parametry modelu

| Parametr | Domyślnie | Znaczenie |
|----------|-----------|-----------|
| `FORM_WINDOW` | 8 | Ostatnie N meczów do formy |
| `FORM_HALFLIFE_DAYS` | 21 | Półokres zaniku wagi formy [dni] |
| `ELO_START` | 1500 | Startowy Elo dla nowych drużyn |
| `ELO_K` | 20 | Współczynnik K Elo (standard piłka nożna) |
| `MIN_EDGE` | 0.05 | Min przewaga 5% |
| `MIN_MODEL_PROB` | 0.40 | Min pewność modelu dla 1X2 |
| `DC_MIN_MODEL_PROB` | 0.55 | Min pewność dla double chance |
| `KELLY_FRACTION` | 0.25 | Agresywność stawek |
| `MAX_BET_PCT` | 0.03 | Max 3% bankrollu na kupon |
| `MIN_ODDS` | 1.50 | Min kurs 1X2 |
| `MAX_ODDS` | 3.20 | Max kurs 1X2 |
| `DC_MIN_ODDS` | 1.20 | Min kurs double chance |
| `DC_MAX_ODDS` | 2.00 | Max kurs double chance |

---

## Mapa plików

```
betting_system/
│
├── main.py                     ← Orkiestrator. Tryby: fetch|train|coupon|stats|bot|full
├── config.py                   ← Wszystkie parametry. SEASONS dynamiczne (nie hardcoded).
├── requirements.txt
│
├── pipeline/
│   ├── api_utils.py            ← Multi-key API, auto-fallback przy 401/402/429
│   ├── fetch_stats.py          ← CSV z football-data.co.uk + deduplikacja po concat
│   ├── fetch_odds.py           ← Kursy z The Odds API (h2h)
│   └── name_mapping.py         ← Mapowanie nazw + fuzzy matching + guard na None
│
├── model/
│   ├── features.py             ← 18 cech, walk-forward, Elo PER LIGA (v1.5)
│   ├── train.py                ← XGBoost + Platt (temporal cv='prefit'), feature importance
│   ├── predict.py              ← Predykcje dla nadchodzących meczów
│   └── evaluate.py             ← Model ROI (poprawiony), auto-resolve (dynamiczny days_back)
│
├── coupon/
│   ├── value_engine.py         ← Value bety 1X2 + double chance
│   ├── kelly.py                ← Frakcjonalne Kelly, guard odds<=1.0, poprawiony parlay
│   └── builder.py              ← Singiel/podwójny/potrójny
│
├── notify/
│   ├── telegram.py             ← send_message(), formatowanie kuponów
│   ├── finance.py              ← Player ROI, per-kupon, poprawiony pending
│   └── bot_handler.py          ← Polling, komendy, auto-resolve
│
├── tests/
│   └── test_kelly.py           ← 33 testy jednostkowe (kelly, remove_margin,
│                                  leg_won, normalize, parse_coupon_nr)
│
└── .github/workflows/
    ├── daily_fetch.yml         ← concurrency: data-write
    ├── coupon_gen.yml          ← concurrency: data-write
    ├── weekly_retrain.yml      ← concurrency: data-write
    └── bot_polling.yml         ← concurrency: data-write
```

---

## Historia wersji

### v1.5 ✅ (obecna) — Poprawki krytyczne + jakość ML

**Błędy krytyczne naprawione:**
- `evaluate.py` — Model ROI liczony na stawkach WON+LOST per kupon (nie proporcja całości)
- `train.py` — `_simulate_roi()`: poprawiony wzór kursu bukmachera (`fair_odds / 1.05`)
- `finance.py` — `pending_player_coupons`: naprawiony błąd domknięcia zmiennej `cid`, wynik w return dict
- `kelly.py` — guard na `odds <= 1.0` (poprzednio dawał błędne Kelly dla kursu 0)

**Błędy średnie naprawione:**
- `train.py` — kalibracja Platta z temporal split `cv='prefit'` (brak data leakage)
- `evaluate.py` — dynamiczny `days_back` (max 14 dni) zamiast hardcoded 7
- `fetch_stats.py` — deduplikacja `drop_duplicates()` po concat
- `coupon/kelly.py` — `parlay_stake`: dzielnik `len(individual)` nie `len(legs)`
- `name_mapping.py` — guard `if not name: return ""` (brak crashu na None)
- `.github/workflows/*.yml` — concurrency groups (brak race condition)

**Nowe funkcje:**
- `model/features.py` — Elo per liga (osobna skala, brak cross-league noise)
- `model/train.py` — logowanie feature importance top-8 przy każdym retreningu
- `config.py` — SEASONS obliczane dynamicznie z daty (koniec hardcoded listy)
- `tests/test_kelly.py` — 33 testy jednostkowe (wszystkie przechodzą)

### v1.4 ✅
Auto-rozliczanie kuponów, Player ROI, per-kupon komendy, publiczne `send_message()`.

### v1.3 ✅
Forma ważona czasowo, Elo rating (cross-liga), calibration plot, FORM_WINDOW=8.

### v1.2 ✅
3 klucze API, double chance markets (1X, X2, 12), kupony oczekujące.

### v1.1 ✅
Strzały celne HST/AST, fuzzy matching name_mapping.

### v1.0 ✅
Fundament: 5 lig, XGBoost+Platt, value engine, Kelly, Telegram, GitHub Actions.

---

## Plan rozwoju

### v1.6 — Model + CLV
**Priorytet: wysoki**

- [ ] CLV tracking — zapisuj kursy w momencie generowania kuponu,
      porównuj z closing odds 24h przed meczem (The Odds API historical endpoint).
      CLV to jedyna obiektywna miara czy model ma prawdziwy edge.
- [ ] Hyperparameter tuning (Optuna, n_trials=100) z expanding window CV
      (nie single split — inaczej tuning daje false confidence)
- [ ] `class_weight={'H': 1, 'D': 1.5, 'A': 1}` — poprawia kalibrację remisów
- [ ] Ensemble: XGBoost + LightGBM z **osobną kalibracją** każdego modelu
      przed uśrednieniem (uśrednianie nieskalibrowanych prob = błędne EV)

### v1.7 — Over/Under + lepsza selekcja
**Priorytet: średni**

- [ ] Totals market (over/under gole) — model Poissona, +1 req/liga
- [ ] CLV monitoring: alert gdy model traci edge (degradacja w czasie)
- [ ] Forma ważona osobno dla meczów domowych i wyjazdowych
- [ ] Elo z uwzględnieniem siły harmonogramu (SOS)

### v2.0 — Nowe sporty
**Priorytet: niski**

- [ ] Tenis ATP/WTA (dane: tennis-data.co.uk + Jeff Sackmann GitHub, oba free)
- [ ] Siatkówka PlusLiga
- [ ] NBA — tylko z dostępem do advanced stats (back-to-back, injuries)
- [ ] Przy dodaniu nowych sportów: Elo musi być per sport/liga (już gotowe w v1.5)

### v2.1 — Monitoring i UX
**Priorytet: niski**

- [ ] Dashboard GitHub Pages: wykres ROI, historia kuponów, CLV trend
- [ ] Cotygodniowy raport PDF na email

---

## Debug checklist

1. Actions → zielony checkmark?
2. Logi → szukaj `ERROR` lub `WARNING`
3. `data/raw/all_matches.csv` istnieje? Jeśli nie: `python main.py fetch`
4. `data/model/model.pkl` istnieje? Jeśli nie: `python main.py train`
5. `data/odds/odds_YYYY-MM-DD.json` z dzisiaj? Jeśli nie: `python main.py fetch`
6. GitHub Secrets → ODDS_API_KEY, TELEGRAM_*, BANKROLL ustawione?
7. BANKROLL > 0? System rzuci `ValueError` przy BANKROLL=0.
8. Telegram → `/start` do bota, potem `/help`
9. Logi "Wszystkie klucze wyczerpane"? → sprawdź limity 3 kont The Odds API
10. Kupony wciąż PENDING po >7 dniach? → `days_back` dynamiczny (max 14), sprawdź logi auto-resolve
11. Testy → `cd betting_system && BANKROLL=1000 python -m pytest tests/ -v`

---

## Typowe błędy

| Błąd w logach | Przyczyna | Rozwiązanie |
|---------------|-----------|-------------|
| `Brak kluczy API` | Secret nie ustawiony | GitHub → Settings → Secrets |
| `Wszystkie klucze wyczerpane` | Limit 3 kont | Poczekaj do resetu miesiąca |
| `Za mało danych < 200` | Pierwsze uruchomienie | `python main.py fetch` → `train` |
| `Brak value betów` | Model konserwatywny | Obniż `MIN_EDGE` do 0.04 |
| `model.pkl not found` | Nie wytrenowany | `python main.py train` |
| `Brak mapowania: X` | Nowa drużyna | Dodaj do `name_mapping.py → TEAM_MAP` |
| `Bot nie odpowiada` | Zły token/chat ID | Sprawdź Secrets, `/start` do bota |
| `error: failed to push` | Race condition | Sprawdź czy concurrency w yml ustawione |

---

## Ważne zastrzeżenia

System generuje sugestie zakładów wyłącznie na potrzeby własne właściciela.
Nie jest to usługa doradztwa finansowego ani bukmacherska.
Stawiaj wyłącznie w legalnych, licencjonowanych serwisach (w Polsce: licencja MF).

Hazard może uzależniać. Graj odpowiedzialnie.
Pomoc: **www.uzaleznienia.info** | Infolinia: **801 889 880**
