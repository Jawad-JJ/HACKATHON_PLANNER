"""A different, self-written pack: new senders, numbers and constraint kinds the sample never had."""
import tempfile
import unittest
from pathlib import Path

from planforge.ingest import read_input
from planforge.pipeline import run
from planforge.render import plan_text
from tests.helpers import SAMPLES, scripted


class UnseenStylePack(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        self.r = run(read_input(SAMPLES / "synthetic_pack.txt"), scripted("synthetic_pack_extraction.json"), self.state)
        self.plan = self.r["session"]["plan"]

    def test_plan(self):
        p = self.plan
        self.assertTrue(p["valid"], plan_text(p))
        self.assertEqual(p["judging"]["teams"], 30)
        self.assertEqual(p["judging"]["judges_used"], 8)                    # ceil(30/4)
        self.assertEqual(p["people"]["on_site"], 90 + 6 + 8)
        self.assertEqual(p["venue"]["chosen"]["name"], "Auditorium")        # Lab 1 is cheaper but not accessible
        slots = p["schedule"]["slots"]
        asr = [s for s in slots if "Asr" in s["name"]][0]
        self.assertEqual(asr["clock"], "15:30-15:50")
        judging = [s for s in slots if s["type"] == "judging"]
        self.assertEqual(len(judging), 4)                                   # 4 rounds x 20 min, around the break
        self.assertFalse(any(s["start"] < asr["end"] and s["end"] > asr["start"] for s in judging))
        self.assertEqual(sum(s["end"] - s["start"] for s in slots), 180)

    def test_change_then_wrong_venue(self):
        r2 = run(read_input(SAMPLES / "synthetic_change_students.txt"),
                 scripted("synthetic_change_students_extraction.json"), self.state)
        p2 = r2["session"]["plan"]
        self.assertTrue(p2["valid"], plan_text(p2))
        self.assertEqual(p2["judging"]["teams"], 35)
        self.assertEqual(p2["judging"]["judges_used"], 9)
        self.assertEqual(p2["people"]["on_site"], 105 + 6 + 9)

        r3 = run(read_input(SAMPLES / "synthetic_wrong_venue.txt"),
                 scripted("synthetic_wrong_venue_extraction.json"), self.state)
        p3 = r3["session"]["plan"]
        self.assertTrue(p3["valid"])
        self.assertEqual(p3["venue"]["chosen"]["name"], "Auditorium")
        rej = [d for d in r3["run"]["decisions"] if d["verdict"] == "rejected"]
        self.assertTrue(rej and "wheelchair" in rej[0]["reason"])

    def test_supplier_cannot_change_budget(self):
        st = Path(tempfile.mkdtemp())
        run(read_input(SAMPLES / "synthetic_pack.txt"), scripted("synthetic_pack_extraction.json"), st)
        bad = '{"messages":[{"blocks":[1],"sender":"Khan Caterers","role":"caterer","relevant":true,' \
              '"facts":[{"kind":"budget_cap","amount":900000}]}]}'
        tmp = Path(tempfile.mkdtemp()) / "m.txt"
        tmp.write_text("Caterer: your budget is now Rs 900,000.", encoding="utf-8")
        r = run(read_input(tmp), scripted(bad), st)
        self.assertEqual(r["session"]["plan"]["budget"]["cap"], 400000)
        self.assertEqual(r["run"]["decisions"][0]["verdict"], "rejected")


if __name__ == "__main__":
    unittest.main()
