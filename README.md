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
| None | No | no mortgage on title, or all discharged |
| Pending | Pending | no title parsed yet |

`Refi Flag` notes: several mortgages in term (largest used, newest named), mortgage pre-dates sale (possible assumption), partial discharge, mortgage exceeds sale price (blanket/portfolio?), title older than 12 months, title certified before the sale. Months missing from the CMB table show `No CMB data` and are listed on the `Exceptions` sheet.

Note that Alberta titles drop discharged mortgages, so `Mortgage#_Discharged = No` mostly means "still listed", not "confirmed active".

## Output workbook

`Sheet1` (database plus mortgage and refi columns), `Mortgage Detail`, `Discharges`, `Exceptions` (failed PDFs, unmatched discharges, missing titles, instrument-count mismatches), `Sheet2` (CMB table used).

## Tests

```
python -m unittest discover -s tests -v
```

`organize_titles.py` and `organize_titles.ipynb` are the older organizer and are superseded by `gettel_workflow.py`.
