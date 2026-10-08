"""Run with:  python -m unittest discover -s tests -v"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gettel_workflow as gw  # noqa: E402

# Encumbrance excerpt of a real title: discharge of an old mortgage (cites its number on the
# header line, so the old parser skipped it), a new mortgage, page-break noise in between.
DISCHARGE_TITLE = """ENCUMBRANCES, LIENS & INTERESTS
REGISTRATION
NUMBER DATE (D/M/Y) PARTICULARS
-----------------------------------------------------------------------------
222 035 285 12/02/2022 CAVEAT
RE : ASSIGNMENT OF RENTS AND LEASES
CAVEATOR - OLYMPIA TRUST COMPANY.
CALGARY
( CONTINUED )
-----------------------------------------------------------------------------
ENCUMBRANCES, LIENS & INTERESTS
PAGE 2
REGISTRATION # 232 315 198
NUMBER DATE (D/M/Y) PARTICULARS
-----------------------------------------------------------------------------
ALBERTA T5T5Z2
232 315 801 18/10/2023 DISCHARGE OF MORTGAGE 222035284
AND CAVEAT 222035285
PARTIAL
AFFECTED PARTY: KEVIN GAINER
232 351 743 17/11/2023 MORTGAGE
MORTGAGEE - PEOPLES TRUST COMPANY.
1400, 888 DUNSMUIR STREET
VANCOUVER
ORIGINAL PRINCIPAL AMOUNT: $1,761,475
232 351 744 17/11/2023 CAVEAT
RE : ASSIGNMENT OF RENTS AND LEASES
CAVEATOR - PEOPLES TRUST COMPANY.
* ADDITIONAL REGISTRATIONS MAY BE SHOWN ON THE CONDOMINIUM ADDITIONAL
PLAN SHEET
TOTAL INSTRUMENTS: 004
THE REGISTRAR OF TITLES CERTIFIES THIS TO BE AN
"""


def parse(text):
    h = gw.ENC_HEADER_RE.search(text)
    entries = gw.split_entries(text[h.end():])
    mortgages = [gw.parse_mortgage_entry(e) for e in entries if e["etype"] == "MORTGAGE"]
    discharges = [gw.parse_discharge_entry(e) for e in entries if "DISCHARGE" in e["etype"]]
    gw.match_discharges(mortgages, discharges)
    return entries, mortgages, discharges


class ParserTests(unittest.TestCase):
    def test_all_four_instruments_found(self):
        entries, _, _ = parse(DISCHARGE_TITLE)
        self.assertEqual(len(entries), 4)

    def test_discharge_header_with_reference(self):
        _, _, discharges = parse(DISCHARGE_TITLE)
        self.assertEqual(len(discharges), 1)
        d = discharges[0]
        self.assertEqual(d["ref_regnum"], "222035284")
        self.assertTrue(d["partial"])
        self.assertEqual(d["date"], date(2023, 10, 18))

    def test_mortgage_fields(self):
        _, mortgages, _ = parse(DISCHARGE_TITLE)
        self.assertEqual(len(mortgages), 1)
        m = mortgages[0]
        self.assertEqual((m["lender"], m["amount"], m["date"]), ("PEOPLES TRUST COMPANY", 1761475.0, date(2023, 11, 17)))

    def test_discharge_of_unlisted_mortgage_leaves_new_mortgage_active(self):
        _, mortgages, discharges = parse(DISCHARGE_TITLE)
        self.assertEqual(mortgages[0]["discharged"], "No")
        self.assertFalse(discharges[0]["unmatched"])

    def test_page_noise_not_in_entries(self):
        entries, _, _ = parse(DISCHARGE_TITLE)
        caveat = entries[0]
        self.assertFalse(any("REGISTRATION #" in l or "PAGE 2" in l for l in caveat["lines"]))

    def test_lender_wrapping_onto_next_line(self):
        text = ("ENCUMBRANCES, LIENS & INTERESTS\n"
                "182 058 105 09/03/2018 MORTGAGE\n"
                "MORTGAGEE - COMPUTERSHARE TRUST COMPANY OF\n"
                "CANADA.\n"
                "100 UNIVERSITY AVENUE\n"
                "ORIGINAL PRINCIPAL AMOUNT: $2,000,000\n")
        _, mortgages, _ = parse(text)
        self.assertEqual(mortgages[0]["lender"], "COMPUTERSHARE TRUST COMPANY OF CANADA")

    def test_individual_lender_without_period_stops_at_care_of(self):
        text = ("ENCUMBRANCES, LIENS & INTERESTS\n162 281 424 07/10/2016 MORTGAGE\n"
                "MORTGAGEE - PAUL DARYL WILSON\nC/O 2900 MANULIFE PLACE\n10180-101 ST\nEDMONTON\n"
                "ORIGINAL PRINCIPAL AMOUNT: $250,000\n")
        _, mortgages, _ = parse(text)
        self.assertEqual(mortgages[0]["lender"], "PAUL DARYL WILSON")

    def test_two_mortgagees(self):
        text = ("ENCUMBRANCES, LIENS & INTERESTS\n232 325 894 25/10/2023 MORTGAGE\n"
                "MORTGAGEE - CANADA ICI CAPITAL CORPORATION.\n106-205 CARNEGIE DRIVE\n"
                "MORTGAGEE - GENERAL BANK OF CANADA.\n100, 11523 100 AVE\nORIGINAL PRINCIPAL AMOUNT: $6,345,000\n")
        _, mortgages, _ = parse(text)
        self.assertEqual(mortgages[0]["lender"], "CANADA ICI CAPITAL CORPORATION; GENERAL BANK OF CANADA")

    def test_discharge_of_listed_mortgage(self):
        text = ("ENCUMBRANCES, LIENS & INTERESTS\n"
                "182 058 105 09/03/2018 MORTGAGE\nMORTGAGEE - ABC BANK.\nORIGINAL PRINCIPAL AMOUNT: $1,000,000\n"
                "192 000 001 01/02/2019 DISCHARGE OF MORTGAGE 182058105\n")
        _, mortgages, _ = parse(text)
        self.assertEqual(mortgages[0]["discharged"], "Yes")

    def test_discharge_without_reference_marks_unknown(self):
        text = ("ENCUMBRANCES, LIENS & INTERESTS\n"
                "182 058 105 09/03/2018 MORTGAGE\nMORTGAGEE - ABC BANK.\n"
                "192 000 001 01/02/2019 DISCHARGE OF MORTGAGE\nMORTGAGEE - SOMEONE ELSE.\n")
        _, mortgages, discharges = parse(text)
        self.assertEqual(mortgages[0]["discharged"], "Unknown")
        self.assertTrue(discharges[0]["unmatched"])

    def test_old_style_registration_number(self):
        text = ("ENCUMBRANCES, LIENS & INTERESTS\n3173NI 27/06/1963 CAVEAT\nCAVEATOR - THE CITY OF EDMONTON.\n"
                "982 281 412 16/09/1998 CAVEAT\nTOTAL INSTRUMENTS: 002\n")
        entries, _, _ = parse(text)
        self.assertEqual([e["regnum"] for e in entries], ["3173NI", "982 281 412"])

    def test_certified_date(self):
        self.assertEqual(gw.parse_certified("CERTIFIES THIS TO BE\nTITLE REPRESENTED HEREIN THIS 25 DAY OF\nJANUARY, 2024 AT 08:40 P.M."),
                         date(2024, 1, 25))


class RefiTests(unittest.TestCase):
    AS_OF = date(2026, 10, 8)

    @staticmethod
    def mtg(d, discharged="No"):
        return {"date": d, "discharged": discharged}

    def test_inside_window(self):
        r = gw.refi_for_pid([self.mtg(date(2023, 11, 17))], date(2023, 10, 17), self.AS_OF)
        self.assertEqual(r["include"], "Yes")
        self.assertEqual(r["refi_date"], date(2028, 11, 17))
        self.assertEqual(r["months"], 26)
        self.assertEqual(gw.refi_window_label(r["months"]), "25–30 months")

    def test_october_1_2021_is_past_term(self):
        r = gw.refi_for_pid([self.mtg(date(2021, 10, 1))], date(2021, 9, 1), self.AS_OF)
        self.assertEqual(r["include"], "No")
        self.assertIn("past its 5-yr term", r["flag"])

    def test_old_mortgage_ignored_when_newer_one_qualifies(self):
        r = gw.refi_for_pid([self.mtg(date(2017, 9, 11)), self.mtg(date(2024, 3, 1))], date(2023, 6, 26), self.AS_OF)
        self.assertEqual(r["include"], "Yes")
        self.assertEqual(r["mortgage"]["date"], date(2024, 3, 1))

    def test_assumed_mortgage_kept_and_noted(self):
        r = gw.refi_for_pid([self.mtg(date(2022, 5, 1))], date(2024, 1, 1), self.AS_OF)
        self.assertEqual(r["include"], "Yes")
        self.assertIn("pre-dates sale", r["flag"])

    def test_past_term_gets_renewal_estimate(self):
        r = gw.refi_for_pid([self.mtg(date(2018, 1, 11))], date(2017, 12, 1), self.AS_OF)
        self.assertEqual((r["include"], r["signal"]), ("No", "Past term, likely renewed"))
        self.assertEqual(r["renewal_date"], date(2028, 1, 11))
        self.assertIn("next maturity est. Jan 2028", r["flag"])

    def test_largest_in_term_drives_and_newest_is_noted(self):
        big = {"date": date(2024, 1, 1), "discharged": "No", "amount": 5_000_000.0, "lender": "BIG BANK"}
        small = {"date": date(2025, 6, 1), "discharged": "No", "amount": 500_000.0, "lender": "SMALL LENDER"}
        r = gw.refi_for_pid([small, big], date(2023, 1, 1), self.AS_OF)
        self.assertEqual(r["mortgage"]["lender"], "BIG BANK")
        self.assertEqual(r["refi_date"], date(2029, 1, 1))
        self.assertIn("newest in-term is SMALL LENDER", r["flag"])

    def test_lender_term_override(self):
        m = {"date": date(2023, 1, 1), "discharged": "No", "lender": "CANADA ICI CAPITAL CORPORATION"}
        r = gw.refi_for_pid([m], None, self.AS_OF, 5, {"canada ici": 10})
        self.assertEqual((r["term"], r["refi_date"]), (10, date(2033, 1, 1)))

    def test_mortgage_exceeding_sale_price_flagged(self):
        m = {"date": date(2024, 1, 1), "discharged": "No", "amount": 50_000_000.0}
        r = gw.refi_for_pid([m], None, self.AS_OF, sale_price=40_000_000)
        self.assertIn("exceeds sale price", r["flag"])

    def test_discharged_and_missing(self):
        self.assertEqual(gw.refi_for_pid([self.mtg(date(2024, 1, 1), "Yes")], None, self.AS_OF)["flag"], "All mortgages discharged")
        self.assertEqual(gw.refi_for_pid([], None, self.AS_OF)["flag"], "No mortgage on title")

    def test_duplicate_browser_suffix(self):
        self.assertEqual(gw.canon("Property 46727 (2).pdf"), "property 46727.pdf")
        self.assertEqual(gw.canon("232042594_46669258_0_3 (1).pdf"), "232042594_46669258_0_3.pdf")


if __name__ == "__main__":
    unittest.main()
