# Rural Risk Radar — Modelling Roadmap

**Scope:** (1) 3-month and 6-month rolling-window net cash flow forecasting at
enterprise level, (2) stress assessment, (3) microenterprise risk rolled up
per field investigator (FI) and per sector.

**Data:** `district_indices.csv` (28 districts × 24 months), `enterprises.csv`
(398 rows, static), `enterprise_ground_truth.csv` (398 rows, hidden labels),
`monthly_records.csv` (398 × 24 panel), `transactions.csv` (~160k rows,
underlies the UPI columns). Verified against the PDF export — columns match
the methodology doc exactly.

---

## 0. Why the leakage audit comes before anything else

This generator builds `monthly_records.csv` so that several columns are
**deterministic or near-deterministic functions of the same month's target**.
If those go into a model as features "because they're in the file," the
model will report near-perfect accuracy that evaporates the moment it's
asked to forecast a month it hasn't seen yet — which is the entire point of
a 3/6-month-ahead product. So step 0 is a hard rule table, not a suggestion.

| Column | Why it's risky | Rule |
|---|---|---|
| `net_cash_flow` | `= income − expenses − emi_due`, exact identity | This **is** the (rolled-up) target. Never a feature at the same or later month. |
| `savings_balance` | Updated *using that month's* `net_cash_flow` | Lag ≥ 1 only. |
| `repayment_status`, realized `emi_due` outcome | Computed from that month's cash flow vs. EMI | Lag ≥ 1 only. The EMI **schedule itself** (amount/tenure/start offset) is static master data known in advance — see below, that part is safe. |
| `upi_outflow_txn_count/volume`, `loan_repayment_collected_upi` | Reconciled from `transactions.csv`, which is itself expanded from that month's `income`/`expenses` | Lag ≥ 1 only. |
| `upi_inflow_txn_count/volume` | Scaled directly off that month's `income` | Lag ≥ 1 only. |
| `income`, `expenses` | Feed directly into `net_cash_flow` | Only lagged versions (t, t−1, t−2, …) relative to the forecast origin. |
| `scripted_stress`, `performance_multiplier` (ground truth file) | These are literally the generator's hidden stress/quality dials | **Never a feature.** Validation/calibration only — see §5. |
| `data_complete` | Doesn't leak a value, just a flag | Safe as a feature (and useful — see §2). |
| Static `enterprises.csv` fields (sector, district, vintage, digital_adoption, loan terms, `field_investigator_id`) | Fixed at enterprise creation | Safe, always available. |
| `district_indices.csv` for month ≤ forecast origin | Exogenous, not derived from any single enterprise's outcome | Safe up to the origin month. **Not** safe for months inside the forecast window unless you're explicitly using a macro forecast/climatology for those — treat future macro as unknown in production. |

One subtlety worth flagging explicitly: **`emi_due` for future months is not leakage** the way the others are. `loan_amount`, `loan_tenure_months`, and `loan_start_month_offset` are static and known up front, so the entire EMI schedule (via the annuity formula in the methodology doc) can be computed in advance for any future month. That's a genuinely predictive, non-leaky feature — a big EMI landing next quarter is a real stress driver, not something borrowed from the target.

**First deliverable of the project, before any modelling:** a script that re-derives `net_cash_flow`, the EMI schedule, and the UPI reconciliation from raw inputs and asserts they match the file exactly. If they don't, something about the data pull is wrong and everything downstream is suspect.

---

## 1. Framing the three targets

**1a. Rolling net cash flow forecast.** For enterprise *e* at forecast origin
month *t*, using only information available up to and including *t*:

- `Y3(e,t) = Σ net_cash_flow(e, t+1 .. t+3)`
- `Y6(e,t) = Σ net_cash_flow(e, t+1 .. t+6)`

(Assumption stated explicitly: "rolling window" here means a forward-looking
cumulative forecast — the cash buffer the enterprise will generate over the
next quarter/half-year — since that's the operationally useful number for a
risk radar. If what's wanted is a trailing smoothed indicator instead, that's
a one-line change to a backward-looking rolling mean; it's kept as a
*feature*, not a target, in the pipeline below either way.)

With 24 months of panel per enterprise, a 6-month-ahead target leaves usable
origins roughly `t = 1..18`; the last 6 months of the panel can only be used
to *evaluate* forecasts made earlier, not to train new ones (there's nothing
to sum forward into). This shrinks the effective training set — worth
knowing before promising more precision than 398×~18 origins can support.

**1b. Stress assessment.** In deployment there is no `scripted_stress` column
— it's a hidden generator variable. So the *model's* stress label has to be
built from observables: e.g. `Y3(e,t) < α × trailing_avg_expenses(e)` OR
`≥2 of the next 3 months have repayment_status ∈ {missed, late}`. The hidden
`scripted_stress`/`performance_multiplier` fields are used only to check, in
backtesting, that this observable proxy actually tracks the true generative
stress arc (§5) — never as training input.

**1c. FI/sector risk roll-up.** Aggregate per-enterprise forecasts and stress
probabilities up two ways: by `field_investigator_id` (~20 enterprises per
FI — small enough that naive averaging will be noisy) and by `sector`. This
is a pooling/small-area-estimation problem, not just a `groupby().mean()`.

---

## 2. Feature engineering (everything here respects §0)

