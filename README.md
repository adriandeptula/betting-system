# 🤖 AI Betting System – v1.1

System automatyczny do generowania value betów oparty na XGBoost + kalibracji Platta.
Działa w 100% na GitHub Actions. Koszt: **0 zł/miesiąc**.

---

## Spis treści

1. [Jak to działa](#jak-to-działa)
2. [Krok po kroku: pierwsze uruchomienie](#krok-po-kroku-pierwsze-uruchomienie)
3. [Harmonogram działania](#harmonogram-działania)
4. [Zarządzanie bankrollem](#zarządzanie-bankrollem)
5. [Plan rozwoju](#plan-rozwoju)

---

## Jak to działa

```
Co tydzień automatycznie:

PON  05:00 → Pobierz świeże dane → Retrenuj model → Wyślij statystyki ROI
CZW  06:00 → Pobierz dane (wyniki + kursy + kontuzje)
PT   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
ŚR   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
```

**Źródła danych:**
- football-data.co.uk – historyczne wyniki 5 lig (EPL, Bundesliga, La Liga, Serie A, Ekstraklasa)
- The Odds API – aktualne kursy z ~40 bukmacherów europejskich
- API-Football *(v1.1, opcjonalne)* – kontuzje i zawieszenia graczy

**Model:** XGBoost z kalibracją Platta (3 klasy: H/D/A)

**Nowe cechy v1.1:** strzały celne (HST/AST), wskaźnik kontuzji drużyny

**Stawki:** Frakcjonalne kryterium Kelly (25% pełnego Kelly)

**Klucze API:** każde API obsługuje 2 klucze z automatycznym przełączaniem gdy limit wyczerpany

---

## Krok po kroku: pierwsze uruchomienie

### KROK 1: Stwórz konto(a) na The Odds API

1. Wejdź na **https://the-odds-api.com**
2. Kliknij **Get API Key** → zarejestruj się
3. Skopiuj klucz API
4. **Opcjonalnie:** załóż drugie konto (inny email) i skopiuj drugi klucz

> Free tier: 500 requestów/miesiąc na konto. System używa ~60-90/miesiąc.
> Z 2 kontami masz 1000 req/miesiąc – pełna redundancja.
> Gdy pierwszy klucz się wyczerpie, system **automatycznie** przełączy się na drugi.

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

### KROK 3: *(Opcjonalne)* Stwórz konto(a) na API-Football

Kontuzje to opcjonalna funkcja v1.1. Bez tego klucza system działa normalnie,
tylko model nie uwzględnia niedostępnych graczy.

1. Wejdź na **https://www.api-football.com** (hostowane przez RapidAPI)
2. Kliknij **Subscribe** → wybierz plan **Free** (100 req/dzień)
3. Skopiuj klucz z zakładki **Security** → `X-RapidAPI-Key`
4. **Opcjonalnie:** zarejestruj drugie konto i skopiuj drugi klucz

> Free tier: 100 requestów/dzień. System używa ~10/dzień (1 req/liga).
> Z 2 kontami masz 200 req/dzień – pełna redundancja.

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
git commit -m "feat: v1.1 initial setup"
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
| `TELEGRAM_TOKEN` | token bota Telegram | ✅ Tak |
| `TELEGRAM_CHAT_ID` | Twój chat ID | ✅ Tak |
| `BANKROLL` | Twój bankroll w PLN, np. `1000` | ✅ Tak |
| `API_FOOTBALL_KEY` | klucz #1 z API-Football | ☑️ Opcjonalny |
| `API_FOOTBALL_KEY_2` | klucz #2 (drugie konto) | ☑️ Opcjonalny |

> ⚠️ Nigdy nie wpisuj kluczy bezpośrednio w kod! Tylko przez Secrets.

**Jak działa fallback kluczy:**
System próbuje klucz #1. Jeśli odpowiedź to HTTP 429/401/402 (limit wyczerpany),
automatycznie przełącza się na klucz #2. Żaden kupon nie zostanie pominięty.

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
- ✅ Value bety znalezione
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

> Godziny UTC → dodaj +1h (CET) lub +2h (CEST latem)

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

### v1.0 ✅ (poprzednia)
- 5 lig piłkarskich, XGBoost + Platt, value engine, kupony, Kelly, Telegram, GitHub Actions

### v1.1 ✅ (obecna)
- ✅ Integracja API-Football (kontuzje i zawieszenia)
- ✅ Nowe cechy modelu: strzały celne (HST/AST)
- ✅ Podwójne klucze API z automatycznym fallbackiem (The Odds API + API-Football)
- ✅ Fuzzy matching w name_mapping.py (rapidfuzz)

---

### v1.2 – Lepszy model
**Priorytet: średni | Szacowany czas: 2-3 tygodnie**

- [ ] Hyperparameter tuning (Optuna/RandomSearch)
- [ ] Ensemble: XGBoost + LightGBM + uśrednianie
- [ ] Feature: forma ważona (ostatnie mecze ważniejsze niż dawne)
- [ ] Feature: dysproporcja sił (ranking Elo drużyn)
- [ ] Osobny mini-model dla remisów
- [ ] Calibration plot – wizualizacja jakości kalibracji

---

### v1.3 – Lepsze kupony
**Priorytet: średni | Szacowany czas: 1 tydzień**

- [ ] Round-robin: z 4 value betów generuj wszystkie kombinacje 2-nożne
- [ ] Filtr: nie łącz meczów tej samej ligi w jednym parlaylu
- [ ] Filtr: nie łącz meczów z tej samej kolejki (korelacja wyników)
- [ ] Śledzenie Closing Line Value (CLV) jako metryki jakości modelu

---

### v2.0 – Nowe sporty
**Priorytet: niski | Szacowany czas: 4-6 tygodni**

- [ ] Tenis ATP/WTA (dane: Jeff Sackmann GitHub, darmowe)
- [ ] NBA / Koszykówka (dane: basketball-reference.com)
- [ ] Siatkówka PlusLiga (dane: volleyball.pl)

---

### v2.1 – Monitoring i UX
**Priorytet: niski | Szacowany czas: 1-2 tygodnie**

- [ ] Dashboard webowy (prosty HTML w GitHub Pages): wykres ROI, historia kuponów
- [ ] Powiadomienie gdy model traci edge (degradacja)
- [ ] Tygodniowy raport PDF wysyłany na email
- [ ] Komenda Telegram: `/stats` → natychmiastowe statystyki (już jest, ale bez historii graficznej)

---

## Ważne zastrzeżenia prawne

System generuje sugestie zakładów wyłącznie na potrzeby własne właściciela.
Nie jest to usługa doradztwa finansowego ani bukmacherska.
Stawiaj wyłącznie w legalnych, licencjonowanych serwisach.
W Polsce legalni bukmacherzy posiadają licencję Ministra Finansów.

Hazard może uzależniać. Graj odpowiedzialnie.
Pomoc: **www.uzaleznienia.info** | Infolinia: **801 889 880**
