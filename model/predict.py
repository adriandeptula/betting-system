"""
model/predict.py
Generuje predykcje dla nadchodzących meczów na podstawie wytrenowanego modelu.

v1.6 zmiany:
  - load_model(): obsługuje nowy format ensemble {"model_type": "ensemble", "models": [...]}
    i stary format {"model": ...} (backward compat)
  - predict_matches(): proba = mean([m.predict_proba(X) for m in models])
"""
import json
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config import DATA_ODDS, DATA_RAW, MODEL_PATH
from model.features import FEATURE_COLS, compute_features_upcoming, remove_margin
from pipeline.name_mapping import normalize

log = logging.getLogger(__name__)


def load_model() -> tuple | None:
    """
    Wczytuje model(e) i metadane z pliku pkl.

    Obsługuje dwa formaty:
      v1.6 ensemble: {"model_type": "ensemble", "models": [cal_xgb, cal_lgb], ...}
      v1.5 single:   {"model": cal_xgb, ...}  (backward compat)

    Zwraca (models_list, feature_cols, league_codes) lub None przy błędzie.
    """
    if not Path(MODEL_PATH).exists():
        log.error(f"Brak modelu: {MODEL_PATH}. Uruchom: python main.py train")
        return None

    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)

    feature_cols = saved["feature_cols"]
    league_codes = saved["league_codes"]

    # v1.6 ensemble format
    if saved.get("model_type") == "ensemble":
        models     = saved["models"]
        names      = saved.get("model_names", [f"model_{i}" for i in range(len(models))])
        n_models   = len(models)
        metrics    = saved.get("metrics", {})
        log.info(
            f"Wczytano ensemble: {' + '.join(names)} "
            f"(acc={metrics.get('accuracy', 0):.3f}, "
            f"ll={metrics.get('log_loss', 0):.4f}, "
            f"Optuna trials={metrics.get('optuna_trials', 0)})"
        )
        return models, feature_cols, league_codes

    # v1.5 single model format (backward compat)
    if "model" in saved:
        log.info("Wczytano model w formacie v1.5 (single XGBoost). "
                 "Retrenuj żeby uaktualnić do ensemble v1.6.")
        return [saved["model"]], feature_cols, league_codes

    log.error("Nieznany format modelu w pkl. Uruchom: python main.py train")
    return None


def load_latest_odds() -> list:
    """Wczytuje najnowszy plik z kursami."""
    files = sorted(Path(DATA_ODDS).glob("odds_*.json"))
    if not files:
        log.error("Brak plików z kursami! Uruchom: python main.py fetch")
        return []
    latest = files[-1]
    log.info(f"Wczytuję kursy: {latest.name}")
    with open(latest, encoding="utf-8") as f:
        return json.load(f)


def _best_odds(
    bookmakers: list, home_team: str, away_team: str
) -> tuple[float, float, float]:
    """Najlepsze dostępne kursy 1X2 ze wszystkich bukmacherów."""
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
                elif name == home_team:
                    best_h = max(best_h, price)
                else:
                    best_a = max(best_a, price)

    return (
        best_h if best_h > 1.0 else 2.0,
        best_d if best_d > 1.0 else 3.5,
        best_a if best_a > 1.0 else 4.0,
    )


def _parse_odds_to_upcoming(events: list) -> list[dict]:
    """Parsuje eventy z The Odds API do formatu compute_features_upcoming()."""
    upcoming = []
    now      = datetime.now(timezone.utc)

    for ev in events:
        commence_raw = ev.get("commence_time", "")
        try:
            commence_dt = datetime.fromisoformat(commence_raw.replace("Z", "+00:00"))
        except Exception:
            continue

        if commence_dt <= now:
            continue

        home_raw    = ev.get("home_team", "")
        away_raw    = ev.get("away_team", "")
        league_code = ev.get("_league_code", "")

        home_norm = normalize(home_raw, source="odds_api")
        away_norm = normalize(away_raw, source="odds_api")

        odds_h, odds_d, odds_a = _best_odds(
            ev.get("bookmakers", []), home_raw, away_raw
        )

        upcoming.append({
            "match_id":      ev.get("id", f"{home_raw}_vs_{away_raw}"),
            "home_team":     home_norm,
            "away_team":     away_norm,
            "home_team_raw": home_raw,
            "away_team_raw": away_raw,
            "league":        league_code,
            "date":          commence_dt,
            "commence_time": commence_raw,
            "odds_h":        odds_h,
            "odds_d":        odds_d,
            "odds_a":        odds_a,
        })

    log.info(f"Sparsowano {len(upcoming)} nadchodzących meczów z kursami")
    return upcoming


def predict_matches() -> list:
    """
    Generuje predykcje dla wszystkich nadchodzących meczów.

    v1.6: proba = mean([model.predict_proba(X) for model in models])
    Backward compat: działa też ze starym single-model pkl.

    Returns
    -------
    Lista słowników z prawdopodobieństwami modelu i rynku.
    """
    loaded = load_model()
    if not loaded:
        return []
    models, feature_cols, league_codes = loaded

    df_hist         = pd.read_csv(f"{DATA_RAW}/all_matches.csv")
    df_hist["Date"] = pd.to_datetime(df_hist["Date"], errors="coerce")

    events = load_latest_odds()
    if not events:
        return []

    upcoming = _parse_odds_to_upcoming(events)
    if not upcoming:
        log.warning("Brak nadchodzących meczów do predykcji.")
        return []

    features_df = compute_features_upcoming(upcoming, df_hist)
    if features_df.empty:
        log.warning("Brak features do predykcji!")
        return []

    X = features_df[FEATURE_COLS].fillna(0)

    # Ensemble: uśrednij skalibrowane prawdopodobieństwa
    proba = np.mean([m.predict_proba(X) for m in models], axis=0)

    results = []
    for i, match in enumerate(upcoming):
        if i >= len(proba):
            break

        odds_h, odds_d, odds_a = match["odds_h"], match["odds_d"], match["odds_a"]
        mkt_h, mkt_d, mkt_a   = remove_margin(odds_h, odds_d, odds_a)

        results.append({
            "match_id":         match["match_id"],
            "home_team":        match["home_team"],
            "away_team":        match["away_team"],
            "league_code":      match["league"],
            "commence_time":    match["commence_time"],
            "odds_home":        odds_h,
            "odds_draw":        odds_d,
            "odds_away":        odds_a,
            "prob_home":        float(proba[i, 0]),
            "prob_draw":        float(proba[i, 1]),
            "prob_away":        float(proba[i, 2]),
            "market_prob_home": mkt_h,
            "market_prob_draw": mkt_d,
            "market_prob_away": mkt_a,
        })

    log.info(f"Wygenerowano predykcje dla {len(results)} meczów")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for p in predict_matches()[:5]:
        print(
            f"{p['home_team']} vs {p['away_team']} | "
            f"H: {p['prob_home']:.0%}  D: {p['prob_draw']:.0%}  A: {p['prob_away']:.0%}"
        )
