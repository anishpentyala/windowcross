import builtins
import csv
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from windowcross import audit


class LiveSplitTests(unittest.TestCase):
    def run_rows(self, rows, examples=0):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "windows.csv"
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["id", "entity", "split", "start_at", "end_at"])
                for key, split, a, b in rows:
                    writer.writerow(
                        [
                            key,
                            "e",
                            split,
                            (start + timedelta(seconds=a)).isoformat(),
                            (start + timedelta(seconds=b)).isoformat(),
                        ]
                    )
            scans = []

            def tracked_sorted(value, *args, **kwargs):
                if isinstance(value, Counter):
                    scans.append(dict(value))
                return builtins.sorted(value, *args, **kwargs)

            with patch(
                "windowcross.core.sorted", side_effect=tracked_sorted, create=True
            ):
                report = audit(path, examples=examples)
            # audit sorts active per row, then totals once when rendering splits.
            return report, scans[:-1]

    def test_expired_split_keys_are_not_scanned(self):
        rows = [(str(i), str(i % 100), i * 2, i * 2 + 1) for i in range(300)]
        for cap in [0, 1, 1000]:
            report, scans = self.run_rows(rows, cap)
            self.assertTrue(report["passed"])
            self.assertEqual(len(scans), len(rows))
            self.assertTrue(all(not scan for scan in scans))

    def test_split_survives_partial_expiry(self):
        rows = [
            ("a", "train", 0, 10),
            ("b", "train", 1, 3),
            ("c", "test", 3, 4),
            ("d", "test", 10, 11),
        ]
        report, scans = self.run_rows(rows, 1000)
        self.assertEqual(scans, [{}, {"train": 1}, {"train": 1}, {}])
        self.assertEqual(report["counts"]["cross_split_pairs"], 1)
        self.assertEqual(report["counts"]["affected_records"], 2)
        self.assertEqual(report["examples"][0]["earlier_id"], "a")
        self.assertEqual(report["examples"][0]["later_id"], "c")

    def test_expired_split_can_return_without_changing_witness_order(self):
        rows = [
            ("a", "a", 0, 2),
            ("b", "b", 1, 2),
            ("c", "a", 3, 6),
            ("d", "b", 4, 5),
            ("e", "c", 4, 7),
            ("f", "a", 8, 9),
        ]
        report, scans = self.run_rows(rows, 1000)
        self.assertEqual(scans, [{}, {"a": 1}, {}, {"a": 1}, {"a": 1, "b": 1}, {}])
        self.assertEqual(report["counts"]["cross_split_pairs"], 4)
        self.assertEqual(
            [(x["earlier_id"], x["later_id"]) for x in report["examples"]],
            [("a", "b"), ("c", "d"), ("c", "e"), ("d", "e")],
        )
        self.assertTrue(all(count > 0 for scan in scans for count in scan.values()))

    def test_all_same_start_and_end_multiplicity_preserved(self):
        rows = [(str(i), str(i % 4), 0, 10) for i in range(40)]
        report, scans = self.run_rows(rows, 1)
        self.assertEqual(report["counts"]["cross_split_pairs"], 600)
        self.assertEqual(report["counts"]["affected_records"], 40)
        self.assertEqual(sum(scans[-1].values()), 39)


if __name__ == "__main__":
    unittest.main()
