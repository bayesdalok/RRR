"""
11_generate_figures.py

Produces the static PNG figures referenced in the write-up / slide deck:
one file per figure, saved to reports/figures/, built directly from the
same data/model artifacts every other script already produced — nothing
here is recomputed differently from scripts 06-10, it's purely
visualization of their outputs.
"""

import json
from pathlib import Path

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_curve

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"
METRICS = ROOT / "reports" / "metrics"
FIGDIR = ROOT / "reports" / "figures"
FIGDIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
})

CATEGORICAL_COLS = ["field_investigator_id", "sector", "district"]
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


def load_json(name):
    return json.load(open(METRICS / name))


def prep_features(df):
    df = df.copy()
    for c in CATEGORICAL_COLS:
        df[c] = df[c].astype("category")
    df["has_loan_at_origin"] = df["has_loan_at_origin"].astype(float)
    df["data_complete_lag1"] = df["data_complete_lag1"].astype(float)
    df["loan_taken_in_dataset"] = df["loan_taken_in_dataset"].astype(float)
    return df


def feature_cols(df):
    return [c for c in df.columns if c not in EXCLUDE_ALWAYS]


# ---------------------------------------------------------------------------
def fig_risk_ranking(csv_name, title, out_name, color):
    df = pd.read_csv(METRICS / csv_name, index_col=0).sort_values("pooled_estimate")
    fig, ax = plt.subplots(figsize=(7, max(3, 0.35 * len(df))))
    y_pos = np.arange(len(df))
    xerr = np.vstack([
        df["pooled_estimate"] - df["hdi_lower"],
        df["hdi_upper"] - df["pooled_estimate"],
    ])
    ax.barh(y_pos, df["pooled_estimate"], xerr=xerr, color=color, alpha=0.85,
            capsize=3, ecolor="black", height=0.6)
    ax.scatter(df["empirical_rate"], y_pos, color="black", marker="|", s=120, zorder=5,
               label="raw empirical rate")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(df.index)
    ax.set_xlabel("Pooled stress rate (94% credible interval)")
    ax.set_title(title)
    ax.legend(loc="lower right", frameon=False)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    fig.tight_layout()
    fig.savefig(FIGDIR / out_name, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_name}")


def fig_cashflow_vs_baseline():
    baseline = load_json("baseline_metrics.json")
    cashflow = load_json("cashflow_model_metrics.json")
    horizons, splits = ["3", "6"], ["val", "test", "shock_holdout"]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=False)
    for ax, h in zip(axes, horizons):
        base_vals, model_vals = [], []
        for split in splits:
            b = next(r for r in baseline[f"y{h}_persistence"] if r["split"] == split)
            m = cashflow[f"y{h}"][split]
            base_vals.append(b["mae"])
            model_vals.append(m["median_mae"])
        x = np.arange(len(splits))
        w = 0.35
        ax.bar(x - w / 2, base_vals, w, label="Persistence baseline", color="#95a5a6")
        ax.bar(x + w / 2, model_vals, w, label="LightGBM (P50)", color="#3b6fd6")
        ax.set_xticks(x)
        ax.set_xticklabels(splits)
        ax.set_ylabel("MAE (Rs)")
        ax.set_title(f"Y{h} cash flow forecast")
        for i, (b, m) in enumerate(zip(base_vals, model_vals)):
            pct = (b - m) / b
            ax.annotate(f"{pct:+.0%}", (i, max(b, m) * 1.02), ha="center", fontsize=9,
                        color="#2e7d32" if pct > 0 else "#c0392b")
    axes[0].legend(frameon=False)
    fig.suptitle("Cash flow forecast: model vs. persistence baseline (lower is better)")
    fig.tight_layout()
    fig.savefig(FIGDIR / "cashflow_vs_baseline.png", dpi=150)
    plt.close(fig)
    print("Wrote cashflow_vs_baseline.png")


def fig_quantile_calibration():
    cashflow = load_json("cashflow_model_metrics.json")
    fig, ax = plt.subplots(figsize=(6, 5))
    for h, marker in zip(("3", "6"), ("o", "s")):
        for split, color in zip(("val", "test", "shock_holdout"), ("#3b6fd6", "#e67e22", "#c0392b")):
            m = cashflow[f"y{h}"][split]
            ax.scatter([10, 90], [m["p10_empirical_coverage"] * 100, m["p90_empirical_coverage"] * 100],
                       color=color, marker=marker, s=60,
                       label=f"Y{h} {split}" if marker == "o" else None)
    ax.plot([0, 100], [0, 100], "k--", alpha=0.4, label="perfect calibration")
    ax.set_xlabel("Target quantile (%)")
    ax.set_ylabel("Empirical coverage (%)")
    ax.set_title("Quantile calibration: P10/P90 target vs. actual coverage\n(circle=Y3, square=Y6)")
    ax.legend(fontsize=8, frameon=False, ncol=1, loc="upper left", bbox_to_anchor=(1, 1))
    fig.tight_layout()
    fig.savefig(FIGDIR / "quantile_calibration.png", dpi=150)
    plt.close(fig)
    print("Wrote quantile_calibration.png")


