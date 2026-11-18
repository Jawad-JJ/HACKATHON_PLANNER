"""Unit tests: parsing, dates, aliases, ledger matching, pricing variants, ingestion, trace honesty."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from planforge import ledger
from planforge.ingest import read_input, split_blocks
from planforge.planner import build_plan
from planforge.reader import normalize_fact, norm_role, num, parse_reading
from planforge.trace import CallRecord, token_totals


class Parsing(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual([num("Rs 1,200"), num("1.5 lakh"), num("PKR 650,000"), num("50k")], [1200, 150000, 650000, 50000])

    def test_dates(self):
        self.assertEqual(ledger.parse_date("9 Nov", 2026), date(2026, 11, 9))
        self.assertEqual(ledger.parse_date("Nov 12", 2026), date(2026, 11, 12))
        self.assertEqual(ledger.parse_date("2026-10-20"), date(2026, 10, 20))
        self.assertIsNone(ledger.parse_date("yesterday"))

    def test_aliases(self):
        self.assertEqual(normalize_fact({"kind": "venue", "name": "X", "seats": "250", "rent": "Rs 9,000"})["capacity"], 250)
        self.assertEqual(norm_role("Dean's office"), "organizer")
        self.assertEqual(norm_role("Accounts"), "finance")

    def test_code_fenced_json(self):
        out = parse_reading('```json\n{"messages":[{"blocks":[1],"role":"finance","facts":[{"kind":"committed_cost","item":"x","amount":"Rs 5"}]}]}\n```', 1)
        self.assertEqual(out[0]["facts"][0]["amount"], 5)

    def test_item_matching(self):
        self.assertTrue(ledger.same_item("printing", "printing bill"))
        self.assertFalse(ledger.same_item("printing", "prizes"))


class Ingest(unittest.TestCase):
    def test_exact_text_and_hash(self):
        p = Path(tempfile.mkdtemp()) / "m.txt"
        p.write_bytes("﻿Salam bhai!\r\nab Rs 1,200 hoga\r\n\r\nNext msg".encode("utf-8"))
        raw = read_input(p)
        self.assertEqual(raw.blocks, ["Salam bhai!\nab Rs 1,200 hoga", "Next msg"])
        self.assertEqual(len(raw.sha256), 64)

    def test_one_line_per_message(self):
        self.assertEqual(len(split_blocks("a\nb\nc\nd")), 4)


def F(i, kind, **kw):
    return dict(kind=kind, id=f"T{i}", order=i, key=[kind, str(i)], state="active", date_iso=None, status="confirmed", **kw)


class PlannerVariants(unittest.TestCase):
    def base(self):
        return [F(1, "headcount", role="students", count=30), F(2, "team_size", value=3), F(3, "duration", minutes=120),
                F(4, "budget_cap", amount=200000), F(5, "headcount", role="judges", count=5),
                F(6, "judge_terms", minutes_per_team=10)]

    def test_hourly_venue_delivery_unavailable_no_honorarium(self):
        facts = self.base() + [
            F(7, "venue_option", name="Hall H", capacity=50, cost_per_hour=10000),
            F(8, "venue_option", name="Hall Z", capacity=500, cost=1000, available=False),
            F(9, "food_option", name="Box", price_per_head=500, fixed_cost=2000)]
        facts = ledger.active_facts(facts)
        p = build_plan(facts)
        self.assertEqual(p["venue"]["chosen"]["name"], "Hall H")
        self.assertEqual(p["venue"]["chosen"]["cost"], 20000)              # 2 hours x 10,000
        self.assertEqual(p["food"]["cost"], p["food"]["quantity"] * 500 + 2000)
        self.assertEqual(p["judging"]["judges_used"], 1)                   # no per-judge limit: fewest judges that fit the time
        self.assertEqual(p["judging"]["judging_minutes"], 100)
        self.assertFalse(any(i["level"] == "fail" for i in p["issues"]))


class TraceHonesty(unittest.TestCase):
    def test_bad_tag_refused(self):
        with self.assertRaises(ValueError):
            CallRecord(number=1, run_id=1, tag="planning", model="m", request=[], response="", status="ok")

    def test_unreported_tokens_not_estimated(self):
        t = token_totals([{"input_tokens": None, "output_tokens": None, "total_tokens": None}])
        self.assertEqual((t["total"], t["unreported_calls"]), (0, 1))


if __name__ == "__main__":
    unittest.main()


class HeadcountRoles(unittest.TestCase):
    def test_role_synonyms(self):
        roles = [normalize_fact({"kind": "headcount", "role": r, "count": 5})["role"]
                 for r in ("participants", "Volunteers", "jury members", "students")]
        self.assertEqual(roles, ["students", "volunteers", "judges", "students"])


class Words(unittest.TestCase):
    def test_number_words_and_hours(self):
        self.assertEqual([num("three"), num("Ten staff"), num("twenty")], [3, 10, 20])
        self.assertEqual(normalize_fact({"kind": "duration", "hours": 4})["minutes"], 240)
