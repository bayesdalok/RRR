"""
00_extract_pdf_to_csv.py  (now reading directly from the source xlsx)

The original PDF-based version of this script reconstructed 4 of 5 tables
from a 116-page PDF print export, with two known limitations: enterprises/
enterprise_ground_truth capped at 372 of 398 rows, and transactions.csv
unavailable entirely. That PDF export also turned out to share a real,
upstream data problem — see docs/PROGRESS_LOG.md's script 00/01 history
for the full story of how that was diagnosed.

The person has since supplied the actual source spreadsheet
(rural-risk-radar_1.xlsx) with all 5 tables, generated consistently in one
run: every table now shares the same 398 enterprise_ids (verified before
this script was written — see PROGRESS_LOG). This version simply reads
each sheet directly. Kept as script 00 (not renumbered) so the pipeline's
script order and PROGRESS_LOG history stay intact.
"""

from pathlib import Path

import pandas as pd

XLSX = "/mnt/user-data/uploads/rural-risk-radar_1.xlsx"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED_ROWS = {
    "district_indices": 672,
    "enterprises": 398,
    "enterprise_ground_truth": 398,
    "monthly_records": 9552,
    "transactions": None,  # size not fixed/predictable in the methodology doc
}


def main():
    xls = pd.ExcelFile(XLSX)
    for sheet in xls.sheet_names:
        df = xls.parse(sheet)
        out_path = RAW_DIR / f"{sheet}.csv"
        df.to_csv(out_path, index=False)
        expected = EXPECTED_ROWS.get(sheet)
        note = f"(expected {expected})" if expected else ""
        flag = "OK" if expected is None or len(df) == expected else "MISMATCH"
        print(f"[{flag}] {sheet}: {len(df)} rows, {df.shape[1]} cols {note} -> {out_path}")


if __name__ == "__main__":
    main()
