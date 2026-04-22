"""
model/train.py
Trenuje model XGBoost do przewidywania wyników meczów (H/D/A).

Kluczowe decyzje projektowe:
- Multiclass (3 klasy), nie binary
- Kalibracja Platta (CalibratedClassifierCV) → prawdopodobieństwa działają jako EV
- Walk-forward validation (nie random split) – unika data leakage
- Brier Score jako główna metryka (nie accuracy)
- Calibration plot zapisywany do data/model/calibration.png [v1.3]

Uwaga o accuracy: piłka nożna ma dużą losowość – nawet najlepsze modele
osiągają ~54-58% dla 1X2. Wartość systemu leży w ROI, nie accuracy.
"""
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import brier_score_loss, log_loss
from xgboost import XGBClassifier

from config import DATA_RAW, MODEL_PATH
from model.features import FEATURE_COLS, compute_features

log = logging.getLogger(__name__)


def train_model() -> None:
    """Główna funkcja treningowa."""
    Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)

    csv_path = f"{DATA_RAW}/all_matches.csv"
    if not Path(csv_path).exists():
        log.error(f"Brak danych: {csv_path}. Uruchom najpierw: python main.py fetch")
        return

    df = pd.read_csv(csv_path)
    log.info(f"Wczytano {len(df)} historycznych meczów")

    # Buduj cechy walk-forward (v1.3: forma ważona + Elo)
    X, y = compute_features(df)

    if len(X) < 200:
        log.error(f"Za mało danych treningowych: {len(X)}. Potrzeba min. 200.")
        return

    # league_codes do zapisu w model.pkl
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    league_col = "league" if "league" in df.columns else "League"
    league_codes = {c: i for i, c in enumerate(sorted(df[league_col].dropna().unique()))}

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

    acc          = (preds == y_test).mean()
    bs_h         = brier_score_loss(y_test == 0, proba[:, 0])
    bs_a         = brier_score_loss(y_test == 2, proba[:, 2])
    ll           = log_loss(y_test, proba)
    baseline_acc = (y_test == 0).mean()

    log.info("─── WYNIKI MODELU ───────────────────────────────")
    log.info(f"Accuracy:      {acc:.3f}  (baseline faworyt: {baseline_acc:.3f})")
    log.info(f"Brier (Home):  {bs_h:.4f}  (niższy = lepszy)")
    log.info(f"Brier (Away):  {bs_a:.4f}")
    log.info(f"Log Loss:      {ll:.4f}")
    log.info("─────────────────────────────────────────────────")
    log.info(
        "Uwaga: accuracy 54-58% to norma dla piłki nożnej. "
        "Wartość systemu = ROI z value betów, nie sama accuracy."
    )

    if acc <= baseline_acc:
        log.warning("⚠ Model nie bije baseline! Sprawdź dane i cechy.")
    else:
        log.info(f"✓ Model bije baseline o {acc - baseline_acc:.3f}")

    _simulate_roi(X_test, y_test, proba)
    _save_calibration_plot(y_test, proba)

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
    col_map = [
        (0, "market_prob_h"),
        (1, "market_prob_d"),
        (2, "market_prob_a"),
    ]
    total_staked = 0
    total_return = 0
    bets_placed  = 0

    for i, (_, row) in enumerate(X_test.iterrows()):
        for col_idx, prob_col in col_map:
            market_p = row.get(prob_col, 0)
            if market_p <= 0:
                continue
            model_p = proba[i, col_idx]
            edge    = model_p - market_p
            if edge >= min_edge:
                odds = 1.0 / market_p
                total_staked += 1
                bets_placed  += 1
                if y_test.iloc[i] == col_idx:
                    total_return += odds

    if bets_placed > 0:
        roi = (total_return - total_staked) / total_staked * 100
        log.info(f"Symulacja ROI: {roi:.1f}% na {bets_placed} zakładach")
    else:
        log.info("Brak zakładów spełniających kryteria w symulacji ROI.")


def _save_calibration_plot(y_test, proba) -> None:
    """
    Zapisuje calibration plot do data/model/calibration.png [v1.3].
    Dobra kalibracja = linia blisko przekątnej (predicted ≈ actual).
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 6))
        ax.plot([0, 1], [0, 1], "k--", label="Idealna kalibracja", alpha=0.6)

        labels_map = {0: ("Wygrana gospodarza", "steelblue"),
                      1: ("Remis",              "orange"),
                      2: ("Wygrana gościa",     "crimson")}

        for cls_idx, (label, color) in labels_map.items():
            frac_pos, mean_pred = calibration_curve(
                (y_test == cls_idx).astype(int),
                proba[:, cls_idx],
                n_bins=10,
                strategy="quantile",
            )
            ax.plot(mean_pred, frac_pos, marker="o", label=label, color=color)

        ax.set_xlabel("Średnie przewidywane prawdopodobieństwo")
        ax.set_ylabel("Rzeczywista częstość")
        ax.set_title("Calibration Plot – jakość kalibracji modelu\n"
                     "(im bliżej przekątnej, tym lepsza kalibracja)")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)

        out_path = Path(MODEL_PATH).parent / "calibration.png"
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        log.info(f"✓ Calibration plot zapisany → {out_path}")

    except ImportError:
        log.warning("matplotlib niedostępny – pominięto calibration plot")
    except Exception as exc:
        log.warning(f"Błąd generowania calibration plot: {exc}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    train_model()
