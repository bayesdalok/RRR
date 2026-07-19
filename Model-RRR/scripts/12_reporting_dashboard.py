"""
12_reporting_dashboard.py

Assembles every prior script's output into one static HTML report. Now
includes the sector-level risk view and real ground-truth backtest
numbers, both blocked in the previous (PDF-sourced) run of this pipeline.
Still a static single-file report by design — no server, no external JS —
so it opens directly in a browser.
"""

import base64
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "reports" / "metrics"
FIGDIR = ROOT / "reports" / "figures"
OUT = ROOT / "reports" / "rural_risk_radar_dashboard.html"


def load_json(name):
    path = METRICS / name
    return json.load(open(path)) if path.exists() else None


def img_tag(filename, alt=""):
    path = FIGDIR / filename
    if not path.exists():
        return f"<p><em>(figure {filename} not found — run scripts/12_generate_figures.py)</em></p>"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="max-width:100%;margin:10px 0"/>'


def svg_bar_chart(labels, values, title, color="#3b6fd6", value_fmt="{:.1%}"):
    width, bar_h, gap, left_pad = 680, 20, 8, 130
    height = len(labels) * (bar_h + gap) + 40
    max_val = max(values) if values else 1
    bars = []
    for i, (lbl, val) in enumerate(zip(labels, values)):
        y = 30 + i * (bar_h + gap)
        w = (val / max_val) * (width - left_pad - 60) if max_val > 0 else 0
        bars.append(
            f'<text x="0" y="{y + bar_h - 5}" font-size="12" font-family="monospace">{lbl}</text>'
            f'<rect x="{left_pad}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{color}" rx="3"/>'
            f'<text x="{left_pad + w + 6}" y="{y + bar_h - 5}" font-size="12" font-family="monospace">{value_fmt.format(val)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:680px">'
        f'<text x="0" y="16" font-size="14" font-weight="bold">{title}</text>'
        + "".join(bars) + "</svg>"
    )


def risk_table(df, group_label):
    rows = "".join(
        f"<tr><td>{name}</td><td>{r.pooled_estimate:.1%}</td>"
        f"<td>{r.hdi_lower:.1%} – {r.hdi_upper:.1%}</td>"
        f"<td>{r.empirical_rate:.1%}</td><td>{int(r.n_enterprise_months)}</td></tr>"
        for name, r in df.iterrows()
    )
    return f'''<table>
      <tr><th>{group_label}</th><th>Pooled estimate</th><th>94% credible interval</th><th>Raw empirical rate</th><th>N enterprise-months</th></tr>
      {rows}
    </table>'''


