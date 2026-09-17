import unittest
from unittest.mock import patch

from app.core.timing import elapsed_ms


class ElapsedMsTests(unittest.TestCase):
    def test_elapsed_ms_uses_current_perf_counter_when_end_time_missing(self):
        with patch("app.core.timing.time.perf_counter", return_value=1.23456):
            self.assertEqual(elapsed_ms(1.0), 234.56)

    def test_elapsed_ms_rounds_to_two_decimals(self):
        self.assertEqual(elapsed_ms(2.0, 2.003333), 3.33)


if __name__ == "__main__":
    unittest.main()
