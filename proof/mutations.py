"""Run same-target intact tests, a deliberate test fault, and code mutations.

Each isolated mutant must produce actual assertion failures, not import errors.
Run from the project root: python proof/mutations.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = [
    ("closed-boundary", "ends[0][0] <= start", "ends[0][0] < start"),
    (
        "same-split-counted",
        "if other == split or not active[other]:",
        "if not active[other]:",
    ),
    ("drop-pair-multiplicity", "pairs[pair] += len(active[other])", "pairs[pair] += 1"),
    (
        "no-pending-affected",
        "affected[other] += len(unmarked[other])",
        "affected[other] += 0",
    ),
    ("no-current-affected", "affected[split] += 1", "affected[split] += 0"),
    (
        "keep-expired-pending",
        "unmarked[old_split].pop(old_key, None)",
        "None  # mutant retains expired pending",
    ),
    ("accept-empty-window", "if a >= b:", "if a > b:"),
    ("drop-entity-scope", "key=lambda row: row[0]", 'key=lambda row: "constant"'),
]


def run(directory):
    env = dict(
        os.environ, PYTHONPATH=str(directory / "src"), PYTHONDONTWRITEBYTECODE="1"
    )
    p = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
    )
    text = p.stdout + p.stderr
    failures = re.search(r"failures=(\d+)", text)
    errors = re.search(r"errors=(\d+)", text)
    return (
        p.returncode,
        int(failures[1]) if failures else 0,
        int(errors[1]) if errors else 0,
        text,
    )


def main():
    with tempfile.TemporaryDirectory(prefix="windowcross-controls-") as td:
        root = Path(td)
        for name, before, after in [
            ("intact", None, None),
            ("test-fault", None, None),
            *MUTANTS,
        ]:
            dest = root / name
            shutil.copytree(
                ROOT,
                dest,
                ignore=shutil.ignore_patterns(
                    ".git", "dist", "build", ".venv*", "*.egg-info", "__pycache__"
                ),
            )
            target = dest / "src/windowcross/core.py"
            if name == "test-fault":
                target = dest / "tests/test_audit.py"
                text = target.read_text()
                needle = 'self.assertEqual(row["counts"]["cross_split_pairs"], 48)'
                assert text.count(needle) == 1
                target.write_text(text.replace(needle, needle.replace("48)", "49)")))
            elif before:
                text = target.read_text()
                assert text.count(before) == 1, (name, text.count(before))
                target.write_text(text.replace(before, after))
            code, failures, errors, text = run(dest)
            print(
                f"{name}: exit={code} assertion_failures={failures} errors={errors}",
                flush=True,
            )
            if name == "intact":
                assert code == 0, text
            else:
                assert code != 0 and failures > 0 and errors == 0, text
            if name == "test-fault":
                assert failures == 1, text


if __name__ == "__main__":
    main()
