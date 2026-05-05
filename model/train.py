"""
model/train.py
Trenuje ensemble XGBoost + LightGBM do przewidywania wyników meczów (H/D/A).

v1.6 zmiany:
  - Optuna hyperparameter tuning z expanding window CV (TimeSeriesSplit n_splits=3)
    Poprzednio: stałe parametry. Teraz: 30 prób Optuna na X_train_full.
    Expanding window gwarantuje brak data leakage w tuningu.
  - LightGBM jako drugi model ensemble (jeśli zainstalowany)
    Oba modele kalibrowane osobno (Platt, cv='prefit') przed uśrednieniem.
    Uśrednianie nieskalibrowanych prob = błędne EV — stąd osobna kalibracja.
  - sample_weight dla remisów: klasa D wagowana × DRAW_CLASS_WEIGHT (domyślnie 1.5)
    Remisy są najtrudniejsze do kalibracji — wyższa waga poprawia ich predykcję.
  - model.pkl format v1.6: {"model_type": "ensemble", "models": [...], ...}
    Backward compat: predict.py obsługuje też stary format {"model": ...}

Kluczowe decyzje projektowe (niezmienione):
  - Walk-forward validation (nie random split) — unika data leakage w treningu
  - Kalibracja Platta z temporal split (cv='prefit') — bez data leakage w kalibracji
  - Brier Score jako główna metryka (nie accuracy)
  - Calibration plot zapisywany do data/model/calibration.png

Uwaga o accuracy: ~54-58% dla 1X2 to norma nawet dla najlepszych modeli.
Wartość systemu leży w długoterminowym ROI z value betów, nie accuracy.
"""
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

import config
from config import DATA_RAW, MODEL_PATH, DRAW_CLASS_WEIGHT, OPTUNA_TRIALS
from model.features import FEATURE_COLS, compute_features

log = logging.getLogger(__name__)

# ── Opcjonalny LightGBM ───────────────────────────────────────────────────────
try:
    from lightgbm import LGBMClassifier
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False
    log.warning("lightgbm niedostępny — ensemble będzie tylko XGBoost. "
                "Dodaj lightgbm do requirements.txt.")

# ── Opcjonalna Optuna ─────────────────────────────────────────────────────────
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _OPTUNA_AVAILABLE = True
except ImportError:
    _OPTUNA_AVAILABLE = False
    log.warning("optuna niedostępna — używam domyślnych parametrów XGBoost. "
                "Dodaj optuna do requirements.txt.")


# ── Domyślne parametry XGBoost (gdy Optuna wyłączona / niedostępna) ───────────

def _default_xgb_params() -> dict:
    return {
        "n_estimators":     300,
        "max_depth":        4,
        "learning_rate":    0.05,
        "subsample":        0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "gamma":            0.0,
        "reg_alpha":        0.0,
        "reg_lambda":       1.0,
    }


# ── Optuna tuning z expanding window CV ──────────────────────────────────────

