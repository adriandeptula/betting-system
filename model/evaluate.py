"""
model/evaluate.py
Automatyczne rozliczanie kuponów i śledzenie ROI.

Dwa niezależne systemy:
  1. Model ROI  – mierzy jakość modelu niezależnie od gracza.
                  Kupony rozliczane automatycznie przez The Odds API /scores.
                  Podstawa: coupons_history.json (sugerowane stawki Kelly).

  2. Player ROI – mierzy rzeczywisty P&L gracza.
                  Stawki: /stake [nr_kuponu] [kwota]  (osobno na każdy kupon)
                  Wypłaty: /won [nr_kuponu] [kwota]   (gracz podaje rzeczywistą wypłatę)
                  Podstawa: finance.json (rzeczywiste transakcje per kupon).

Przepływ:
  weekly_retrain (poniedziałek) → auto_resolve_pending_coupons() → update_coupon_results()
  bot_polling (co godzinę)      → auto_resolve_pending_coupons() (szybko wraca gdy brak PENDING)
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from config import DATA_RESULTS, LEAGUES, ODDS_API_BASE, ODDS_API_KEYS

log = logging.getLogger(__name__)


# ── Pobieranie wyników z The Odds API ────────────────────────────────────────

def fetch_results(league_key: str, days_back: int = 7) -> list:
    """Pobiera wyniki zakończonych meczów z ostatnich N dni z The Odds API."""
    if not ODDS_API_KEYS:
        log.warning("Brak kluczy API – pomijam pobieranie wyników.")
        return []

    from pipeline.api_utils import api_get
    url = f"{ODDS_API_BASE}/sports/{league_key}/scores"
    params = {"daysFrom": days_back, "dateFormat": "iso"}
    try:
        data, _ = api_get(url=url, keys=ODDS_API_KEYS, params=params, key_param="apiKey")
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"Błąd pobierania wyników {league_key}: {e}")
        return []


# ── Logika rozliczania ────────────────────────────────────────────────────────

def _determine_ftr(home_score: int, away_score: int) -> str:
    """Wyznacza wynik (H/D/A) na podstawie liczby goli."""
    if home_score > away_score:
        return "H"
    if home_score == away_score:
        return "D"
    return "A"


def _leg_won(ftr: str, bet_outcome: str) -> bool:
    """Sprawdza czy noga kuponu wygrała."""
    mapping = {
        "H":  ftr == "H",
        "D":  ftr == "D",
        "A":  ftr == "A",
        "1X": ftr in ("H", "D"),
        "X2": ftr in ("D", "A"),
        "12": ftr in ("H", "A"),
    }
    return mapping.get(bet_outcome, False)


def _build_result_lookups(league_keys: set) -> tuple[dict, dict]:
    """
    Pobiera wyniki dla podanych lig i buduje dwa słowniki wyszukiwania:
      results_by_id    : {match_id: ftr}
      results_by_teams : {(home_norm_lower, away_norm_lower): ftr}

    Dwa indeksy dla niezawodności – match_id może się różnić między API calls
    gdy np. event był aktualizowany, stąd fallback po nazwach drużyn.
    """
    from pipeline.name_mapping import normalize

    results_by_id: dict[str, str]                = {}
    results_by_teams: dict[tuple[str, str], str] = {}

    for odds_key in league_keys:
        scores = fetch_results(odds_key, days_back=7)
        for score in scores:
            if not score.get("completed", False):
                continue

            raw_scores = score.get("scores") or []
            scores_dict: dict[str, int] = {}
            for s in raw_scores:
                try:
                    scores_dict[s["name"]] = int(s["score"])
                except (KeyError, ValueError, TypeError):
                    continue

            if len(scores_dict) < 2:
                continue

            home_raw  = score.get("home_team", "")
            away_raw  = score.get("away_team", "")
            home_score = scores_dict.get(home_raw, -1)
            away_score = scores_dict.get(away_raw, -1)

            if home_score < 0 or away_score < 0:
                continue

            ftr      = _determine_ftr(home_score, away_score)
            event_id = score.get("id", "")

            if event_id:
                results_by_id[event_id] = ftr

            home_norm = normalize(home_raw, "scores_api").lower()
            away_norm = normalize(away_raw, "scores_api").lower()
            results_by_teams[(home_norm, away_norm)] = ftr

    log.info(
        f"Pobrano wyniki: {len(results_by_id)} meczów wg ID, "
        f"{len(results_by_teams)} wg nazw drużyn"
    )
    return results_by_id, results_by_teams


def _resolve_coupon_status(
    coupon: dict,
    results_by_id: dict,
    results_by_teams: dict,
) -> str:
    """
    Wyznacza aktualny status kuponu na podstawie wyników.
    Zwraca: 'WON' | 'LOST' | 'PENDING'

    Parlay (akumulator) wygrywa gdy WSZYSTKIE nogi wygrały.
    Parlay przegrywa gdy JAKAKOLWIEK noga przegrała (i wynik jest znany).
    Pozostaje PENDING jeśli którakolwiek noga jeszcze nie ma wyniku.
    """
    legs = coupon.get("legs", [])
    if not legs:
        return "PENDING"

    any_pending = False

    for leg in legs:
        match_id    = leg.get("match_id", "")
        bet_outcome = leg.get("bet_outcome", "")
        home_norm   = leg.get("home_team", "").lower()
        away_norm   = leg.get("away_team", "").lower()

        # Szukaj wyniku: najpierw po match_id, potem po znormalizowanych nazwach
        ftr = results_by_id.get(match_id) or results_by_teams.get(
            (home_norm, away_norm)
        )

        if ftr is None:
            any_pending = True
            continue

        if not _leg_won(ftr, bet_outcome):
            return "LOST"

    if any_pending:
        return "PENDING"

    return "WON"


# ── Auto-rozliczanie ──────────────────────────────────────────────────────────

def auto_resolve_pending_coupons() -> int:
    """
    Pobiera wyniki z The Odds API i automatycznie rozlicza PENDING kupony.

    Wywoływana:
      - w run_stats() (weekly_retrain, poniedziałek)
      - w poll_and_respond() (bot_polling, co godzinę) gdy są PENDING kupony

    Zwraca liczbę nowo rozliczonych kuponów.
    """
    history_path = Path(DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        return 0

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    # Zbierz PENDING kupony i ligi których potrzebujemy
    pending_coupons: list[dict] = []
    league_keys: set[str] = set()

    for entry in history:
        for coupon in entry.get("coupons", []):
            if coupon.get("result", "PENDING") == "PENDING":
                pending_coupons.append(coupon)
                for leg in coupon.get("legs", []):
                    lc = leg.get("league_code", "")
                    if lc in LEAGUES:
                        league_keys.add(LEAGUES[lc]["odds_key"])

    if not pending_coupons:
        log.info("Brak PENDING kuponów – pomijam auto-resolve.")
        return 0

    log.info(
        f"Auto-resolve: {len(pending_coupons)} PENDING kuponów, "
        f"{len(league_keys)} lig do sprawdzenia"
    )

    if not ODDS_API_KEYS:
        log.warning(
            "Brak kluczy The Odds API – auto-resolve niemożliwy. "
            "Użyj /won lub /lost żeby ręcznie rozliczyć kupony."
        )
        return 0

    results_by_id, results_by_teams = _build_result_lookups(league_keys)

    if not results_by_id and not results_by_teams:
        log.warning("Nie pobrano żadnych wyników – API może być niedostępne.")
        return 0

    resolved = 0
    for entry in history:
        for coupon in entry.get("coupons", []):
            if coupon.get("result", "PENDING") != "PENDING":
                continue
            new_status = _resolve_coupon_status(coupon, results_by_id, results_by_teams)
            if new_status != "PENDING":
                coupon["result"]      = new_status
                coupon["resolved_at"] = datetime.now().isoformat()
                resolved += 1
                log.info(
                    f"  [{new_status}] {coupon.get('type','?')} "
                    f"@ {coupon.get('total_odds', '?')} "
                    f"(sugerowana stawka Kelly: {coupon.get('stake', '?')} PLN)"
                )

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    log.info(f"Auto-resolve zakończony: rozliczono {resolved} kuponów.")
    return resolved


# ── Statystyki modelu (Model ROI) ─────────────────────────────────────────────

def update_coupon_results() -> dict:
    """
    Rozlicza kupony i oblicza Model ROI.

    Model ROI używa SUGEROWANYCH stawek Kelly z coupons_history.json
    i jest NIEZALEŻNY od tego czy gracz faktycznie postawił.
    Mierzy wyłącznie jakość modelu.

    Dla Player ROI (rzeczywistego P&L gracza) użyj notify.finance.get_summary().
    """
    # Najpierw spróbuj auto-rozliczyć PENDING
    auto_resolve_pending_coupons()

    history_path = Path(DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        log.info("Brak historii kuponów.")
        return _empty_stats()

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    stats = _empty_stats()

    for entry in history:
        for coupon in entry.get("coupons", []):
            stats["total_coupons"] += 1
            model_stake = float(coupon.get("stake", 0))
            stats["total_model_staked"] += model_stake
            result = coupon.get("result", "PENDING")

            if result == "WON":
                stats["won"] += 1
                payout = model_stake * float(coupon.get("total_odds", 1))
                stats["total_model_return"] += payout
            elif result == "LOST":
                stats["lost"] += 1
            else:
                stats["pending"] += 1

    resolved = stats["won"] + stats["lost"]
    if resolved > 0 and stats["total_model_staked"] > 0:
        resolved_frac   = resolved / stats["total_coupons"]
        staked_resolved = stats["total_model_staked"] * resolved_frac
        stats["model_roi"] = (
            (stats["total_model_return"] - staked_resolved) / staked_resolved * 100
            if staked_resolved > 0 else 0.0
        )

    log.info("─── MODEL ROI (sugerowane stawki Kelly) ─────────")
    log.info(f"Łącznie kuponów: {stats['total_coupons']}")
    log.info(f"  WON:     {stats['won']}")
    log.info(f"  LOST:    {stats['lost']}")
    log.info(f"  PENDING: {stats['pending']}")
    log.info(f"Model ROI: {stats['model_roi']:.1f}%")
    log.info("─────────────────────────────────────────────────")

    Path(DATA_RESULTS).mkdir(parents=True, exist_ok=True)
    stats_path = Path(DATA_RESULTS) / "stats.json"
    stats["updated_at"] = datetime.now().isoformat()
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    return stats


def _empty_stats() -> dict:
    return {
        "total_coupons":      0,
        "won":                0,
        "lost":               0,
        "pending":            0,
        "total_model_staked": 0.0,
        "total_model_return": 0.0,
        "model_roi":          0.0,
    }


# ── Kupony oczekujące (dla bota) ──────────────────────────────────────────────

def get_pending_summary() -> dict:
    """
    Zwraca podsumowanie PENDING kuponów z ich numerami.
    Numery kuponów używane przez gracza w komendach /stake i /won.

    Format numeru kuponu: sekwencyjny indeks w historii (1, 2, 3...) –
    wyświetlany przy każdym wysłaniu kuponu na Telegram.
    """
    history_path = Path(DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        return {"count": 0, "total_staked_model": 0.0, "potential_return": 0.0, "legs_summary": []}

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    count            = 0
    total_staked     = 0.0
    potential_return = 0.0
    legs_summary     = []

    # Globalny licznik kuponów – ten sam co nadawany przy wysyłaniu
    global_idx = 0
    for entry in history:
        for coupon in entry.get("coupons", []):
            global_idx += 1
            if coupon.get("result", "PENDING") != "PENDING":
                continue

            count += 1
            stake = float(coupon.get("stake", 0))
            odds  = float(coupon.get("total_odds", 1.0))
            total_staked     += stake
            potential_return += stake * odds

            date_str    = entry.get("date", "?")[:10]
            coupon_type = coupon.get("type", "?")
            legs        = coupon.get("legs", [])
            teams = " + ".join(
                f"{l.get('home_team','?')[:12]} vs {l.get('away_team','?')[:12]}"
                for l in legs
            )
            legs_summary.append(
                f"#{global_idx} {date_str} | {coupon_type} @ {odds:.2f}x | {teams}"
            )

    return {
        "count":              count,
        "total_staked_model": round(total_staked, 2),
        "potential_return":   round(potential_return, 2),
        "legs_summary":       legs_summary,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    update_coupon_results()
