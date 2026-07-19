# Progress Log

Running record of what's been built, what it found, and what's still open.
Updated after every script, in order. Each entry: what the script does, what
it found when run against the real data, and any shortcoming/open question
it surfaces for later scripts.

---

## 00 — Data extraction (not in the original 11-script plan)

**Status:** done, with two documented shortcomings

**Why this exists:** the roadmap's script list assumes `data/raw/*.csv`
already exist. In this project they don't — the only source available is
`rural-risk-radar.pdf`, a 116-page Google Sheets export containing
`district_indices`, `enterprises`, `enterprise_ground_truth`, and
`monthly_records`. `transactions.csv` was not exported to the PDF (at
~160k rows it wouldn't fit) — **it is not available in this project**, which
is a real constraint, not a bug: any feature or audit step that needs
transaction-level detail (day-of-week concentration, EMI-payment-in-cash
detection) has to be marked as unavailable rather than silently skipped.

**Page layout found:** pages 1–14 → `district_indices` (header p.1),
15–102 → `monthly_records` (header p.15), 103–107 → `enterprises` (header
p.103), 108–116 → `enterprise_ground_truth` (header p.108). `transactions`
has no pages at all.

**Advancement — form-feed bug caught and fixed.** `pdftotext` inserts a bare
`\x0c` between pages with no preceding newline, which silently breaks any
`^`-anchored `re.MULTILINE` regex on the first record of every page after
the first. First run of the extractor lost 13/672 `district_indices` rows,
87/9552 `monthly_records` rows, and 26/398 rows on each of `enterprises`
and `enterprise_ground_truth` — all exactly the rows sitting on a page
boundary. Fixed by normalizing `\x0c → \n` before any regex runs.
`district_indices` (672/672) and `monthly_records` (9552/9552) are now
extracted at 100%.

**Shortcoming 1 — `enterprises.csv` / `enterprise_ground_truth.csv` are
short by 26 rows each (372 of 398).** After the form-feed fix, these two
sheets *still* lose the same 26 enterprise IDs. Root cause is different
from the form-feed bug: per-page row counts came back as `42, 43, 43, 43,
43, 43, 43, 43, 29` — i.e. a real, silent row-count deficit baked into the
PDF's own pagination, not a regex miss (confirmed by grepping raw
`pdftotext` output directly, no parsing involved). Most likely a Google
Sheets print-export quirk where a row that would straddle a page break gets
dropped rather than pushed to the next page. Because `enterprises.csv` and
`enterprise_ground_truth.csv` lose exactly the same 26 IDs (they're 100%
overlap-consistent with each other, see script 01), this looks like both
sheets were paginated identically rather than the two sheets disagreeing
with each other — so the *pair* is internally consistent, just short of
the full 398.

**Shortcoming 2 — the `enterprises.csv` "name" column corrupts adjacent
columns when it wraps.** Word-position extraction (pdfplumber) produces
character-interleaved garbage wherever a long name wraps to 2–3 lines
within one row (the renderer overlaps the wrapped line with an adjacent
column at the pixel level — this is a genuine PDF rendering defect, not an
extraction bug). Switched to `pdftotext -layout` instead, which keeps every
wrapped fragment as clean, correctly-spelled text spread across several
physical lines — just not in a fixed column order. Recovered `sector` and
`district` via controlled-vocabulary substring search (12 known sectors, 28
known districts) rather than fixed positions, anchoring the rest of the
record (vintage/digital_adoption/loan fields) on the `FI\d+` token, which
always renders cleanly. Net result: **100% of the 372 available rows now
parse** (was 314/372 on the first pass). `name` itself is discarded — the
methodology doc says it's cosmetic, so nothing of modeling value is lost.
`place` is kept but flagged low-confidence: in a few rows a leftover
wrapped name fragment (e.g. "Co-op") lands between `district` and the real
`place` value in the flattened text, so `place` should be spot-checked
before being relied on; `district` itself is unaffected since it's found by
direct vocabulary search, not by position relative to `place`.

