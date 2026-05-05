"""
pipeline/fetch_clv.py – Śledzenie Closing Line Value (CLV) dla kuponów.

CLV = (bet_odds / closing_odds - 1) × 100 %
  Dodatnie CLV = model trafił lepszy kurs niż rynek zamknął → model ma edge.
  Cel długoterminowy: średnie CLV > 0 %.

Kluczowe właściwości:
  - ZERO dodatkowych wywołań API — używa już pobranego pliku data/odds/*.json
  - Wywoływana z run_fetch() po fetch_all_odds(), gdy kursy są najświeższe
  - Closing odds zapisywane jednorazowo (pierwsze trafienie blokuje wartość)
  - Double chance: closing_odds obliczane matematycznie z h2h (jak w value_engine)

Format danych w coupons_history.json (per noga):
  "closing_odds": 2.05         ← kurs rynkowy ~24h przed meczem
  "clv_pct":      +2.38        ← (bet_odds/closing_odds - 1)*100
  "clv_at":       "2025-..."   ← kiedy zapisano CLV

v1.6: nowy plik
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import config
from pipeline.name_mapping import normalize

log = logging.getLogger(__name__)


# ── Wczytywanie kursów ────────────────────────────────────────────────────────

def _load_latest_odds() -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    """
    Wczytuje najnowszy plik odds_*.json.
    Zwraca dwa słowniki: po match_id i po (home_norm, away_norm).
    """
    files = sorted(Path(config.DATA_ODDS).glob("odds_*.json"))
    if not files:
        return {}, {}

    with open(files[-1], encoding="utf-8") as f:
        events: list[dict] = json.load(f)

    by_id:    dict[str, dict]              = {}
    by_teams: dict[tuple[str, str], dict]  = {}

    for ev in events:
        if "id" in ev:
            by_id[ev["id"]] = ev
        h = normalize(ev.get("home_team", ""), "clv").lower()
        a = normalize(ev.get("away_team", ""), "clv").lower()
        if h and a:
            by_teams[(h, a)] = ev

    return by_id, by_teams


def _best_h2h_odds(
    bookmakers: list, home_raw: str, away_raw: str
) -> tuple[float, float, float]:
    """Najlepsze dostępne kursy h2h ze wszystkich bukmacherów."""
    best_h = best_d = best_a = 0.0
    for bm in bookmakers:
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                name  = outcome.get("name", "")
                price = float(outcome.get("price", 0))
                if name == "Draw":
                    best_d = max(best_d, price)
                elif name == home_raw:
                    best_h = max(best_h, price)
                else:
                    best_a = max(best_a, price)
    return (
        best_h if best_h > 1.0 else 0.0,
        best_d if best_d > 1.0 else 0.0,
        best_a if best_a > 1.0 else 0.0,
    )


def _closing_odds_for_outcome(
    outcome: str,
    odds_h: float,
    odds_d: float,
    odds_a: float,
) -> float:
    """
    Zwraca closing odds dla konkretnego wyniku.
    Double chance obliczane matematycznie z h2h (zero dodatkowych requestów).
    """
    if outcome == "H":
        return odds_h
    if outcome == "D":
        return odds_d
    if outcome == "A":
        return odds_a

    # Double chance: fair prob → DC fair odds
    from model.features import remove_margin
    mh, md, ma = remove_margin(odds_h, odds_d, odds_a)

    if outcome == "1X":
        p = mh + md
    elif outcome == "X2":
        p = md + ma
    elif outcome == "12":
        p = mh + ma
    else:
        return 0.0

    return round(1.0 / p, 3) if p > 0 else 0.0


# ── Główna funkcja update ─────────────────────────────────────────────────────

def update_clv() -> int:
    """
    Dla każdej nogi w PENDING kuponach porównuje bet_odds z aktualnymi kursami.
    Zapisuje closing_odds + clv_pct gdy mecz zaczyna się w ciągu CLV_CLOSING_HOURS.

    Nie nadpisuje raz zapisanego CLV — pierwsze trafienie blokuje wartość.
    Zwraca liczbę nóg z nowo zapisanym CLV.
    """
    history_path = Path(config.DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        return 0

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    now     = datetime.now(timezone.utc)
    cutoff  = now + timedelta(hours=config.CLV_CLOSING_HOURS)

    by_id, by_teams = _load_latest_odds()
    if not by_id and not by_teams:
        log.warning("Brak pliku z kursami – pomijam CLV update.")
        return 0

    updated = 0

    for entry in history:
        for coupon in entry.get("coupons", []):
            # CLV liczymy też dla rozliczonych kuponów (brak danych ≠ brak wartości)
            for leg in coupon.get("legs", []):

                # Już zapisany CLV – nie nadpisujemy
                if leg.get("closing_odds") is not None:
                    continue

                # Znajdź event w aktualnych kursach
                event = by_id.get(leg.get("match_id", ""))
                if event is None:
                    h = leg.get("home_team", "").lower()
                    a = leg.get("away_team", "").lower()
                    event = by_teams.get((h, a))
                if event is None:
                    continue

                # Sprawdź czy mecz jest dostatecznie blisko (closing window)
                try:
                    commence = datetime.fromisoformat(
                        event["commence_time"].replace("Z", "+00:00")
                    )
                except (KeyError, ValueError):
                    continue

                if commence > cutoff:
                    continue  # Za wcześnie — rynek jeszcze może się dużo ruszyć

                # Pobierz best odds
                home_raw = event.get("home_team", "")
                away_raw = event.get("away_team", "")
                odds_h, odds_d, odds_a = _best_h2h_odds(
                    event.get("bookmakers", []), home_raw, away_raw
                )
                if odds_h <= 0:
                    continue

                closing = _closing_odds_for_outcome(
                    leg.get("bet_outcome", ""), odds_h, odds_d, odds_a
                )
                if closing <= 0:
                    continue

                bet_odds = float(leg.get("bet_odds", 0))
                if bet_odds <= 0:
                    continue

                clv_pct = (bet_odds / closing - 1.0) * 100.0

                leg["closing_odds"] = round(closing, 3)
                leg["clv_pct"]      = round(clv_pct, 2)
                leg["clv_at"]       = now.isoformat()
                updated += 1

                log.info(
                    f"CLV [{leg.get('bet_outcome')}] "
                    f"{leg.get('home_team')} vs {leg.get('away_team')}: "
                    f"bet={bet_odds:.2f} closing={closing:.2f} "
                    f"CLV={clv_pct:+.1f}%"
                )

    if updated > 0:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        log.info(f"CLV: zaktualizowano {updated} nóg kuponów.")

    return updated


# ── Statystyki CLV ────────────────────────────────────────────────────────────

def get_clv_summary() -> dict:
    """
    Oblicza zbiorcze statystyki CLV dla wszystkich kuponów z zapisanym CLV.

    Klucze zwracanego słownika:
      legs_with_clv    – liczba nóg z zapisanym CLV
      avg_clv          – średnie CLV [%]
      positive_clv_pct – % nóg z dodatnim CLV (długoterminowy cel: >50%)
      by_outcome       – avg CLV per typ zakładu (H/D/A/1X/X2/12)
    """
    history_path = Path(config.DATA_RESULTS) / "coupons_history.json"
    if not history_path.exists():
        return _empty_clv()

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    clv_values: list[float]             = []
    by_outcome: dict[str, list[float]]  = {}

    for entry in history:
        for coupon in entry.get("coupons", []):
            for leg in coupon.get("legs", []):
                clv = leg.get("clv_pct")
                if clv is None:
                    continue
                clv_values.append(float(clv))
                outcome = leg.get("bet_outcome", "?")
                by_outcome.setdefault(outcome, []).append(float(clv))

    if not clv_values:
        return _empty_clv()

    positive = sum(1 for v in clv_values if v > 0)

    return {
        "legs_with_clv":    len(clv_values),
        "avg_clv":          round(sum(clv_values) / len(clv_values), 2),
        "positive_clv_pct": round(positive / len(clv_values) * 100, 1),
        "by_outcome": {
            k: round(sum(v) / len(v), 2)
            for k, v in sorted(by_outcome.items())
        },
    }


def _empty_clv() -> dict:
    return {
        "legs_with_clv":    0,
        "avg_clv":          0.0,
        "positive_clv_pct": 0.0,
        "by_outcome":       {},
    }
