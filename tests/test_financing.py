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
        self.assertEqual((score, cls), (9, "Likely insured"))
        self.assertIn("Canada Ici", ev)

    def test_low_leverage_leans_conventional(self):
        m = mtg("SERVUS CREDIT UNION LTD", date(2023, 10, 13), 900_000)
        score, cls, ev = fin.classify(m, 1_697_500, date(2023, 10, 13))
        self.assertEqual((score, cls), (-3, "Unknown (leans conventional)"))
        self.assertIn("typical conventional leverage", ev)

    def test_leverage_between_65_and_75_is_neutral(self):
        self.assertEqual(fin.classify(mtg("ATB FINANCIAL", date(2023, 1, 1), 700_000), 1_000_000, date(2023, 1, 1))[0], 0)

    def test_high_leverage_from_unspecialised_lender_leans_insured(self):
        score, cls, _ = fin.classify(mtg("PEOPLES TRUST COMPANY", date(2023, 11, 17), 1_761_475), 1_920_000, date(2023, 10, 17))
        self.assertEqual((score, cls), (6, "Unknown (leans insured)"))

    def test_ltv_ignored_for_refinance_or_amount_above_price(self):
        self.assertIsNone(fin.title_ltv(mtg("X", date(2025, 1, 1), 1_000_000), 2_000_000, date(2023, 1, 1)))
        self.assertIsNone(fin.title_ltv(mtg("X", date(2023, 1, 1), 3_000_000), 2_000_000, date(2023, 1, 1)))

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
        self.assertTrue(fin.combine_status("Unknown (leans conventional)", "ok", "distressed").endswith("leans conventional"))


class ParserCoTests(unittest.TestCase):
    def test_c_o_line_captured(self):
        lines = ["MORTGAGEE - COMPUTERSHARE TRUST COMPANY OF CANADA.", "C/O CANADA ICI CAPITAL CORPORATION",
                 "106 205 CARNEGIE DRIVE", "ORIGINAL PRINCIPAL AMOUNT: $80,893,080"]
        self.assertEqual(gw.parse_lender_co(lines), "CANADA ICI CAPITAL CORPORATION")

    def test_no_c_o(self):
        self.assertIsNone(gw.parse_lender_co(["MORTGAGEE - ATB FINANCIAL.", "25TH FLOOR", "ORIGINAL PRINCIPAL AMOUNT: $1"]))


class LeverTests(unittest.TestCase):
    def test_big_stressed_loan_in_sweet_spot_is_call_now(self):
        out = {"DSCR at Renewal (base)": 1.02, "Conv DSCR at Renewal": 0.75, "Financing Class": "Likely insured"}
        r = gw.prospect_lever(out, 14, 80_893_080, 91_600_000, True)
        self.assertEqual((r["Prospect Score"], r["Prospect Priority"]), (3 + 3 + 2, "Call now"))
        self.assertEqual((r["DSCR Range Low"], r["DSCR Range High"]), (0.75, 1.02))

    def test_unknown_class_uses_worst_case_dscr(self):
        out = {"DSCR at Renewal (base)": 1.6, "Conv DSCR at Renewal": 0.95, "Financing Class": "Unknown"}
        r = gw.prospect_lever(out, 25, 2_000_000, 3_000_000, True)
        self.assertEqual(r["Prospect Score"], 2 + 1 + 3)
        self.assertIn("financing type unknown", r["Priority Why"])
        self.assertIn("scenarios disagree", r["Priority Why"])
        self.assertEqual(r["Data Confidence"], "Low")

    def test_no_noi_scores_no_stress_and_flags_doubt(self):
        r = gw.prospect_lever({"Financing Class": "Likely conventional"}, 10, 6_000_000, 8_000_000, False)
        self.assertEqual(r["Prospect Score"], 3 + 2 + 0)
        self.assertEqual(r["Prospect Priority"], "Worth a call")
        self.assertIsNone(r["DSCR Range Low"])


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
