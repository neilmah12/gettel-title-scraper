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

Uses the newest mortgage that is not discharged and is still inside its 5 year term (registered date + 5 years is after today).

- Past term: `Refi Include = No`, flagged, off the map. Should already have refinanced.
- A mortgage registered before the sale that is still in term is kept and noted as a possible assumption.
- `Refi Include = Pending` means no title has been parsed for that property yet.
- `Est. Refi Date` is looked up in the CMB table (`Maturity Month`, `Estimated 5-Yr CMB Rate`, `Risk Tier for Refi`). Months missing from the table show `No CMB data` and are listed on the `Exceptions` sheet.

## Output workbook

`Sheet1` (database plus mortgage and refi columns), `Mortgage Detail`, `Discharges`, `Exceptions` (failed PDFs, unmatched discharges, missing titles, instrument-count mismatches), `Sheet2` (CMB table used).

## Tests

```
python -m unittest discover -s tests -v
```

`organize_titles.py` and `organize_titles.ipynb` are the older organizer and are superseded by `gettel_workflow.py`.