def _tune_hyperparams(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    n_trials: int = OPTUNA_TRIALS,
) -> dict:
    """
    Optuna hyperparameter tuning XGBoost z expanding window CV.

    TimeSeriesSplit(n_splits=3) — dane chronologiczne, brak data leakage.
    Każdy fold to expanding window: więcej danych w każdej iteracji.

    Parametry
    ---------
    X_train : pełny zbiór treningowy (X_base + X_cal, 85% danych)
    y_train : odpowiadające etykiety
    n_trials: liczba prób Optuna (z config.OPTUNA_TRIALS)

    Zwraca
    ------
    Słownik najlepszych hiperparametrów XGBoost.
    """
    if not _OPTUNA_AVAILABLE or n_trials <= 0:
        log.info("Optuna wyłączona — używam domyślnych parametrów XGBoost.")
        return _default_xgb_params()

    log.info(f"Optuna: rozpoczynam tuning ({n_trials} prób, TimeSeriesSplit n_splits=3)...")
    tscv = TimeSeriesSplit(n_splits=3)

    def objective(trial: "optuna.Trial") -> float:
        params = {
            "n_estimators":     trial.suggest_int("n_estimators", 100, 500),
            "max_depth":        trial.suggest_int("max_depth", 3, 7),
            "learning_rate":    trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "subsample":        trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 3, 15),
            "gamma":            trial.suggest_float("gamma", 0.0, 1.0),
            "reg_alpha":        trial.suggest_float("reg_alpha", 0.0, 1.0),
            "reg_lambda":       trial.suggest_float("reg_lambda", 0.5, 2.0),
        }

        scores = []
        for train_idx, val_idx in tscv.split(X_train):
            X_tr  = X_train.iloc[train_idx]
            X_val = X_train.iloc[val_idx]
            y_tr  = y_train.iloc[train_idx]
            y_val = y_train.iloc[val_idx]

            # sample_weight dla remisów — identycznie jak w finalnym treningu
            w_tr = np.where(y_tr == 1, DRAW_CLASS_WEIGHT, 1.0)

            clf = XGBClassifier(
                **params,
                eval_metric="mlogloss",
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )
            clf.fit(X_tr, y_tr, sample_weight=w_tr)
            proba = clf.predict_proba(X_val)
            scores.append(log_loss(y_val, proba))

        return float(np.mean(scores))

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    log.info(f"Optuna: najlepszy log_loss = {study.best_value:.4f}")
    log.info(f"Najlepsze parametry XGB: {best}")
    return best


# ── Trening pojedynczego modelu ───────────────────────────────────────────────

