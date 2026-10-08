"""Rate model checks with a flat mock GoC series (the real series needs the Bank of Canada)."""
import os
import sys
import unittest
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refi_rates as rr  # noqa: E402


def daily(goc_flat=3.0):
    idx = pd.bdate_range("2021-12-01", "2026-10-08")
    return rr.build_daily_series(pd.Series(goc_flat, index=idx), rr.load_tables())


class RateTests(unittest.TestCase):
    def test_tables_load(self):
        cmb, band = rr.load_tables()
        self.assertEqual(len(cmb), 20)
        self.assertEqual(str(band.quarter.iloc[-1]), "2026Q4")
        self.assertEqual(cmb.spread_bps.iloc[0], 30.2)     # calculated before 2024
        self.assertEqual(cmb.spread_bps.iloc[-1], 13.0)    # BoC published

    def test_all_in_rate_is_goc_plus_cmb_plus_lender(self):
        d = daily(3.0)
        row = d.loc["2021-12-14"]
        self.assertAlmostEqual(row["all_in_base_pct"], 3.0 + 0.302 + 0.52, places=6)
        self.assertAlmostEqual(row["all_in_low_pct"], 3.0 + 0.302 + 0.42, places=6)

    def test_cmb_spread_forward_filled_by_issue_date(self):
        d = daily()
        self.assertEqual(d.loc["2022-03-14", "cmb_spread_bps"], 30.2)
        self.assertEqual(d.loc["2022-03-15", "cmb_spread_bps"], 37.2)

    def test_no_data_before_first_issue(self):
        with self.assertRaises(ValueError):
            rr.screen_loan(daily(), "2021-06-01", 1_000_000)

    def test_higher_goc_at_renewal_raises_payment(self):
        idx = pd.bdate_range("2021-12-01", "2026-10-08")
        goc = pd.Series([2.0 if d < pd.Timestamp("2026-01-01") else 4.0 for d in idx], index=idx)
        d = rr.build_daily_series(goc, rr.load_tables())
        r = rr.screen_loan(d, "2022-01-14", 10_000_000, renewal_date="2026-10-01")
        self.assertGreater(r["payment_shock_base_pct"], 0)
        self.assertGreater(r["renewal_rate_base_pct"], r["orig_rate_base_pct"])

    def test_status_follows_dscr_floor(self):
        d = daily()
        kw = dict(orig_date="2022-01-14", principal=10_000_000, daily=d, renewal_date="2026-10-01")
        self.assertEqual(rr.screen_loan(noi=2_000_000, **kw)["status"], "ok")
        self.assertEqual(rr.screen_loan(noi=300_000, **kw)["status"], "distressed")
        self.assertEqual(rr.screen_loan(**kw)["status"], "needs NOI")

    def test_future_renewal_uses_current_market(self):
        r = rr.screen_loan(daily(), "2023-10-18", 5_000_000, renewal_date="2028-10-18")
        self.assertEqual(r["renewal_basis"], "current market")


if __name__ == "__main__":
    unittest.main()