**Output:** `data/raw/{district_indices,monthly_records,enterprises,enterprise_ground_truth}.csv`

---

## 01 — Data audit

**Status:** done — found one BLOCKING issue. Full machine-readable output in
`reports/metrics/data_audit_report.json`; script exits non-zero when a
blocking issue is present, so it can gate script 02 in CI.

**Passed:**
- `district_indices` (672/672) and `monthly_records` (9552/9552) row counts exact.
- `net_cash_flow = income − expenses − emi_due` holds to within 0.01 across
  all 9,552 rows (2dp display rounding only) — the core generator identity
  from the methodology doc is intact in this export.
- `emi_due == 0` and `repayment_status ∈ {no_loan, loan_closed}` whenever
  `has_loan` is False, with zero violations — internal loan-state logic is
  consistent.
- Every district in `enterprises.csv` exists in `district_indices.csv`.
- `enterprises.csv` and `enterprise_ground_truth.csv` are 100%
  ID-consistent with each other (372/372 shared).

**🔴 BLOCKING — `monthly_records.csv` and `enterprises.csv` /
`enterprise_ground_truth.csv` reference completely disjoint enterprises.**
Zero of the 398 `enterprise_id` values in `monthly_records.csv` appear in
`enterprises.csv` (or `enterprise_ground_truth.csv`). This isn't a parsing
artifact — it's confirmed by a plain set intersection on the extracted
IDs, and both `enterprises.csv`/`enterprise_ground_truth.csv` agree with
each other, they just don't agree with `monthly_records.csv`. Practical
effect: as this PDF stands, **none of sector, district, loan terms, or the
hidden stress/performance ground truth can be joined onto the monthly
panel.** That removes almost every static feature in §2 of the roadmap and
all of §5's backtest step. `field_investigator_id` is the one static
attribute that's still usable as-is, since it's just a namespaced code
(`FI001`–`FI020`) shared across sheets rather than a per-enterprise key,
and district-month macro indices remain usable in isolation (they don't
require an enterprise join at all) — but sector- or district-conditioned
features are blocked until this is resolved.

**Most likely cause:** the `monthly_records` tab was generated (or
regenerated) in a different run of the underlying Python generator than
the `enterprises`/`enterprise_ground_truth` tabs, so the tabs in the source
Google Sheet went out of sync before this PDF was exported — enterprise IDs
are randomly drawn per run, so two runs of the same generator produce
disjoint ID sets even with the same config.

**Recommended fix (needs your input to proceed):** re-export all four
tables from a single, current state of the spreadsheet — ideally as actual
CSV downloads rather than a PDF print, since a plain CSV export would have
avoided literally every issue logged in script 00 above (form feeds,
column-overlap corruption, pagination row loss). If the original
`generate_data.py`/`generate_transactions.py` scripts (mentioned in the
methodology doc) are available, running them fresh and exporting straight
to CSV would be more reliable than any PDF re-export.

**Decision (per your instruction to proceed cautiously):** continuing with
scripts 02+ using only what's cleanly joinable, rather than pausing or
building a proxy join. `field_investigator_id` already lives directly on
`monthly_records.csv`, so FI-level grouping isn't blocked by any of this —
only sector/district-conditioned features and the ground-truth backtest
are. One workaround was considered and deliberately **not** implemented
without sign-off: the methodology doc notes each FI's caseload is
geographically contiguous, so a "modal district per FI" derived from
`enterprises.csv` could be joined onto `monthly_records` via FI code as a
coarse district proxy. That's a real option if district-conditioned macro
features turn out to matter a lot, but it's an approximation that risks
misattributing district effects to whichever FI happens to correlate with
them, so it's flagged here rather than silently built in.

---

## 02 — Build panel

**Status:** done, with the same scope limitation as above by design

**What it does:** sorts `monthly_records.csv` by `(enterprise_id, month)`,
adds a 0–23 `month_index` per enterprise (so later lag/lead logic is plain
integer arithmetic instead of calendar math), and validates completeness.

