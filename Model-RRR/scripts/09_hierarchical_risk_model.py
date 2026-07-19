"""
09_hierarchical_risk_model.py

Per docs/modeling_roadmap.md §4 step 4, now with sector included — this
was blocked before (script 01) and is the direct "and sector" half of the
original brief. Crossed random-effects logistic model:

    stress_label ~ Bernoulli(sigmoid(mu + alpha_fi[fi] + alpha_sector[sector]))
    alpha_fi     ~ Normal(0, sigma_fi)      # partial pooling across FIs
    alpha_sector ~ Normal(0, sigma_sector)  # partial pooling across sectors
    mu           ~ Normal(0, 1.5)
    sigma_fi, sigma_sector ~ HalfNormal(1)

"Crossed" (not nested) because a given FI serves multiple sectors and a
given sector spans multiple FIs — this lets a sector-wide effect (e.g.
brick_kiln portfolios doing badly everywhere) separate cleanly from an
FI-specific effect (e.g. one FI having a genuinely under-performing
caseload regardless of sector mix).

Run on every enterprise-month with a computable stress_label, across all
splits — this is a portfolio-monitoring aggregation, not a held-out
predictive claim.
"""

import json
from pathlib import Path

import arviz as az
import numpy as np
import pandas as pd
import pymc as pm

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
METRICS = ROOT / "reports" / "metrics"


def summarize(trace, var_name, codes):
    summary = az.summary(trace, var_names=[var_name], ci_prob=0.94)
    summary.index = codes
    ci_cols = [c for c in summary.columns if c.startswith("eti") or c.startswith("hdi")]
    out = summary[["mean", ci_cols[0], ci_cols[1]]].copy()
    out.columns = ["pooled_estimate", "hdi_lower", "hdi_upper"]
    return out


def main():
    df = pd.read_csv(PROCESSED / "splits.csv")
    df = df[df["stress_label"].notna()].copy()
    df["stress_label"] = df["stress_label"].astype(int)

    fi_codes = sorted(df["field_investigator_id"].unique())
    sector_codes = sorted(df["sector"].unique())
    fi_idx_map = {c: i for i, c in enumerate(fi_codes)}
    sector_idx_map = {c: i for i, c in enumerate(sector_codes)}
    df["fi_idx"] = df["field_investigator_id"].map(fi_idx_map)
    df["sector_idx"] = df["sector"].map(sector_idx_map)

    print(f"Fitting crossed FI x sector hierarchical model on {len(df)} enterprise-months "
          f"across {len(fi_codes)} FIs and {len(sector_codes)} sectors")

    with pm.Model():
        mu = pm.Normal("mu", mu=0, sigma=1.5)
        sigma_fi = pm.HalfNormal("sigma_fi", sigma=1)
        sigma_sector = pm.HalfNormal("sigma_sector", sigma=1)
        alpha_fi = pm.Normal("alpha_fi", mu=0, sigma=sigma_fi, shape=len(fi_codes))
        alpha_sector = pm.Normal("alpha_sector", mu=0, sigma=sigma_sector, shape=len(sector_codes))

        logit_p = mu + alpha_fi[df["fi_idx"].values] + alpha_sector[df["sector_idx"].values]
        p = pm.Deterministic("p", pm.math.sigmoid(logit_p))
        pm.Bernoulli("obs", p=p, observed=df["stress_label"].values)

        # Also track the marginal (all-else-average) risk per FI and per
        # sector as deterministic quantities, since alpha_fi/alpha_sector
        # alone are relative-to-mu effects, not directly interpretable rates.
        p_fi_marginal = pm.Deterministic("p_fi_marginal", pm.math.sigmoid(mu + alpha_fi))
        p_sector_marginal = pm.Deterministic("p_sector_marginal", pm.math.sigmoid(mu + alpha_sector))

        trace = pm.sample(1000, tune=1000, chains=2, cores=2, random_seed=42, progressbar=False)

    fi_summary = summarize(trace, "p_fi_marginal", fi_codes)
    sector_summary = summarize(trace, "p_sector_marginal", sector_codes)

    fi_raw = df.groupby("field_investigator_id")["stress_label"].agg(["mean", "size"])
    fi_raw.columns = ["empirical_rate", "n_enterprise_months"]
    fi_table = fi_summary.join(fi_raw).sort_values("pooled_estimate", ascending=False)

    sector_raw = df.groupby("sector")["stress_label"].agg(["mean", "size"])
    sector_raw.columns = ["empirical_rate", "n_enterprise_months"]
    sector_table = sector_summary.join(sector_raw).sort_values("pooled_estimate", ascending=False)

    print("\nField investigator risk (pooled, holding sector mix constant):")
    print(fi_table.round(3))
    print("\nSector risk (pooled, holding FI mix constant):")
    print(sector_table.round(3))

    METRICS.mkdir(parents=True, exist_ok=True)
    fi_table.to_csv(METRICS / "fi_risk_pooled_estimates.csv")
    sector_table.to_csv(METRICS / "sector_risk_pooled_estimates.csv")
    print(f"\nWrote {METRICS / 'fi_risk_pooled_estimates.csv'} and {METRICS / 'sector_risk_pooled_estimates.csv'}")


if __name__ == "__main__":
    main()
