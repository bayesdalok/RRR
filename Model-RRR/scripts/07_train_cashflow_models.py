"""
07_train_cashflow_models.py

Per docs/modeling_roadmap.md §4 step 2: one LightGBM quantile-regression
model per horizon (Y3, Y6), trained at P10/P50/P90 so the low tail (the
number that actually matters for risk-flagging) is available, not just a
median that can look fine while the downside is ugly.

Feature set is every column added by scripts 03/04 EXCEPT anything that's
a same-month function of income/expenses/net_cash_flow at the origin
itself (per roadmap §0) — i.e. only lag/rolling/trend/calendar columns,
plus the two current-origin facts justified in script 03
(emi_due_at_origin, has_loan_at_origin), plus field_investigator_id as a
categorical. Sector/district features are absent because they're blocked
(script 01) — this is a real ceiling on how much this model can currently
learn, not a modeling choice.
"""

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"
METRICS = ROOT / "reports" / "metrics"

QUANTILES = [0.1, 0.5, 0.9]

# Columns that are same-month functions of the target and must NEVER be
# features (roadmap §0), plus identifiers/targets/split bookkeeping.
EXCLUDE_ALWAYS = {
    "enterprise_id", "month", "month_index", "name", "place",
    "income", "expenses", "net_cash_flow", "savings_balance",
    "has_loan", "emi_due", "repayment_status",
    "upi_inflow_txn_count", "upi_inflow_txn_volume", "data_complete",
    "upi_outflow_txn_count", "upi_outflow_txn_volume",
    "loan_repayment_collected_upi",
    "target_y3", "target_y6", "stress_label",
    "chronological_split", "split_y3", "split_y6",
    "shock_window_overlap_y3", "shock_window_overlap_y6",
}
CATEGORICAL_COLS = ["field_investigator_id", "sector", "district"]


def pinball_loss(y_true, y_pred, quantile):
    diff = y_true - y_pred
    return np.mean(np.maximum(quantile * diff, (quantile - 1) * diff))


def get_feature_cols(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in EXCLUDE_ALWAYS]


def main():
    df = pd.read_csv(PROCESSED / "splits.csv")
    for c in CATEGORICAL_COLS:
        df[c] = df[c].astype("category")
    df["has_loan_at_origin"] = df["has_loan_at_origin"].astype(float)
    df["data_complete_lag1"] = df["data_complete_lag1"].astype(float)
    df["loan_taken_in_dataset"] = df["loan_taken_in_dataset"].astype(float)
    df["has_loan_at_origin"] = df["has_loan_at_origin"].astype(float)
    # data_complete is boolean in the source panel; shifting it in script 03
    # mixes True/False with NaN for the first lag of each enterprise, which
    # pandas stores as dtype=object rather than float — LightGBM rejects
    # object columns outright, so cast explicitly.
    df["data_complete_lag1"] = df["data_complete_lag1"].astype(float)

    feature_cols = get_feature_cols(df)
    print(f"Feature columns ({len(feature_cols)}): {feature_cols}")

    all_metrics = {}
    for h in (3, 6):
        target_col = f"target_y{h}"
        split_col = f"split_y{h}"
        usable = df[target_col].notna()

        train_mask = usable & (df[split_col] == "train")
        X_train, y_train = df.loc[train_mask, feature_cols], df.loc[train_mask, target_col]
        print(f"\n=== Horizon {h}: training on {len(X_train)} rows ===")

        horizon_metrics = {}
        models = {}
        for q in QUANTILES:
            model = lgb.LGBMRegressor(
                objective="quantile", alpha=q,
                n_estimators=300, learning_rate=0.05, num_leaves=15,
                min_child_samples=20, random_state=42, verbose=-1,
            )
            model.fit(X_train, y_train, categorical_feature=CATEGORICAL_COLS)
            models[q] = model

        MODELS_DIR = MODELS / f"cashflow_y{h}"
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        for q, model in models.items():
            model.booster_.save_model(str(MODELS_DIR / f"q{int(q*100)}.txt"))

        for split_name in ["val", "test", "shock_holdout"]:
            mask = usable & (df[split_col] == split_name)
            if mask.sum() == 0:
                continue
            X_eval, y_eval = df.loc[mask, feature_cols], df.loc[mask, target_col]
            preds = {q: models[q].predict(X_eval) for q in QUANTILES}

            median_mae = mean_absolute_error(y_eval, preds[0.5])
            median_rmse = mean_squared_error(y_eval, preds[0.5]) ** 0.5
            pinballs = {q: pinball_loss(y_eval.values, preds[q], q) for q in QUANTILES}
            # calibration: fraction of true values actually below the P10 prediction
            # (should be close to 10% if the quantile model is well-calibrated)
            p10_coverage = float(np.mean(y_eval.values < preds[0.1]))
            p90_coverage = float(np.mean(y_eval.values < preds[0.9]))

            horizon_metrics[split_name] = {
                "n": int(mask.sum()),
                "median_mae": median_mae,
                "median_rmse": median_rmse,
                "pinball_loss": pinballs,
                "p10_empirical_coverage": p10_coverage,
                "p90_empirical_coverage": p90_coverage,
            }
            print(f"  {split_name:>14}: n={mask.sum():>5}  median MAE={median_mae:>12,.2f}  "
                  f"median RMSE={median_rmse:>12,.2f}  P10 coverage={p10_coverage:.1%} (target ~10%)  "
                  f"P90 coverage={p90_coverage:.1%} (target ~90%)")

        all_metrics[f"y{h}"] = horizon_metrics

    METRICS.mkdir(parents=True, exist_ok=True)
    with open(METRICS / "cashflow_model_metrics.json", "w") as f:
        json.dump(all_metrics, f, indent=2, default=float)
    print(f"\nWrote {METRICS / 'cashflow_model_metrics.json'} and models/cashflow_y{{3,6}}/")


if __name__ == "__main__":
    main()