**Result — panel is clean:** 398 enterprises × 24 months = 9,552 rows, zero
duplicate `(enterprise_id, month)` pairs, every enterprise has exactly 24
months, and every enterprise's span is the same Aug 2024–Jul 2026 window.
No gaps, no misalignment.

**What's deliberately not in this panel yet:** sector, district, loan
terms, vintage, digital_adoption (all blocked per script 01), and
`district_indices.csv` isn't joined either — not because it has a problem
of its own, but because there's no per-enterprise `district` column
available yet to join it on. `scripted_stress`/`performance_multiplier`
were never going to be joined here regardless (ground-truth, backtest-only
per roadmap §5).

**Output:** `data/processed/panel.csv` (17 columns — the original
`monthly_records.csv` columns plus `month_index`).

---

## 03 — Feature engineering

**Status:** done, scoped to what's available (sector/district blocks skipped)

**What it does:** dynamic panel block (lag-1/2/3/6 and trailing 3/6-month
mean+std for income/expenses/net_cash_flow), a 6-month trend slope on
net_cash_flow, share of trailing months with negative net_cash_flow,
repayment history (lag-1 savings_balance, trailing missed/late count),
digital footprint (lag-safe UPI inflow/outflow rolling stats, trailing
`data_complete` rate), the origin month's own `emi_due`/`has_loan` (used
contemporaneously — see reasoning below), and a cyclical month-of-year
encoding. 46 feature columns added to the 17-column panel.

**Lag discipline, verified not just asserted:** every rolling/lag feature
is built by calling `.shift(1)` before any `.rolling(...)`, so a "trailing
3-month" feature as of month *t* covers *t*-3..*t*-1 and never *t* itself.
Spot-checked directly on one enterprise: `net_cash_flow_lag1` at
month_index 1 exactly equals `net_cash_flow` at month_index 0, and
`net_cash_flow_roll_mean_3` at month_index 3 exactly equals the mean of
month_index 0–2. First 6 months per enterprise carry expected NaNs from
insufficient trailing history — not a bug, just means those origins can't
be used for the 6-month rolling features (documented, not silently
dropped).

**One deliberate non-lag, justified inline in the script:** the forecast
origin month's own `emi_due` and `has_loan` are used as-is, not lagged.
This is different from income/expenses/net_cash_flow: those are lagged
because using them contemporaneously would leak the same-month target.
`emi_due`/`has_loan` at the origin month are realized facts *about the
origin itself*, not about the future window being forecast — so using them
is standard "features known at prediction time," not leakage. (The
*better* version of this — the forward EMI schedule for months t+1..t+6,
which is knowable in advance per roadmap §2 — still needs
`enterprises.csv`'s loan fields and is blocked along with everything else
that needs that join.)

**Output:** `data/processed/features.csv` (63 columns).

---

## 04 — Define targets

**Status:** done

**What it does:** `target_y3`/`target_y6` = forward sum of `net_cash_flow`
over the next 3/6 months from each origin; an observable `stress_label`
built only from information a real system would have (no ground truth
involved — it isn't joinable anyway).

**Coverage:** 87.5% of origins (8,358/9,552) have enough future months for
a Y3 target; 75.0% (7,164/9,552) for Y6 — this is the "shrinking usable
training set" the roadmap flagged in §1a, now measured exactly. The last 3
(Y3) / 6 (Y6) months of each enterprise's panel are right-censored and
correctly carry NaN targets rather than a misleadingly partial sum.

**Bug caught during a sanity check, not by luck:** the first version
compared `NaN < threshold` directly to decide whether a stress condition
was "computable." In pandas/NumPy, a comparison against NaN silently
evaluates to `False`, not NaN — so every right-censored origin was getting
labeled "not stressed" instead of correctly being marked unlabelable. This
surfaced immediately on a spot-check of one enterprise's last 3 rows
(target NaN, but label showed `0.0` instead of NaN) and was fixed by
explicitly masking NaN inputs before combining conditions, rather than
relying on the comparison operators to propagate missingness themselves.
Re-checked after the fix: the same enterprise's last 3 rows now correctly
show `NaN` for the label. This is exactly the kind of silent, plausible-
looking-but-wrong output that's worth calling out — the script would have
run and produced a clean-looking file either way.

**Result:** 11.1% observable stress rate among the 87.5% labelable origins.
Can't be validated against `scripted_stress` (blocked, see script 01) — so
right now this rate is a face-value proxy statistic, not a
generator-validated one.

**Output:** `data/processed/targets.csv` (66 columns).

---

## 05 — Splits

**Status:** done, one design flaw caught and corrected before it affected anything downstream

**What it does:** chronological split by `month_index` (train 0–12, val
13–15, test 16–23), no shuffling. Per horizon, additionally flags whether
an origin's forecast window overlaps `month_index` 10–15 (the roadmap's
"shock window," where drought/disruption signal concentrates).

