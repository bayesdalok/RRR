"""
10_backtest_against_ground_truth.py

Per docs/modeling_roadmap.md §5: the ONLY script allowed to open
enterprise_ground_truth.csv, used purely to validate the observable
proxies built in scripts 04/08/09 — never to feed anything back upstream.

As documented in script 01's audit and every PROGRESS_LOG entry since,
`enterprise_ground_truth.csv` shares zero enterprise_ids with
monthly_records.csv on this export. This script checks that directly
(rather than assuming yesterday's finding still holds) and, if the join is
still broken, reports that clearly and exits without fabricating numbers —
a script that silently produced "0% correlation" here would look like a
negative result about model quality, when it's actually a data problem
that has nothing to do with the model.
"""

import json
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import pointbiserialr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
METRICS = ROOT / "reports" / "metrics"


def main():
    gt = pd.read_csv(RAW / "enterprise_ground_truth.csv")
    df = pd.read_csv(PROCESSED / "splits.csv")

    overlap = set(gt["enterprise_id"]) & set(df["enterprise_id"])
    report = {
        "gt_enterprise_count": int(gt["enterprise_id"].nunique()),
        "panel_enterprise_count": int(df["enterprise_id"].nunique()),
        "overlap_count": len(overlap),
    }

    if len(overlap) == 0:
        report["status"] = "BLOCKED"
        report["reason"] = (
            "enterprise_ground_truth.csv shares 0 enterprise_ids with the monthly "
            "panel — same finding as script 01, re-confirmed here rather than assumed. "
            "No backtest can be run. This is a data problem (see docs/PROGRESS_LOG.md), "
            "not a statement about model quality."
        )
        print(f"BLOCKED — {report['reason']}")
        METRICS.mkdir(parents=True, exist_ok=True)
        with open(METRICS / "ground_truth_backtest_report.json", "w") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote {METRICS / 'ground_truth_backtest_report.json'} (status: BLOCKED)")
        sys.exit(1)

    # --- If the join is ever fixed, this is the backtest that should run ---
    merged = df.merge(gt, on="enterprise_id", how="inner")

    stress_corr = pointbiserialr(
        merged["scripted_stress"].astype(int), merged["stress_label"].fillna(0).astype(int)
    )
    report["scripted_stress_vs_observable_label_correlation"] = float(stress_corr.correlation)
    report["scripted_stress_vs_observable_label_pvalue"] = float(stress_corr.pvalue)

    resid_y3 = merged["target_y3"] - merged["net_cash_flow_roll_mean_3"] * 3
    perf_corr = resid_y3.corr(merged["performance_multiplier"])
    report["forecast_residual_vs_performance_multiplier_correlation"] = float(perf_corr)
    report["status"] = "OK"

    METRICS.mkdir(parents=True, exist_ok=True)
    with open(METRICS / "ground_truth_backtest_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
