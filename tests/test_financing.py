import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import financing as fin  # noqa: E402
import gettel_workflow as gw  # noqa: E402
import refi_rates as rr  # noqa: E402
import pandas as pd  # noqa: E402


def mtg(lender, d, amount=None, co=None):
    return {"lender": lender, "lender_co": co, "date": d, "amount": amount}


class FinancingTests(unittest.TestCase):
    def test_custodian_with_originator_and_high_ltv_is_likely_insured(self):
        m = mtg("COMPUTERSHARE TRUST COMPANY OF CANADA", date(2023, 9, 22), 80_893_080, "CANADA ICI CAPITAL CORPORATION")
        score, cls, ev = fin.classify(m, 91_600_000, date(2023, 9, 22))
        self.assertEqual((score, cls), (8, "Likely insured"))
        self.assertIn("Canada Ici", ev)

    def test_custodian_without_originator_is_unknown(self):
        score, cls, _ = fin.classify(mtg("COMPUTERSHARE TRUST COMPANY OF CANADA", date(2018, 1, 11), 15_203_161), None, None)
        self.assertEqual((score, cls), (3, "Unknown"))

    def test_private_individual_is_conventional(self):
        score, cls, _ = fin.classify(mtg("PAUL DARYL WILSON", date(2016, 10, 7), 250_000), None, None)
        self.assertEqual((score, cls), (-10, "Likely conventional"))

    def test_kv_capital_only_penalised_through_2023(self):
        self.assertEqual(fin.classify(mtg("KV CAPITAL INC", date(2023, 9, 28), 3_375_000), None, None)[1], "Likely conventional")
        self.assertEqual(fin.classify(mtg("KV CAPITAL INC", date(2024, 9, 28), 3_375_000), None, None)[0], 0)

    def test_canada_ici_only_counts_from_2021(self):
        self.assertEqual(fin.classify(mtg("CANADA ICI CAPITAL CORPORATION", date(2019, 5, 1)), None, None)[0], 0)
        self.assertEqual(fin.classify(mtg("CANADA ICI CAPITAL CORPORATION", date(2023, 5, 1)), None, None)[0], 3)

    def test_banks_carry_no_weight_and_missing_lender_is_not_private(self):
        self.assertEqual(fin.classify(mtg("ATB FINANCIAL", date(2023, 9, 8), 2_532_600), None, None)[0], 0)
        self.assertEqual(fin.classify(mtg(float("nan"), date(2023, 9, 8)), None, None)[0], 0)

    def test_dscr_test_adds_points(self):
        base = fin.classify(mtg("PEOPLES TRUST COMPANY", date(2023, 5, 1), 5_000_000), None, None)[0]
        more = fin.classify(mtg("PEOPLES TRUST COMPANY", date(2023, 5, 1), 5_000_000), None, None, 1.35, 1.10)[0]
        self.assertEqual(more - base, 2)

    def test_combined_status(self):
        self.assertEqual(fin.combine_status("Likely insured", "ok", "distressed"), "ok")
        self.assertEqual(fin.combine_status("Likely conventional", "ok", "distressed"), "distressed")
        self.assertEqual(fin.combine_status("Unknown", "ok", "ok"), "ok")
        self.assertIn("Uncertain", fin.combine_status("Unknown", "ok", "distressed"))


class ParserCoTests(unittest.TestCase):
    def test_c_o_line_captured(self):
        lines = ["MORTGAGEE - COMPUTERSHARE TRUST COMPANY OF CANADA.", "C/O CANADA ICI CAPITAL CORPORATION",
                 "106 205 CARNEGIE DRIVE", "ORIGINAL PRINCIPAL AMOUNT: $80,893,080"]
        self.assertEqual(gw.parse_lender_co(lines), "CANADA ICI CAPITAL CORPORATION")

    def test_no_c_o(self):
        self.assertIsNone(gw.parse_lender_co(["MORTGAGEE - ATB FINANCIAL.", "25TH FLOOR", "ORIGINAL PRINCIPAL AMOUNT: $1"]))


class ConventionalSeriesTests(unittest.TestCase):
    def test_all_in_is_goc_plus_spread(self):
        idx = pd.bdate_range("2021-10-01", "2026-10-08")
        d = rr.build_conventional_series(pd.Series(3.0, index=idx), rr.load_conventional_band())
        self.assertAlmostEqual(d.loc["2023-08-15", "all_in_base_pct"], 3.0 + 1.90)
        self.assertAlmostEqual(d.loc["2026-10-01", "all_in_low_pct"], 3.0 + 1.25)

    def test_conventional_costs_more_than_insured_at_same_loan(self):
        idx = pd.bdate_range("2021-10-01", "2026-10-08")
        goc = pd.Series(3.0, index=idx)
        ins = rr.build_daily_series(goc, rr.load_tables())
        conv = rr.build_conventional_series(goc, rr.load_conventional_band())
        a = rr.screen_loan(ins, "2023-10-18", 5_000_000, amort_years=40, renewal_date="2028-10-18", noi=500_000)
        b = rr.screen_loan(conv, "2023-10-18", 5_000_000, amort_years=25, renewal_date="2028-10-18", noi=500_000)
        self.assertGreater(b["orig_rate_base_pct"], a["orig_rate_base_pct"])
        self.assertLess(b["dscr_renewal_base"], a["dscr_renewal_base"])


if __name__ == "__main__":
    unittest.main()