def fig_stress_classifier_curves():
    df = prep_features(pd.read_csv(PROCESSED / "splits.csv"))
    cols = feature_cols(df)
    model = lgb.Booster(model_file=str(MODELS / "stress_classifier" / "model.txt"))
    usable = df["stress_label"].notna()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    colors = {"val": "#3b6fd6", "test": "#e67e22", "shock_holdout": "#c0392b"}
    for split, color in colors.items():
        mask = usable & (df["split_y3"] == split)
        X, y = df.loc[mask, cols], df.loc[mask, "stress_label"]
        probs = model.predict(X)
        fpr, tpr, _ = roc_curve(y, probs)
        prec, rec, _ = precision_recall_curve(y, probs)
        axes[0].plot(fpr, tpr, label=split, color=color)
        axes[1].plot(rec, prec, label=split, color=color)
    axes[0].plot([0, 1], [0, 1], "k--", alpha=0.3)
    axes[0].set_xlabel("False positive rate"); axes[0].set_ylabel("True positive rate")
    axes[0].set_title("ROC curve"); axes[0].legend(frameon=False)
    axes[1].set_xlabel("Recall"); axes[1].set_ylabel("Precision")
    axes[1].set_title("Precision-recall curve"); axes[1].legend(frameon=False)
    fig.suptitle("Stress classifier performance by split")
    fig.tight_layout()
    fig.savefig(FIGDIR / "stress_classifier_curves.png", dpi=150)
    plt.close(fig)
    print("Wrote stress_classifier_curves.png")


def fig_feature_importance(model_path, title, out_name, top_n=15):
    model = lgb.Booster(model_file=str(model_path))
    importance = model.feature_importance(importance_type="gain")
    names = model.feature_name()
    order = np.argsort(importance)[::-1][:top_n]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh([names[i] for i in order][::-1], [importance[i] for i in order][::-1], color="#2c3e50")
    ax.set_xlabel("Total gain (feature importance)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(FIGDIR / out_name, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_name}")


def fig_forecast_example():
    df = prep_features(pd.read_csv(PROCESSED / "splits.csv", parse_dates=["month"]))
    cols = feature_cols(df)
    models = {q: lgb.Booster(model_file=str(MODELS / "cashflow_y3" / f"q{int(q*100)}.txt")) for q in (0.1, 0.5, 0.9)}

    # pick one enterprise from test split with a reasonable spread of origins
    candidates = df[(df["split_y3"] == "test") & df["target_y3"].notna()]["enterprise_id"].unique()
    ent_id = candidates[0]
    sub = df[df["enterprise_id"] == ent_id].sort_values("month_index")
    mask = sub["target_y3"].notna()

    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = sub.loc[mask, "month_index"]
    actual = sub.loc[mask, "target_y3"]
    preds = {q: m.predict(sub.loc[mask, cols]) for q, m in models.items()}

    ax.plot(x, actual, "o-", color="#1a1a1a", label="Actual Y3 (forward 3-month sum)")
    ax.plot(x, preds[0.5], "o-", color="#3b6fd6", label="Predicted (P50)")
    ax.fill_between(x, preds[0.1], preds[0.9], color="#3b6fd6", alpha=0.2, label="P10-P90 band")
    ax.axvspan(10, 15, color="orange", alpha=0.1, label="shock window (month_index 10-15)")
    ax.set_xlabel("Origin month_index")
    ax.set_ylabel("3-month forward net cash flow (Rs)")
    ax.set_title(f"Example forecast vs. actual — enterprise {ent_id}")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGDIR / "example_forecast_vs_actual.png", dpi=150)
    plt.close(fig)
    print("Wrote example_forecast_vs_actual.png")


def fig_sector_district_heatmap():
    df = pd.read_csv(PROCESSED / "splits.csv")
    df = df[df["stress_label"].notna()]
    pivot = df.pivot_table(index="sector", columns="district", values="stress_label", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(pivot.values, cmap="Reds", aspect="auto", vmin=0, vmax=pivot.values[~np.isnan(pivot.values)].max())
    ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns, rotation=90, fontsize=7)
    ax.set_yticks(range(len(pivot.index))); ax.set_yticklabels(pivot.index, fontsize=8)
    fig.colorbar(im, ax=ax, label="Observed stress rate", shrink=0.7)
    ax.set_title("Observed stress rate by sector x district (raw, unpooled — sparse cells are noisy)")
    fig.tight_layout()
    fig.savefig(FIGDIR / "sector_district_heatmap.png", dpi=150)
    plt.close(fig)
    print("Wrote sector_district_heatmap.png")


def main():
    fig_risk_ranking("fi_risk_pooled_estimates.csv", "Field investigator portfolio risk (pooled, sector-adjusted)",
                      "fi_risk_ranking.png", "#c0392b")
    fig_risk_ranking("sector_risk_pooled_estimates.csv", "Sector risk (pooled, FI-mix-adjusted)",
                      "sector_risk_ranking.png", "#8e44ad")
    fig_cashflow_vs_baseline()
    fig_quantile_calibration()
    fig_stress_classifier_curves()
    fig_feature_importance(MODELS / "cashflow_y3" / "q50.txt", "Cash flow model (Y3, P50) — top 15 features by gain",
                            "cashflow_feature_importance.png")
    fig_feature_importance(MODELS / "stress_classifier" / "model.txt", "Stress classifier — top 15 features by gain",
                            "stress_classifier_feature_importance.png")
    fig_forecast_example()
    fig_sector_district_heatmap()
    print(f"\nAll figures written to {FIGDIR}")


if __name__ == "__main__":
    main()
