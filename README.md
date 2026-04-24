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

### Dwa niezależne systemy ROI

**Model ROI** (`/stats`) – mierzy jakość predykcji modelu. Kupony są **automatycznie rozliczane** przez The Odds API (bot sprawdza wyniki co godzinę). Używa sugerowanych stawek Kelly – niezależny od tego czy gracz faktycznie postawił.

**Player ROI** (`/balance`) – mierzy Twój rzeczywisty P&L. Stawki i wypłaty wprowadzasz ręcznie, per kupon.

### Jak działa tracking P&L

```
1. Śr/Pt: bot wysyła kupony z numerami (#1, #2, #3)
   → wpisz /stake [nr] [kwota] dla każdego kuponu osobno
   → np. /stake 1 100  /stake 2 50  /stake 3 0

2. Mecze rozgrywają się → bot AUTO-ROZLICZA Model ROI przez API

3. Gdy wiesz wynik u swojego bukmachera:
   → /won [nr] [kwota]   np. /won 1 350
   → /lost [nr]          np. /lost 2

4. /balance pokazuje Twój rzeczywisty P&L
   /stats   pokazuje Model ROI (jakość predykcji)
```

### Komendy Telegram

| Komenda | Opis | Przykład |
|---------|------|---------|
| `/help` | Lista wszystkich komend | `/help` |
| `/stats` | Model ROI (jakość predykcji) | `/stats` |
| `/balance` | Twój rzeczywisty P&L | `/balance` |
| `/pending` | Lista kuponów czekających na wynik | `/pending` |
| `/setbalance X` | Ustaw punkt startowy | `/setbalance -1500` |
| `/stake [nr] X` | Zaloguj stawkę na konkretny kupon | `/stake 1 100` |
| `/won [nr] X` | Kupon wygrany, dostałem X PLN | `/won 1 350` |
| `/lost [nr]` | Kupon przegrany | `/lost 2` |

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

### v1.0 ✅ → v1.1 ✅ → v1.2 ✅ → v1.3 ✅ → v1.4 ✅ (obecna)

### v1.4 ✅ – Poprawki i rozliczanie
- ✅ Auto-rozliczanie kuponów przez The Odds API /scores
- ✅ Rozdzielenie Model ROI (predykcje) od Player ROI (rzeczywiste stawki)
- ✅ Per-kupon komendy: `/stake [nr] [kwota]`, `/won [nr] [kwota]`, `/lost [nr]`
- ✅ Walidacja BANKROLL (błąd przy BANKROLL=0)
- ✅ Realistyczna symulacja ROI w train.py (z marżą bukmachera ~5%)
- ✅ Naprawka `kelly_stake` liczone dwukrotnie w `parlay_stake`
- ✅ Naprawka kolizji aliasów w name_mapping.py (Sassuolo/Sampdoria)
- ✅ Publiczne API `send_message()` zamiast prywatnego `_send()`
- ✅ Numery kuponów (#1, #2, #3) widoczne w wiadomościach Telegram
- ✅ Usunięto fetch_injuries.py (darmowe API nie zawiera danych bieżącego sezonu)

> **Podatek 12%** (od gier) wliczony w overround bukmachera – `remove_margin()` go eliminuje.
> **Podatek 10%** (od wygranych > 2280 PLN) przy obecnych parametrach nieosiągalny.
> Przy bankrollu > 15 000 PLN należy uwzględnić w obliczeniach Kelly (v1.5 TODO).

> **Elo cross-liga** – obecna implementacja buduje rating Elo dla wszystkich lig razem.
> Nie ma to negatywnego wpływu dopóki predykcje są wykonywane w ramach jednej ligi.
> Przy dodaniu porównań cross-liga (np. tenis, puchary UEFA) należy rozdzielić Elo per liga.
> Zaplanowane jako część v2.0 (nowe sporty).

---

### v1.5 – Model + CLV
**Priorytet: wysoki | Szacowany czas: 2-3 tygodnie**

- [ ] Hyperparameter tuning (Optuna, n_trials=100)
- [ ] Ensemble: XGBoost + LightGBM z uśrednianiem prawdopodobieństw
- [ ] CLV tracking: zapisuj kursy w momencie generowania kuponu i porównuj
      z kursami 24h przed meczem (The Odds API historical odds endpoint)
- [ ] `class_weight={'H': 1, 'D': 1.5, 'A': 1}` – poprawi kalibrację remisów
- [ ] Elo osobno per liga (nie all-in-one)

---

### v1.6 – Over/under + lepsza selekcja
**Priorytet: średni | Szacowany czas: 1-2 tygodnie**

- [ ] Over/Under gole (totals) — model Poissona, +1 req/liga The Odds API
- [ ] CLV monitoring: alert gdy model traci edge (degradacja)
- [ ] Forma ważona osobno dla meczów domowych i wyjazdowych
- [ ] Elo z uwzględnieniem siły harmonogramu (SOS)

---

### v2.0 – Nowe sporty
**Priorytet: niski | Szacowany czas: 4-6 tygodni**

- [ ] Tenis ATP/WTA (dane: tennis-data.co.uk + Jeff Sackmann GitHub, oba free)
- [ ] Siatkówka PlusLiga
- [ ] NBA – tylko jeśli dostęp do advanced stats (back-to-back, injuries feed)

---

### v2.1 – Monitoring i UX
**Priorytet: niski | Szacowany czas: 1-2 tygodnie**

- [ ] Dashboard webowy (GitHub Pages): wykres ROI, historia kuponów, CLV trend
- [ ] Raport PDF na email (cotygodniowy)
- [ ] Tygodniowy raport PDF wysyłany na email

---

## Ważne zastrzeżenia prawne

System generuje sugestie zakładów wyłącznie na potrzeby własne właściciela.
Nie jest to usługa doradztwa finansowego ani bukmacherska.
Stawiaj wyłącznie w legalnych, licencjonowanych serwisach.
W Polsce legalni bukmacherzy posiadają licencję Ministra Finansów.

Hazard może uzależniać. Graj odpowiedzialnie.
Pomoc: **www.uzaleznienia.info** | Infolinia: **801 889 880**
