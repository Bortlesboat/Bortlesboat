"""Readiness and report evidence checks; no Bitcoin process needed."""

import unittest

from rebuild_delay import ready_height


class ReadinessTests(unittest.TestCase):
    def test_zero_delay_is_ready_before_the_start_height_block(self):
        self.assertEqual(ready_height(293, 0), 293)

    def test_three_blocks_of_work_release_before_height_296(self):
        self.assertEqual(ready_height(293, 3), 296)

    def test_invalid_height_and_delay_are_rejected(self):
        for height, delay in ((0, 1), (293, -1), (True, 1), (293, 1.5)):
            with self.subTest(height=height, delay=delay):
                with self.assertRaises(ValueError):
                    ready_height(height, delay)


if __name__ == '__main__':
    unittest.main()
