# 🤖 AI Betting System

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
CZW  06:00 → Pobierz dane
PT   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
ŚR   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
```

**Źródła danych:**
- football-data.co.uk – historyczne wyniki 5 lig (EPL, Bundesliga, La Liga, Serie A, Ekstraklasa)
- The Odds API – aktualne kursy z ~40 bukmacherów europejskich

**Model:** XGBoost z kalibracją Platta (3 klasy: H/D/A)

**Stawki:** Frakcjonalne kryterium Kelly (25% pełnego Kelly)

---

## Krok po kroku: pierwsze uruchomienie

### KROK 1: Stwórz konto na The Odds API

1. Wejdź na **https://the-odds-api.com**
2. Kliknij **Get API Key** → zarejestruj się
3. Skopiuj klucz API (długi ciąg znaków)
4. **Zachowaj** – będzie potrzebny w Kroku 4

> Free tier: 500 requestów/miesiąc. System używa ~60-90/miesiąc. Wystarczy w zupełności.

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
3. Od teraz bot może Ci wysyłać wiadomości

---

### KROK 3: Utwórz prywatne repozytorium GitHub

1. Zaloguj się na **https://github.com**
2. Kliknij **+** → **New repository**
3. Nazwa: `betting-system` (lub dowolna)
4. Ustaw **Private** (ważne! repo musi być prywatne)
5. **NIE** zaznaczaj "Initialize repository"
6. Kliknij **Create repository**

---

### KROK 4: Wgraj kod do repozytorium

Otwórz terminal na swoim komputerze:

```bash
# Klonuj puste repo
git clone https://github.com/TWOJA_NAZWA/betting-system.git
cd betting-system

# Wgraj wszystkie pliki projektu do tego katalogu
# (skopiuj zawartość betting_system/ tutaj)

