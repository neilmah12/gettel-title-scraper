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

## Rate model (renewal rate and distress)

`refi_rates.py` (adapted from `refi_distress_screen.py`) prices CMHC-insured 5-year fixed loans:
`all-in = GoC 5-yr + CMB spread + lender spread over CMB`. Tables live in `data/cmb_issue_spreads.csv` (add each new CMB issue) and `data/lender_spread_band.csv` (replace the assumed 2024Q2+ rows with real quotes).

For each property with a mortgage `In term`, the workflow adds original rate (low/base/high), renewal rate, payment shock, DSCR at renewal and a `Distress Status` (`distressed` fails the 1.20 floor even at the low lender spread, `watch` only at the high spread, `ok`, or `needs NOI`).

- **GoC yields:** read from `goc_5y.csv` (columns `date,yield`) in the base folder. If the file is missing, the workflow pulls Bank of Canada series `BD.CDN.5YR.DQ.YLD` and saves it; `refresh_goc` forces a new pull. Where the Bank of Canada host is blocked (e.g. the cloud session), run the pull once locally or in Colab and put `goc_5y.csv` in the folder; otherwise the rate columns stay blank and the Exceptions sheet says why.
- **Inputs:** principal = registered mortgage amount; amortization 40 years (`amort_years`); NOI = Sale Price x Cap Rate at sale, not current (a Cap Rate of 0 counts as missing).
- **Scope:** only mortgages `In term`. Anything before 2021-12-14 has no CMB data. Set `cmb_priced_lenders` (e.g. `["COMPUTERSHARE", "PEOPLES TRUST"]`) to apply the model to CMB-priced lenders only; empty applies it to all, which overstates the CMHC assumption for conventional bank loans.
- `Rate Confidence` shows how solid the lender band was at origination and at renewal.

## Output workbook

`Sheet1` (database plus mortgage and refi columns), `Mortgage Detail`, `Discharges`, `Exceptions` (failed PDFs, unmatched discharges, missing titles, instrument-count mismatches), `Sheet2` (CMB table used), `CMB Spreads` and `Lender Band` (rate model tables used).

## Tests

```
python -m unittest discover -s tests -v
```

`organize_titles.py` and `organize_titles.ipynb` are the older organizer and are superseded by `gettel_workflow.py`.
