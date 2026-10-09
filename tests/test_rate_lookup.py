import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402

import build_rate_lookup as bl  # noqa: E402
import refi_rates as rr  # noqa: E402


class LookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        goc = rr.load_goc(os.path.join(rr.DATA_DIR, "goc_5y.csv"))
        cls.daily = bl.build_daily(goc, rr.load_tables(), rr.load_conventional_band())
        cls.by_date = cls.daily.set_index(pd.to_datetime(cls.daily["date"]))

    def row(self, d):
        return self.by_date.loc[pd.Timestamp(d)]

    def test_one_row_per_calendar_day(self):
        self.assertEqual(len(self.daily), (self.daily["date"].max() - self.daily["date"].min()).days + 1)
        self.assertTrue(self.daily["date"].is_unique)

    def test_known_value_matches_workflow(self):
        r = self.row("2023-11-17")                      # GoC 3.82 + CMB 25.5 + lender 55
        self.assertAlmostEqual(r["ins_all_in_base_pct"], 4.625, places=6)
        self.assertAlmostEqual(r["conv_all_in_base_pct"], 3.82 + 1.90, places=6)

    def test_weekend_carries_last_observation(self):
        sat, fri = self.row("2023-10-14"), self.row("2023-10-13")
        self.assertEqual(sat["goc_5y_pct"], fri["goc_5y_pct"])
        self.assertEqual(sat["ins_all_in_base_pct"], fri["ins_all_in_base_pct"])
        self.assertEqual(str(sat["goc_obs_date"]), "2023-10-13")

    def test_blank_before_coverage(self):
        self.assertTrue(pd.isna(self.row("2021-11-01")["ins_all_in_base_pct"]))
        self.assertFalse(pd.isna(self.row("2021-11-01")["conv_all_in_base_pct"]))
        self.assertFalse(pd.isna(self.row("2021-07-02")["goc_5y_pct"]))
        self.assertFalse(pd.isna(self.row("2021-12-14")["ins_all_in_base_pct"]))

    def test_low_base_high_ordered(self):
        d = self.daily.dropna(subset=["ins_all_in_base_pct"])
        self.assertTrue((d["ins_all_in_low_pct"] <= d["ins_all_in_base_pct"]).all())
        self.assertTrue((d["ins_all_in_base_pct"] <= d["ins_all_in_high_pct"]).all())
        self.assertTrue((d["conv_all_in_base_pct"] >= d["ins_all_in_base_pct"]).all())

    def test_lag_column_is_earlier_value(self):
        self.assertEqual(self.row("2023-11-17")["ins_all_in_base_lag30_pct"], self.row("2023-10-18")["ins_all_in_base_pct"])

    def test_monthly_keys(self):
        m = bl.build_monthly(self.daily)
        self.assertIn("2023-11", set(m["month"]))
        self.assertIn("Nov 2023", set(m["month_label"]))


if __name__ == "__main__":
    unittest.main()
