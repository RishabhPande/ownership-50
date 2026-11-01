"""Unit tests for validation, aggregation and the CLI."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ofac50 import InputError, Seed, Stake, evaluate, validate


def seed(name, status="blocked", program="example"):
    return Seed(name=name, program=program, status=status)


class TestValidation(unittest.TestCase):
    def test_over_subscribed_entity_rejected(self):
        with self.assertRaisesRegex(InputError, "sums? to|> 100"):
            validate([Stake("X", "A", 60), Stake("Y", "A", 60)])

    def test_duplicate_edge_rejected(self):
        with self.assertRaisesRegex(InputError, "duplicate edge"):
            validate([Stake("X", "A", 30), Stake("X", "A", 30)])

    def test_self_ownership_rejected(self):
        with self.assertRaisesRegex(InputError, "self-ownership"):
            validate([Stake("A", "A", 10)])

    def test_out_of_range_rejected(self):
        with self.assertRaisesRegex(InputError, "out of range"):
            validate([Stake("X", "A", 0)])
        with self.assertRaisesRegex(InputError, "out of range"):
            validate([Stake("X", "A", 120)])

    def test_exactly_100_accepted(self):
        validate([Stake("X", "A", 60), Stake("Y", "A", 40)])

    def test_unknown_edges_skip_sum_check(self):
        validate([Stake("X", "A", 60), Stake("Y", "A", None)])


class TestAggregation(unittest.TestCase):
    def test_threshold_is_inclusive(self):
        res = evaluate([seed("X")], [Stake("X", "A", 50)])
        self.assertEqual(res["A"].status, "blocked")

    def test_just_below_threshold(self):
        res = evaluate([seed("X")], [Stake("X", "A", 49.99)])
        self.assertEqual(res["A"].status, "not_blocked")

    def test_transitive_chain(self):
        res = evaluate([seed("X")], [Stake("X", "A", 50), Stake("A", "B", 50),
                                     Stake("B", "C", 50), Stake("C", "D", 50)])
        for e in "ABCD":
            self.assertEqual(res[e].status, "blocked", e)
        # chain is explanatory, not multiplied: D's contributor is C at 50%
        self.assertEqual(res["D"].contributors, [("C", 50.0, "")])

    def test_non_blocked_seed_status_not_applied(self):
        res = evaluate([seed("X", status="directive-4")], [Stake("X", "A", 100)])
        self.assertEqual(res["X"].status, "not_blocked")
        self.assertEqual(res["A"].status, "not_blocked")
        self.assertIn("Directive", " ".join(res["X"].reasons))

    def test_unrelated_entity_untouched(self):
        res = evaluate([seed("X")], [Stake("X", "A", 100), Stake("P", "Q", 75)])
        self.assertEqual(res["Q"].status, "not_blocked")

    def test_contributor_chain_carries_provenance(self):
        res = evaluate([seed("X")], [Stake("X", "A", 50, source="filing 10-K")])
        self.assertEqual(res["A"].contributors, [("X", 50.0, "filing 10-K")])


class TestCli(unittest.TestCase):
    def run_cli(self, doc, *extra):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(doc, fh)
            path = fh.name
        env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), "..", "src"))
        proc = subprocess.run([sys.executable, "-m", "ofac50", path, *extra],
                              capture_output=True, text=True, env=env)
        os.unlink(path)
        return proc

    def test_cli_evaluates_example(self):
        doc = {"blocked_persons": [{"name": "X"}],
               "stakes": [{"owner": "X", "entity": "A", "pct": 50},
                          {"owner": "A", "entity": "B", "pct": 50}]}
        proc = self.run_cli(doc)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("B: BLOCKED", proc.stdout)

    def test_cli_json_format(self):
        doc = {"blocked_persons": [{"name": "X"}],
               "stakes": [{"owner": "X", "entity": "A", "pct": 50}]}
        proc = self.run_cli(doc, "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["A"]["status"], "blocked")

    def test_cli_rejects_bad_input_with_exit_2(self):
        doc = {"stakes": [{"owner": "X", "entity": "A", "pct": 60},
                          {"owner": "Y", "entity": "A", "pct": 60}]}
        proc = self.run_cli(doc)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("input rejected", proc.stderr)


if __name__ == "__main__":
    unittest.main()
