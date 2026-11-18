"""End-to-end: sample pack, both practice messages, prediction, trace honesty, rollback."""
import tempfile
import unittest
from pathlib import Path

from planforge.ingest import read_input
from planforge.pipeline import run
from planforge.render import plan_text, trace_text
from tests.helpers import SAMPLES, scripted


class SamplePack(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        self.r1 = run(read_input(SAMPLES / "sample_pack.txt"), scripted("sample_pack_extraction.json"), self.state)
        self.plan = self.r1["session"]["plan"]

    def test_valid_and_six_checks(self):
        self.assertTrue(self.r1["ok"])
        self.assertTrue(self.plan["valid"], plan_text(self.plan))
        self.assertEqual(len(self.plan["checks"]), 6)

    def test_people_and_judges(self):
        self.assertEqual(self.plan["judging"]["teams"], 50)
        self.assertEqual(self.plan["judging"]["judges_used"], 17)          # ceil(50/3)
        self.assertLessEqual(self.plan["judging"]["max_load"], 3)
        self.assertEqual(self.plan["people"]["on_site"], 177)               # 150 + 10 + 17
        self.assertEqual(len({a["team"] for a in self.plan["judging"]["assignment"]}), 50)

    def test_venue_cheapest_that_fits(self):
        self.assertEqual(self.plan["venue"]["chosen"]["name"], "Hall A")

    def test_food_latest_price_and_quantity(self):
        self.assertEqual(self.plan["food"]["chosen"]["price_per_head"], 1200)  # corrected price, not 1,000
        self.assertEqual(self.plan["food"]["quantity"], 177)

    def test_budget(self):
        b = self.plan["budget"]
        self.assertEqual(b["total"], 120000 + 177 * 1200 + 17 * 5000 + 130000)
        self.assertLessEqual(b["total"], b["cap"])
        self.assertEqual([o["item"] for o in b["not_included"]], ["DJ for closing"])  # quote not approved

    def test_schedule(self):
        s = self.plan["schedule"]
        self.assertEqual(sum(x["end"] - x["start"] for x in s["slots"]), 240)
        self.assertTrue(any("Prayer" in x["name"] for x in s["slots"]))
        self.assertEqual(sum(1 for x in s["slots"] if x["type"] == "judging"), 3)

    def test_tentative_delay_is_risk_not_absence(self):
        self.assertEqual(self.plan["judging"]["judges_available"], 20)
        self.assertTrue(self.plan["risks"])

    def test_trace_and_prediction(self):
        sess, r = self.r1["session"], self.r1["run"]
        self.assertEqual([c["tag"] for c in sess["calls"]], ["reading"])
        self.assertEqual(sess["calls"][0]["total_tokens"], 150)      # copied from the reported usage
        self.assertTrue(r["prediction_matched"])
        self.assertIn("TOTAL TOKENS", trace_text(sess, [1]).splitlines()[-3])

    def test_change_then_wrong_message(self):
        r2 = run(read_input(SAMPLES / "practice_change_printing.txt"),
                 scripted("practice_change_printing_extraction.json"), self.state)
        p2 = r2["session"]["plan"]
        self.assertEqual(r2["run"]["mode"], "update")
        self.assertTrue(p2["valid"])
        self.assertEqual(p2["budget"]["total"], self.plan["budget"]["total"] + 5000)  # replaced, not added
        self.assertEqual(len(r2["run"]["calls"]), 1)
        self.assertTrue(r2["run"]["prediction_matched"])

        r3 = run(read_input(SAMPLES / "practice_wrong_caterer.txt"),
                 scripted("practice_wrong_caterer_extraction.json"), self.state)
        p3 = r3["session"]["plan"]
        self.assertTrue(p3["valid"])
        self.assertEqual(p3["food"]["quantity"], 177)
        rej = [d for d in r3["run"]["decisions"] if d["verdict"] == "rejected"]
        self.assertEqual(len(rej), 1)
        self.assertIn("177", rej[0]["reason"])
        self.assertIn("rejected", trace_text(r3["session"], [3]).lower())
        self.assertEqual([c["number"] for c in r3["session"]["calls"]], [1, 2, 3])


class Honesty(unittest.TestCase):
    def test_failed_call_is_traced_and_plan_kept(self):
        state = Path(tempfile.mkdtemp())
        run(read_input(SAMPLES / "sample_pack.txt"), scripted("sample_pack_extraction.json"), state)
        r = run(read_input(SAMPLES / "practice_change_printing.txt"), scripted("ERROR", "ERROR"), state)
        self.assertFalse(r["ok"])
        self.assertEqual([c["status"] for c in r["session"]["calls"]][-2:], ["error", "error"])
        self.assertTrue(r["session"]["plan"]["valid"])
        self.assertEqual(r["session"]["plan"]["budget"]["total"], 547400)

    def test_unusable_output_retried_once(self):
        state = Path(tempfile.mkdtemp())
        r = run(read_input(SAMPLES / "sample_pack.txt"), scripted("not json at all", "sample_pack_extraction.json"), state)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["session"]["calls"]), 2)


if __name__ == "__main__":
    unittest.main()
