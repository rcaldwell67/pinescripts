"""
Unit tests for backtest_backtrader_alpaca.py
"""
import unittest
from backend import backtest_backtrader_alpaca

class TestBacktestBacktraderAlpaca(unittest.TestCase):
    def test_result_label(self):
        self.assertEqual(backtest_backtrader_alpaca._result_label("TP"), "TP")
        self.assertEqual(backtest_backtrader_alpaca._result_label("SL"), "SL")
        self.assertEqual(backtest_backtrader_alpaca._result_label("TRAILING_STOP"), "TRAIL")
        self.assertEqual(backtest_backtrader_alpaca._result_label("MAX_BARS"), "MB")
        self.assertEqual(backtest_backtrader_alpaca._result_label(""), None)

    def test_to_native(self):
        self.assertEqual(backtest_backtrader_alpaca._to_native(5), 5)
        self.assertEqual(backtest_backtrader_alpaca._to_native("foo"), "foo")

    def test_timestamp_at(self):
        import pandas as pd
        df = pd.DataFrame({"timestamp": ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"]})
        self.assertEqual(backtest_backtrader_alpaca._timestamp_at(df, 0), "2024-01-01T00:00:00Z")
        self.assertEqual(backtest_backtrader_alpaca._timestamp_at(df, 1), "2024-01-02T00:00:00Z")
        self.assertIsNone(backtest_backtrader_alpaca._timestamp_at(df, 2))

if __name__ == "__main__":
    unittest.main()
