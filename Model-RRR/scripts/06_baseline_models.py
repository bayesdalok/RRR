"""
06_baseline_models.py

Per docs/modeling_roadmap.md §4 step 1: a persistence baseline is mandatory,
not optional, before any gradient-boosted model is trusted. "Persistence"
here = "the next window's total net cash flow equals the horizon-matched
trailing window's total" — e.g. for Y3, predict trailing 3-month sum
(already lag-safe, from script 03's roll_mean_3 x 3) as the forecast for
the next 3 months.

Evaluated on val, test, and shock_holdout (never train — a baseline earning
a good train score by definition, since it's just restating history).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
METRICS = ROOT / "reports" / "metrics"


def evaluate(y_true, y_pred, label):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    naive_mae = mean_absolute_error(y_true, np.zeros_like(y_true))  # "predict zero" as a sanity floor
    return {"split": label, "n": len(y_true), "mae": mae, "rmse": rmse, "mae_vs_predict_zero": mae / naive_mae if naive_mae else None}


def main():
    df = pd.read_csv(PROCESSED / "splits.csv")

    results = {}
    for h in (3, 6):
        target_col = f"target_y{h}"
        pred_col = f"net_cash_flow_roll_mean_{h if h in (3, 6) else 3}"
        # persistence prediction = trailing horizon-month sum = roll_mean_h * h
        pred = df[f"net_cash_flow_roll_mean_{h}"] * h
        usable = df[target_col].notna() & pred.notna()
        split_col = f"split_y{h}"

        horizon_results = []
        for split_name in ["val", "test", "shock_holdout"]:
            mask = usable & (df[split_col] == split_name)
            if mask.sum() == 0:
                continue
            horizon_results.append(evaluate(df.loc[mask, target_col], pred[mask], split_name))
        results[f"y{h}_persistence"] = horizon_results
        print(f"\n--- Y{h} persistence baseline (predict {h}x trailing {h}-month average) ---")
        for r in horizon_results:
            print(f"  {r['split']:>14}: n={r['n']:>5}  MAE={r['mae']:>12,.2f}  RMSE={r['rmse']:>12,.2f}")

    METRICS.mkdir(parents=True, exist_ok=True)
    with open(METRICS / "baseline_metrics.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {METRICS / 'baseline_metrics.json'}")
    print("\nAny model in script 07 that doesn't beat these MAE/RMSE numbers on val/test/shock_holdout isn't earning its complexity.")


if __name__ == "__main__":
    main()
