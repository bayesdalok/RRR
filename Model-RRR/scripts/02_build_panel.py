"""
02_build_panel.py

Now that script 01 confirms a clean join, this builds the panel the
roadmap always intended: monthly_records + enterprises (sector, district,
place, FI, vintage, digital_adoption, loan terms) + district_indices
(joined on district + month).
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)


def main():
    mr = pd.read_csv(RAW / "monthly_records.csv", parse_dates=["month"])
    ent = pd.read_csv(RAW / "enterprises.csv")
    di = pd.read_csv(RAW / "district_indices.csv", parse_dates=["month"])

    mr = mr.sort_values(["enterprise_id", "month"]).reset_index(drop=True)
    mr["month_index"] = mr.groupby("enterprise_id").cumcount()

    # --- Join static enterprise attributes -----------------------------------
    static_cols = ["enterprise_id", "name", "sector", "district", "place",
                   "vintage_years", "digital_adoption", "upi_adoption_start_month",
                   "loan_taken_in_dataset", "loan_amount", "loan_tenure_months",
                   "loan_start_month_offset"]
    panel = mr.merge(ent[static_cols], on="enterprise_id", how="left", validate="many_to_one")
    unmatched = panel["sector"].isna().sum()
    print(f"Rows with no matching enterprise static record: {unmatched} (expect 0)")

    # --- Join district-month macro indices -----------------------------------
    panel = panel.merge(di, on=["district", "month"], how="left", validate="many_to_one")
    unmatched_macro = panel["rainfall_index"].isna().sum()
    print(f"Rows with no matching district_indices record: {unmatched_macro} (expect 0)")

    # --- Completeness checks (same as before) --------------------------------
    counts = mr.groupby("enterprise_id").size()
    dupes = mr.duplicated(subset=["enterprise_id", "month"]).sum()
    span = mr.groupby("enterprise_id")["month"].agg(["min", "max"])
    global_min, global_max = mr["month"].min(), mr["month"].max()
    misaligned = span[(span["min"] != global_min) | (span["max"] != global_max)]

    print(f"\nEnterprises: {mr['enterprise_id'].nunique()}")
    print(f"Rows: {len(panel)}")
    print(f"Duplicate (enterprise_id, month) pairs: {dupes}")
    print(f"Enterprises without exactly 24 months: {(counts != 24).sum()}")
    print(f"Enterprises with misaligned span: {len(misaligned)}")

    out_path = PROCESSED / "panel.csv"
    panel.to_csv(out_path, index=False)
    print(f"\nWrote {out_path} ({len(panel)} rows, {panel.shape[1]} columns)")

    summary = {
        "n_enterprises": int(mr["enterprise_id"].nunique()),
        "n_rows": int(len(panel)),
        "unmatched_static_join": int(unmatched),
        "unmatched_macro_join": int(unmatched_macro),
        "duplicate_enterprise_month_pairs": int(dupes),
        "enterprises_without_24_months": int((counts != 24).sum()),
        "columns_available": list(panel.columns),
    }
    with open(ROOT / "reports" / "metrics" / "panel_build_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)


if __name__ == "__main__":
    main()
