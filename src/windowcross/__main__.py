"""Complete audit JSON or exit 2 if an audit or its output is incomplete."""

import argparse
import json
import sys

from .core import AuditError, Limits, audit


def _write_text(stream, text):
    if stream is None:
        raise OSError("output stream is unavailable")
    written = stream.write(text)
    if type(written) is not int or written != len(text):
        raise OSError("output stream did not accept the complete text")
    stream.flush()


class _ArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        # argparse can suppress immediate write errors. They must reach main's
        # output boundary even when help is written without Python buffering.
        if message:
            _write_text(sys.stderr if file is None else file, message)


def _error(message):
    # Do not echo raw I/O errors, paths or manifest contents. A broken diagnostic
    # destination must not replace the incomplete-audit status with a traceback.
    try:
        _write_text(sys.stderr, "windowcross: audit incomplete; " + message + "\n")
    except (OSError, ValueError):
        pass
    return 2


def main(argv=None):
    parser = _ArgumentParser(
        description="Audit explicit half-open windows across fixed partitions"
    )
    parser.add_argument("manifest")
    parser.add_argument("--examples", type=int, default=0)
    for name, value in vars(Limits()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=value)
    try:
        args = parser.parse_args(argv)
    except (OSError, ValueError):
        return _error("output delivery failed")
    try:
        limits = Limits(**{name: getattr(args, name) for name in vars(Limits())})
        report = audit(args.manifest, examples=args.examples, limits=limits)
        text = json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    except AuditError as exc:
        return _error(str(exc))
    except MemoryError:
        return _error("memory exhausted")
    try:
        _write_text(sys.stdout, text)
    except (OSError, ValueError):
        return _error("output delivery failed")
    return 0 if report["passed"] else 1


def cli(argv=None):
    """Terminating process boundary, including argparse and final flushes."""
    try:
        status = main(argv)
    except SystemExit as exc:
        status = exc.code if isinstance(exc.code, int) else 0 if exc.code is None else 1
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            continue
        try:
            stream.flush()
        except (OSError, ValueError):
            if name == "stdout" and status in (0, 1):
                _error("output delivery failed")
            # Only the process entry point changes streams. Prevent Python from
            # retrying the failed flush at shutdown and replacing exit 2 by 120.
            setattr(sys, name, None)
            status = 2
    return status


if __name__ == "__main__":
    sys.exit(cli())
