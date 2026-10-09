"""
Rate model for CMHC-insured 5-year fixed multifamily mortgages (Edmonton).
Adapted from refi_distress_screen.py (same maths, tables moved to data/*.csv).

    all-in rate = GoC 5-yr benchmark yield (BoC Valet BD.CDN.5YR.DQ.YLD)
                  + CMB spread (data/cmb_issue_spreads.csv, forward-filled by issue date)
                  + lender spread over CMB (data/lender_spread_band.csv, low / base / high by quarter)

Data status:
  * CMB spreads: hard data; 2024-03 onward Bank of Canada published, earlier calculated.
  * Lender spread: a BAND, not observed rates. 2024Q2 onward is ASSUMED; edit the CSV with real quotes.
  * No data before the first CMB issue (2021-12-14).
Rates are nominal annual, compounded semi-annually, monthly payments.
"""
import os
import urllib.request
import json

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
GOC_SERIES = "BD.CDN.5YR.DQ.YLD"
CASES = ("low", "base", "high")


# --------------------------------------------------------------------------- tables
def load_tables(data_dir=DATA_DIR):
    """Return (cmb_issues, lender_band) DataFrames from the CSVs in data_dir."""
    cmb = pd.read_csv(os.path.join(data_dir, "cmb_issue_spreads.csv"), parse_dates=["issue_date"])
    cmb["spread_bps"] = cmb["boc_published_bps"].fillna(cmb["calc_daily_close_bps"])
    band = pd.read_csv(os.path.join(data_dir, "lender_spread_band.csv"))
    band["quarter"] = pd.PeriodIndex(band["quarter"], freq="Q")
    return cmb, band


def load_conventional_band(data_dir=DATA_DIR):
    """Conventional (uninsured) multifamily spread over the GoC 5-yr yield, low/base/high bps by quarter."""
    band = pd.read_csv(os.path.join(data_dir, "conventional_spread_band.csv"))
    band["quarter"] = pd.PeriodIndex(band["quarter"], freq="Q")
    return band


# --------------------------------------------------------------------------- GoC yields
def parse_boc_download(path):
    """
    Parse a Bank of Canada 'Selected Bond Yields' download (daily series first, then weekly and
    monthly blocks). 'Bank holiday' rows are skipped. Returns a daily Series of yields (%).
    """
    rows, in_daily = {}, False
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not in_daily:
                in_daily = line.startswith("Date,V")
                continue
            if not line:
                break                                   # blank line ends the daily block
            d, _, v = (x.strip() for x in line.partition(","))
            try:
                rows[pd.Timestamp(d)] = float(v)
            except ValueError:
                continue
    if not rows:
        raise ValueError(f"No daily yields found in {path}")
    return pd.Series(rows, name="goc_5y_yield").sort_index()


def load_goc(csv_path, refresh=False, start="2021-12-01", log=print):
    """
    Daily GoC 5-yr yield (%) as a Series. Reads csv_path (columns date,yield) when it exists.
    With refresh=True, or no file, pulls the Bank of Canada Valet API and saves csv_path.
    A failed pull falls back to the saved file.
    """
    def read_cache():
        with open(csv_path, encoding="utf-8-sig") as f:
            if f.readline().startswith("Selected Bond Yields"):
                return parse_boc_download(csv_path)       # raw Bank of Canada download
        df = pd.read_csv(csv_path, parse_dates=[0])
        return pd.Series(df.iloc[:, 1].astype(float).values, index=df.iloc[:, 0], name="goc_5y_yield").sort_index()

    if os.path.exists(csv_path) and not refresh:
        return read_cache()
    try:
        url = f"https://www.bankofcanada.ca/valet/observations/{GOC_SERIES}/json?start_date={start}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            obs = json.load(resp)["observations"]
        s = pd.Series({pd.Timestamp(o["d"]): float(o[GOC_SERIES]["v"]) for o in obs if GOC_SERIES in o},
                      name="goc_5y_yield").sort_index()
        s.rename_axis("date").to_csv(csv_path, header=["yield"])
        log(f"GoC yields pulled from Bank of Canada: {len(s)} days to {s.index.max().date()}")
        return s
    except Exception as e:
        if os.path.exists(csv_path):
            log(f"[WARN] GoC refresh failed ({e}); using saved {csv_path}")
            return read_cache()
        raise


# --------------------------------------------------------------------------- rate maths
def _monthly_rate(rate_pct):
    return (1 + rate_pct / 100 / 2) ** (1 / 6) - 1


def payment(principal, rate_pct, amort_years):
    i, n = _monthly_rate(rate_pct), amort_years * 12
    return principal * i / (1 - (1 + i) ** -n)


def balance_after(principal, rate_pct, amort_years, months):
    i = _monthly_rate(rate_pct)
    pmt = payment(principal, rate_pct, amort_years)
    return principal * (1 + i) ** months - pmt * ((1 + i) ** months - 1) / i


def max_loan(noi, rate_pct, amort_years, dscr):
    i, n = _monthly_rate(rate_pct), amort_years * 12
    return noi / dscr / 12 * (1 - (1 + i) ** -n) / i


