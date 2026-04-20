"""
model/train.py
Trenuje model XGBoost do przewidywania wyników meczów (H/D/A).

Kluczowe decyzje projektowe:
- Multiclass (3 klasy), nie binary
- Kalibracja Platta (CalibratedClassifierCV) → prawdopodobieństwa działają jako EV
- Walk-forward validation (nie random split) – unika data leakage
- Brier Score jako główna metryka (nie accuracy)
"""
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import brier_score_loss, log_loss
from xgboost import XGBClassifier

from config import DATA_RAW, FORM_WINDOW, MODEL_PATH
from model.features import FEATURE_COLS, _form, _h2h, remove_margin

log = logging.getLogger(__name__)

RESULT_MAP = {"H": 0, "D": 1, "A": 2}


def prepare_training_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, dict]:
    """
    Buduje cechy dla każdego historycznego meczu.
    Używa tylko danych PRZED datą meczu (walk-forward).
    """
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTR"])
    df = df[df["FTR"].isin(["H", "D", "A"])].sort_values("Date").reset_index(drop=True)
    df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce").fillna(0)
    df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce").fillna(0)
    df["Result"] = df["FTR"].map(RESULT_MAP)

    league_codes = {c: i for i, c in enumerate(sorted(df["League"].unique()))}
    rows = []

    log.info(f"Przetwarzam {len(df)} meczów...")

    for idx in range(len(df)):
        row = df.iloc[idx]
        df_before = df.iloc[:idx]  # tylko dane PRZED tym meczem

        if len(df_before) < FORM_WINDOW * 3:
            continue  # za mało historii

        lcode = row["League"]
        df_lg = df_before[df_before["League"] == lcode]

        hf  = _form(df_lg, row["HomeTeam"], row["Date"])
        af  = _form(df_lg, row["AwayTeam"], row["Date"])
        h2h = _h2h(df_lg, row["HomeTeam"], row["AwayTeam"], row["Date"])

        # Kursy historyczne (Bet365)
        has_odds = all(c in df.columns for c in ["B365H", "B365D", "B365A"])
        if has_odds and pd.notna(row.get("B365H")) and float(row.get("B365H", 0)) > 1.0:
            mh, md, ma = remove_margin(row["B365H"], row["B365D"], row["B365A"])
            oh, od, oa = float(row["B365H"]), float(row["B365D"]), float(row["B365A"])
        else:
            mh, md, ma = 0.45, 0.27, 0.28
            oh, od, oa = 2.2, 3.5, 3.5

        rows.append({
            "league_encoded":    league_codes.get(lcode, 0),
            "home_form_pts":     hf["form_pts"],
            "home_form_gf":      hf["form_gf"],
            "home_form_ga":      hf["form_ga"],
            "home_form_wins":    hf["form_wins"],
            "away_form_pts":     af["form_pts"],
            "away_form_gf":      af["form_gf"],
            "away_form_ga":      af["form_ga"],
            "away_form_wins":    af["form_wins"],
            "pts_diff":          hf["form_pts"] - af["form_pts"],
            "gf_diff":           hf["form_gf"]  - af["form_gf"],
            "ga_diff":           hf["form_ga"]  - af["form_ga"],
            "h2h_home_wins":     h2h["h2h_home_wins"],
            "h2h_draws":         h2h["h2h_draws"],
            "h2h_away_wins":     h2h["h2h_away_wins"],
            "market_prob_home":  mh,
            "market_prob_draw":  md,
            "market_prob_away":  ma,
            "result":            row["Result"],
        })

    fdf = pd.DataFrame(rows).dropna()
    X = fdf[FEATURE_COLS]
    y = fdf["result"]

    log.info(f"Dataset: {len(X)} rekordów | H={sum(y==0)} D={sum(y==1)} A={sum(y==2)}")
    return X, y, league_codes


