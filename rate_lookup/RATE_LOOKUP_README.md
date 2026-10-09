# Rate lookup: estimated 5-year multifamily mortgage rate on any date

Built 2026-10-09 by `build_rate_lookup.py` (repo: gettel-title-scraper). Coverage: GoC from 2021-07-02;
insured estimates from 2021-12-14; conventional estimates from 2021-10-01; all through 2026-10-08.

**These are modeled estimates, not quoted or observed rates.** Use them to size what a loan likely cost around a sale or
registration date. Do not quote them to a client as a lender's rate.

## Files

| File | Use |
|---|---|
| `rate_lookup_daily.csv` | One row per calendar day. Primary lookup table. |
| `rate_lookup_monthly.csv` | Month averages of the same columns, keyed `YYYY-MM` and `Mon YYYY`. |
| `rate_lookup.xlsx` | Both tables, the source tables, the data dictionary and this README in one workbook. |
| `data_dictionary.csv` | Every column: meaning, units, source, confidence. |
| `data/*.csv` (repo) | Inputs: `goc_5y.csv`, `cmb_issue_spreads.csv`, `lender_spread_band.csv`, `conventional_spread_band.csv`. |

## How to look up a rate

Headline columns for a sale date: **`ins_all_in_base_pct`** (if the loan was CMHC-insured) and **`conv_all_in_base_pct`**
(if conventional). `*_low_pct` and `*_high_pct` give the range. Percent units (4.625 = 4.625%).

Excel (the Daily sheet is contiguous, so exact match works; the sale date in A2 must be a real date, not text):
```
=XLOOKUP(A2, Daily!A:A, Daily!L:L, "no data")
=XLOOKUP(A2, Daily!A:A, Daily!S:S, "no data")
=IFERROR(VLOOKUP(A2, Daily!A:AB, MATCH("ins_all_in_base_pct", Daily!1:1, 0), FALSE), "no data")
```
Column letters on the Daily sheet: date = A, goc_5y_pct = B, ins_all_in_low/base/high = K/L/M,
conv_all_in_low/base/high = R/S/T.
Python:
```python
import pandas as pd
rates = pd.read_csv("rate_lookup_daily.csv", parse_dates=["date"])
sales["date"] = pd.to_datetime(sales["Sale Date"]).dt.normalize()
sales = sales.merge(rates[["date", "ins_all_in_base_pct", "conv_all_in_base_pct"]], on="date", how="left")
```
Example: a sale on 2023-10-18 gives GoC 4.32%, CMB spread 25.5 bps,
insured 5.005% / **5.125%** / 5.175% (low / base / high),
conventional 6.020% / **6.220%** / 6.820%.
Latest row (2026-10-08): GoC 3.60%, insured base 4.280%, conventional base 5.100%.

A blank means no estimate exists for that date (before the coverage start).

## How each number is built

- **GoC 5-year** (`goc_5y_pct`): Bank of Canada daily benchmark yield V39053. Hard data.
- **CMB spread** (`cmb_spread_bps`): spread of the 5-year Canada Mortgage Bond over the GoC, from the 20 quarterly Canada Housing Trust
  issues since 2021-12-14, held constant until the next issue. From 2024-03 it is the Bank of Canada published initial spread; before that
  it is the issue yield minus the GoC close on the pricing date (verified to reproduce all nine calculated spreads exactly).
  The two methods can differ by up to about 6 bps.
- **Insured all-in** = GoC + CMB spread + lender spread over CMB. CMHC-insured loans are quoted over the CMB, not the GoC.
  The lender spread is a band (low / base / high) by quarter: sourced from CMLS commentary ranges through 2024Q1, estimated for 2022Q4,
  and **assumed (45 / 55 / 70 bps) from 2024Q2**. 2022Q2's base is an index average, a different definition from neighbouring quarters.
  Replace the assumed rows in `data/lender_spread_band.csv` with real quotes and rebuild.
- **Conventional all-in** = GoC + conventional spread (uninsured multifamily is priced over the GoC with a wider spread).
  Bands by quarter come from CMLS and Intellifi commentary for 2021 to 2023 (150 bps at 2021 year-end, 210 to 250 typical at 2022 year-end,
  160 to 210 through 2023) and are **estimates from 2024** (no public Alberta multifamily series exists).

## Confidence by period

| Period | Insured band | Conventional band |
|---|---|---|
| 2021-12 to 2022-Q1 | partly sourced | partly sourced |
| 2022 | sourced / estimated | partly sourced to sourced |
| 2023 | sourced / partly sourced | sourced / partly sourced |
| 2024-Q1 | sourced | estimated |
| 2024-Q2 onward | **assumed** | **estimated** |

The `ins_confidence` and `conv_confidence` columns carry this row by row. The GoC and CMB spread inputs are hard data in every period;
the uncertainty sits almost entirely in the lender and conventional spreads, which move slowly. Before-and-after comparisons
(for example a loan's original vs renewal rate) are therefore more reliable than absolute levels, because a constant spread cancels.

## Limits and cautions

1. **Five-year terms only.** Ten-year insured loans price over the 10-year CMB and GoC; the CMB spread was roughly 45 bps for ten years vs
   about 30 for five in 2023. Not modeled here.
2. **Sale date is not the rate-lock date.** Rates are usually locked weeks before closing or registration. The `*_lag30/60/90_pct` columns give the
   base estimate 30, 60 and 90 days earlier; use them to see how much a lock-date difference would move the answer.
3. **No coverage before 2021-12-14** (insured) or 2021-10-01 (conventional). Sales earlier than that return blanks.
   Extending back needs CMB issue spreads and lender or conventional spread commentary for those years.
4. **Insured vs conventional is not known from the sale record.** Use `ins_*` for loans believed to be CMHC-insured (typically 75%+ leverage,
   40-year amortization, specialized lenders), `conv_*` otherwise, and show both when unsure. The mortgage workflow scores this per loan.
5. **Not an offered rate.** Actual pricing depends on leverage, property quality, borrower, term, lender appetite and insurance product (MLI Select, etc.).
6. **Updating.** Download a fresh Bank of Canada "Selected Bond Yields" file into `data/goc_5y.csv`, add each new CMB issue to `data/cmb_issue_spreads.csv`,
   and run `python build_rate_lookup.py`. GoC rows after the last observation do not exist, so the table ends on the last GoC date.

## Provenance

GoC yields: Bank of Canada V39053 (file `goc_5y.csv`, last observation 2026-10-08).
CMB spreads and the insured lender band: prior analysis (`refi_distress_screen.py`); CMB 2024+ spreads checked against the Bank of Canada CMB_PURCH dataset.
Conventional bands: deep-research summary of CMLS Commercial Mortgage Commentary and Intellifi reports (Q4 2021, Q4 2022, Q1 and Q3 2023); later years estimated.
