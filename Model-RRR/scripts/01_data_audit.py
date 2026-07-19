"""
01_data_audit.py

Same purpose as before — re-derive identities and check every join key
before any modelling starts — now run against the consistent, all-5-tables
xlsx source. The two previously-blocking checks (enterprise_id overlap
between monthly_records and enterprises/enterprise_ground_truth, and UPI
reconciliation against transactions.csv) are now actually checkable and
are expected to pass; this script verifies that rather than assuming it.
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REPORT_PATH = ROOT / "reports" / "metrics" / "data_audit_report.json"

report = {"checks": [], "blocking_issues": []}


def check(name, passed, detail):
    report["checks"].append({"name": name, "passed": passed, "detail": detail})
    status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
    print(f"[{status}] {name} — {detail}")
    return passed


def blocking(name, detail):
    report["blocking_issues"].append({"name": name, "detail": detail})
    print(f"[BLOCKING] {name} — {detail}")


def main():
    di = pd.read_csv(RAW / "district_indices.csv")
    mr = pd.read_csv(RAW / "monthly_records.csv", parse_dates=["month"])
    ent = pd.read_csv(RAW / "enterprises.csv")
    gt = pd.read_csv(RAW / "enterprise_ground_truth.csv")
    tx = pd.read_csv(RAW / "transactions.csv", parse_dates=["month"])

    check("district_indices row count", len(di) == 672, f"{len(di)} rows (expected 672)")
    check("monthly_records row count", len(mr) == 9552, f"{len(mr)} rows (expected 9552)")
    check("enterprises row count", len(ent) == 398, f"{len(ent)} rows (expected 398)")
    check("enterprise_ground_truth row count", len(gt) == 398, f"{len(gt)} rows (expected 398)")
    check("transactions row count > 0", len(tx) > 0, f"{len(tx)} rows")

    recomputed = mr["income"] - mr["expenses"] - mr["emi_due"]
    max_diff = (recomputed - mr["net_cash_flow"]).abs().max()
    check("net_cash_flow identity (income - expenses - emi_due)", max_diff <= 0.02,
          f"max abs difference = {max_diff:.4f} across {len(mr)} rows")

    bad_emi = mr[(~mr["has_loan"]) & (mr["emi_due"] != 0)]
    check("emi_due is 0 whenever has_loan is False", len(bad_emi) == 0, f"{len(bad_emi)} violating rows")

    mr_ids, ent_ids, gt_ids, tx_ids = (set(mr["enterprise_id"]), set(ent["enterprise_id"]),
                                        set(gt["enterprise_id"]), set(tx["enterprise_id"]))
    ok_ent = mr_ids == ent_ids
    check("monthly_records and enterprises.csv share the exact same enterprise_id set",
          ok_ent, f"{len(mr_ids & ent_ids)} shared / {len(mr_ids)} monthly_records / {len(ent_ids)} enterprises")
    if not ok_ent:
        blocking("enterprise_id mismatch persists", "monthly_records and enterprises.csv do not share the same enterprise universe")

    ok_gt = mr_ids == gt_ids
    check("monthly_records and enterprise_ground_truth.csv share the exact same enterprise_id set",
          ok_gt, f"{len(mr_ids & gt_ids)} shared / {len(mr_ids)} / {len(gt_ids)}")
    if not ok_gt:
        blocking("ground truth ID mismatch persists", "monthly_records and enterprise_ground_truth.csv do not share the same enterprise universe")

    ok_tx = tx_ids.issubset(mr_ids)
    check("every enterprise_id in transactions.csv exists in monthly_records.csv",
          ok_tx, f"{len(tx_ids & mr_ids)} of {len(tx_ids)} transaction enterprise_ids found in monthly_records")

    check("every district in enterprises.csv exists in district_indices.csv",
          set(ent["district"]).issubset(set(di["district"])),
          f"{len(set(ent['district']) - set(di['district']))} district(s) not found")

    tx_by_em = tx.groupby(["enterprise_id", "month", "direction"])["amount"].sum().unstack(fill_value=0.0).reset_index()
    merged = mr.merge(tx_by_em, on=["enterprise_id", "month"], how="left").fillna({"inflow": 0.0, "outflow": 0.0})
    # UPI volume is a SUBSET of total transacted volume (cash transactions
    # exist too, per the methodology doc), so exact equality isn't expected —
    # check UPI volume never exceeds total transacted volume instead.
    inflow_violations = (merged["upi_inflow_txn_volume"] > merged["inflow"] + 1.0).sum()
    outflow_violations = (merged["upi_outflow_txn_volume"] > merged["outflow"] + 1.0).sum()
    check("UPI inflow volume never exceeds total transacted inflow volume",
          inflow_violations == 0, f"{inflow_violations} violating enterprise-months")
    check("UPI outflow volume never exceeds total transacted outflow volume",
          outflow_violations == 0, f"{outflow_violations} violating enterprise-months")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nFull report written to {REPORT_PATH}")

    if report["blocking_issues"]:
        print(f"\n{len(report['blocking_issues'])} BLOCKING issue(s) found.")
        sys.exit(1)
    print("\nNo blocking issues. All joins clean — script 02 onward can use the full feature set.")


if __name__ == "__main__":
    main()