**Design flaw caught before any model was trained on it:** the first pass
just added the shock-window flag as a diagnostic column and left the
chronological split untouched. Checking the actual counts showed why that
doesn't work: `month_index` 0–12 (the train range) *heavily* overlaps
10–15, so 2,388 of train's 5,174 Y3-usable origins (46%) and 3,582 of
Y6's 5,174 (69%) were shock-window origins — meaning a "held-out shock
window" evaluation, if just measured on whichever split those rows
happened to land in, would mostly be measuring performance on data the
model had already trained on. That defeats the entire point of that
check in the roadmap (§3): testing generalization to the exact regime
the radar needs to catch.

**Fix:** for each horizon, shock-window-overlapping origins are carved out
of `train` into a separate `shock_holdout` split (`split_y3`/`split_y6`
columns) rather than left in place — the model genuinely never trains on
them, so evaluating on `shock_holdout` is now an honest generalization
check, not an after-the-fact relabeling of training data.

**Side effect worth flagging, not hiding:** this shrinks the real Y6
training set to 1,592 usable origins (was 5,174 before the carve-out) —
a meaningful cost on top of the right-censoring loss already noted in
script 04. This is a genuine tradeoff, not a bug: a bigger, easier-looking
training set that includes the shock episodes would produce a model that
looks better in-sample and generalizes worse to the cases that matter most.

**Output:** `data/processed/splits.csv` (71 columns).

---

## 06 — Baseline models

**Status:** done

**What it does:** persistence baseline — predicts the next window's total
net cash flow as `horizon x trailing-horizon-month average` (e.g. Y3
forecast = `net_cash_flow_roll_mean_3 x 3`), evaluated on val/test/
shock_holdout only (never train, since a baseline restating recent history
back at itself would look artificially good there).

**Result (MAE, ₹):**

| Horizon | val | test | shock_holdout |
|---|---|---|---|
| Y3 | 9,972 | 8,796 | 8,637 |
| Y6 | 18,152 | 15,925 | 18,497 |

Anything in script 07 that doesn't clear these numbers on val/test/
shock_holdout isn't earning its complexity, per roadmap §4 step 1.

**Output:** `reports/metrics/baseline_metrics.json`.

---

## 07 — Cash flow forecast models

**Status:** done, but the result is a genuine mixed bag — reported as such, not smoothed over

**What it does:** LightGBM quantile regression (P10/P50/P90) per horizon,
trained only on the 47 lag/rolling/calendar features that are actually
joinable right now (no sector/district — blocked per script 01).

**Result vs. the script 06 persistence baseline (MAE, ₹):**

| Horizon | Split | Baseline | Model | Model wins? |
|---|---|---|---|---|
| Y3 | val | 9,972 | 10,410 | No — 4% worse |
| Y3 | test | 8,796 | 6,962 | Yes — 21% better |
| Y3 | shock_holdout | 8,637 | 8,201 | Yes — 5% better |
| Y6 | val | 18,152 | 19,299 | No — 6% worse |
| Y6 | test | 15,925 | 15,964 | No — essentially tied |
| Y6 | shock_holdout | 18,497 | 17,558 | Yes — 5% better |

