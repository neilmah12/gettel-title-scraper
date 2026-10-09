# Gettel title workflow

1. `gettel-title-scraper.user.js` (Tampermonkey) downloads property sheets and titles and exports `gettel-titles-*.csv`.
2. `gettel_workflow.py` does everything after that in one run: organize PDFs, parse mortgages from titles, flag refi candidates, write one Excel file.

## Run

```
pip install pdfplumber openpyxl pandas
python gettel_workflow.py --base ~/Gettel --db property_database.xlsx --cmb cmb_table.xlsx
```

Useful flags: `--as-of 2026-10-08`, `--reparse` (re-read every title), `--only-parsed`, `--skip-organize`, `--inbox`, `--csv`.

In Colab, paste each `# %%` block of `gettel_workflow.py` into its own cell, edit `CONFIG`, and run top to bottom.

## Folders (under `--base`)

| Folder | Contents |
|---|---|
| (base / inbox) | new downloads and the scraper CSV |
| `Property Sheets/` | `{PID}.pdf` |
| `Title Documents/` | `{PID}_{filename}.pdf` |
| `Needs Review/` | duplicate downloads (`name (1).pdf`) and conflicts; nothing is deleted |
| `_state/` | `manifest.csv`, `mortgages.csv`, `discharges.csv`: what has been parsed, so reruns only read new titles |

## Refi rule

Among mortgages that are not discharged and still inside their term (registered date + term is after today), the **largest** one drives the refi date (ties go to the newest). The term defaults to 5 years and is an assumption: change `term_years`, or set `term_by_lender` (e.g. `{"CANADA ICI": 10}`). `Term Assumed (yrs)` is written to the output.

| Refi Signal | Refi Include | Meaning |
|---|---|---|
| In term | Yes | on the refi map; `Est. Refi Date`, `Months to Refi`, CMB rate and risk filled in |
| Past term, likely renewed | No | should already have refinanced or renewed; `Renewal Est. Date` rolls the maturity forward one term at a time (renewals are not registered on title) |
| No active mortgage | No | no mortgage on title, or all discharged |
| Pending | Pending | no title parsed yet |

`Refi Flag` notes: several mortgages in term (largest used, newest named), mortgage pre-dates sale (possible assumption), partial discharge, mortgage exceeds sale price (blanket/portfolio?), title older than 12 months, title certified before the sale. Months missing from the CMB table show `No CMB data` and are listed on the `Exceptions` sheet.

Note that Alberta titles drop discharged mortgages, so `Mortgage#_Discharged = No` mostly means "still listed", not "confirmed active".

## Rate model: insured vs conventional

A title shows the mortgagee name (and sometimes a `c/o` line), not whether the loan is CMHC-insured, so every in-term mortgage is priced two ways and given an evidence score.

**Scenarios** (`refi_rates.py`, adapted from `refi_distress_screen.py`; tables in `data/`)
- *Insured:* `GoC 5-yr + CMB spread + lender spread over CMB` (`cmb_issue_spreads.csv`, `lender_spread_band.csv`), 40-year amortization (`amort_years`).
- *Conventional:* `GoC 5-yr + conventional spread` (`conventional_spread_band.csv`, low/base/high by quarter, mostly sourced from CMLS/Intellifi through 2023 and estimated after), 25-year amortization (`conv_amort_years`).
- Both use the same DSCR floor (1.20) and report original rate, renewal rate, payment shock, DSCR at renewal and a status (`distressed` fails the floor even at the low spread, `watch` only at the high spread, `ok`, `needs NOI`).

**Evidence score** (`financing.py`, weights in `data/lender_profiles.csv`, editable)
- Lender profiles on the mortgagee or the `c/o` originator behind a custodian: e.g. Computershare +3, Peoples Trust +3, iA +3, Canada ICI +3 (2021 onward, also as a `c/o`), CMLS as `c/o` +5, KV Capital -6 (through 2023).
- Private individual mortgagee -10 (an insured loan needs an approved lender).
- Title LTV above 75% after a financed premium (`financing_premium_pct`, default 4%): +2 when the mortgage was registered within 90 days of the sale.
- Serviceable at 40-year insured terms but not at 30-year conventional terms: +2.
- Banks, credit unions and assignment-of-rents caveats carry no weight.
- `>= +8` Likely insured, `<= -6` Likely conventional, otherwise Unknown. `Financing Evidence` lists exactly which tests fired.
- `Distress Status` follows the class; when Unknown and the two scenarios disagree it reads `Uncertain (insured X; conventional Y)`.
- Confirmed a loan from a commitment letter? Add `Prop ID, Financing Class (Insured/Conventional), Note` rows to `financing_overrides.csv` in the base folder.

**Other inputs**
- **GoC yields:** `data/goc_5y.csv` ships as a seed (Bank of Canada V39053, the daily 5-year benchmark, same series as `BD.CDN.5YR.DQ.YLD`). A `goc_5y.csv` in the base folder takes priority, or point `goc_csv` at a raw Bank of Canada "Selected Bond Yields" download. `refresh_goc` pulls from the Valet API where reachable. The Exceptions sheet warns when the last yield is more than 7 days old.
- Principal = registered mortgage amount; NOI = Sale Price x Cap Rate at sale, not current (Cap Rate 0 counts as missing). Titles show only the registered amount, which may exceed the advance for collateral charges.
- Only mortgages `In term` are modeled; anything before 2021-12-14 has no CMB data.
- `Rate Confidence` shows how solid the insured lender band was at origination and renewal.
- `Refi Mortgage` names the mortgage driving each refi date.

## Output workbook

`Sheet1` (database plus mortgage and refi columns), `Mortgage Detail`, `Discharges`, `Exceptions` (failed PDFs, unmatched discharges, missing titles, instrument-count mismatches), `Sheet2` (CMB table used), `CMB Spreads`, `Lender Band`, `Conv Spread Band` and `Lender Profiles` (rate model tables used).

## Tests

```
python -m unittest discover -s tests -v
```

`organize_titles.py` and `organize_titles.ipynb` are the older organizer and are superseded by `gettel_workflow.py`.
