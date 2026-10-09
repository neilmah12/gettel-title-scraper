"""
Insured vs conventional evidence score for a mortgage registered on an Alberta title.

A title shows only the mortgagee name (and sometimes a c/o line), so the score combines:
  * lender profiles (data/lender_profiles.csv, editable) matched on the mortgagee or c/o text
  * private-individual mortgagee (an insured loan needs an approved lender)
  * title leverage after allowing for a financed CMHC premium
  * whether the registered amount is only serviceable at an insured-style amortization

>= +8 Likely insured | <= -6 Likely conventional | otherwise Unknown (run both rate scenarios).
The weights are deliberately conservative and should be checked against loans you have confirmed.
"""
import os
import re

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INSURED_AT, CONVENTIONAL_AT = 8, -6
CORPORATE = re.compile(
    r"\b(LTD|LIMITED|INC|CORP|CORPORATION|BANK|TRUST|COMPANY|CREDIT|UNION|CAPITAL|FINANCIAL|FUND|FUNDS|LP|"
    r"MORTGAGE|INSURANCE|SOCIETY|ASSOCIATION|HOLDINGS|PARTNERSHIP|ALBERTA|CANADA|CO)\b", re.I)


def load_profiles(path=None):
    df = pd.read_csv(path or os.path.join(DATA_DIR, "lender_profiles.csv"))
    df["pattern"] = df["pattern"].str.upper()
    return df


def _s(x):
    return x if isinstance(x, str) else ""


def is_individual(lender_text):
    first = _s(lender_text).split(";")[0].strip()
    return bool(first) and not CORPORATE.search(first)


def classify(m, sale_price=None, sale_date=None, dscr_insured_40=None, dscr_conv_30=None,
             profiles=None, premium_pct=4.0, floor_insured=1.20, floor_conv=1.25):
    """m: mortgage dict (lender, lender_co, date, amount). Returns (score, class, evidence text)."""
    profiles = load_profiles() if profiles is None else profiles
    score, ev = 0, []

    def add(pts, why):
        nonlocal score
        score += pts
        ev.append(f"{pts:+d} {why}")

    year = m["date"].year if m.get("date") else None
    fields = {"lender": _s(m.get("lender")).upper(), "co": _s(m.get("lender_co")).upper()}
    for r in profiles.itertuples():
        if r.pattern not in fields[r.field]:
            continue
        if year is not None:
            if pd.notna(r.year_from) and year < r.year_from:
                continue
            if pd.notna(r.year_to) and year > r.year_to:
                continue
        add(int(r.score), f"{'c/o ' if r.field == 'co' else ''}{r.pattern.title()}: {r.note}")

    if is_individual(m.get("lender")):
        add(-10, "Private individual mortgagee (insured loans need an approved lender)")

    amt = m.get("amount")
    if (amt and pd.notna(amt) and sale_price and sale_date and m.get("date") and abs((m["date"] - sale_date).days) <= 90
            and amt <= sale_price):
        ltv = amt / (1 + premium_pct / 100) / sale_price
        if ltv > 0.75:
            add(2, f"Title LTV {ltv:.0%} after a {premium_pct:g}% financed premium (above conventional range)")

    if dscr_insured_40 is not None and dscr_conv_30 is not None \
            and dscr_insured_40 >= floor_insured and dscr_conv_30 < floor_conv:
        add(2, f"Serviceable at 40-yr insured terms (DSCR {dscr_insured_40:.2f}) but not at 30-yr conventional ({dscr_conv_30:.2f})")

    cls = "Likely insured" if score >= INSURED_AT else "Likely conventional" if score <= CONVENTIONAL_AT else "Unknown"
    return score, cls, "; ".join(ev) if ev else "No distinguishing evidence on title"


def combine_status(cls, insured, conventional):
    """One Distress Status from the two scenarios, according to the financing class."""
    if cls == "Likely insured":
        return insured
    if cls == "Likely conventional":
        return conventional
    if insured == conventional:
        return insured
    return f"Uncertain (insured {insured}; conventional {conventional})"