**This is not a clean win, and it shouldn't be presented as one.** The
model beats the baseline on `test` and `shock_holdout` but loses to it on
`val` for both horizons. Two plausible, non-exclusive explanations worth
checking before trusting this model further: (1) the missing sector/
district features (blocked per script 01) may matter enough that a model
without them can't reliably beat a simple trailing average — sector-level
seasonality in particular (monsoon-sensitive sectors) is exactly the kind
of signal a persistence baseline can't see but this model also can't see
without `enterprises.csv`; (2) the training set is small (2,786 rows for
Y3, 1,592 for Y6 after the shock-window carve-out in script 05), and `val`
sits chronologically right after `train` — a regime-shift between those
periods would hurt a fitted model more than a baseline that just restates
recent history.

**Quantile calibration is also off, not just borderline.** P90 empirical
coverage should sit near 90% and instead ranges 48–93% across
splits/horizons; P10 coverage should sit near 10% and ranges 8–27%. The
P10/P90 bands from this model should not be treated as reliable
uncertainty estimates yet — they're directionally useful (wider bands do
correspond to noisier enterprises) but not calibrated enough to hang a
"P10 forecast is deeply negative" stress rule on without recalibration.

**Recommendation before this model is used for anything:** resolve the
script 01 blocker and re-train with sector/district features before
drawing conclusions about whether GBM is the right approach here at all —
the current result is as consistent with "missing features" as with
"wrong model," and it would be premature to pick between those
explanations on this evidence.

**Output:** `models/cashflow_y{3,6}/q{10,50,90}.txt`, `reports/metrics/cashflow_model_metrics.json`.

---

## 08 — Stress classifier

**Status:** done — noticeably stronger signal than the cash flow regressor

**What it does:** LightGBM classifier (class-balanced) on the same feature
set as script 07, trained against the script 04 observable `stress_label`.

**Result:**

| Split | Positive rate | PR-AUC | ROC-AUC | Precision @ top 20% |
|---|---|---|---|---|
| val | 10.6% | 0.586 | 0.891 | 43.3% |
| test | 12.0% | 0.719 | 0.911 | 51.3% |
| shock_holdout | 14.4% | 0.700 | 0.881 | 56.4% |

Flagging the riskiest 20% of enterprise-months by predicted probability
catches stressed cases at 4–5x the base rate on every split, including
`shock_holdout` (never trained on) — a real, useful signal from lag-only
features, and notably more consistent across splits than script 07's
regressor was. Worth noting the obvious asymmetry: classification
("is this headed for trouble") is working better right now than regression
("exactly how much cash flow"), which is a reasonable place to be for an
FI-facing watchlist even before the sector/district blocker is resolved.

**Caveat, same as everywhere else:** these numbers are against the
observable proxy label, not `scripted_stress` — there's no ground-truth
validation possible until script 01's join issue is fixed.

**Output:** `models/stress_classifier/model.txt`, `reports/metrics/stress_classifier_metrics.json`.

---

## 09 — Hierarchical risk model (FI-level)

**Status:** done, sector-level pooling blocked as expected

**What it does:** partial-pooling logistic model in PyMC —
`stress_label ~ Bernoulli(sigmoid(alpha_fi))`, `alpha_fi ~ Normal(mu,
sigma)` — fit across all 20 FIs on every labeled enterprise-month (8,358
rows), giving each FI's stress rate a posterior estimate with a credible
interval instead of a raw average. Run on the full labeled panel (not
train/test-restricted) since this is a portfolio-monitoring aggregation,
not a held-out predictive claim.

**Sector-level pooling from roadmap §4 step 4 is skipped** — sector lives
in `enterprises.csv`, which doesn't join to this panel (script 01). Only
the FI level is available right now.

