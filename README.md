# 🤖 AI Betting System – v1.3

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
COD  06:00 → Pobierz dane (wyniki + kursy)
ŚR   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
PT   09:00 → Generuj kupony → Wyślij na Telegram  ← TY DECYDUJESZ CZY STAWIAĆ
CO H 00:00 → Bot sprawdza komendy Telegram i odpowiada
```

**Źródła danych:**
- football-data.co.uk – historyczne wyniki 5 lig (EPL, Bundesliga, La Liga, Serie A, Ekstraklasa)
- The Odds API – aktualne kursy z ~40 bukmacherów europejskich

**Model:** XGBoost z kalibracją Platta (3 klasy: H/D/A)

**Cechy modelu (v1.3):**
- Forma ważona czasowo (wykładniczy zanik, nowsze mecze ważą więcej)
- Elo rating drużyn (liczony z pełnej historii meczów)
- Statystyki: gole, strzały celne, H2H
- Kursy rynkowe (fair probabilities po usunięciu marży)

**Obsługiwane typy zakładów:**
- **1X2** – wygrana gospodarza / remis / wygrana gościa
- **Double chance** – 1X, X2, 12 (wyprowadzane z kursów h2h – zero dodatkowych requestów)

**Stawki:** Frakcjonalne kryterium Kelly (25% pełnego Kelly)

**Klucze API:** The Odds API obsługuje **3 klucze** z automatycznym przełączaniem

**Uwaga o accuracy:** piłka nożna ma dużą losowość – nawet najlepsze modele osiągają
~54-58% accuracy dla 1X2. Wartość systemu leży w długoterminowym ROI z value betów,
nie w samej accuracy.

---

## Krok po kroku: pierwsze uruchomienie

### KROK 1: Stwórz konta na The Odds API

1. Wejdź na **https://the-odds-api.com**
2. Kliknij **Get API Key** → zarejestruj się
3. Skopiuj klucz API
4. **Zalecane:** załóż drugie i trzecie konto (różne emaile) i skopiuj klucze

> Free tier: 500 requestów/miesiąc na konto. System używa ~200/miesiąc.
> Z 3 kontami masz **1500 req/miesiąc** — pełna redundancja.

---

### KROK 2: Stwórz bota Telegram

**2a. Utwórz bota:**
1. Otwórz Telegram, wyszukaj **@BotFather**
2. Napisz `/newbot`
3. Podaj nazwę bota (np. `Mój Betting Bot`)
4. Podaj username bota (musi kończyć się na `bot`)
5. BotFather wyśle Ci **TOKEN** – skopiuj i zachowaj

**2b. Pobierz swój Chat ID:**
1. Wyszukaj **@userinfobot** w Telegram
2. Napisz `/start`
3. Wyśle Ci Twoje **ID** (liczba, np. `123456789`)

**2c. Aktywuj bota:**
1. Wyszukaj swojego nowego bota po username
2. Napisz `/start`

---

### KROK 3: Utwórz prywatne repozytorium GitHub

1. Zaloguj się na **https://github.com**
2. Kliknij **+** → **New repository**
3. Nazwa: `betting-system` (lub dowolna)
4. Ustaw **Private** (ważne!)
5. **NIE** zaznaczaj "Initialize repository"
6. Kliknij **Create repository**

---

### KROK 4: Wgraj kod do repozytorium

```bash
git clone https://github.com/TWOJA_NAZWA/betting-system.git
cd betting-system
# Skopiuj wszystkie pliki projektu tutaj
git add .
git commit -m "feat: v1.3 initial setup"
git push origin main
```

---

### KROK 5: Ustaw GitHub Secrets (klucze API)

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

> ⚠️ Nigdy nie wpisuj kluczy bezpośrednio w kod! Tylko przez Secrets.

---

### KROK 6: Pierwsze uruchomienie

**6a. Pobierz dane historyczne:**
1. W repo: zakładka **Actions**
2. Wybierz workflow **"Daily Data Fetch"**
3. Kliknij **"Run workflow"** → poczekaj ~3-5 minut

**6b. Wytrenuj model:**
1. Wybierz workflow **"Weekly Retrain"**
2. Kliknij **"Run workflow"** → poczekaj ~5-10 minut

**6c. Pierwsze kupony:**
1. Wybierz workflow **"Generate Coupons"**
2. Kliknij **"Run workflow"**
3. Po ~2 minutach sprawdź Telegram!

---

### KROK 7: Weryfikacja

Sprawdź w logach Actions czy:
- ✅ Dane pobrane (X meczów historycznych)
- ✅ Model wytrenowany (accuracy > baseline ~45%)
- ✅ Calibration plot zapisany do data/model/calibration.png
- ✅ Value bety znalezione
- ✅ Kupony wysłane na Telegram

---

## Harmonogram działania

| Dzień | Godzina (UTC) | Akcja |
|-------|---------------|-------|
| Pon–Niedz | 06:00 | Pobierz dane + kursy |
| Poniedziałek | 05:00 | Retrenuj model + wyślij statystyki ROI |
| Środa | 09:00 | Generuj kupony (mecze środkotygodniowe) |
| Piątek | 09:00 | Generuj kupony (mecze weekendowe) |
| Co godzinę | — | Bot sprawdza komendy Telegram |

> Godziny UTC → dodaj +1h (CET) lub +2h (CEST latem)

---

## Śledzenie finansów i kupony Telegram

### Jak działa tracking P&L

```
1. Środa/Piątek: bot wysyła kupony → pyta "Ile wpłaciłeś?" → wpisz /stake 100
2. Mecze rozgrywają się przez 1-3 dni
3. Poniedziałek: bot pyta "Wygrałeś?" → /won 350 lub /lost
4. /balance pokazuje aktualny całościowy wynik
```

### Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| `/help` | Lista wszystkich komend | `/help` |
| `/stats` | ROI i historia kuponów | `/stats` |
| `/balance` | Pełny status finansowy P&L | `/balance` |
| `/setbalance X` | Ustaw punkt startowy | `/setbalance -1500` |
| `/stake X` | Zaloguj wpłatę na zakłady | `/stake 100` |
| `/payout X` | Zaloguj wypłatę wygranej | `/payout 500` |
| `/won X` | Kupon wygrany + kwota wypłaty | `/won 350` |
| `/lost` | Kupon przegrany | `/lost` |

---

## Zarządzanie bankrollem

### Zasady których należy przestrzegać

1. **Nigdy nie stawiaj więcej niż sugeruje Kelly** – to górna granica, nie cel
2. **Bankroll = odłożona kwota** – nie używaj pieniędzy potrzebnych do życia
3. **Skala stopniowo** – zacznij od małych stawek, sprawdź czy system działa
4. **Śledź wyniki** – co miesiąc analizuj ROI, przy -15% zatrzymaj się

### Kiedy zatrzymać system

- ROI < -15% po 50+ zakładach = zatrzymaj, sprawdź model
- Seria 10 przegranych kuponów z rzędu = sprawdź dane wejściowe
- Bukmacher ogranicza konto = zmień bukmachera lub strategię

---

## Plan Rozwoju

### v1.0 ✅ → v1.1 ✅ → v1.2 ✅ → v1.3 ✅ (obecna)

### v1.3 ✅ – Lepszy model
- ✅ Forma ważona czasowo (wykładniczy zanik, halflife=21 dni)
- ✅ Elo rating drużyn (home_elo, away_elo, elo_diff)
- ✅ Calibration plot (data/model/calibration.png)
- ✅ FORM_WINDOW zwiększony z 5 do 8 meczów
- ✅ Usunięto zależność od zewnętrznego API kontuzji

---

### v1.4 – Zaawansowany model
**Priorytet: wysoki | Szacowany czas: 2-3 tygodnie**

- [ ] Hyperparameter tuning (Optuna) – gdy Elo i forma ważona są już ustabilizowane
- [ ] Ensemble: XGBoost + LightGBM + uśrednianie
- [ ] Osobny mini-model dla remisów (najtrudniejszy wynik do przewidzenia)
- [ ] Forma ważona osobno dla meczów domowych i wyjazdowych
- [ ] Elo z uwzględnieniem siły przeciwnika (SOS – Strength of Schedule)

---

### v1.5 – Lepsze kupony i over/under
**Priorytet: średni | Szacowany czas: 1-2 tygodnie**

- [ ] Over/Under gole (totals) — wymaga osobnego modelu regresji sumy goli
- [ ] Round-robin: z 4 value betów generuj wszystkie kombinacje 2-nożne
- [ ] Śledzenie Closing Line Value (CLV) jako metryki jakości modelu
- [ ] Automatyczne rozliczanie wyników przez The Odds API scores

---

### v2.0 – Nowe sporty
**Priorytet: niski | Szacowany czas: 4-6 tygodni**

- [ ] Tenis ATP/WTA
- [ ] NBA / Koszykówka (dane: basketball-reference.com)
- [ ] Siatkówka PlusLiga

---

### v2.1 – Monitoring i UX
**Priorytet: niski | Szacowany czas: 1-2 tygodnie**

- [ ] Dashboard webowy (GitHub Pages): wykres ROI, historia kuponów
- [ ] Powiadomienie gdy model traci edge (degradacja)
- [ ] Tygodniowy raport PDF wysyłany na email

---

## Ważne zastrzeżenia prawne

System generuje sugestie zakładów wyłącznie na potrzeby własne właściciela.
Nie jest to usługa doradztwa finansowego ani bukmacherska.
Stawiaj wyłącznie w legalnych, licencjonowanych serwisach.
W Polsce legalni bukmacherzy posiadają licencję Ministra Finansów.

Hazard może uzależniać. Graj odpowiedzialnie.
Pomoc: **www.uzaleznienia.info** | Infolinia: **801 889 880**
