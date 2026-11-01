"""Every file in examples/ is a test vector: the engine must reproduce the
published OFAC outcome (or, for the synthetic cases, the documented
indeterminate answer)."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ofac50 import Seed, Stake, evaluate

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def load(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    seeds = [Seed(name=s["name"], program=s.get("program", "unspecified"),
                  status=s.get("status", "blocked"))
             for s in doc.get("blocked_persons", [])]
    stakes = [Stake(owner=s["owner"], entity=s["entity"], pct=s.get("pct"),
                    source=s.get("source", ""))
              for s in doc.get("stakes", [])]
    return doc, seeds, stakes


class TestPublishedExamples(unittest.TestCase):
    def test_all_example_files(self):
        files = sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".json"))
        self.assertGreaterEqual(len(files), 8, "expected the FAQ vectors and edge cases")
        for fname in files:
            with self.subTest(example=fname):
                doc, seeds, stakes = load(os.path.join(EXAMPLES, fname))
                results = evaluate(seeds, stakes)
                for entity, want in doc["expected"].items():
                    got = results[entity].status
                    self.assertEqual(got, want,
                                     f"{fname}: {entity}: want {want}, got {got} "
                                     f"({results[entity].reasons})")

    def test_naive_disagrees_where_ofac_says_it_should(self):
        """FAQ 401 examples 1-3: path-product math undercounts vs OFAC's rule."""
        for fname, entity in [("faq401_ex1.json", "B"),
                              ("faq401_ex2.json", "C"),
                              ("faq401_ex3.json", "B")]:
            with self.subTest(example=fname):
                _, seeds, stakes = load(os.path.join(EXAMPLES, fname))
                results = evaluate(seeds, stakes, compare_naive=True)
                r = results[entity]
                self.assertEqual(r.status, "blocked")
                self.assertEqual(r.naive_status, "not_blocked")
                self.assertTrue(r.naive_disagrees)
                self.assertLess(r.naive_pct, 50.0)

    def test_naive_agrees_on_example_4(self):
        _, seeds, stakes = load(os.path.join(EXAMPLES, "faq401_ex4.json"))
        results = evaluate(seeds, stakes, compare_naive=True)
        self.assertEqual(results["C"].status, "not_blocked")
        self.assertFalse(results["C"].naive_disagrees)

    def test_cycle_case_is_flagged_cycle_sensitive(self):
        _, seeds, stakes = load(os.path.join(EXAMPLES, "cycle_crossholdings.json"))
        results = evaluate(seeds, stakes)
        self.assertTrue(results["A"].cycle_sensitive)
        self.assertTrue(results["B"].cycle_sensitive)

    def test_unknown_case_reports_bounds(self):
        _, seeds, stakes = load(os.path.join(EXAMPLES, "unknown_stakes.json"))
        r = evaluate(seeds, stakes)["A"]
        self.assertEqual(r.status, "indeterminate")
        self.assertAlmostEqual(r.aggregate_pct, 40.0)
        self.assertAlmostEqual(r.upper_pct, 100.0)
        self.assertFalse(r.cycle_sensitive)


if __name__ == "__main__":
    unittest.main()
