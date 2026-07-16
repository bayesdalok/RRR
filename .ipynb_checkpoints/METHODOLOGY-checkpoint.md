# Data Generation Methodology -- Rural Risk Radar

This document explains how every synthetic value in this dataset was constructed,
so the modeling and app teams (and hackathon judges) can audit the logic rather
than treat it as an opaque `np.random` dump.

## 1. Geography
46 real Gujarat towns/villages are grouped into 5 regions that mirror
actual regional economic geography:
- **Central Gujarat** (Anand, Kheda belt): the traditional Amul dairy cooperative
  heartland -- dairy enterprises are weighted 3x more likely to appear here.
- **South Gujarat** (Surat, Navsari, Valsad): high rainfall, textile/weaving economy.
- **North Gujarat**: moderate rainfall, mixed agriculture.
- **Saurashtra**: semi-arid, groundnut/oil-mill economy, drought-prone.
- **Kutch**: arid, drought-prone, and the real historical center of Gujarat's
  handicrafts/embroidery economy -- handicrafts enterprises are weighted 3.5x
  more likely to appear here.

Each enterprise is assigned a region using sector-specific affinity weights,
then a specific town within that region uniformly at random.

## 2. Enterprise identity
- **Enterprise ID**: `GJ` + first two letters of the town name (uppercase) +
  6 random digits, e.g. an Anand-based enterprise gets an ID like `GJAN482913`.
  Uniqueness is enforced at generation time.
- **Names** are built compositionally from three pools -- honorific prefixes
  (Shree, Jay, Om, regional mata names like Umiya/Khodiyar/Ambe), owner
  surnames drawn from communities realistically tied to rural livelihoods
  (Rabari/Bharwad = pastoral/dairy, Prajapati = potter/oil-pressing, Vankar =
  weaving, Patel/Desai = general trading/agriculture), and sector-specific
  business suffixes -- combined in one of three patterns so names don't read
  as templated.
- **Sector counts** are randomized via a Dirichlet allocation across 12
  sectors (not a fixed N-per-sector grid), summing to a randomly chosen
  portfolio size between 300 and 400.

## 3. Sectors (12 total)
dairy, poultry, food_processing, handicrafts, rural_retail, flour_mill,
oil_mill, textile_weaving, brick_kiln, agri_input_retail, tea_stall_eatery,
auto_repair.

Each sector has its own: base income range, monthly seasonality curve,
region affinity, typical UPI transaction count/ticket size, and a
digital-adoption range (see below). Brick kilns additionally have an
**operating_months** restriction -- they realistically shut down during the
monsoon (June-September) and this shows up as a near-zero-activity period
in their monthly records, not a demand dip.

## 4. Enterprise-level realism factors
- **Vintage (years in operation)**: older enterprises get lower idiosyncratic
  month-to-month volatility (an established customer base smooths income),
  simulated via a `vintage_stability` multiplier on noise variance.
- **Digital adoption score** (0.1-0.9): controls what fraction of an
  enterprise's *real* cash flow is visible via UPI. The remainder is assumed
  to be cash transactions, which are real in rural India but invisible to
  any digital-proxy-based model -- this is a deliberately realistic
  limitation of the UPI-as-proxy approach, not an oversight.
- **Loan source**: bank / SHG group loan / NBFC microfinance / none, each
  with a different effective EMI burden (NBFC microfinance carries the
  highest rate, consistent with real microfinance pricing; SHG group loans
  the lowest).
- **Missing data**: ~5% of income/expenses/savings_balance values are
  randomly nulled in monthly_records.csv to simulate real-world field
  reporting gaps -- deliberately, so the modeling pipeline has to handle
  missing values rather than assume a clean feed.

## 5. Climate & market indices (district/town level)
Each index starts from a shared Gujarat-wide seasonal base curve, then adds:
- a **region-level offset and volatility** (drought-prone regions like
  Saurashtra and Kutch swing harder on rainfall, using a 1.6x shock
  multiplier during the injected monsoon-shock window), and
- **town-level idiosyncratic noise** on top.

Two scripted shocks are injected at fixed points in the 24-month timeline so
every district feels them (to varying degrees): a delayed/weak monsoon
(months 14-16), and a poultry feed price spike (months 7-9, hitting
Saurashtra hardest since feed/grain markets are more exposed there). A milk
procurement price cut (months 10-12) is also injected into the milk price
index.

## 6. Monthly financial records
Income = base_income x seasonality x sector-specific market-shock multiplier
x scripted-stress multiplier (if applicable) x idiosyncratic noise x a slow
per-enterprise drift term. Expenses are a randomized fraction (55-75%) of
income. Net cash flow = income - expenses - EMI (if any).

**Scripted stress arcs**: ~15-22% of enterprises per sector are pre-selected
to go through a deliberate 6-month stress arc (months 10-15 of the
24-month window) with income dropping progressively then partially
recovering -- this ensures the risk model has real, learnable signal to
detect, rather than relying on the incidental noise, and gives the demo a
concrete "here's an enterprise the system caught early" story.

**Repayment status** (on_time / late / missed) is derived from operating
cash flow versus the EMI due that month (with a small savings cushion), not
generated independently -- so late/missed payments are a downstream
consequence of cash flow stress, matching how repayment actually breaks
down in reality.

## 7. Transaction-level UPI ledger (transactions.csv)
For every enterprise-month, a target UPI-visible income and expense figure
is computed as `real_amount x digital_adoption_score` (with some noise).
The ledger generator then:
1. Picks a transaction count from the sector's typical range, scaled by the
   enterprise's digital adoption score (a low-digital-adoption enterprise
   logs fewer, not just smaller, transactions).
2. Splits the target amount across that many transactions using a lognormal
   distribution (many small/medium transactions, a few larger ones -- not a
   flat split), clipped to the sector's plausible ticket-size range.
3. Assigns each transaction a random timestamp within the month, a
   direction (in/out), and a counterparty type (customer_payment,
   cooperative_payout, supplier_payment, wage_payment, loan_repayment, etc.)

**Critically**: `upi_txn_count` and `upi_txn_volume` in monthly_records.csv
are *recomputed from this ledger after generation*, not produced
independently -- so the monthly aggregate file and the transaction-level
file are always internally consistent. If you sum the "in" transactions in
transactions.csv for a given enterprise-month, you get exactly the
upi_txn_volume shown in monthly_records.csv for that row.

## 8. What this data does NOT include (by design)
- No real personal identifiers -- names, IDs, and locations are all
  synthetic/compositional, per the hackathon's data-sensitivity constraint.
- No cash transactions in the ledger -- only the UPI-visible portion,
  consistent with the framing of UPI as a *proxy* signal, not a complete
  income record.
- No claim of real predictive accuracy -- shock timing, magnitudes, and
  scripted stress arcs are designed to make the story demonstrable within a
  4-day hackathon, not to model actual historical Gujarat agricultural or
  credit conditions.


## Actual generated portfolio stats (this run)
- Total enterprises: 309
- Total transaction ledger rows: 231234
- Months of history: 24 (2024-08 onward)