def train_model() -> None:
    """Główna funkcja treningowa."""
    Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)

    # Wczytaj dane
    csv_path = f"{DATA_RAW}/all_matches.csv"
    if not Path(csv_path).exists():
        log.error(f"Brak danych: {csv_path}. Uruchom najpierw: python main.py fetch")
        return

    df = pd.read_csv(csv_path)
    log.info(f"Wczytano {len(df)} historycznych meczów")

    X, y, league_codes = prepare_training_data(df)

    if len(X) < 200:
        log.error(f"Za mało danych treningowych: {len(X)}. Potrzeba min. 200.")
        return

    # Walk-forward split: ostatnie 15% jako test (nie random!)
    split = int(len(X) * 0.85)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    log.info(f"Train: {len(X_train)}, Test: {len(X_test)}")

    # XGBoost
    base = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )

    # Kalibracja Platta – kluczowa dla value bettingu!
    model = CalibratedClassifierCV(base, cv=5, method="sigmoid")
    model.fit(X_train, y_train)

    # ── Ewaluacja ────────────────────────────────────────────────────────────
    proba = model.predict_proba(X_test)
    preds = model.predict(X_test)

    acc     = (preds == y_test).mean()
    bs_h    = brier_score_loss(y_test == 0, proba[:, 0])
    bs_a    = brier_score_loss(y_test == 2, proba[:, 2])
    ll      = log_loss(y_test, proba)

    # Baseline: zawsze typuj wygraną gospodarza
    baseline_acc = (y_test == 0).mean()

    log.info("─── WYNIKI MODELU ───────────────────────────────")
    log.info(f"Accuracy:      {acc:.3f}  (baseline faworyt: {baseline_acc:.3f})")
    log.info(f"Brier (Home):  {bs_h:.4f}  (niższy = lepszy)")
    log.info(f"Brier (Away):  {bs_a:.4f}")
    log.info(f"Log Loss:      {ll:.4f}")
    log.info("─────────────────────────────────────────────────")

    if acc <= baseline_acc:
        log.warning("⚠ Model nie bije baseline! Sprawdź dane i cechy.")
    else:
        log.info(f"✓ Model bije baseline o {acc - baseline_acc:.3f}")

    # ── Symulacja ROI na danych testowych ────────────────────────────────────
    _simulate_roi(X_test, y_test, proba)

    # ── Zapis ────────────────────────────────────────────────────────────────
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({
            "model":        model,
            "feature_cols": FEATURE_COLS,
            "league_codes": league_codes,
            "metrics": {
                "accuracy": float(acc),
                "baseline": float(baseline_acc),
                "brier_h":  float(bs_h),
                "log_loss": float(ll),
            },
        }, f)

    log.info(f"✓ Model zapisany → {MODEL_PATH}")


def _simulate_roi(X_test, y_test, proba, min_edge: float = 0.05) -> None:
    """Symulacja prostego value betting na danych testowych."""
    outcomes = [
        {"col": 0, "label": "H", "odds_col": "market_prob_home"},
        {"col": 1, "label": "D", "odds_col": "market_prob_draw"},
        {"col": 2, "label": "A", "odds_col": "market_prob_away"},
    ]

    total_staked = 0
    total_return = 0
    bets_placed  = 0

    for i, (_, row) in enumerate(X_test.iterrows()):
        for o in outcomes:
            model_p  = proba[i, o["col"]]
            market_p = row[o["odds_col"]]
            if market_p <= 0:
                continue
            odds = 1.0 / market_p
            edge = model_p - market_p

            if edge >= min_edge:
                total_staked += 1
                bets_placed  += 1
                if y_test.iloc[i] == o["col"]:
                    total_return += odds

    if bets_placed > 0:
        roi = (total_return - total_staked) / total_staked * 100
        log.info(f"Symulacja ROI: {roi:.1f}% na {bets_placed} zakładach")
    else:
        log.info("Brak zakładów spełniających kryteria w symulacji ROI.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    train_model()