def main():
    audit = load_json("data_audit_report.json")
    baseline = load_json("baseline_metrics.json")
    cashflow = load_json("cashflow_model_metrics.json")
    stress = load_json("stress_classifier_metrics.json")
    backtest = load_json("ground_truth_backtest_report.json")
    fi_risk = pd.read_csv(METRICS / "fi_risk_pooled_estimates.csv", index_col=0)
    sector_risk = pd.read_csv(METRICS / "sector_risk_pooled_estimates.csv", index_col=0)

    blocking = audit["blocking_issues"] if audit else []
    banner = (
        '<div style="background:#e8f5e9;border:1px solid #4caf50;padding:14px;border-radius:6px;margin-bottom:20px">'
        '<strong>Data audit: no blocking issues.</strong> All 5 source tables (district_indices, '
        'monthly_records, enterprises, enterprise_ground_truth, transactions) share a consistent '
        '398-enterprise universe, verified in script 01.</div>'
    ) if not blocking else (
        f'<div style="background:#fff3cd;border:1px solid #ffcc00;padding:14px;border-radius:6px;margin-bottom:20px">'
        f'<strong>{len(blocking)} blocking issue(s):</strong><ul>'
        + "".join(f"<li>{b['name']}: {b['detail']}</li>" for b in blocking) + '</ul></div>'
    )

    fi_sorted = fi_risk.sort_values("pooled_estimate", ascending=False)
    sector_sorted = sector_risk.sort_values("pooled_estimate", ascending=False)

    cashflow_rows = []
    for h in ("3", "6"):
        for split in ("val", "test", "shock_holdout"):
            b = next((r for r in baseline.get(f"y{h}_persistence", []) if r["split"] == split), None)
            m = cashflow.get(f"y{h}", {}).get(split)
            if not b or not m:
                continue
            win = "yes" if m["median_mae"] < b["mae"] else "no"
            pct = (b["mae"] - m["median_mae"]) / b["mae"]
            cashflow_rows.append(
                f"<tr><td>Y{h}</td><td>{split}</td><td>Rs {b['mae']:,.0f}</td>"
                f"<td>Rs {m['median_mae']:,.0f}</td><td>{win} ({pct:+.0%})</td></tr>"
            )
    cashflow_section = f'''
    <h2>Cash flow forecast: model vs. persistence baseline (MAE)</h2>
    <table>
      <tr><th>Horizon</th><th>Split</th><th>Baseline MAE</th><th>Model MAE</th><th>vs. baseline</th></tr>
      {"".join(cashflow_rows)}
    </table>
    <p><em>Model beats the baseline on every split for both horizons, once sector/district/loan-schedule
    features were available (see docs/PROGRESS_LOG.md for the before/after).</em></p>'''

    stress_rows = "".join(
        f"<tr><td>{split}</td><td>{m['positive_rate']:.1%}</td><td>{m['pr_auc']:.3f}</td>"
        f"<td>{m['roc_auc']:.3f}</td><td>{m['precision_at_top_20pct']:.1%}</td></tr>"
        for split, m in stress.items()
    )
    stress_section = f'''
    <h2>Stress classifier performance</h2>
    <table>
      <tr><th>Split</th><th>Positive rate</th><th>PR-AUC</th><th>ROC-AUC</th><th>Precision @ top 20%</th></tr>
      {stress_rows}
    </table>'''

    backtest_section = ""
    if backtest:
        status_color = "#2e7d32" if backtest.get("status") == "OK" else "#c0392b"
        corr = backtest.get("scripted_stress_vs_observable_label_correlation")
        pval = backtest.get("scripted_stress_vs_observable_label_pvalue")
        perf_corr = backtest.get("forecast_residual_vs_performance_multiplier_correlation")
        backtest_section = f'''
        <h2>Ground-truth backtest</h2>
        <p style="color:{status_color};font-weight:bold">Status: {backtest.get("status")}</p>
        <p>Correlation between the observable stress label and the hidden ground-truth stress flag:
        <strong>{corr:.3f}</strong> (p={pval:.4f}) &mdash; statistically significant given the sample size,
        but weak in practical terms. The observable proxy label points in the right direction but should not
        be presented as a validated stand-in for the true generative stress mechanism.</p>
        <p>Correlation between the Y3 forecast residual and the hidden performance multiplier:
        <strong>{perf_corr:.3f}</strong> &mdash; small, and in the expected direction (higher-performing
        enterprises have slightly smaller forecast errors).</p>'''

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Rural Risk Radar - Dashboard</title>
<style>
body {{ font-family: -apple-system, Arial, sans-serif; max-width: 940px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; }}
h1 {{ border-bottom: 3px solid #3b6fd6; padding-bottom: 8px; }}
h2 {{ margin-top: 36px; color: #2c3e50; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 14px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
th {{ background: #f4f6f8; }}
tr:nth-child(even) {{ background: #fafbfc; }}
</style></head>
<body>
<h1>Rural Risk Radar - Dashboard</h1>
<p>398 microenterprises, 20 field investigators, 12 sectors, 28 districts, 24-month panel (Aug 2024 - Jul 2026)</p>
{banner}
<h2>Field investigator risk ranking</h2>
{img_tag("fi_risk_ranking.png", "FI risk ranking with credible intervals")}
{risk_table(fi_sorted, "FI")}
<h2>Sector risk ranking</h2>
{img_tag("sector_risk_ranking.png", "Sector risk ranking with credible intervals")}
{risk_table(sector_sorted, "Sector")}
<h2>Sector x district stress rate (raw, unpooled)</h2>
{img_tag("sector_district_heatmap.png", "Sector by district stress heatmap")}
<p><em>Sparse cells (few enterprises in that sector/district combination) are noisy — treat as exploratory, not a pooled estimate.</em></p>
{cashflow_section}
{img_tag("cashflow_vs_baseline.png", "Cash flow model vs baseline MAE")}
{img_tag("quantile_calibration.png", "Quantile calibration plot")}
{img_tag("example_forecast_vs_actual.png", "Example forecast vs actual for one enterprise")}
{img_tag("cashflow_feature_importance.png", "Cash flow model feature importance")}
{stress_section}
{img_tag("stress_classifier_curves.png", "Stress classifier ROC and PR curves")}
{img_tag("stress_classifier_feature_importance.png", "Stress classifier feature importance")}
{backtest_section}
</body></html>"""

    OUT.write_text(html)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
