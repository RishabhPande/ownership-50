"""Counterexamples found in the public-prototype review."""
import unittest

from ofac50 import InputError, Seed, Stake, evaluate, validate


class OwnershipRegressionTests(unittest.TestCase):
    def test_nonblocking_designation_does_not_override_blocked_ownership(self):
        results = evaluate([Seed('X'), Seed('A', status='directive-4')],
                           [Stake('X', 'A', 100), Stake('A', 'B', 50)])
        self.assertEqual(results['A'].status, 'blocked')
        self.assertEqual(results['A'].aggregate_pct, 100)
        self.assertEqual(results['B'].status, 'blocked')
        self.assertTrue(any('Directive' in r for r in results['A'].reasons))

    def test_nonblocking_designation_with_uncertain_ownership_is_indeterminate(self):
        results = evaluate([Seed('X'), Seed('A', status='directive-4')], [Stake('X', 'A', None)])
        self.assertEqual(results['A'].status, 'indeterminate')
        self.assertEqual(results['A'].upper_pct, 100)

    def test_nonblocking_designation_below_threshold_keeps_own_prohibitions_separate(self):
        result = evaluate([Seed('X'), Seed('A', status='directive-4')], [Stake('X', 'A', 25)])['A']
        self.assertEqual(result.status, 'not_blocked')
        self.assertEqual(result.aggregate_pct, 25)
        self.assertTrue(any('Directive' in r for r in result.reasons))

    def test_direct_blocking_designation_still_overrides_ownership(self):
        self.assertEqual(evaluate([Seed('A')], [])['A'].status, 'blocked')

    def test_unknown_ownership_bounds_propagate_through_known_stakes(self):
        results = evaluate([Seed('X')], [Stake('X', 'A', None), Stake('A', 'B', 100), Stake('B', 'C', 60)])
        for entity, upper in [('A', 100), ('B', 100), ('C', 60)]:
            with self.subTest(entity=entity):
                self.assertEqual(results[entity].status, 'indeterminate')
                self.assertEqual(results[entity].aggregate_pct, 0)
                self.assertEqual(results[entity].upper_pct, upper)

    def test_known_and_possible_owners_both_contribute_to_upper_bound(self):
        r = evaluate([Seed('X'), Seed('Y')], [Stake('X', 'A', None), Stake('A', 'B', 30), Stake('Y', 'B', 25)])['B']
        self.assertEqual((r.status, r.aggregate_pct, r.upper_pct), ('indeterminate', 25, 55))

    def test_propagated_uncertainty_below_threshold_is_not_blocked(self):
        r = evaluate([Seed('X')], [Stake('X', 'A', None), Stake('A', 'B', 49)])['B']
        self.assertEqual((r.status, r.upper_pct), ('not_blocked', 49))

    def test_circular_ownership_exposes_possible_aggregate(self):
        r = evaluate([Seed('X')], [Stake('X', 'A', 20), Stake('X', 'B', 20), Stake('A', 'B', 30), Stake('B', 'A', 30)])['A']
        self.assertEqual((r.status, r.aggregate_pct, r.upper_pct), ('indeterminate', 20, 50))

    def test_unknown_duplicate_edges_rejected_in_either_order(self):
        for values in [(None, 30), (30, None), (None, None)]:
            with self.subTest(values=values), self.assertRaisesRegex(InputError, 'duplicate edge'):
                validate([Stake('X', 'A', value) for value in values])

    def test_invalid_numeric_stakes_rejected(self):
        for value in [True, False, float('nan'), float('inf'), float('-inf'), '50', [], {}]:
            with self.subTest(value=value), self.assertRaises(InputError):
                validate([Stake('X', 'A', value)])

    def test_valid_integer_float_and_unknown_stakes_remain_supported(self):
        for value in [1, 49.9, 50, 100.0, None]:
            with self.subTest(value=value):
                validate([Stake('X', 'A', value)])
