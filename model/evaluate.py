"""
model/evaluate.py
Automatyczne rozliczanie kuponow i sledzenie ROI.

v1.6 zmiany:
  - auto_resolve_pending_coupons(): zwraca list[dict] zamiast int
    Kazdy element zawiera: coupon_nr, type, result, total_odds, stake,
    payout, legs, clv_parts — uzywane do bogatego powiadomienia Telegram
  - update_coupon_results(): obsluguje nowy typ zwracany
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from config import DATA_RESULTS, LEAGUES, ODDS_API_BASE, ODDS_API_KEYS

log = logging.getLogger(__name__)


# ── Pobieranie wynikow z The Odds API ────────────────────────────────────────

def fetch_results(league_key: str, days_back: int = 7) -> list:
    if not ODDS_API_KEYS:
        log.warning("Brak kluczy API – pomijam pobieranie wynikow.")
        return []

    from pipeline.api_utils import api_get
    url    = f"{ODDS_API_BASE}/sports/{league_key}/scores"
    params = {"daysFrom": days_back, "dateFormat": "iso"}
    try:
        data, _ = api_get(url=url, keys=ODDS_API_KEYS, params=params, key_param="apiKey")
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"Blad pobierania wynikow {league_key}: {e}")
        return []


# ── Logika rozliczania ────────────────────────────────────────────────────────

def _determine_ftr(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "H"
    if home_score == away_score:
        return "D"
    return "A"


def _leg_won(ftr: str, bet_outcome: str) -> bool:
    mapping = {
        "H":  ftr == "H",
        "D":  ftr == "D",
        "A":  ftr == "A",
        "1X": ftr in ("H", "D"),
        "X2": ftr in ("D", "A"),
        "12": ftr in ("H", "A"),
    }
    return mapping.get(bet_outcome, False)


def _build_result_lookups(league_keys: set, days_back: int) -> tuple[dict, dict]:
    from pipeline.name_mapping import normalize

    results_by_id:    dict[str, str]             = {}
    results_by_teams: dict[tuple[str, str], str] = {}

    for odds_key in league_keys:
        scores = fetch_results(odds_key, days_back=days_back)
        for score in scores:
            if not score.get("completed", False):
                continue

            raw_scores  = score.get("scores") or []
            scores_dict: dict[str, int] = {}
            for s in raw_scores:
                try:
                    scores_dict[s["name"]] = int(s["score"])
                except (KeyError, ValueError, TypeError):
                    continue

            if len(scores_dict) < 2:
                continue

            home_raw   = score.get("home_team", "")
            away_raw   = score.get("away_team", "")
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
        f"Pobrano wyniki: {len(results_by_id)} meczow wg ID, "
        f"{len(results_by_teams)} wg nazw druzyn"
    )
    return results_by_id, results_by_teams


def _resolve_coupon_status(
    coupon: dict,
    results_by_id: dict,
    results_by_teams: dict,
) -> str:
    legs = coupon.get("legs", [])
    if not legs:
        return "PENDING"

    any_pending = False

    for leg in legs:
        match_id    = leg.get("match_id", "")
        bet_outcome = leg.get("bet_outcome", "")
        home_norm   = leg.get("home_team", "").lower()
        away_norm   = leg.get("away_team", "").lower()

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

def _compute_dynamic_days_back(history: list, max_days: int = 14) -> int:
    oldest: datetime | None = None
    for entry in history:
        for coupon in entry.get("coupons", []):
            if coupon.get("result", "PENDING") != "PENDING":
                continue
            try:
                d = datetime.fromisoformat(entry.get("date", "")[:16])
                if oldest is None or d < oldest:
                    oldest = d
            except ValueError:
                continue

    if oldest is None:
        return 7

    days_since = (datetime.now() - oldest).days + 2
    return min(max_days, max(7, days_since))


def auto_resolve_pending_coupons() -> list[dict]:
    """
    Pobiera wyniki z The Odds API i automatycznie rozlicza PENDING kupony.

    Zwraca liste slownikow z detalami rozliczonych kuponow:
      [{
        "coupon_nr":  3,          <- globalny numer kuponu
        "type":       "SINGIEL",
        "result":     "WON",
        "total_odds": 2.10,
        "stake":      30.0,
        "payout":     63.0,       <- stake * odds (tylko WON, inaczej 0)
        "legs":       [...],
        "clv_parts":  ["+2.4%"],  <- CLV per noga jesli dostepne
      }, ...]
    """
    history_path = Path(DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        return []

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    pending_coupons: list[dict] = []
    league_keys:     set[str]   = set()

    for entry in history:
        for coupon in entry.get("coupons", []):
            if coupon.get("result", "PENDING") == "PENDING":
                pending_coupons.append(coupon)
                for leg in coupon.get("legs", []):
                    lc = leg.get("league_code", "")
                    if lc in LEAGUES:
                        league_keys.add(LEAGUES[lc]["odds_key"])

    if not pending_coupons:
        log.info("Brak PENDING kuponow – pomijam auto-resolve.")
        return []

    days_back = _compute_dynamic_days_back(history)
    log.info(
        f"Auto-resolve: {len(pending_coupons)} PENDING kuponow, "
        f"{len(league_keys)} lig, days_back={days_back}"
    )

    if not ODDS_API_KEYS:
        log.warning(
            "Brak kluczy The Odds API – auto-resolve niemozliwy. "
            "Uzyj /won lub /lost zeby recznie rozliczyc kupony."
        )
        return []

    results_by_id, results_by_teams = _build_result_lookups(league_keys, days_back)

    if not results_by_id and not results_by_teams:
        log.warning("Nie pobrano zadnych wynikow – API moze byc niedostepne.")
        return []

    # Buduj mape kupon -> globalny numer przed modyfikacja historii
    global_idx_map: dict[int, int] = {}
    global_idx = 0
    for entry in history:
        for coupon in entry.get("coupons", []):
            global_idx += 1
            global_idx_map[id(coupon)] = global_idx

    resolved_details: list[dict] = []

    for entry in history:
        for coupon in entry.get("coupons", []):
            if coupon.get("result", "PENDING") != "PENDING":
                continue
            new_status = _resolve_coupon_status(coupon, results_by_id, results_by_teams)
            if new_status != "PENDING":
                coupon["result"]      = new_status
                coupon["resolved_at"] = datetime.now().isoformat()

                stake      = float(coupon.get("stake", 0))
                total_odds = float(coupon.get("total_odds", 1))
                coupon_nr  = global_idx_map.get(id(coupon), "?")
                clv_parts  = [
                    f"{leg['clv_pct']:+.1f}%"
                    for leg in coupon.get("legs", [])
                    if leg.get("clv_pct") is not None
                ]

                resolved_details.append({
                    "coupon_nr":  coupon_nr,
                    "type":       coupon.get("type", "?"),
                    "result":     new_status,
                    "total_odds": total_odds,
                    "stake":      stake,
                    "payout":     round(stake * total_odds, 2) if new_status == "WON" else 0.0,
                    "legs":       coupon.get("legs", []),
                    "clv_parts":  clv_parts,
                })

                clv_str = f"  [CLV: {', '.join(clv_parts)}]" if clv_parts else ""
                log.info(
                    f"  [{new_status}] #{coupon_nr} {coupon.get('type','?')} "
                    f"@ {total_odds} (Kelly: {stake:.0f} PLN){clv_str}"
                )

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    log.info(f"Auto-resolve zakończony: rozliczono {len(resolved_details)} kuponow.")
    return resolved_details


# ── Statystyki modelu (Model ROI) ─────────────────────────────────────────────

def update_coupon_results() -> dict:
    """
    Rozlicza kupony i oblicza Model ROI + statystyki CLV.
    """
    auto_resolve_pending_coupons()

    history_path = Path(DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        log.info("Brak historii kuponow.")
        return _empty_stats()

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    stats = _empty_stats()

    for entry in history:
        for coupon in entry.get("coupons", []):
            stats["total_coupons"] += 1
            model_stake = float(coupon.get("stake", 0))
            result      = coupon.get("result", "PENDING")

            if result == "WON":
                stats["won"]                += 1
                stats["staked_resolved"]    += model_stake
                stats["total_model_return"] += model_stake * float(coupon.get("total_odds", 1))
            elif result == "LOST":
                stats["lost"]            += 1
                stats["staked_resolved"] += model_stake
            else:
                stats["pending"] += 1

    if stats["staked_resolved"] > 0:
        stats["model_roi"] = (
            (stats["total_model_return"] - stats["staked_resolved"])
            / stats["staked_resolved"] * 100
        )

    # CLV statystyki (zero dodatkowych API calls)
    try:
        from pipeline.fetch_clv import get_clv_summary
        clv = get_clv_summary()
        stats["clv_avg"]          = clv["avg_clv"]
        stats["clv_legs"]         = clv["legs_with_clv"]
        stats["clv_positive_pct"] = clv["positive_clv_pct"]
    except Exception as e:
        log.warning(f"Nie udalo sie zaladowac statystyk CLV: {e}")

    log.info("─── MODEL ROI (sugerowane stawki Kelly) ─────────")
    log.info(f"Lacznie kuponow:  {stats['total_coupons']}")
    log.info(f"  WON:     {stats['won']}")
    log.info(f"  LOST:    {stats['lost']}")
    log.info(f"  PENDING: {stats['pending']}")
    log.info(f"  Postawiono (rozliczone): {stats['staked_resolved']:.0f} PLN")
    log.info(f"  Zwrot (WON):             {stats['total_model_return']:.0f} PLN")
    log.info(f"Model ROI: {stats['model_roi']:.1f}%")
    if stats.get("clv_legs", 0) > 0:
        log.info(
            f"CLV: avg={stats['clv_avg']:+.2f}% "
            f"(+CLV: {stats['clv_positive_pct']:.0f}%, "
            f"n={stats['clv_legs']})"
        )
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
        "staked_resolved":    0.0,
        "total_model_return": 0.0,
        "model_roi":          0.0,
        "clv_avg":            0.0,
        "clv_legs":           0,
        "clv_positive_pct":   0.0,
    }


# ── Kupony oczekujace (dla bota) ──────────────────────────────────────────────

def get_pending_summary() -> dict:
    history_path = Path(DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        return {"count": 0, "total_staked_model": 0.0, "potential_return": 0.0, "legs_summary": []}

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    count            = 0
    total_staked     = 0.0
    potential_return = 0.0
    legs_summary     = []

    global_idx = 0
    for entry in history:
        for coupon in entry.get("coupons", []):
            global_idx += 1
            if coupon.get("result", "PENDING") != "PENDING":
                continue

            count        += 1
            stake         = float(coupon.get("stake", 0))
            odds          = float(coupon.get("total_odds", 1.0))
            total_staked     += stake
            potential_return += stake * odds

            date_str    = entry.get("date", "?")[:10]
            coupon_type = coupon.get("type", "?")
            legs        = coupon.get("legs", [])
            teams       = " + ".join(
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