**Result:** FI-level pooled stress rates range from 3.1% (FI017) to 19.7%
(FI018) — a real 6x spread across field investigators, worth a portfolio
manager's attention on its own. Shrinkage toward the population mean was
modest everywhere (largest movement ~1pp, e.g. FI018's empirical 20.2% →
pooled 19.7%), which makes sense given every FI has ~420 labeled
enterprise-months here — a much bigger n per group than the "~20
enterprises" the roadmap worried about, because this aggregates across all
24 months per enterprise rather than one snapshot. Partial pooling would
matter more if this were run per-month or per-quarter rather than pooled
across the whole panel — worth revisiting once sector is available and a
genuinely small-n slice (e.g. one FI in one month) is being estimated.

**Debugging note:** this arviz version (1.2.0) renamed `az.summary`'s
`hdi_prob` parameter to `ci_prob` and its output columns from `hdi_3%`/
`hdi_97%` to `eti94_lb`/`eti94_ub` — worth knowing if re-running this on a
different environment with an older arviz pinned.

**Output:** `reports/metrics/fi_risk_pooled_estimates.csv`.

---

## 10 — Backtest against ground truth

**Status:** BLOCKED, as expected — re-confirmed rather than assumed

**What it does:** the one script allowed to open
`enterprise_ground_truth.csv` (per roadmap §5 and the ground rules in
`README.md`). Before doing anything else, it re-checks the join overlap
directly rather than trusting yesterday's finding — and confirms it's
still 0 of however many IDs are in each file. Exits non-zero with a clear
`BLOCKED` status in its JSON report rather than silently computing a
correlation of effectively nothing and presenting that as a real (bad)
result — a `0%` correlation printed without context here would look like
a statement about the stress classifier's quality, when it's actually
just describing a data problem that has nothing to do with the model.

**What this script will do once script 01's blocker is fixed** (already
written and ready, just unreachable on this data): join on
`enterprise_id`, compute the correlation between the observable
`stress_label` (script 04) and `scripted_stress`, and correlate the Y3
forecast residual against `performance_multiplier` — exactly the two
checks specified in roadmap §5.

**Output:** `reports/metrics/ground_truth_backtest_report.json` (status: `BLOCKED`).

---

## 11 — Reporting dashboard

**Status:** done — static HTML, FI-level only (same scope limitation as everything since script 02)

