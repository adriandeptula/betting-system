"""
model/predict.py
Generuje predykcje dla nadchodzących meczów na podstawie wytrenowanego modelu.
"""
import json
import logging
import pickle
from pathlib import Path

import pandas as pd

from config import DATA_ODDS, DATA_RAW, MODEL_PATH
from model.features import FEATURE_COLS, build_features

log = logging.getLogger(__name__)


def load_model() -> tuple | None:
    """Wczytuje model i metadane z pliku."""
    if not Path(MODEL_PATH).exists():
        log.error(f"Brak modelu: {MODEL_PATH}. Uruchom: python main.py train")
        return None
    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    return saved["model"], saved["feature_cols"], saved["league_codes"]


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


def predict_matches() -> list:
    """
    Generuje predykcje dla wszystkich nadchodzących meczów.

    Returns:
        Lista słowników z prawdopodobieństwami modelu i rynku.
    """
    loaded = load_model()
    if not loaded:
        return []
    model, feature_cols, league_codes = loaded

    df_hist = pd.read_csv(f"{DATA_RAW}/all_matches.csv")
    upcoming = load_latest_odds()
    if not upcoming:
        return []

    features_df = build_features(df_hist, upcoming, league_codes)
    if features_df.empty:
        log.warning("Brak features do predykcji!")
        return []

    X = features_df[FEATURE_COLS].fillna(0)
    proba = model.predict_proba(X)

    results = []
    for i, row in features_df.iterrows():
        results.append({
            "match_id":          row["match_id"],
            "home_team":         row["home_team"],
            "away_team":         row["away_team"],
            "league_code":       row["league_code"],
            "commence_time":     row["commence_time"],
            "odds_home":         float(row["odds_home"]),
            "odds_draw":         float(row["odds_draw"]),
            "odds_away":         float(row["odds_away"]),
            # Prawdopodobieństwa modelu
            "prob_home":         float(proba[i, 0]),
            "prob_draw":         float(proba[i, 1]),
            "prob_away":         float(proba[i, 2]),
            # Uczciwe prawdopodobieństwa rynku
            "market_prob_home":  float(row["market_prob_home"]),
            "market_prob_draw":  float(row["market_prob_draw"]),
            "market_prob_away":  float(row["market_prob_away"]),
        })

    log.info(f"Wygenerowano predykcje dla {len(results)} meczów")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for p in predict_matches()[:5]:
        print(
            f"{p['home_team']} vs {p['away_team']} | "
            f"H: {p['prob_home']:.0%} D: {p['prob_draw']:.0%} A: {p['prob_away']:.0%}"
        )