# Pierwsza wersja commitów
git add .
git commit -m "feat: initial system setup"
git push origin main
```

---

### KROK 5: Ustaw GitHub Secrets (klucze API)

1. Wejdź na stronę swojego repo na GitHub
2. Kliknij **Settings** (górny pasek)
3. W lewym menu: **Secrets and variables** → **Actions**
4. Kliknij **New repository secret** dla każdego poniżej:

| Nazwa | Wartość |
|-------|---------|
| `ODDS_API_KEY` | klucz z Kroku 1 |
| `TELEGRAM_TOKEN` | token z Kroku 2a |
| `TELEGRAM_CHAT_ID` | ID z Kroku 2b |
| `BANKROLL` | Twój bankroll w PLN, np. `1000` |

> ⚠️ Nigdy nie wpisuj kluczy bezpośrednio w kod!

---

### KROK 6: Pierwsze uruchomienie – pobierz dane i wytrenuj model

GitHub Actions nie uruchomi się automatycznie na początku.
Musisz ręcznie uruchomić pipeline pierwszy raz:

**6a. Pobierz dane historyczne:**
1. W repo: zakładka **Actions**
2. Wybierz workflow **"Daily Data Fetch"**
3. Kliknij **"Run workflow"** → **"Run workflow"**
4. Poczekaj ~3-5 minut na zakończenie (zielony checkmark)

**6b. Wytrenuj model:**
1. W repo: zakładka **Actions**
2. Wybierz workflow **"Weekly Retrain"**
3. Kliknij **"Run workflow"** → **"Run workflow"**
4. Poczekaj ~5-10 minut

> Po sukcesie model.pkl pojawi się w `data/model/` w repo.

---

### KROK 7: Pierwsze kupony

1. W repo: zakładka **Actions**
2. Wybierz workflow **"Generate Coupons"**
3. Kliknij **"Run workflow"** → **"Run workflow"**
4. Po ~2 minutach sprawdź Telegram!

Jeśli dostałeś wiadomości na Telegram – **system działa**. 🎉

---

### KROK 8: Weryfikacja systemu

Sprawdź w logach Actions czy:
- ✅ Dane pobrane (X meczów historycznych)
- ✅ Model wytrenowany (accuracy > baseline)
- ✅ ROI symulacji > 0%
- ✅ Value bety znalezione
- ✅ Kupony wysłane na Telegram

Jeśli coś nie gra → sprawdź sekcję **Typowe błędy** w CLAUDE.md.

---

## Harmonogram działania

| Dzień | Godzina (UTC) | Akcja |
|-------|---------------|-------|
| Pon–Niedz | 06:00 | Pobierz dane + aktualne kursy |
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

### v1.0 – Obecna wersja ✅
- 5 lig piłkarskich (EPL, Bundesliga, La Liga, Serie A, Ekstraklasa)
- Model XGBoost + kalibracja Platta
- Value engine z filtrem edge/odds
- Kupony: singiel / podwójny / potrójny
- Stawki Kelly (frakcjonalne)
- Wysyłka na Telegram
- GitHub Actions (całkowicie darmowe)

---

### v1.1 – Poprawa jakości danych
**Priorytet: wysoki | Szacowany czas: 1-2 tygodnie**

- [ ] Integracja API-Football (kontuzje, składy, linia)
  - Klucz: darmowy tier = 100 req/dzień
  - Wpływ: model zyska 2-5% dokładności na meczach z kontuzjami gwiazd
- [ ] Rozszerzenie name_mapping.py o automatyczne fuzzy matching z logowaniem
- [ ] Dodanie strzałów na bramkę (HST/AST) jako feature
- [ ] Obsługa brakujących kursów remisu (fallback 3.50)

---

### v1.2 – Lepszy model
**Priorytet: średni | Szacowany czas: 2-3 tygodnie**

- [ ] Hyperparameter tuning (Optuna/RandomSearch)
- [ ] Ensemble: XGBoost + LightGBM + uśrednianie
- [ ] Feature: forma ważona (ostatnie mecze ważniejsze niż dawne)
- [ ] Feature: dysproporcja sił (ranking Elo drużyn)
- [ ] Osobny mini-model dla remisów (trudne, ale wartościowe)
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

- [ ] **Tenis ATP/WTA**
  - Dane: Jeff Sackmann (GitHub, darmowe)
  - Cechy: ranking, forma na nawierzchni, H2H
  - Setki meczów tygodniowo = dużo okazji
- [ ] **NBA / Koszykówka**
  - Dane: basketball-reference.com
  - Cechy: pace, eFG%, rest days, back-to-back
- [ ] **Siatkówka PlusLiga**
  - Dane: volleyball.pl (scraping)
  - Polskie ligi = potencjalnie linia bukmacherów słabsza

---

### v2.1 – Monitoring i UX
**Priorytet: niski | Szacowany czas: 1-2 tygodnie**

- [ ] Dashboard webowy (prosty HTML w GitHub Pages)
  - Wykres ROI w czasie
  - Historia kuponów
  - Aktualne statystyki
- [ ] Powiadomienie gdy model traci edge (degradacja)
- [ ] Tygodniowy raport PDF wysyłany na email
- [ ] Komenda Telegram: `/stats` → natychmiastowe statystyki

---

### v3.0 – Zaawansowane strategie
**Priorytet: bardzo niski | Szacowany czas: 2-3 miesiące**

- [ ] Porównanie kursów między bukmacherami (line shopping)
  - Wymaga: OddsPapi API lub scraping STS/forBET
- [ ] Detekcja arbitrażu (arb między bukmacherami)
- [ ] Model sieci neuronowej (LSTM na sekwencjach meczów)
- [ ] Live betting sygnały (wymaga płatnego API z WebSocket)

---

## Ważne zastrzeżenia prawne

System generuje sugestie zakładów wyłącznie na potrzeby własne właściciela.
Nie jest to usługa doradztwa finansowego ani bukmacherska.
Stawiaj wyłącznie w legalnych, licencjonowanych serwisach.
W Polsce legalni bukmacherzy posiadają licencję Ministra Finansów.

Hazard może uzależniać. Graj odpowiedzialnie.
Pomoc: **www.uzaleznienia.info** | Infolinia: **801 889 880**