| Block | Features | Reasoning |
|---|---|---|
| **Static** | sector, district, log(vintage_years), digital_adoption, loan terms, encoded `field_investigator_id` | Fixed context; sector/district drive which macro index matters and how (e.g. rainfall helps dairy, hurts brick kilns). |
| **Forward-known credit** | EMI schedule for t+1..t+6 computed from static loan fields; debt-service ratio = trailing net cash flow ÷ upcoming EMI | Genuinely knowable in advance (see §0) and a real stress driver — a known EMI step-up is exactly the kind of thing an early-warning system should catch. |
| **Macro (≤ t only)** | district-month indices as of the origin, 3-month change in the sector-relevant index, active `local_disruption` in trailing 3 months | Exogenous, safe. Sector-specific direction matters — rainfall helps dairy, hurts brick_kiln, per the methodology's `shock_mult` logic — so don't just dump raw indices in, interact sector × relevant index. |
| **Dynamic panel (lagged)** | lag-1/2/3/6 of income, expenses, net_cash_flow; trailing 3/6-month mean, std, and linear trend slope; share of trailing months with negative net_cash_flow | Core autoregressive signal — this is where most of the forecasting power will come from. |
| **Repayment history (lagged)** | count of missed/late in trailing 6 months, lag-1 `savings_balance` | Cheap, strong stress signal; must be lagged per §0. |
| **Digital footprint (lagged)** | trailing UPI inflow/outflow growth, inflow-outflow ratio, `data_complete` rate | `data_complete` also doubles as a confidence weight — low-digital-adoption enterprise-months are noisier, so down-weight them in training loss rather than pretending they're equally reliable. |
| **Calendar** | month-of-year, sector × month | Sector seasonality is strong and structural (monsoon crash for brick kilns, festival bump for retail) — let the model see it explicitly rather than relying on lags alone to recover it. |

---

## 3. Splitting strategy

Two things a random shuffle would break here: temporal order (can't train on
month 15 and validate on month 8) and the fact that the interesting stress
episodes are concentrated in months 10–15 (drought shocks, the scripted
stress arc, disruption windows).

- **Forward-chaining time split:** train on origins t=1–12, validate 13–15,
  test 16–18 (adjusted down for the 6-month horizon's shorter usable range).
  No shuffling across time.
- **Held-out shock window:** additionally evaluate specifically on
  origins whose forecast window overlaps months 10–15 — this is the
  regime where the model actually needs to work, and average performance
  across all months can hide poor performance exactly there.

---

## 4. Modelling approach, staged

1. **Baseline (mandatory, not optional):** persistence — "next window equals
   trailing window of the same length." Any model that doesn't clearly beat
   this on out-of-time data isn't earning its complexity.
2. **Point + uncertainty forecast (1a):** gradient-boosted trees (LightGBM/
   XGBoost/CatBoost), one model per horizon, trained with quantile
   (pinball) loss at ~P10/P50/P90. The P10 band matters more than the
   median here — an enterprise whose *median* forecast looks fine but whose
   P10 is deeply negative is exactly the "quiet until it isn't" case a risk
   radar exists to catch.
3. **Stress classifier (1b):** same feature set, trained against the
   observable proxy label from §1b. PR-AUC over ROC-AUC as the headline
   metric, since flagged enterprises are a minority by construction
   (~20% per sector in the ground-truth generator, useful as a rough prior
   even though it's never fed to the model).
4. **Hierarchical pooling for FI/sector risk (1c):** a partial-pooling
   model — random intercepts for `field_investigator_id` nested under
   `district`/`sector` — on top of the enterprise-level stress
   probabilities. With ~20 enterprises per FI, a couple of noisy cases
   can otherwise swing an FI's whole portfolio score; partial pooling
   shrinks small, uncertain FI estimates toward the sector/district mean
   and gives a defensible credible interval on "% of this FI's portfolio
   at risk" instead of a single noisy point estimate. This is a natural
   fit for a PyMC-style hierarchical model if that's a tool you want to
   reuse from the thesis pipeline — same logic as partial pooling in a
   BYM2-style spatial model, just a simpler non-spatial hierarchy here
   (sector/FI/district as pooling groups, no adjacency structure needed
   unless district-level spatial smoothing is wanted later).

---

## 5. Validation, including the one-way door to ground truth

`enterprise_ground_truth.csv` is opened **only** in a final backtest step,
after the model is otherwise finished, and never merged back into training
data:

- Correlation / AUC between the model's stress probability and the true
  `scripted_stress` flag — sanity-checks that the observable proxy label
  actually captures the hidden stress arc.
- Check whether forecast error correlates with `performance_multiplier` —
  expected to be weak; a strong correlation would mean the model is
  failing specifically on structurally weaker/stronger businesses, which
  is useful diagnostic information even though the multiplier itself can
  never be a feature.
- Regression metrics (MAE, RMSE, pinball loss) and classification metrics
  (PR-AUC, calibration curve) reported per sector and per district as well
  as overall — expect real heterogeneity (e.g. brick_kiln likely harder to
  forecast around monsoon months).

---

## 6. Suggested execution order

```
01_data_audit.py            # re-derive net_cash_flow/EMI/UPI reconciliation, assert exact match
02_build_panel.py           # join district_indices + enterprises onto monthly_records, sort by (enterprise_id, month)
03_feature_engineering.py   # lag/rolling/trend/debt-service features — strict shift(1)+ discipline
04_define_targets.py        # Y3, Y6 forward sums; observable stress label; drop right-censored origins
05_splits.py                # forward-chaining time split + shock-window holdout
06_baseline_models.py       # persistence baseline
07_train_cashflow_models.py # quantile GBM per horizon
08_train_stress_classifier.py
09_hierarchical_risk_model.py   # FI/sector partial pooling
10_backtest_against_ground_truth.py   # only script allowed to open enterprise_ground_truth.csv
11_reporting_dashboard.py   # per-enterprise drill-down + FI/sector risk radar view
```

Each script's output is the next script's only input — makes it straightforward to re-run from any stage after a data refresh without re-deriving everything by hand.
