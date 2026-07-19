"""
08_train_stress_classifier.py

Per docs/modeling_roadmap.md §4 step 3: classifier trained against the
observable stress_label from script 04 (built from Y3 shortfall + forward
missed/late repayment — never from scripted_stress, which isn't joinable
anyway per script 01). Same feature set and exclusion list as script 07,
plus PR-AUC as the headline metric since positives are a minority class.
"""

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models" / "stress_classifier"
METRICS = ROOT / "reports" / "metrics"

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


def main():
    df = pd.read_csv(PROCESSED / "splits.csv")
    for c in CATEGORICAL_COLS:
        df[c] = df[c].astype("category")
    df["has_loan_at_origin"] = df["has_loan_at_origin"].astype(float)
    df["data_complete_lag1"] = df["data_complete_lag1"].astype(float)
    df["loan_taken_in_dataset"] = df["loan_taken_in_dataset"].astype(float)

    feature_cols = [c for c in df.columns if c not in EXCLUDE_ALWAYS]

    # stress_label was built alongside target_y3 in script 04, so it's
    # subject to the same right-censoring — use split_y3 for train/val/test/
    # shock_holdout membership.
    usable = df["stress_label"].notna()
    split_col = "split_y3"

    train_mask = usable & (df[split_col] == "train")
    X_train, y_train = df.loc[train_mask, feature_cols], df.loc[train_mask, "stress_label"]
    print(f"Training on {len(X_train)} rows, positive rate {y_train.mean():.1%}")

    model = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.05, num_leaves=15,
        min_child_samples=20, random_state=42, verbose=-1,
        class_weight="balanced",
    )
    model.fit(X_train, y_train, categorical_feature=CATEGORICAL_COLS)

    MODELS.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(MODELS / "model.txt"))

    results = {}
    for split_name in ["val", "test", "shock_holdout"]:
        mask = usable & (df[split_col] == split_name)
        if mask.sum() == 0:
            continue
        X_eval, y_eval = df.loc[mask, feature_cols], df.loc[mask, "stress_label"]
        probs = model.predict_proba(X_eval)[:, 1]

        pr_auc = average_precision_score(y_eval, probs)
        try:
            roc_auc = roc_auc_score(y_eval, probs)
        except ValueError:
            roc_auc = None  # only one class present in this split

        precision, recall, thresholds = precision_recall_curve(y_eval, probs)
        # report precision/recall at the threshold that flags the top 20% by
        # predicted probability — a FI can realistically follow up on a
        # top-fifth watchlist, not a full ranked list
        k = max(1, int(0.2 * len(probs)))
        top_k_idx = np.argsort(probs)[-k:]
        top_k_precision = y_eval.values[top_k_idx].mean()

        results[split_name] = {
            "n": int(mask.sum()),
            "positive_rate": float(y_eval.mean()),
            "pr_auc": float(pr_auc),
            "roc_auc": float(roc_auc) if roc_auc is not None else None,
            "precision_at_top_20pct": float(top_k_precision),
        }
        print(f"  {split_name:>14}: n={mask.sum():>5}  positive_rate={y_eval.mean():.1%}  "
              f"PR-AUC={pr_auc:.3f}  ROC-AUC={roc_auc if roc_auc is None else f'{roc_auc:.3f}'}  "
              f"precision@top20%={top_k_precision:.1%}")

    METRICS.mkdir(parents=True, exist_ok=True)
    with open(METRICS / "stress_classifier_metrics.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {METRICS / 'stress_classifier_metrics.json'} and {MODELS / 'model.txt'}")
    print("\nNo scripted_stress backtest here — that file doesn't join to this panel (script 01). "
          "PR-AUC/precision above are against the observable proxy label only, not validated ground truth.")


if __name__ == "__main__":
    main()
