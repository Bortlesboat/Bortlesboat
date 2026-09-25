"""Independent boundary examples for the paper model, not a proof verifier."""

import unittest

from policy import (
    AnchorProfile,
    action_at_height,
    boundary_summary,
    make_payload,
    payload_fields,
)


class AnchorTests(unittest.TestCase):
    def test_inclusive_height_boundaries(self):
        profile = AnchorProfile()
        self.assertTrue(profile.eligible(900, 1000))
        self.assertTrue(profile.eligible(999, 1000))
        self.assertFalse(profile.eligible(899, 1000))
        self.assertFalse(profile.eligible(1000, 1000))

    def test_shared_boundary_and_wallet_depth(self):
        profile = AnchorProfile()
        self.assertEqual(profile.choose(201, spacing=16, wallet_depth=6), 192)
        self.assertEqual(profile.choose(201, spacing=1, wallet_depth=6), 195)
        self.assertIsNone(profile.choose(201, spacing=100, wallet_depth=6))
        self.assertIsNone(profile.choose(3, spacing=16, wallet_depth=6))

    def test_known_phase_counts_and_slack(self):
        for depth, spacing, missing, slack in [
            (1, 144, 44, -44),
            (1, 100, 0, 0),
            (1, 16, 0, 84),
            (6, 100, 5, -5),
            (6, 16, 0, 79),
        ]:
            with self.subTest(depth=depth, spacing=spacing):
                result = boundary_summary(AnchorProfile(), spacing, depth)
                self.assertEqual(result['missing_phases'], missing)
                self.assertEqual(result['minimum_margin'], slack)

    def test_invalid_configuration_is_rejected(self):
        for args in [(0, 1), (100, 0), (100, 101), (True, 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                AnchorProfile(*args)
        for spacing, depth in [(0, 6), (16, 0), (16, 101), (16, True)]:
            with self.subTest(spacing=spacing, depth=depth):
                with self.assertRaises(ValueError):
                    AnchorProfile().choose(201, spacing, depth)


class RetryTests(unittest.TestCase):
    def test_identical_fee_schedule_only_refreshes_when_needed(self):
        profile = AnchorProfile()
        self.assertEqual(
            action_at_height('fee_only', 5, 293, 192, 16, 6, profile),
            ('bump', 192),
        )
        self.assertEqual(
            action_at_height('refresh_on_bump', 5, 293, 192, 16, 6, profile),
            ('rebuild', 272),
        )
        self.assertEqual(
            action_at_height('refresh_on_bump', 5, 206, 192, 16, 6, profile),
            ('bump', 192),
        )

    def test_no_future_workload_is_an_input_to_the_decision(self):
        profile = AnchorProfile()
        for name in ('hold', 'fee_only', 'refresh_on_bump'):
            for step in (0, 1, 4, 6, 7):
                self.assertEqual(
                    action_at_height(name, step, 288 + step, 192, 16, 6, profile),
                    ('hold', 192),
                )

    def test_refresh_reserve_boundary(self):
        profile = AnchorProfile()
        self.assertEqual(
            action_at_height('refresh_on_bump', 5, 290, 192, 16, 6, profile),
            ('bump', 192),
        )
        self.assertEqual(
            action_at_height('refresh_on_bump', 5, 291, 192, 16, 6, profile),
            ('rebuild', 272),
        )

    def test_synthetic_payload_is_labeled_and_preserves_input_markers(self):
        first = make_payload(192, 0)
        second = make_payload(272, 1)
        self.assertEqual(len(first), 610)
        self.assertEqual(first[:6], b'LABSB1')
        self.assertNotEqual(first, second)
        left, right = payload_fields(first), payload_fields(second)
        self.assertEqual(left['anchor_height'], 192)
        self.assertEqual(right['anchor_height'], 272)
        self.assertEqual(left['synthetic_input_markers'], right['synthetic_input_markers'])
        self.assertNotEqual(first[76:], second[76:])
        self.assertFalse(left['authentic_shielded_envelope'])
        with self.assertRaises(ValueError):
            payload_fields(b'\x00' * 610)


if __name__ == '__main__':
    unittest.main()
