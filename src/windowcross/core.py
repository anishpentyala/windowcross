"""Exact cross-split overlap audit of caller-declared half-open time windows."""

import csv
import hashlib
import heapq
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import groupby, islice
from pathlib import Path


class AuditError(ValueError):
    """The manifest cannot be completely audited under the declared contract."""


def _integer(name, value, minimum):
    if type(value) is not int or value < minimum:
        raise AuditError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class Limits:
    """Acceptance limits, not hard process memory or time bounds."""

    max_bytes: int = 16777216
    max_records: int = 100000
    max_field_chars: int = 1024
    max_splits: int = 100

    def __post_init__(self):
        for name, value in vars(self).items():
            _integer(name, value, 1)


_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z",
    re.ASCII,
)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def instant(text):
    """Parse the fixed timestamp grammar into integer UTC microseconds."""
    if not isinstance(text, str) or not _TIME.fullmatch(text):
        raise AuditError("timestamp needs ISO date, seconds and explicit offset")
    if int(text[11:13]) > 23 or int(text[14:16]) > 59 or int(text[17:19]) > 59:
        raise AuditError("invalid timestamp clock fields")
    if text[-1] != "Z" and (int(text[-5:-3]) > 23 or int(text[-2:]) > 59):
        raise AuditError("invalid timestamp offset")
    # Python 3.9/3.10 accept only 3 or 6 fractional digits. Normalize the
    # already validated grammar to six without float conversion or rounding.
    normalized = text[:-1] + "+00:00" if text[-1] == "Z" else text
    if normalized[19] == ".":
        clock, offset = normalized[:-6], normalized[-6:]
        whole, fraction = clock.split(".")
        normalized = whole + "." + fraction.ljust(6, "0") + offset
    try:
        dt = datetime.fromisoformat(normalized)
        delta = dt.astimezone(timezone.utc) - _EPOCH
    except (ValueError, OverflowError) as exc:
        raise AuditError("invalid or out-of-range timestamp") from exc
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def _load(path, limits):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(limits.max_bytes + 1)
        if len(raw) > limits.max_bytes:
            raise AuditError("manifest byte limit exceeded")
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise AuditError("manifest must not contain NUL")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        if next(reader, None) != ["id", "entity", "split", "start_at", "end_at"]:
            raise AuditError("expected exact header id,entity,split,start_at,end_at")
        seen, rows, splits = set(), [], Counter()
        for number, row in enumerate(reader, 2):
            if len(rows) >= limits.max_records:
                raise AuditError("manifest record limit exceeded")
            if len(row) != 5 or any(
                not cell.strip() or len(cell) > limits.max_field_chars for cell in row
            ):
                raise AuditError(
                    f"invalid field count, blank or oversized field at record {number}"
                )
            key, entity, split, start, end = row
            if key in seen:
                raise AuditError(f"duplicate id at record {number}")
            seen.add(key)
            a, b = instant(start), instant(end)
            if a >= b:
                raise AuditError(f"interval must have start < end at record {number}")
            rows.append((entity, a, b, key, split))
            splits[split] += 1
            if len(splits) > limits.max_splits:
                raise AuditError("manifest split limit exceeded")
        if not rows:
            raise AuditError("manifest needs at least one record")
    except (OSError, UnicodeError, csv.Error, OverflowError) as exc:
        raise AuditError("unreadable or invalid UTF-8 CSV manifest") from exc
    return rows, splits, {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def audit(path, *, examples=0, limits=None):
    """Return a complete report or raise AuditError, never a partial audit.

    Positive half-open [start_at,end_at) intervals, same exact entity, different
    exact split. All split pairs are symmetric. No embargo or automatic repair.
    """
    _integer("examples", examples, 0)
    if examples > 1000:
        raise AuditError("examples must be <= 1000")
    if limits is None:
        limits = Limits()
    if type(limits) is not Limits:
        raise AuditError("limits must be a Limits instance")
    rows, totals, receipt = _load(path, limits)
    rows.sort()  # entity, start, end, id; globally unique ID breaks all ties.
    pairs, affected, samples = Counter(), Counter(), []
    entities = affected_entities = 0
    for entity, records in groupby(rows, key=lambda row: row[0]):
        entities += 1
        ends = []
        active = defaultdict(dict)
        unmarked = defaultdict(dict)
        entity_bad = False
        for _, start, end, key, split in records:
            # Endpoints touching at start do not share a half-open instant.
            while ends and ends[0][0] <= start:
                _, old_key, old_split = heapq.heappop(ends)
                del active[old_split][old_key]
                unmarked[old_split].pop(old_key, None)
            current_bad = False
            for other in sorted(active):
                if other == split or not active[other]:
                    continue
                pair = tuple(sorted((split, other)))
                pairs[pair] += len(active[other])
                current_bad = entity_bad = True
                # Every pending prior record is newly affected at most once,
                # regardless of how many crossing pairs it participates in.
                affected[other] += len(unmarked[other])
                unmarked[other].clear()
                for old_key, (old_start, old_end) in islice(
                    active[other].items(), examples - len(samples)
                ):
                    samples.append(
                        {
                            "entity": entity,
                            "earlier_id": old_key,
                            "earlier_split": other,
                            "earlier_start_us": old_start,
                            "earlier_end_us": old_end,
                            "later_id": key,
                            "later_split": split,
                            "later_start_us": start,
                            "later_end_us": end,
                            "overlap_us": min(end, old_end) - start,
                        }
                    )
            if current_bad:
                affected[split] += 1
            else:
                unmarked[split][key] = None
            active[split][key] = (start, end)
            heapq.heappush(ends, (end, key, split))
        affected_entities += entity_bad
    count = sum(pairs.values())
    return {
        "schema_version": 1,
        "passed": not count,
        "policy": "same_entity_different_split_positive_half_open_overlap",
        "counts": {
            "records": len(rows),
            "entities": entities,
            "cross_split_pairs": count,
            "affected_records": sum(affected.values()),
            "affected_entities": affected_entities,
        },
        "splits": {
            split: {"records": totals[split], "affected_records": affected[split]}
            for split in sorted(totals)
        },
        "split_pairs": [
            {"left_split": a, "right_split": b, "overlap_pairs": n}
            for (a, b), n in sorted(pairs.items())
        ],
        "examples": samples,
        "examples_omitted": count - len(samples),
        "settings": {"examples": examples, "limits": dict(vars(limits))},
        "input": receipt,
              }
