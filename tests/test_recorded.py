"""Regression: the exact outputs Gemini produced in the first live run must give a valid plan."""
import tempfile
import unittest
from pathlib import Path

from planforge.ingest import read_input
from planforge.pipeline import run
from planforge.render import plan_text
from tests.helpers import FIX, SAMPLES, scripted


def recorded(name):
    return (FIX / name).read_text(encoding="utf-8").strip()


class RecordedGemini(unittest.TestCase):
    def test_live_outputs(self):
        st = Path(tempfile.mkdtemp())
        r1 = run(read_input(SAMPLES / "sample_pack.txt"), scripted(recorded("recorded_gemini35_sample_output.txt")), st)
        p = r1["session"]["plan"]
        self.assertTrue(p["valid"], plan_text(p))
        self.assertEqual((p["people"]["on_site"], p["venue"]["chosen"]["name"], p["budget"]["total"]), (177, "Hall A", 547400))
        r2 = run(read_input(SAMPLES / "practice_change_printing.txt"), scripted(recorded("recorded_gemini35_printing_output.txt")), st)
        self.assertEqual(r2["session"]["plan"]["budget"]["total"], 552400)
        r3 = run(read_input(SAMPLES / "practice_wrong_caterer.txt"), scripted(recorded("recorded_gemini31_caterer_output.txt")), st)
        self.assertTrue(r3["session"]["plan"]["valid"])
        self.assertEqual(r3["run"]["decisions"][0]["verdict"], "rejected")


if __name__ == "__main__":
    unittest.main()
