"""Output delivery is part of the CLI exit contract, not an audit finding."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from windowcross.__main__ import cli, main


class Sink(io.StringIO):
    def __init__(self, failure):
        super().__init__()
        self.failure = failure

    def write(self, text):
        if self.failure == "write":
            raise OSError("PRIVATE synthetic path or device detail")
        if self.failure == "broken":
            raise BrokenPipeError("PRIVATE")
        if self.failure == "closed":
            raise ValueError("PRIVATE")
        if self.failure == "short":
            return len(text) - 1
        if self.failure == "none":
            return None
        if self.failure == "bool":
            return True
        return super().write(text)

    def flush(self):
        if self.failure == "flush":
            raise OSError("PRIVATE")
        return super().flush()


def manifest(path, crossing):
    path.write_text(
        "id,entity,split,start_at,end_at\n"
        "a,e,train,2026-01-01T00:00:00Z,2026-01-03T00:00:00Z\n"
        + (
            "b,e,test,2026-01-02T00:00:00Z,2026-01-04T00:00:00Z\n"
            if crossing
            else "b,e,test,2026-01-03T00:00:00Z,2026-01-04T00:00:00Z\n"
        ),
        encoding="utf-8",
    )


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "windows.csv"

    def test_normal_audit_status_and_payload_are_unchanged(self):
        for crossing in (False, True):
            manifest(self.path, crossing)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(main([str(self.path)]), int(crossing))
            self.assertEqual(json.loads(out.getvalue())["passed"], not crossing)
            self.assertEqual(err.getvalue(), "")

    def test_report_delivery_failure_overrides_both_audit_statuses(self):
        for crossing in (False, True):
            manifest(self.path, crossing)
            for failure in (
                "write",
                "broken",
                "closed",
                "short",
                "none",
                "bool",
                "flush",
            ):
                err = io.StringIO()
                with self.subTest(crossing=crossing, failure=failure):
                    with patch("sys.stdout", Sink(failure)), patch("sys.stderr", err):
                        self.assertEqual(main([str(self.path)]), 2)
                    self.assertIn("output delivery failed", err.getvalue())
                    self.assertNotIn("PRIVATE", err.getvalue())

    def test_missing_stdout_is_incomplete(self):
        manifest(self.path, False)
        with patch("sys.stdout", None), patch("sys.stderr", io.StringIO()):
            self.assertEqual(main([str(self.path)]), 2)

    def test_broken_diagnostics_do_not_escape_main(self):
        self.path.write_text("invalid", encoding="utf-8")
        for failure in ("write", "broken", "closed", "short", "none", "bool", "flush"):
            with self.subTest(failure=failure):
                with (
                    patch("sys.stdout", io.StringIO()),
                    patch("sys.stderr", Sink(failure)),
                ):
                    self.assertEqual(main([str(self.path)]), 2)

    def test_help_write_and_flush_failures_are_not_success(self):
        for failure in ("write", "broken", "closed", "short", "none", "bool", "flush"):
            with self.subTest(failure=failure):
                with (
                    patch("sys.stdout", Sink(failure)),
                    patch("sys.stderr", io.StringIO()),
                ):
                    self.assertEqual(main(["--help"]), 2)

    def test_usage_diagnostic_delivery_failure_returns_two(self):
        with patch("sys.stderr", Sink("write")):
            self.assertEqual(main([]), 2)

    def test_wrapper_handles_final_flush_and_disables_only_failed_stream(self):
        for name in ("stdout", "stderr"):
            out, err = Sink("ok"), Sink("ok")
            stream = out if name == "stdout" else err
            with patch("sys.stdout", out), patch("sys.stderr", err):
                with patch("windowcross.__main__.main", return_value=0):
                    stream.failure = "flush"
                    self.assertEqual(cli([]), 2)
                    self.assertIsNone(getattr(sys, name))
                    other = "stderr" if name == "stdout" else "stdout"
                    self.assertIsNotNone(getattr(sys, other))

    def test_main_does_not_disable_failed_stream(self):
        manifest(self.path, False)
        sink = Sink("flush")
        with patch("sys.stdout", sink), patch("sys.stderr", io.StringIO()):
            self.assertEqual(main([str(self.path)]), 2)
            self.assertIs(sys.stdout, sink)

    @unittest.skipUnless(
        os.name == "posix" and Path("/dev/full").exists(), "POSIX output devices"
    )
    def test_real_launchers_normal_full_and_readerless_pipes(self):
        clean, crossing, invalid = (
            Path(self.temp.name) / name
            for name in ("clean.csv", "cross.csv", "invalid.csv")
        )
        manifest(clean, False)
        manifest(crossing, True)
        invalid.write_text("invalid", encoding="utf-8")
        launchers = [[sys.executable, "-m", "windowcross"]]
        if os.environ.get("WINDOWCROSS_TEST_CONSOLE"):
            launchers.append([os.environ["WINDOWCROSS_TEST_CONSOLE"]])
        cases = [
            ([str(clean)], 0, "stdout"),
            ([str(crossing)], 1, "stdout"),
            ([str(invalid)], 2, "stderr"),
            (["--help"], 0, "stdout"),
            ([], 2, "stderr"),
        ]
        for launcher in launchers:
            for unbuffered in (False, True):
                env = dict(os.environ)
                env.pop("PYTHONUNBUFFERED", None)
                if unbuffered:
                    env["PYTHONUNBUFFERED"] = "1"
                for args, expected, destination in cases:
                    for mode in ("normal", "full", "pipe"):
                        with self.subTest(
                            launcher=launcher,
                            unbuffered=unbuffered,
                            args=args,
                            mode=mode,
                        ):
                            kwargs = dict(
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE
                            )
                            read_fd = write_fd = None
                            device = None
                            if mode == "full":
                                device = open("/dev/full", "wb")
                                kwargs[destination] = device
                            elif mode == "pipe":
                                read_fd, write_fd = os.pipe()
                                os.close(read_fd)
                                kwargs[destination] = write_fd
                            try:
                                process = subprocess.run(
                                    launcher + args,
                                    env=env,
                                    cwd=self.temp.name,
                                    timeout=20,
                                    **kwargs,
                                )
                            finally:
                                if device is not None:
                                    device.close()
                                if write_fd is not None:
                                    os.close(write_fd)
                            self.assertEqual(
                                process.returncode, expected if mode == "normal" else 2
                            )
                            self.assertNotIn(b"Traceback", process.stderr or b"")
                            self.assertNotIn(
                                b"Exception ignored", process.stderr or b""
                            )
                            if (
                                mode == "normal"
                                and expected in (0, 1)
                                and args != ["--help"]
                            ):
                                self.assertEqual(
                                    json.loads(process.stdout)["passed"], expected == 0
                                )
