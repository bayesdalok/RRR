"""
04_define_targets.py

Builds the two forecasting targets and the observable stress label from
docs/modeling_roadmap.md §1, on top of data/processed/features.csv.

Y3(e,t) = sum of net_cash_flow over months t+1..t+3
Y6(e,t) = sum of net_cash_flow over months t+1..t+6

These are FORWARD sums relative to the forecast origin t — the interpretation
picked explicitly in the roadmap (§1a) over a backward/trailing reading,
because a forward liquidity forecast is what a risk radar needs to act on.

Origins in the last 3 (for Y3) or 6 (for Y6) months of each enterprise's
panel are right-censored — there aren't enough future months left to sum —
and are dropped for that horizon rather than filled with a partial sum,
since a partial sum silently understates risk exactly when risk is what
we're trying to catch.

Observable stress label (roadmap §1b): built ONLY from things visible at
run time (no scripted_stress — that file isn't even joinable per script 01,
and wouldn't be used as a feature/label even if it were). Flagged stressed
if EITHER:
  - Y3(e,t) < 0.5 x trailing-6-month average expenses (a quarter's incoming
    cash won't cover half a normal quarter's costs), OR
  - at least 2 of the next 3 months have repayment_status in {missed, late}
    (this one looks at realized future repayment behavior, which is fair
    game for a label — labels are allowed to use the future; features are
    not).
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


def forward_sum(df: pd.DataFrame, col: str, horizon: int) -> pd.Series:
    """Sum of col over t+1..t+horizon, NaN if fewer than `horizon` future
    months exist for that enterprise (right-censored origin)."""
    g = df.groupby("enterprise_id")[col]
    # shift(-1) brings t+1 to row t; rolling(horizon) then sums t+1..t+horizon
    # when read from the "future-aligned" series, walking backwards from the
    # tail. Implemented by reversing within each group, shifting, and rolling.
    def _one_enterprise(s: pd.Series) -> pd.Series:
        rev = s[::-1]
        # rolling sum of the reversed series at position i (reading backwards
        # from the end) covers the horizon values immediately AFTER position
        # i in the original order once un-reversed.
        shifted = rev.shift(1)  # drop current month, keep only strictly-future
        roll = shifted.rolling(horizon, min_periods=horizon).sum()
        return roll[::-1]

    return g.transform(_one_enterprise)


def forward_bad_repayment_count(df: pd.DataFrame, horizon: int = 3) -> pd.Series:
    is_bad = df["repayment_status"].isin(["missed", "late"]).astype(float)
    tmp = df[["enterprise_id"]].copy()
    tmp["is_bad"] = is_bad

    def _one_enterprise(s: pd.Series) -> pd.Series:
        rev = s[::-1]
        shifted = rev.shift(1)
        roll = shifted.rolling(horizon, min_periods=horizon).sum()
        return roll[::-1]

    return tmp.groupby("enterprise_id")["is_bad"].transform(_one_enterprise)


def main():
    df = pd.read_csv(PROCESSED / "features.csv", parse_dates=["month"])
    df = df.sort_values(["enterprise_id", "month"]).reset_index(drop=True)

    df["target_y3"] = forward_sum(df, "net_cash_flow", 3)
    df["target_y6"] = forward_sum(df, "net_cash_flow", 6)

    n_total = len(df)
    n_y3_usable = df["target_y3"].notna().sum()
    n_y6_usable = df["target_y6"].notna().sum()
    print(f"Total enterprise-month origins: {n_total}")
    print(f"Usable origins for Y3 (3 future months available): {n_y3_usable} ({n_y3_usable/n_total:.1%})")
    print(f"Usable origins for Y6 (6 future months available): {n_y6_usable} ({n_y6_usable/n_total:.1%})")

    # --- Observable stress label ------------------------------------------
    trailing_avg_expenses_6 = df["expenses_roll_mean_6"]  # already lag-safe from script 03
    cond_cashflow = (df["target_y3"] < (0.5 * trailing_avg_expenses_6)).astype(float)
    cond_cashflow[df["target_y3"].isna() | trailing_avg_expenses_6.isna()] = np.nan

    bad_repay_next3 = forward_bad_repayment_count(df, horizon=3)
    cond_repayment = (bad_repay_next3 >= 2).astype(float)
    cond_repayment[bad_repay_next3.isna()] = np.nan

    df["stress_label"] = (
        cond_cashflow.fillna(False).astype(bool) | cond_repayment.fillna(False).astype(bool)
    ).astype(float)
    # A row can only carry a real (non-NaN) label if at least one of the two
    # conditions was actually computable; otherwise mark it NaN rather than
    # defaulting to "not stressed" by fillna(False) alone.
    label_computable = cond_cashflow.notna() | cond_repayment.notna()
    df.loc[~label_computable, "stress_label"] = np.nan

    n_labeled = df["stress_label"].notna().sum()
    stress_rate = df.loc[df["stress_label"].notna(), "stress_label"].mean()
    print(f"\nOrigins with a computable stress label: {n_labeled} ({n_labeled/n_total:.1%})")
    print(f"Observable stress rate among labeled origins: {stress_rate:.1%}")
    print("(Cannot compare against scripted_stress ground truth here — that file "
          "doesn't join to this panel; see script 01/10.)")

    out_path = PROCESSED / "targets.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}: {len(df)} rows, {df.shape[1]} columns")


if __name__ == "__main__":
    main()