# --------------------------------------------------------------------------- daily series
def build_daily_series(goc, tables, cmb_method="published"):
    """GoC + forward-filled CMB spread + lender band by quarter -> daily all-in rates (low/base/high)."""
    cmb, band = tables
    col = "spread_bps" if cmb_method == "published" else "calc_daily_close_bps"
    issues = cmb.set_index("issue_date").sort_index()
    first = issues.index.min()
    df = pd.DataFrame({"goc_5y_yield": goc.sort_index()})
    union = df.index.union(issues.index)
    df["cmb_spread_bps"] = issues[col].reindex(union).ffill().reindex(df.index)

    lb = band.set_index("quarter")
    last_q = lb.index.max()
    qs = pd.PeriodIndex([min(q, last_q) for q in df.index.to_period("Q")], freq="Q")
    for c in CASES:
        df[f"lender_{c}_bps"] = lb[f"{c}_bps"].reindex(qs).to_numpy()
        df[f"all_in_{c}_pct"] = df["goc_5y_yield"] + (df["cmb_spread_bps"] + df[f"lender_{c}_bps"]) / 100
    df["lender_confidence"] = lb["confidence"].reindex(qs).to_numpy()
    df = df[df.index >= first]
    df.attrs["first_covered"] = first
    return df


def build_conventional_series(goc, band):
    """GoC + conventional spread band by quarter, shaped like build_daily_series() so screen_loan() works on it."""
    lb = band.set_index("quarter")
    first, last_q = lb.index.min().start_time, lb.index.max()
    df = pd.DataFrame({"goc_5y_yield": goc.sort_index()})
    qs = pd.PeriodIndex([min(q, last_q) for q in df.index.to_period("Q")], freq="Q")
    for c in CASES:
        df[f"lender_{c}_bps"] = lb[f"{c}_bps"].reindex(qs).to_numpy()
        df[f"all_in_{c}_pct"] = df["goc_5y_yield"] + df[f"lender_{c}_bps"] / 100
    df["lender_confidence"] = lb["confidence"].reindex(qs).to_numpy()
    df = df[df.index >= first]
    df.attrs["first_covered"] = first
    return df


def _row_at(daily, date):
    date = pd.Timestamp(date)
    first = daily.attrs.get("first_covered", daily.index.min())
    if date < first:
        raise ValueError(f"{date.date()} is before {first.date()}; no CMB data")
    sub = daily.loc[: min(date, daily.index.max())]
    return sub.iloc[-1], sub.index[-1]


# --------------------------------------------------------------------------- screen
def screen_loan(daily, orig_date, principal, noi=None, noi_at_orig=None, amort_years=40, term_years=5,
                renewal_date=None, renewal_amort_years=None, dscr_floor=1.20, orig_rate_pct=None,
                goc_shock_bps=0):
    """
    Estimate original rate, renewal rate, payment shock, DSCR and refinance gap for one loan.
    Status: 'distressed' = fails the DSCR floor even at the LOW lender spread;
            'watch' = fails only at the HIGH spread; 'ok' = passes at HIGH; 'needs NOI' without NOI.
    """
    orig_ts = pd.Timestamp(orig_date)
    ren_ts = pd.Timestamp(renewal_date) if renewal_date else orig_ts + pd.DateOffset(years=term_years)
    orig, _ = _row_at(daily, orig_ts)
    ren, ren_used = _row_at(daily, ren_ts)
    rem = renewal_amort_years or (amort_years - term_years)

    out = {
        "orig_date": orig_ts.date(), "renewal_date": ren_ts.date(), "renewal_rates_as_of": ren_used.date(),
        "renewal_basis": "scheduled" if ren_ts <= daily.index.max() else "current market",
        "orig_rate_source": "actual" if orig_rate_pct is not None else "estimated",
        "lender_confidence_orig": orig["lender_confidence"],
        "lender_confidence_renewal": ren["lender_confidence"],
    }
    for c in CASES:
        r0 = orig_rate_pct if orig_rate_pct is not None else float(orig[f"all_in_{c}_pct"])
        ds0 = 12 * payment(principal, r0, amort_years)
        bal = balance_after(principal, r0, amort_years, term_years * 12)
        r1 = float(ren[f"all_in_{c}_pct"]) + goc_shock_bps / 100
        ds1 = 12 * payment(bal, r1, rem)
        out[f"orig_rate_{c}_pct"] = round(r0, 3)
        out[f"renewal_rate_{c}_pct"] = round(r1, 3)
        out[f"balance_at_renewal_{c}"] = round(bal)
        out[f"payment_shock_{c}_pct"] = round((ds1 / ds0 - 1) * 100, 1)
        if noi_at_orig:
            out[f"dscr_orig_{c}"] = round(noi_at_orig / ds0, 2)
        if noi:
            out[f"dscr_renewal_{c}"] = round(noi / ds1, 2)
            out[f"max_refi_loan_{c}"] = round(max_loan(noi, r1, rem, dscr_floor))
            out[f"refi_gap_{c}"] = round(bal - out[f"max_refi_loan_{c}"])   # + = shortfall
    if noi:
        if out["dscr_renewal_low"] < dscr_floor:
            out["status"] = "distressed"
        elif out["dscr_renewal_high"] < dscr_floor:
            out["status"] = "watch"
        else:
            out["status"] = "ok"
    else:
        out["status"] = "needs NOI"
    return out
