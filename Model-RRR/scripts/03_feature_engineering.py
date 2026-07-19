"""
03_feature_engineering.py

Same lag-disciplined dynamic panel block as before, now extended with the
features that were blocked pending script 01/02's join:

  - sector, district as categoricals (tree models pick up sector x month
    seasonality and sector x macro-index interactions natively — no need
    to hand-build cross terms)
  - district-month macro indices (rainfall, milk price, poultry feed price,
    raw material price, retail demand, local disruption) as of the origin
    month — exogenous, safe as-is
  - static loan/enterprise attributes (vintage_years, digital_adoption,
    loan_amount, loan_tenure_months, loan_taken_in_dataset)
  - a genuinely forward-known EMI feature: `emi_due` is CONSTANT for the
    life of a loan (fixed reducing-balance annuity, per the methodology
    doc), so once it's been observed even once, its magnitude is knowable
    for every future month the loan is still active — this is fundamentally
    different from lagging income/expenses, which change every month.
    Computed as an expanding-max of past emi_due (lag-safe: uses shift(1)
    before the expanding max) combined with the static loan_start_offset/
    tenure window to project which future months the loan will still be
    active.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


def add_lag_and_rolling(df, col, lags=(1, 2, 3, 6), windows=(3, 6)):
    g = df.groupby("enterprise_id")[col]
    for lag in lags:
        df[f"{col}_lag{lag}"] = g.shift(lag)
    shifted = g.shift(1)
    for w in windows:
        roll = shifted.groupby(df["enterprise_id"]).rolling(w, min_periods=w).mean()
        df[f"{col}_roll_mean_{w}"] = roll.reset_index(level=0, drop=True)
        roll_std = shifted.groupby(df["enterprise_id"]).rolling(w, min_periods=w).std()
        df[f"{col}_roll_std_{w}"] = roll_std.reset_index(level=0, drop=True)
    return df


def trailing_trend_slope(df, col, window=6):
    shifted = df.groupby("enterprise_id")[col].shift(1)
    x = np.arange(window)

    def slope(y):
        if y.isna().any():
            return np.nan
        return np.polyfit(x, y.values, 1)[0]

    return (
        shifted.groupby(df["enterprise_id"])
        .rolling(window, min_periods=window)
        .apply(slope, raw=False)
        .reset_index(level=0, drop=True)
    )


def add_forward_known_emi(df, horizons=(3, 6)):
    """Known-in-advance EMI exposure over the next `horizon` months, using
    only the static loan schedule + the loan's own (constant) magnitude once
    observed. Never uses a future emi_due value directly — only the fixed
    per-loan amount, which the methodology confirms doesn't vary month to
    month once a loan is active."""
    emi_magnitude = (
        df.groupby("enterprise_id")["emi_due"]
        .shift(1)  # lag-safe: only what's been observed strictly before origin t
        .groupby(df["enterprise_id"])
        .expanding()
        .max()
        .reset_index(level=0, drop=True)
        .fillna(0.0)
    )
    df["known_emi_magnitude"] = emi_magnitude

    loan_active_start = df["loan_start_month_offset"]
    loan_active_end = df["loan_start_month_offset"] + df["loan_tenure_months"]  # exclusive
    for h in horizons:
        total = pd.Series(0.0, index=df.index)
        for k in range(1, h + 1):
            future_month = df["month_index"] + k
            will_be_active = df["loan_taken_in_dataset"] & (future_month >= loan_active_start) & (future_month < loan_active_end)
            total = total + np.where(will_be_active, emi_magnitude, 0.0)
        df[f"known_emi_next_{h}"] = total
    return df


def main():
    df = pd.read_csv(PROCESSED / "panel.csv", parse_dates=["month"])
    df = df.sort_values(["enterprise_id", "month"]).reset_index(drop=True)

    for col in ["income", "expenses", "net_cash_flow"]:
        df = add_lag_and_rolling(df, col)

    df["net_cash_flow_trend_slope_6"] = trailing_trend_slope(df, "net_cash_flow", 6)

    shifted_ncf = df.groupby("enterprise_id")["net_cash_flow"].shift(1)
    is_neg = (shifted_ncf < 0).astype(float)
    is_neg[shifted_ncf.isna()] = np.nan
    for w in (3, 6):
        df[f"share_negative_ncf_trailing_{w}"] = (
            is_neg.groupby(df["enterprise_id"]).rolling(w, min_periods=w).mean().reset_index(level=0, drop=True)
        )

    df["savings_balance_lag1"] = df.groupby("enterprise_id")["savings_balance"].shift(1)
    is_bad_status = df["repayment_status"].isin(["missed", "late"]).astype(float)
    is_bad_status_lagged = df.groupby("enterprise_id").apply(
        lambda g: is_bad_status.loc[g.index].shift(1)
    ).reset_index(level=0, drop=True)
    for w in (3, 6):
        df[f"missed_or_late_count_trailing_{w}"] = (
            is_bad_status_lagged.groupby(df["enterprise_id"]).rolling(w, min_periods=1).sum().reset_index(level=0, drop=True)
        )

    for col in ["upi_inflow_txn_volume", "upi_outflow_txn_volume"]:
        df = add_lag_and_rolling(df, col, lags=(1,), windows=(3, 6))
    df["data_complete_lag1"] = df.groupby("enterprise_id")["data_complete"].shift(1).astype(float)
    df["data_complete_rate_trailing_6"] = (
        df.groupby("enterprise_id")["data_complete"].shift(1)
        .groupby(df["enterprise_id"]).rolling(6, min_periods=6).mean().reset_index(level=0, drop=True)
    )

    df["emi_due_at_origin"] = df["emi_due"]
    df["has_loan_at_origin"] = df["has_loan"].astype(float)

    month_of_year = df["month"].dt.month
    df["month_sin"] = np.sin(2 * np.pi * month_of_year / 12)
    df["month_cos"] = np.cos(2 * np.pi * month_of_year / 12)

    # --- NEW: static + macro + forward-known EMI blocks ---------------------
    df = add_forward_known_emi(df, horizons=(3, 6))

    # debt-service pressure: trailing average cash flow vs. known upcoming EMI load
    for h in (3, 6):
        denom = df[f"known_emi_next_{h}"].replace(0, np.nan)
        df[f"debt_service_ratio_{h}"] = df[f"net_cash_flow_roll_mean_{h if h in (3,6) else 3}"] * h / denom
        df[f"debt_service_ratio_{h}"] = df[f"debt_service_ratio_{h}"].replace([np.inf, -np.inf], np.nan)

    out_path = PROCESSED / "features.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path}: {len(df)} rows, {df.shape[1]} columns")
    print("Now includes: sector, district, macro indices, static loan/enterprise attributes, "
          "and forward-known EMI exposure (known_emi_next_3/6, debt_service_ratio_3/6) — "
          "all previously blocked, all now joinable.")


if __name__ == "__main__":
    main()