def _fit_and_calibrate_xgb(
    X_base: pd.DataFrame,
    y_base: pd.Series,
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
    params: dict,
) -> CalibratedClassifierCV:
    """Trenuje XGBoost z tuned params + kalibruje Plattem (temporal split)."""
    w_base = np.where(y_base == 1, DRAW_CLASS_WEIGHT, 1.0)

    base = XGBClassifier(
        **params,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    base.fit(X_base, y_base, sample_weight=w_base)

    cal = CalibratedClassifierCV(base, cv="prefit", method="sigmoid")
    cal.fit(X_cal, y_cal)
    return cal


def _fit_and_calibrate_lgb(
    X_base: pd.DataFrame,
    y_base: pd.Series,
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
    xgb_params: dict,
) -> "CalibratedClassifierCV":
    """
    Trenuje LightGBM + kalibruje Plattem.
    Używa zbliżonych parametrów do XGB (n_estimators, learning_rate, subsample)
    ale z LGB-specyficzną architekturą (num_leaves zamiast max_depth).
    """
    w_base = np.where(y_base == 1, DRAW_CLASS_WEIGHT, 1.0)

    base = LGBMClassifier(
        n_estimators     = xgb_params.get("n_estimators", 300),
        learning_rate    = xgb_params.get("learning_rate", 0.05),
        num_leaves       = 31,    # LGB domyślny – konserwatywny, dobra generalizacja
        subsample        = xgb_params.get("subsample", 0.8),
        colsample_bytree = xgb_params.get("colsample_bytree", 0.8),
        min_child_samples= 20,    # LGB odpowiednik min_child_weight
        reg_alpha        = xgb_params.get("reg_alpha", 0.0),
        reg_lambda       = xgb_params.get("reg_lambda", 1.0),
        random_state     = 42,
        n_jobs           = -1,
        verbose          = -1,
        objective        = "multiclass",
        num_class        = 3,
    )
    base.fit(X_base, y_base, sample_weight=w_base)

    cal = CalibratedClassifierCV(base, cv="prefit", method="sigmoid")
    cal.fit(X_cal, y_cal)
    return cal


# ── Główna funkcja treningowa ─────────────────────────────────────────────────

def train_model() -> None:
    """
    Główna funkcja treningowa v1.6.

    Pipeline:
      1. Wczytaj dane, oblicz cechy
      2. Optuna tuning XGB (expanding window CV)
      3. Trenuj XGB + LGB z tuned params + sample_weight
      4. Kalibruj oba osobno (Platt, temporal split)
      5. Ewaluuj ensemble na hold-out
      6. Zapisz pkl w formacie v1.6 (model_type="ensemble")
    """
    Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)

    csv_path = f"{DATA_RAW}/all_matches.csv"
    if not Path(csv_path).exists():
        log.error(f"Brak danych: {csv_path}. Uruchom najpierw: python main.py fetch")
        return

    df = pd.read_csv(csv_path)
    log.info(f"Wczytano {len(df)} historycznych meczów")

    X, y = compute_features(df)

    if len(X) < 200:
        log.error(f"Za mało danych treningowych: {len(X)}. Potrzeba min. 200.")
        return

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    league_col   = "league" if "league" in df.columns else "League"
    league_codes = {c: i for i, c in enumerate(sorted(df[league_col].dropna().unique()))}

    # ── Splits (chronologiczne — walk-forward) ────────────────────────────────
    split_main = int(len(X) * 0.85)
    X_train_full, X_test = X.iloc[:split_main], X.iloc[split_main:]
    y_train_full, y_test = y.iloc[:split_main], y.iloc[split_main:]

    # 80/20 wewnątrz train_full → base (trening XGB/LGB) | cal (Platt)
    split_cal = int(len(X_train_full) * 0.80)
    X_base, X_cal = X_train_full.iloc[:split_cal], X_train_full.iloc[split_cal:]
    y_base, y_cal = y_train_full.iloc[:split_cal], y_train_full.iloc[split_cal:]

    log.info(
        f"Splity — bazowy: {len(X_base)}, kalibracja Platta: {len(X_cal)}, "
        f"test hold-out: {len(X_test)}"
    )

    # ── Optuna tuning na X_train_full ─────────────────────────────────────────
    best_params = _tune_hyperparams(X_train_full, y_train_full, n_trials=OPTUNA_TRIALS)

    # ── Trening i kalibracja XGBoost ──────────────────────────────────────────
    log.info("Trening XGBoost...")
    cal_xgb = _fit_and_calibrate_xgb(X_base, y_base, X_cal, y_cal, best_params)

    # ── Trening i kalibracja LightGBM (jeśli dostępny) ────────────────────────
    models = [cal_xgb]
    model_names = ["XGBoost"]

    if _LGB_AVAILABLE:
        log.info("Trening LightGBM...")
        cal_lgb = _fit_and_calibrate_lgb(X_base, y_base, X_cal, y_cal, best_params)
        models.append(cal_lgb)
        model_names.append("LightGBM")
    else:
        log.info("LightGBM niedostępny — ensemble tylko z XGBoost.")

    log.info(f"Ensemble: {' + '.join(model_names)} (równe wagi)")

    # ── Ewaluacja ensemble na hold-out ────────────────────────────────────────
    proba = np.mean([m.predict_proba(X_test) for m in models], axis=0)
    preds = np.argmax(proba, axis=1)

    acc          = (preds == y_test.values).mean()
    bs_h         = brier_score_loss(y_test == 0, proba[:, 0])
    bs_a         = brier_score_loss(y_test == 2, proba[:, 2])
    ll           = log_loss(y_test, proba)
    baseline_acc = (y_test == 0).mean()

    log.info("─── WYNIKI ENSEMBLE ─────────────────────────────")
    log.info(f"Modele:        {' + '.join(model_names)}")
    log.info(f"Accuracy:      {acc:.3f}  (baseline faworyt: {baseline_acc:.3f})")
    log.info(f"Brier (Home):  {bs_h:.4f}  (niższy = lepszy, <0.20 bardzo dobry)")
    log.info(f"Brier (Away):  {bs_a:.4f}")
    log.info(f"Log Loss:      {ll:.4f}")
    log.info("─────────────────────────────────────────────────")

    if acc <= baseline_acc:
        log.warning("⚠ Ensemble nie bije baseline! Sprawdź dane i cechy.")
    else:
        log.info(f"✓ Ensemble bije baseline o {acc - baseline_acc:.3f}")

    # Feature importance z XGB (pierwszego modelu)
    _log_feature_importance(cal_xgb.calibrated_classifiers_[0].estimator)
    _simulate_roi(X_test, y_test, proba)
    _save_calibration_plot(y_test, proba, model_names)

    # ── Zapis pkl (format v1.6) ───────────────────────────────────────────────
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({
            "model_type":     "ensemble",
            "models":         models,
            "model_names":    model_names,
            "weights":        [1.0 / len(models)] * len(models),
            "feature_cols":   FEATURE_COLS,
            "league_codes":   league_codes,
            "best_params_xgb": best_params,
            "metrics": {
                "accuracy":    float(acc),
                "baseline":    float(baseline_acc),
                "brier_h":     float(bs_h),
                "brier_a":     float(bs_a),
                "log_loss":    float(ll),
                "n_models":    len(models),
                "draw_weight": DRAW_CLASS_WEIGHT,
                "optuna_trials": OPTUNA_TRIALS,
            },
        }, f)

    log.info(f"✓ Ensemble zapisany → {MODEL_PATH}  ({len(models)} modeli)")


