"""
Insured vs conventional evidence score for a mortgage registered on an Alberta title.

A title shows only the mortgagee name (and sometimes a c/o line), so the score combines:
  * lender profiles (data/lender_profiles.csv, editable) matched on the mortgagee or c/o text
  * private-individual mortgagee (an insured loan needs an approved lender)
  * title leverage after allowing for a financed CMHC premium: insured loans are typically high leverage
    (up to 85%+ of value) while conventional multifamily debt is typically 75% or less, so a high title LTV
    points to insured and a low one to conventional
  * whether the registered amount is only serviceable at an insured-style amortization

>= +8 Likely insured | <= -6 Likely conventional | otherwise Unknown (run both rate scenarios),
labelled "leans insured" at >= +4 and "leans conventional" at <= -2.
The weights are deliberately conservative and should be checked against loans you have confirmed.
"""
import os
import re

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INSURED_AT, CONVENTIONAL_AT = 8, -6
LEAN_INSURED, LEAN_CONVENTIONAL = 4, -2
HIGH_LTV, LOW_LTV = 0.75, 0.65
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


def title_ltv(m, sale_price, sale_date, window_days=90):
    """Registered amount / sale price, only for a mortgage registered within window_days of the sale
    (an acquisition loan) and not above the price (a larger amount points to a blanket or portfolio charge)."""
    amt = m.get("amount")
    if not (amt and pd.notna(amt) and sale_price and sale_date and m.get("date")):
        return None
    if abs((m["date"] - sale_date).days) > window_days or amt > sale_price:
        return None
    return amt / sale_price


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

    ltv = title_ltv(m, sale_price, sale_date)
    if ltv is not None:
        adj = ltv / (1 + premium_pct / 100)
        if adj > HIGH_LTV:
            add(3, f"Title LTV {ltv:.0%} ({adj:.0%} after a {premium_pct:g}% financed premium): above the ~75% conventional ceiling")
        elif ltv <= LOW_LTV:
            add(-3, f"Title LTV {ltv:.0%}: typical conventional leverage (insured loans are usually higher)")

    if dscr_insured_40 is not None and dscr_conv_30 is not None \
            and dscr_insured_40 >= floor_insured and dscr_conv_30 < floor_conv:
        add(2, f"Serviceable at 40-yr insured terms (DSCR {dscr_insured_40:.2f}) but not at 30-yr conventional ({dscr_conv_30:.2f})")

    if score >= INSURED_AT:
        cls = "Likely insured"
    elif score <= CONVENTIONAL_AT:
        cls = "Likely conventional"
    elif score >= LEAN_INSURED:
        cls = "Unknown (leans insured)"
    elif score <= LEAN_CONVENTIONAL:
        cls = "Unknown (leans conventional)"
    else:
        cls = "Unknown"
    return score, cls, "; ".join(ev) if ev else "No distinguishing evidence on title"


def combine_status(cls, insured, conventional):
    """One Distress Status from the two scenarios, according to the financing class."""
    if cls == "Likely insured":
        return insured
    if cls == "Likely conventional":
        return conventional
    if insured == conventional:
        return insured
    lean = cls[cls.find("(") + 1:-1] if cls.startswith("Unknown (") else ""
    return f"Uncertain (insured {insured}; conventional {conventional})" + (f", {lean}" if lean else "")
