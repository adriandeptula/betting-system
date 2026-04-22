# 🤖 AI Betting System – v1.2

System automatyczny do generowania value betów oparty na XGBoost + kalibracji Platta.
Działa w 100% na GitHub Actions. Koszt: **0 zł/miesiąc**.

---

## Spis treści

1. [Jak to działa](#jak-to-działa)
2. [Krok po kroku: pierwsze uruchomienie](#krok-po-kroku-pierwsze-uruchomienie)
3. [Harmonogram działania](#harmonogram-działania)
4. [Śledzenie finansów i kupony Telegram](#śledzenie-finansów-i-kupony-telegram)
5. [Zarządzanie bankrollem](#zarządzanie-bankrollem)
6. [Plan rozwoju](#plan-rozwoju)

---

## Jak to działa

```
Co tydzień automatycznie:

PON  05:00 → Pobierz świeże dane → Retrenuj model → Wyślij statystyki ROI
COD  06:00 → Pobierz dane (wyniki + kursy + kontuzje)
ŚR   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
PT   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
CO H 00:00 → Bot sprawdza komendy Telegram i odpowiada
```

**Źródła danych:**
- football-data.co.uk – historyczne wyniki 5 lig (EPL, Bundesliga, La Liga, Serie A, Ekstraklasa)
- The Odds API – aktualne kursy z ~40 bukmacherów europejskich
- API-Football *(opcjonalne)* – kontuzje i zawieszenia graczy

**Model:** XGBoost z kalibracją Platta (3 klasy: H/D/A)

**Cechy modelu:** forma (pkt/gole/strzały celne), H2H, kursy rynkowe (fair prob), wskaźnik kontuzji drużyny

**Obsługiwane typy zakładów:**
- **1X2** – wygrana gospodarza / remis / wygrana gościa
- **Double chance** – 1X (gospodarz lub remis), X2 (remis lub gość), 12 (gospodarz lub gość bez remisu)
  *(wyprowadzane z kursów h2h — zero dodatkowych requestów API)*

**Stawki:** Frakcjonalne kryterium Kelly (25% pełnego Kelly)

**Klucze API:** każde API obsługuje **3 klucze** z automatycznym przełączaniem gdy limit wyczerpany

---

## Krok po kroku: pierwsze uruchomienie

### KROK 1: Stwórz konta na The Odds API

1. Wejdź na **https://the-odds-api.com**
2. Kliknij **Get API Key** → zarejestruj się
3. Skopiuj klucz API
4. **Zalecane:** załóż drugie i trzecie konto (różne emaile) i skopiuj klucze

> Free tier: 500 requestów/miesiąc na konto. System używa ~200/miesiąc.
> Z 3 kontami masz **1500 req/miesiąc** — pełna redundancja z zapasem na rozbudowę.
> Gdy klucz #1 się wyczerpie, system **automatycznie** przełączy się na #2, potem #3.

---

### KROK 2: Stwórz bota Telegram

**2a. Utwórz bota:**
1. Otwórz Telegram, wyszukaj **@BotFather**
2. Napisz `/newbot`
3. Podaj nazwę bota (np. `Mój Betting Bot`)
4. Podaj username bota (musi kończyć się na `bot`, np. `mojbettingbot`)
5. BotFather wyśle Ci **TOKEN** – długi ciąg jak `7123456789:AAHxxx...`
6. **Skopiuj i zachowaj token**

**2b. Pobierz swój Chat ID:**
1. Wyszukaj **@userinfobot** w Telegram
2. Napisz do niego `/start`
3. Wyśle Ci Twoje **ID** (liczba, np. `123456789`)
4. **Skopiuj i zachowaj ID**

**2c. Aktywuj bota:**
1. Wyszukaj swojego nowego bota po username
2. Napisz `/start`

---

### KROK 3: *(Opcjonalne)* Stwórz konta na API-Football

Kontuzje to opcjonalna funkcja. Bez tego klucza system działa normalnie,
tylko model nie uwzględnia niedostępnych graczy.

**Rejestracja bezpośrednia na api-sports.io (zalecana):**

1. Wejdź na **https://dashboard.api-football.com** (api-sports.io – bezpośrednio, nie przez RapidAPI)
2. Kliknij **Register** → zarejestruj się
3. Po zalogowaniu wejdź w **My Account** → skopiuj wartość pola **API Key**
4. **Zalecane:** zarejestruj drugie i trzecie konto (różne emaile) i skopiuj klucze

> ⚠️ **Nie rejestruj się przez RapidAPI** – system używa nagłówka `x-apisports-key`
> charakterystycznego dla bezpośredniej rejestracji. Klucze z RapidAPI (`X-RapidAPI-Key`)
> wymagałyby zmiany w kodzie (`fetch_injuries.py`).

> Free tier: 100 requestów/dzień na konto. System używa ~5 req/dzień (1 req/liga).
> Z 3 kontami masz **300 req/dzień** — wystarczy na dalszą rozbudowę o kolejne ligi.

---

### KROK 4: Utwórz prywatne repozytorium GitHub

1. Zaloguj się na **https://github.com**
2. Kliknij **+** → **New repository**
3. Nazwa: `betting-system` (lub dowolna)
4. Ustaw **Private** (ważne!)
5. **NIE** zaznaczaj "Initialize repository"
6. Kliknij **Create repository**

---

### KROK 5: Wgraj kod do repozytorium

```bash
git clone https://github.com/TWOJA_NAZWA/betting-system.git
cd betting-system
# Skopiuj wszystkie pliki projektu tutaj
git add .
git commit -m "feat: v1.2 initial setup"
git push origin main
```

---

### KROK 6: Ustaw GitHub Secrets (klucze API)

1. Wejdź na stronę repo → **Settings** → **Secrets and variables** → **Actions**
2. Kliknij **New repository secret** dla każdego poniżej:

| Nazwa | Wartość | Wymagany |
|-------|---------|---------|
| `ODDS_API_KEY` | klucz #1 z The Odds API | ✅ Tak |
| `ODDS_API_KEY_2` | klucz #2 (drugie konto) | ⚡ Zalecany |
| `ODDS_API_KEY_3` | klucz #3 (trzecie konto) | ⚡ Zalecany |
| `TELEGRAM_TOKEN` | token bota Telegram | ✅ Tak |
| `TELEGRAM_CHAT_ID` | Twój chat ID | ✅ Tak |
| `BANKROLL` | Twój bankroll w PLN, np. `1000` | ✅ Tak |
| `API_FOOTBALL_KEY` | klucz #1 z API-Football | ☑️ Opcjonalny |
| `API_FOOTBALL_KEY_2` | klucz #2 (drugie konto) | ☑️ Opcjonalny |
| `API_FOOTBALL_KEY_3` | klucz #3 (trzecie konto) | ☑️ Opcjonalny |

> ⚠️ Nigdy nie wpisuj kluczy bezpośrednio w kod! Tylko przez Secrets.

**Jak działa fallback kluczy:**
System próbuje klucz #1. Jeśli odpowiedź to HTTP 429/401/402 (limit wyczerpany),
automatycznie przełącza się na #2, potem #3. Żaden kupon nie zostanie pominięty.

---

### KROK 7: Pierwsze uruchomienie

**7a. Pobierz dane historyczne:**
1. W repo: zakładka **Actions**
2. Wybierz workflow **"Daily Data Fetch"**
3. Kliknij **"Run workflow"** → **"Run workflow"**
4. Poczekaj ~3-5 minut

**7b. Wytrenuj model:**
1. Wybierz workflow **"Weekly Retrain"**
2. Kliknij **"Run workflow"**
3. Poczekaj ~5-10 minut

**7c. Pierwsze kupony:**
1. Wybierz workflow **"Generate Coupons"**
2. Kliknij **"Run workflow"**
3. Po ~2 minutach sprawdź Telegram!

---

### KROK 8: Weryfikacja

Sprawdź w logach Actions czy:
- ✅ Dane pobrane (X meczów historycznych)
- ✅ Kontuzje pobrane (lub pominięte gdy brak klucza API-Football)
- ✅ Model wytrenowany (accuracy > baseline)
- ✅ Value bety znalezione (w tym ewentualnie double chance)
- ✅ Kupony wysłane na Telegram

Jeśli coś nie gra → sprawdź sekcję **Typowe błędy** w CLAUDE.md.

---

## Harmonogram działania

| Dzień | Godzina (UTC) | Akcja |
|-------|---------------|-------|
| Pon–Niedz | 06:00 | Pobierz dane + kursy + kontuzje |
| Poniedziałek | 05:00 | Retrenuj model + wyślij statystyki ROI |
| Środa | 09:00 | Generuj kupony (mecze środkotygodniowe) |
| Piątek | 09:00 | Generuj kupony (mecze weekendowe) |
| Co godzinę | — | Bot sprawdza komendy Telegram |

> Godziny UTC → dodaj +1h (CET) lub +2h (CEST latem)

---

## Śledzenie finansów i kupony Telegram

### Jak działa tracking P&L

Po otrzymaniu kuponów na Telegram typowy przepływ wygląda tak:

```
1. Środa/Piątek: bot wysyła kupony → pyta "Ile wpłaciłeś?" → wpisz /stake 100
2. Mecze rozgrywają się przez 1-3 dni
3. Poniedziałek: bot pyta "Wygrałeś?" → /won 350 lub /lost
4. /balance pokazuje aktualny całościowy wynik
```

Po wpisaniu `/stake` status finansowy pokazuje również **kupony oczekujące** – dzięki temu wyświetlana „strata" jest zawsze w kontekście kwot wciąż w grze:

```
⏳ Kupony oczekujące: 2
  🎲 Łączna stawka:       50 PLN
  🏆 Potencjalny zwrot:  187 PLN
  (wynik powyżej nie uwzględnia kuponów w grze)

📉 CAŁOŚCIOWY WYNIK: -50 PLN
📊 Zakres z uwzgl. kuponów:
  Worst: -100 PLN | Best: +137 PLN
```

### Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| `/help` | Lista wszystkich komend | `/help` |
| `/stats` | ROI i historia kuponów | `/stats` |
| `/balance` | Pełny status finansowy P&L z oczekującymi | `/balance` |
| `/setbalance X` | Ustaw punkt startowy (może być ujemny) | `/setbalance -1500` |
| `/stake X` | Zaloguj wpłatę na zakłady | `/stake 100` |
| `/payout X` | Zaloguj wypłatę wygranej | `/payout 500` |
| `/won X` | Kupon wygrany + kwota wypłaty | `/won 350` |
| `/lost` | Kupon przegrany | `/lost` |

> Komendy są przetwarzane co godzinę (bot_polling.yml), nie natychmiastowo.

### Uwaga o zaokrągleniach

Stawki Kelly są zaokrąglane do 5 PLN w sugestiach kuponów. Jeśli wpisujesz do `/stake` własną kwotę (np. `/stake 12.64`), system zapisuje dokładną wartość float i sumuje precyzyjnie – wyświetlanie jest zaokrąglone do pełnych PLN wyłącznie wizualnie.

---

## Zarządzanie bankrollem

### Zasady których należy przestrzegać

1. **Nigdy nie stawiaj więcej niż sugeruje Kelly** – to górna granica, nie cel
2. **Bankroll = odłożona kwota** – nie używaj pieniędzy potrzebnych do życia
3. **Skala stopniowo** – zacznij od małych stawek, sprawdź czy system działa
4. **Śledź wyniki** – co miesiąc analizuj ROI, przy -15% zatrzymaj się

### Przykładowe stawki przy bankrollu 1000 PLN

| Typ kuponu | Kelly sugeruje | Realna stawka |
|------------|---------------|---------------|
| Singiel (mocny) | 30-50 PLN | 20-30 PLN |
| Podwójny | 20-35 PLN | 15-20 PLN |
| Potrójny | 15-25 PLN | 10-15 PLN |

### Kiedy zatrzymać system

- ROI < -15% po 50+ zakładach = zatrzymaj, sprawdź model
- Seria 10 przegranych kuponów z rzędu = sprawdź dane wejściowe
- Bukmacher ogranicza konto = zmień bukmachera lub strategię

---

## Plan Rozwoju

### v1.0 ✅
- 5 lig piłkarskich, XGBoost + Platt, value engine, kupony, Kelly, Telegram, GitHub Actions

### v1.1 ✅
- ✅ Integracja API-Football (kontuzje i zawieszenia jako cecha modelu)
- ✅ Nowe cechy modelu: strzały celne (HST/AST)
- ✅ Podwójne klucze API z automatycznym fallbackiem
- ✅ Fuzzy matching w name_mapping.py (rapidfuzz)
- ✅ Status finansowy pokazuje kupony oczekujące (zakres worst/best case)

### v1.2 ✅ (obecna)
- ✅ **3 klucze API** dla The Odds API i API-Football (1500 req/mies. + 300 req/dzień)
- ✅ **Double chance markets** (1X, X2, 12) — wyprowadzane z h2h, zero nowych requestów
  - Osobny zakres kursów: DC_MIN_ODDS=1.20, DC_MAX_ODDS=2.00
  - Wyższy próg pewności modelu: DC_MIN_MODEL_PROB=0.55
  - Nowe emoji w kuponach Telegram: 🏠🤝 / 🤝✈️ / 🏠✈️

---

### v1.3 – Lepszy model
**Priorytet: wysoki | Szacowany czas: 2-3 tygodnie**

- [ ] Hyperparameter tuning (Optuna/RandomSearch)
- [ ] Ensemble: XGBoost + LightGBM + uśrednianie
- [ ] Feature: forma ważona wagą czasową (ostatnie mecze ważniejsze)
- [ ] Feature: ranking Elo drużyn
- [ ] Osobny mini-model dla remisów
- [ ] Calibration plot – wizualizacja jakości kalibracji

---

### v1.4 – Lepsze kupony i over/under
**Priorytet: średni | Szacowany czas: 1-2 tygodnie**

- [ ] Over/Under gole (totals) — wymaga osobnego modelu regresji sumy goli
- [ ] Round-robin: z 4 value betów generuj wszystkie kombinacje 2-nożne
- [ ] Filtr: nie łącz meczów tej samej ligi w jednym parlaylu
- [ ] Śledzenie Closing Line Value (CLV) jako metryki jakości modelu
- [ ] Automatyczne rozliczanie wyników przez The Odds API scores

---

### v2.0 – Nowe sporty
**Priorytet: niski | Szacowany czas: 4-6 tygodni**

- [ ] Tenis ATP/WTA – źródło danych do ustalenia (Tennis Abstract API lub sofascore; Jeff Sackmann GitHub nieaktualne w 2026)
- [ ] NBA / Koszykówka (dane: basketball-reference.com)
- [ ] Siatkówka PlusLiga (dane: volleyball.pl)

---

### v2.1 – Monitoring i UX
**Priorytet: niski | Szacowany czas: 1-2 tygodnie**

- [ ] Dashboard webowy (prosty HTML w GitHub Pages): wykres ROI, historia kuponów
- [ ] Powiadomienie gdy model traci edge (degradacja)
- [ ] Tygodniowy raport PDF wysyłany na email
- [ ] API-Football premium (7500 req/mies.) — rozważyć przy v2.0+ gdy więcej lig/sportów; na etapie v1.x darmowy tier (100 req/dzień × 3 konta) w zupełności wystarczy

---

## Ważne zastrzeżenia prawne

System generuje sugestie zakładów wyłącznie na potrzeby własne właściciela.
Nie jest to usługa doradztwa finansowego ani bukmacherska.
Stawiaj wyłącznie w legalnych, licencjonowanych serwisach.
W Polsce legalni bukmacherzy posiadają licencję Ministra Finansów.

Hazard może uzależniać. Graj odpowiedzialnie.
Pomoc: **www.uzaleznienia.info** | Infolinia: **801 889 880**