# ── Narzędzia pomocnicze ──────────────────────────────────────────────────────

def _log_feature_importance(base_model: XGBClassifier) -> None:
    """Loguje top-8 cech według feature importance XGBoost."""
    try:
        importances = base_model.feature_importances_
        pairs = sorted(zip(FEATURE_COLS, importances), key=lambda x: x[1], reverse=True)
        log.info("─── FEATURE IMPORTANCE (top 8) ──────────────────")
        for name, imp in pairs[:8]:
            bar = "█" * int(imp * 200)
            log.info(f"  {name:<22} {imp:.4f}  {bar}")
        log.info("─────────────────────────────────────────────────")
    except Exception as exc:
        log.warning(f"Nie udało się zalogować feature importance: {exc}")


def _simulate_roi(X_test, y_test, proba, min_edge: float = 0.05) -> None:
    """
    Symulacja value betting na danych testowych.
    Kurs bukmachera: fair_odds / 1.05 (~5% overround).
    """
    total_staked = 0
    total_return = 0
    bets_placed  = 0

    col_map = [
        (0, "market_prob_h"),
        (1, "market_prob_d"),
        (2, "market_prob_a"),
    ]

    for i, (_, row) in enumerate(X_test.iterrows()):
        for col_idx, prob_col in col_map:
            market_p = row.get(prob_col, 0)
            if market_p <= 0:
                continue
            model_p = proba[i, col_idx]
            edge    = model_p - market_p

            if edge >= min_edge:
                fair_odds      = 1.0 / market_p
                bookmaker_odds = fair_odds / 1.05

                total_staked += 1
                bets_placed  += 1
                if y_test.iloc[i] == col_idx:
                    total_return += bookmaker_odds

    if bets_placed > 0:
        roi = (total_return - total_staked) / total_staked * 100
        log.info(
            f"Symulacja ROI (kursy z ~5% marżą): "
            f"{roi:.1f}% na {bets_placed} zakładach"
        )
    else:
        log.info("Brak zakładów spełniających kryteria w symulacji ROI.")


def _save_calibration_plot(y_test, proba, model_names: list) -> None:
    """Zapisuje calibration plot do data/model/calibration.png."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 6))
        ax.plot([0, 1], [0, 1], "k--", label="Idealna kalibracja", alpha=0.6)

        labels_map = {
            0: ("Wygrana gospodarza", "steelblue"),
            1: ("Remis",              "orange"),
            2: ("Wygrana gościa",     "crimson"),
        }

        for cls_idx, (label, color) in labels_map.items():
            frac_pos, mean_pred = calibration_curve(
                (y_test == cls_idx).astype(int),
                proba[:, cls_idx],
                n_bins=10,
                strategy="quantile",
            )
            ax.plot(mean_pred, frac_pos, marker="o", label=label, color=color)

        ensemble_label = " + ".join(model_names)
        ax.set_xlabel("Średnie przewidywane prawdopodobieństwo")
        ax.set_ylabel("Rzeczywista częstość")
        ax.set_title(
            f"Calibration Plot — Ensemble: {ensemble_label}\n"
            "(im bliżej przekątnej, tym lepsza kalibracja)"
        )
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)

        out_path = Path(MODEL_PATH).parent / "calibration.png"
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        log.info(f"✓ Calibration plot zapisany → {out_path}")

    except ImportError:
        log.warning("matplotlib niedostępny — pominięto calibration plot")
    except Exception as exc:
        log.warning(f"Błąd generowania calibration plot: {exc}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    train_model()
