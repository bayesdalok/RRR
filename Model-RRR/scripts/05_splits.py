"""
05_splits.py

Time-based splits per docs/modeling_roadmap.md §3. No shuffling across
time, ever — origins are split purely by month_index (0-23, Aug 2024-Jul
2026), same boundaries for every enterprise:

  train : month_index 0-12   (origins, not months a target reaches into)
  val   : month_index 13-15
  test  : month_index 16-23  (as many as remain; horizon scripts filter out
                               rows with a NaN target for whatever horizon
                               they're evaluating, so test set size differs
                               between Y3 and Y6 automatically)

Also flags whether each origin's forecast window overlaps month_index
10-15 — the "shock window" per the roadmap, months that concentrate
drought/disruption signal in district_indices.csv. This is a diagnostic
flag, not a fourth split: the model never trains differently because of
it, but 07/08's evaluation reports performance on this subset separately,
since average performance elsewhere can hide poor performance exactly
where it matters most.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

TRAIN_END = 12   # inclusive
VAL_END = 15     # inclusive
SHOCK_START, SHOCK_END = 10, 15  # inclusive, month_index


def assign_split(month_index: int) -> str:
    if month_index <= TRAIN_END:
        return "train"
    if month_index <= VAL_END:
        return "val"
    return "test"


def overlaps_shock_window(origin: int, horizon: int) -> bool:
    window_start, window_end = origin + 1, origin + horizon
    return not (window_end < SHOCK_START or window_start > SHOCK_END)


def main():
    df = pd.read_csv(PROCESSED / "targets.csv", parse_dates=["month"])

    df["chronological_split"] = df["month_index"].apply(assign_split)
    df["shock_window_overlap_y3"] = df["month_index"].apply(lambda t: overlaps_shock_window(t, 3))
    df["shock_window_overlap_y6"] = df["month_index"].apply(lambda t: overlaps_shock_window(t, 6))

    # A purely chronological split puts most shock-window-overlapping origins
    # inside `train` (month_index 0-12 overlaps months 10-15 heavily), which
    # would let the model train on exactly the episodes we want to test
    # generalization to. So for each horizon, carve those origins out of
    # train into a dedicated shock_holdout split instead of leaving them in
    # — train_usable_yH below is what 06/07/08 should actually train on.
    for h in (3, 6):
        overlap_col = f"shock_window_overlap_y{h}"
        df[f"split_y{h}"] = df["chronological_split"].where(
            ~((df["chronological_split"] == "train") & df[overlap_col]),
            "shock_holdout",
        )

    print("Chronological month_index ranges: train 0-12, val 13-15, test 16-23")
    print(f"Shock window (month_index {SHOCK_START}-{SHOCK_END}) carved out of train into 'shock_holdout' per horizon:\n")
    for h, target_col in [(3, "target_y3"), (6, "target_y6")]:
        usable = df[target_col].notna()
        print(f"Horizon {h} — usable origins per split:")
        print(df[usable][f"split_y{h}"].value_counts().reindex(["train", "val", "test", "shock_holdout"]))
        print()

    out_path = PROCESSED / "splits.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path}: {len(df)} rows, {df.shape[1]} columns")


if __name__ == "__main__":
    main()