**What it does:** assembles every prior script's JSON/CSV output into one
self-contained HTML file (`reports/rural_risk_radar_dashboard.html`) — no
server, no external JS dependency, opens directly in a browser. Sections:
a blocking-issues banner (pulled live from script 01's audit report, not
hand-written, so it can't silently go stale), the FI risk ranking from
script 09 as an inline SVG bar chart plus table, the cash flow
model-vs-baseline comparison from scripts 06/07 (with the mixed-result
caveat carried through, not smoothed over), the stress classifier metrics
from script 08, and the backtest status from script 10.

**What this deliberately is not yet:** the roadmap's §6 vision was a
Streamlit/pydeck app with per-enterprise drill-down, sector cuts, and a
map view — none of that is possible without the script 01 join fixed
(no sector, no district, no per-enterprise ground truth). This static
version is the honest version of that vision given what's actually
available today; upgrading it to the full interactive app is mechanical
once the data issue is resolved, not a redesign.

**Output:** `reports/rural_risk_radar_dashboard.html`.

---

## Pipeline status summary (all 12 scripts, 00–11)

| Script | Status |
|---|---|
| 00 extract_pdf_to_csv | ✅ done (100% of available rows; enterprises/ground_truth capped at 372/398 by source PDF pagination) |
| 01 data_audit | ✅ done — 🔴 found the blocking ID-mismatch issue |
| 02 build_panel | ✅ done, scoped to what's joinable |
| 03 feature_engineering | ✅ done, 46 lag-safe features |
| 04 define_targets | ✅ done (caught + fixed a NaN-comparison bug) |
| 05 splits | ✅ done (caught + fixed a shock-window leakage-into-train design flaw) |
| 06 baseline_models | ✅ done |
| 07 train_cashflow_models | ✅ done — mixed result vs. baseline, needs re-run once sector/district available |
| 08 train_stress_classifier | ✅ done — solid, consistent signal |
| 09 hierarchical_risk_model | ✅ done, FI-level only (sector level blocked) |
| 10 backtest_against_ground_truth | 🔴 BLOCKED by design (reports this cleanly rather than faking a result) |
| 11 reporting_dashboard | ✅ done, FI-level static HTML |

**The one thing every remaining item in this table depends on:** resolving
script 01's finding that `monthly_records.csv` and `enterprises.csv`/
`enterprise_ground_truth.csv` reference disjoint enterprise universes. Once
that's fixed and 00/01 are re-run against consistent data, scripts 02–09
and 11 should be re-run as-is (they're already written to pick up
sector/district/ground-truth the moment the join works — see each
script's `EXCLUDE_ALWAYS`/join-scope comments) and 10 will produce a real
backtest instead of a `BLOCKED` status.

---

## RESOLVED — consistent data supplied, full pipeline re-run

**What happened:** two files arrived after the above was written.

The first (`rural-risk-radar.xlsx`) was read directly — no PDF parsing
involved — to double-check whether the mismatch was a PDF-export artifact
as originally suspected. **It wasn't.** `enterprises.csv`/
`enterprise_ground_truth.csv` were still 372 rows, still zero enterprise_id
overlap with `monthly_records.csv`, even reading the source spreadsheet
directly. Digging further: `enterprises.csv` had no `FI020` caseload at all
and only 12 of `FI019`'s usual 20 — meaning `enterprises`/
`enterprise_ground_truth` were an **earlier, smaller run of the
generator** (fewer enterprises configured) that never got refreshed after
`monthly_records` was regenerated with more enterprises added. This
corrects what was said earlier in this log about PDF pagination being the
cause of the 372-row shortfall — that diagnosis was wrong, or at least
incomplete; the real cause was upstream of any PDF export.

The second file (`rural-risk-radar_1.xlsx`) is a properly consistent
export: all 5 tables (including `transactions.csv`, unavailable until now)
share the same 398 enterprise_ids, verified explicitly before touching the
pipeline — 398/398 overlap on every pairwise check, FI group sizes
matching exactly between `monthly_records` and `enterprises`.

**What changed in the pipeline once this was confirmed:**
- Script 00 replaced entirely — reads the xlsx directly, no more PDF text
  reconstruction needed.
- Script 01 now checks (and passes) the join-key coverage that used to be
  blocking, plus a new check made possible by `transactions.csv`: UPI
  volumes never exceed total transacted volume per enterprise-month
  (0 violations).
- Script 02 now performs the real joins: static enterprise attributes
  (sector, district, place, vintage, digital_adoption, loan terms) onto
  `monthly_records`, and `district_indices` onto that via `(district,
  month)`. Zero unmatched rows on both joins.
- Script 03 adds sector/district as categoricals, the district-month macro
  block, static loan/enterprise features, and a **forward-known EMI
  feature**: since `emi_due` is constant for the life of a loan (fixed
  reducing-balance annuity per the methodology), its magnitude — once
  observed even once — is knowable for every future month the loan stays
  active. This is different in kind from lagging income/expenses: it's a
  genuinely forward-looking, non-leaky feature, computed from the static
  loan schedule plus an expanding-max of past `emi_due` (still lag-safe,
  `shift(1)` before the expanding max).
- Scripts 07/08 retrained with the full ~67-feature set.
- Script 09 rebuilt as a **crossed FI x sector** hierarchical model
  (previously FI-only) — this is the direct fix for the "and sector" half
  of the original brief that was blocked before.
- Script 10 now actually runs instead of reporting `BLOCKED`.
- Script 11 dashboard rebuilt with the sector view and real backtest numbers.

**Result — cash flow model, before vs. after (MAE, ₹):**

| Horizon | Split | Before (no sector/district) | After | Change |
|---|---|---|---|---|
| Y3 | val | 10,410 (lost to baseline) | 9,180 | beats baseline by 8% |
| Y3 | test | 6,962 | 6,082 | beats baseline by 31% |
| Y3 | shock_holdout | 8,201 | 7,769 | beats baseline by 10% |
| Y6 | val | 19,299 (lost to baseline) | 16,857 | beats baseline by 7% |
| Y6 | test | 15,964 (roughly tied) | 15,115 | beats baseline by 5% |
| Y6 | shock_holdout | 17,558 | 17,100 | beats baseline by 8% |

**The model now beats the persistence baseline on every split for both
horizons** — it previously lost on `val` for both. This confirms the
suspicion flagged earlier: the missing sector/district features were the
actual problem, not the modeling approach. Quantile calibration is
better but still imperfect (P10 coverage now 8–29% against a 10% target,
P90 coverage 45–90% against a 90% target) — still worth recalibrating
before leaning on the P10/P90 bands for anything precise, but directionally
usable.

**Stress classifier, before vs. after (PR-AUC):** val 0.586→0.729, test
0.719→0.756, shock_holdout 0.700→0.844. Meaningful lift across the board,
largest on the shock-holdout set — exactly where it matters most.

**Sector-level risk is now real, not blocked.** Crossed FI x sector
hierarchical model gives both dimensions simultaneously: FI-level pooled
stress rates range 2.5% (FI017) to 23.4% (FI018); sector-level pooled
rates range 4.3% (food_processing) to 26.5% (handicrafts) — a genuinely
new finding this pipeline couldn't produce before.

**Ground-truth backtest — run, and the result should be reported
honestly, not oversold.** The observable `stress_label` built in script 04
correlates with the true hidden `scripted_stress` flag at only **r=0.027**
(p=0.008 — statistically significant given ~8,300 rows, but practically
weak). At the enterprise level, stressed enterprises do show a somewhat
higher observable stress rate than non-stressed ones (13.0% vs 10.7%), and
the Y3 forecast residual correlates with the hidden performance multiplier
at -0.030 — small, but in the expected direction. **Conclusion: the
observable proxy label points the right way but is a weak stand-in for
the true generative mechanism.** If sharpening the observable label matters
more going forward, the missed/late-repayment component of the label
(rather than the cash-flow-shortfall component) is the more promising
piece to investigate first, given repayment behavior is closer to what
`scripted_stress` most directly drives per the methodology doc.

**Output:** `reports/rural_risk_radar_dashboard.html`, updated
`reports/metrics/*.json`, `reports/metrics/sector_risk_pooled_estimates.csv`.

---

## 11 — Generate figures (new)

**Status:** done. Renumbered so figures generate before the dashboard that
embeds them — the dashboard script moved from 11 to 12 accordingly.

**What it does:** 9 static PNG figures, built directly from the same
model/metrics artifacts every other script already produced (no
recomputation, purely visualization):
- `fi_risk_ranking.png` / `sector_risk_ranking.png` — pooled estimate with
  94% credible interval error bars, raw empirical rate marked separately,
  so the shrinkage effect is visible at a glance
- `cashflow_vs_baseline.png` — grouped bar chart, model vs. persistence
  baseline MAE, per horizon and split, with the % improvement annotated
- `quantile_calibration.png` — target vs. empirical coverage for P10/P90
  across every split/horizon, so the calibration gap flagged in script 07
  is visible rather than just stated in a table
- `stress_classifier_curves.png` — ROC and PR curves per split
- `cashflow_feature_importance.png` / `stress_classifier_feature_importance.png`
  — top-15 features by gain for each model
- `example_forecast_vs_actual.png` — one enterprise's actual vs. P10/P50/P90
  forecast over time, shock window shaded, so the forecast bands mean
  something concrete rather than abstract percentages
- `sector_district_heatmap.png` — raw (unpooled) stress rate by sector x
  district, explicitly labeled as noisy/exploratory since many cells have
  few enterprises

**Output:** `reports/figures/*.png` (9 files), and embedded as base64 into
`reports/rural_risk_radar_dashboard.html` so the dashboard stays a single
self-contained file (~1MB) rather than depending on relative image paths.

---

## 12 — Reporting dashboard (renumbered from 11)
