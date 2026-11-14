import contextlib
import csv
import hashlib
import io
import itertools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from windowcross import AuditError, Limits, audit
from windowcross.__main__ import main
from windowcross.core import instant


def stamp(us):
    return "2024-01-01T00:00:%02d.%06dZ" % divmod(us, 1000000)


def literal(rows, examples, receipt, limits):
    ordered = sorted(rows, key=lambda r: (r[1], r[3], r[4], r[0], r[2]))
    pairs, affected, entities, bad_entities, evidence = (
        Counter(),
        set(),
        set(),
        set(),
        [],
    )
    for i, (key, entity, split, start, end) in enumerate(ordered):
        entities.add(entity)
        before = [
            v
            for v in ordered[:i]
            if v[1] == entity and v[2] != split and max(v[3], start) < min(v[4], end)
        ]
        for old in sorted(before, key=lambda v: (v[2], v[3], v[4], v[0])):
            old_id, _, old_split, a, b = old
            pairs[tuple(sorted((split, old_split)))] += 1
            affected.update((key, old_id))
            bad_entities.add(entity)
            if len(evidence) < examples:
                evidence.append(
                    dict(
                        entity=entity,
                        earlier_id=old_id,
                        earlier_split=old_split,
                        earlier_start_us=instant(stamp(a)),
                        earlier_end_us=instant(stamp(b)),
                        later_id=key,
                        later_split=split,
                        later_start_us=instant(stamp(start)),
                        later_end_us=instant(stamp(end)),
                        overlap_us=min(b, end) - max(a, start),
                    )
                )
    totals = Counter(r[2] for r in rows)
    aff = Counter(r[2] for r in rows if r[0] in affected)
    count = sum(pairs.values())
    return dict(
        schema_version=1,
        passed=not count,
        policy="same_entity_different_split_positive_half_open_overlap",
        counts=dict(
            records=len(rows),
            entities=len(entities),
            cross_split_pairs=count,
            affected_records=len(affected),
            affected_entities=len(bad_entities),
        ),
        splits={
            s: dict(records=totals[s], affected_records=aff[s]) for s in sorted(totals)
        },
        split_pairs=[
            dict(left_split=a, right_split=b, overlap_pairs=n)
            for (a, b), n in sorted(pairs.items())
        ],
        examples=evidence,
        examples_omitted=count - len(evidence),
        settings=dict(examples=examples, limits=vars(limits)),
        input=receipt,
    )


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "windows.csv"
        self.rows = [("a", "e", "train", 0, 10), ("b", "e", "test", 5, 15)]

    def write(self, rows=None):
        if rows is None:
            rows = self.rows
        with self.path.open("w", newline="", encoding="utf8") as f:
            w = csv.writer(f)
            w.writerow(["id", "entity", "split", "start_at", "end_at"])
            w.writerows((k, e, s, stamp(a), stamp(b)) for k, e, s, a, b in rows)
        return self.path

    def run_audit(self, **kw):
        return audit(self.write(), **kw)

    def test_crossing_and_receipt_and_input_preserved(self):
        path = self.write()
        before = path.read_bytes()
        report = audit(path, examples=2)
        self.assertEqual(
            report,
            literal(
                self.rows,
                2,
                dict(sha256=hashlib.sha256(before).hexdigest(), bytes=len(before)),
                Limits(),
            ),
        )
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(report["examples"][0]["overlap_us"], 5)

    def test_touching_not_crossing(self):
        self.rows[1] = ("b", "e", "test", 10, 20)
        self.assertTrue(self.run_audit()["passed"])

    def test_nested_not_just_adjacent(self):
        self.rows = [
            ("long", "e", "train", 0, 100),
            ("short", "e", "train", 1, 2),
            ("late", "e", "test", 50, 60),
        ]
        row = self.run_audit(examples=5)
        self.assertEqual(row["counts"]["cross_split_pairs"], 1)
        self.assertEqual(row["counts"]["affected_records"], 2)
        self.assertEqual(row["examples"][0]["earlier_id"], "long")

    def test_multiple_split_pairs_affected_once(self):
        self.rows = [(str(i), "e", str(i % 3), 0, 10) for i in range(12)]
        row = self.run_audit(examples=1000)
        self.assertEqual(row["counts"]["cross_split_pairs"], 48)
        self.assertEqual(row["counts"]["affected_records"], 12)
        self.assertEqual(len(row["examples"]), 48)
        self.assertEqual([v["overlap_pairs"] for v in row["split_pairs"]], [16, 16, 16])

    def test_same_entity_only_exact_strings(self):
        self.rows = [
            ("a", "001", "train", 0, 10),
            ("b", "1", "test", 0, 10),
            ("c", "001", "train", 0, 10),
        ]
        row = self.run_audit()
        self.assertTrue(row["passed"])
        self.assertEqual(row["counts"]["entities"], 2)

    def test_same_split_overlap_not_violation(self):
        self.rows[1] = ("b", "e", "train", 5, 15)
        row = self.run_audit()
        self.assertTrue(row["passed"])
        self.assertEqual(row["counts"]["affected_records"], 0)

    def test_affected_pending_expiration_and_later_partner(self):
        self.rows = [
            ("old", "e", "train", 0, 2),
            ("long", "e", "train", 0, 20),
            ("other", "e", "test", 3, 6),
            ("last", "e", "test", 10, 21),
        ]
        row = self.run_audit()
        self.assertEqual(row["counts"]["affected_records"], 3)
        self.assertEqual(row["counts"]["cross_split_pairs"], 2)

    def test_affected_current_can_expire_before_future_crossing(self):
        self.rows = [
            ("a", "e", "x", 0, 3),
            ("b", "e", "y", 1, 8),
            ("c", "e", "z", 5, 9),
        ]
        row = self.run_audit()
        self.assertEqual(row["counts"]["affected_records"], 3)
        self.assertEqual(row["counts"]["cross_split_pairs"], 2)

    def test_example_cap_and_default_privacy(self):
        self.rows = [
            ("PRIVATE" + str(i), "SECRET", "x" if i % 2 else "y", 0, 10)
            for i in range(8)
        ]
        row = self.run_audit()
        text = json.dumps(row)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("start_us", text)
        row = self.run_audit(examples=3)
        self.assertEqual(len(row["examples"]), 3)
        self.assertEqual(row["examples_omitted"], 13)

    def test_reordered_inputs_witness_ties_stable(self):
        self.rows = [
            ("b", "e", "z", 0, 10),
            ("a", "e", "z", 0, 10),
            ("d", "e", "b", 0, 10),
            ("c", "e", "a", 0, 10),
        ]
        baseline = self.run_audit(examples=1000)
        for rows in itertools.permutations(self.rows):
            self.rows = list(rows)
            row = self.run_audit(examples=1000)
            row.pop("input")
            expected = dict(baseline)
            expected.pop("input")
            self.assertEqual(row, expected)

    def test_oracle_random_complete_reports(self):
        rng = random.Random(15671)
        for case in range(400):
            rows = []
            for i in range(rng.randrange(1, 36)):
                a = rng.randrange(60)
                b = rng.randrange(a + 1, 101)
                rows.append(
                    (
                        str(i),
                        rng.choice(["e", "f", "001"]),
                        rng.choice(["train", "test", "val"]),
                        a,
                        b,
                    )
                )
            rng.shuffle(rows)
            self.rows = rows
            for examples in [0, 1, 7, 1000]:
                row = self.run_audit(examples=examples)
                raw = self.path.read_bytes()
                receipt = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
                with self.subTest(case=case, examples=examples):
                    self.assertEqual(row, literal(rows, examples, receipt, Limits()))

    def test_dense_pair_count_without_pair_materialization(self):
        n = 10000
        self.rows = [(str(i), "e", "x" if i % 2 else "y", 0, 10) for i in range(n)]
        row = self.run_audit(examples=2, limits=Limits(max_bytes=2000000))
        self.assertEqual(row["counts"]["cross_split_pairs"], 25000000)
        self.assertEqual(row["counts"]["affected_records"], n)
        self.assertEqual(len(row["examples"]), 2)

    def test_invalid_intervals_and_duplicate_ids(self):
        for rows in [
            [("a", "e", "x", 0, 0)],
            [("a", "e", "x", 5, 1)],
            [("a", "e", "x", 0, 2), ("a", "f", "y", 2, 3)],
        ]:
            self.rows = rows
            with self.assertRaises(AuditError):
                self.run_audit()

    def test_no_records_invalid(self):
        self.rows = []
        with self.assertRaisesRegex(AuditError, "at least"):
            self.run_audit()

    def test_strict_headers_fields_and_encoding(self):
        values = [
            b"",
            b"id,entity,split,start_at,end_at\n\n",
            b"entity,id,split,start_at,end_at\n",
            b"id,entity,split,start_at,end_at,extra\n",
            b"id,entity,split,start_at,end_at\na,e,x,2024-01-01T00:00:00Z\n",
            b"id,entity,split,start_at,end_at\n\xff",
            b"id,entity,split,start_at,end_at\n\x00",
            b'id,entity,split,start_at,end_at\n"unterminated',
            b"id,entity,split,start_at,end_at\n ,e,x,2024-01-01T00:00:00Z,2024-01-01T00:00:01Z\n",
        ]
        for raw in values:
            self.path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(AuditError):
                audit(self.path)

    def test_optional_bom_and_multiline_identifiers(self):
        self.rows = [('a\n,"❄"', " e ", "x", 0, 3), ("b", " e ", "y", 1, 4)]
        self.write()
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        self.assertFalse(audit(self.path)["passed"])

    def test_limits_exact_and_exceeded(self):
        self.write()
        size = self.path.stat().st_size
        self.assertFalse(
            audit(
                self.path,
                limits=Limits(
                    max_bytes=size, max_records=2, max_splits=2, max_field_chars=27
                ),
            )["passed"]
        )
        for limits in [
            Limits(max_bytes=size - 1),
            Limits(max_records=1),
            Limits(max_splits=1),
            Limits(max_field_chars=5),
        ]:
            with self.subTest(limits=limits), self.assertRaises(AuditError):
                audit(self.path, limits=limits)

    def test_validation_options_before_io(self):
        for kw in [
            dict(examples=-1),
            dict(examples=True),
            dict(examples=1.0),
            dict(examples=1001),
            dict(limits={}),
            dict(limits=1),
        ]:
            with self.subTest(kw=kw), self.assertRaises(AuditError):
                audit("notfound", **kw)
        for name in vars(Limits()):
            for value in [0, -1, True, 1.0]:
                with self.assertRaises(AuditError):
                    replace(Limits(), **{name: value})

    def test_path_read_error(self):
        with self.assertRaises(AuditError):
            audit(self.path)
        with patch("windowcross.core.Path.open", side_effect=OSError("injected")):
            with self.assertRaises(AuditError):
                audit(self.path)

    def test_timestamp_rejections(self):
        for t in [
            "2024-01-01",
            "2024-01-01T00:00:00",
            "2024-01-01T00:00:00.1234567Z",
            "2024-01-01T24:00:00Z",
            "2024-01-01T00:60:00Z",
            "2024-01-01T00:00:60Z",
            "2024-01-01T00:00:00+24:00",
            "2024-01-01T00:00:00+00:60",
            "2024-02-30T00:00:00Z",
            "0000-01-01T00:00:00Z",
            "0001-01-01T00:00:00+23:59",
            "9999-12-31T23:59:59-23:59",
            None,
        ]:
            with self.subTest(t=t), self.assertRaises(AuditError):
                instant(t)

    def test_timestamp_integer_boundaries(self):
        self.assertEqual(instant("1970-01-01T00:00:00Z"), 0)
        self.assertEqual(instant("1969-12-31T23:59:59.999999Z"), -1)
        self.assertEqual(instant("2024-01-01T01:00:00.000001+01:00"), instant(stamp(1)))
        self.assertLess(instant("0001-01-01T00:00:00Z"), 0)
        self.assertGreater(instant("9999-12-31T23:59:59.999999Z"), 0)

    def test_all_fraction_lengths_across_offsets_and_csv(self):
        for digits in ("5", "25", "123", "1234", "12345", "123456"):
            us = int(digits.ljust(6, "0"))
            for clock, offset in (
                ("00:00:00", "Z"),
                ("01:00:00", "+01:00"),
                ("00:00:00", "-00:00"),
            ):
                with self.subTest(digits=digits, offset=offset):
                    self.assertEqual(
                        instant("1970-01-01T" + clock + "." + digits + offset), us
                    )
            self.assertEqual(
                instant("1969-12-31T23:59:59." + digits + "Z"), us - 1000000
            )
            self.path.write_text(
                "id,entity,split,start_at,end_at\n"
                "a,e,x,1970-01-01T00:00:00." + digits + "Z,1970-01-01T00:00:02Z\n"
                "b,e,y,1970-01-01T00:00:01Z,1970-01-01T00:00:03Z\n"
            )
            report = audit(self.path, examples=1)
            self.assertEqual(report["examples"][0]["earlier_start_us"], us)
            self.assertEqual(report["counts"]["cross_split_pairs"], 1)
        self.assertEqual(instant("1970-01-01T00:00:00Z"), 0)
        self.assertEqual(instant("1970-01-01T00:00:00-01:00"), 3600000000)

    def witness_writes(self, examples):
        from collections import defaultdict

        writes = []

        class Spy(dict):
            def __setitem__(self, key, value):
                if isinstance(value, tuple):
                    writes.append((key, value))
                super().__setitem__(key, value)

        def tracked(factory):
            self.assertIs(factory, dict)
            return defaultdict(Spy)

        with patch("windowcross.core.defaultdict", side_effect=tracked):
            report = self.run_audit(examples=examples)
        return report, writes

    def test_counts_only_retains_no_active_record_metadata(self):
        self.rows = [(str(i), "e", "x" if i % 2 else "y", 0, 10) for i in range(100)]
        report, writes = self.witness_writes(0)
        self.assertEqual(writes, [])
        self.assertEqual(report["counts"]["cross_split_pairs"], 2500)

    def test_full_example_cap_stops_retaining_active_metadata(self):
        self.rows = [
            (str(i).zfill(3), "e", "x" if i % 2 else "y", 0, 10) for i in range(100)
        ]
        report, writes = self.witness_writes(1)
        self.assertEqual(len(writes), 1)
        self.assertEqual(len(report["examples"]), 1)
        self.assertEqual(report["counts"]["cross_split_pairs"], 2500)

    def test_unfilled_cap_retains_metadata_until_no_longer_needed(self):
        self.rows = [(str(i), "e", "x", i, i + 2) for i in range(10)]
        report, writes = self.witness_writes(3)
        self.assertEqual(len(writes), 10)
        self.assertTrue(report["passed"])

    def test_csv_field_parser_limit(self):
        self.write()
        before = csv.field_size_limit()
        try:
            csv.field_size_limit(4)
            with self.assertRaises(AuditError):
                audit(self.path)
        finally:
            csv.field_size_limit(before)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main([str(self.path), *argv])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_cli_status_json_and_no_partial_output(self):
        self.write()
        code, out, err = self.cli("--examples", "1")
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out)["counts"]["cross_split_pairs"], 1)
        self.rows[1] = ("b", "e", "test", 10, 20)
        self.write()
        self.assertEqual(self.cli()[0], 0)
        self.path.write_text("invalid")
        code, out, err = self.cli()
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("incomplete", err)
        code, out, err = self.cli("--examples", "no")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

    def test_cli_memoryerror_and_broken_pipe(self):
        with patch("windowcross.__main__.audit", side_effect=MemoryError):
            code, out, err = self.cli()
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("memory exhausted", err)
        self.write()
        with patch(
            "windowcross.__main__.sys.stdout.write", side_effect=BrokenPipeError
        ):
            self.assertEqual(main([str(self.path)]), 2)

    def test_module_entrypoint(self):
        self.write()
        p = subprocess.run(
            [sys.executable, "-m", "windowcross", str(self.path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["counts"]["cross_split_pairs"], 1)
        self.assertEqual(p.stderr, "")
