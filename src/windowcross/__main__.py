"""Complete audit JSON or a nonzero invalid-input result without partial JSON."""

import argparse
import json
import sys

from .core import AuditError, Limits, audit


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit explicit half-open windows across fixed partitions"
    )
    parser.add_argument("manifest")
    parser.add_argument("--examples", type=int, default=0)
    for name, value in vars(Limits()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=value)
    args = parser.parse_args(argv)
    try:
        limits = Limits(**{name: getattr(args, name) for name in vars(Limits())})
        report = audit(args.manifest, examples=args.examples, limits=limits)
        text = json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    except AuditError as exc:
        print("windowcross: audit incomplete; " + str(exc), file=sys.stderr)
        return 2
    except MemoryError:
        print("windowcross: audit incomplete; memory exhausted", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(text)
    except BrokenPipeError:
        return 2
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
