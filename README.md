# windowcross

Audit whether explicitly assigned time windows overlap across dataset partitions.

A label might depend on an outcome observed after its prediction time. Two rows
assigned to different splits can therefore use overlapping outcome windows even
if their prediction times are ordered. `windowcross` checks the declared windows
without creating or changing the split.

It reads one local CSV, validates the entire input, and reports exact pair and
affected-record counts. It uses Python's standard library and makes no network
calls. This is source-only software, not a hosted service or registry release.

## Run from source

Python 3.9 or newer:

```sh
python -m pip install .
windowcross examples/crossing.csv
windowcross examples/crossing.csv --examples 5
```

Or, without installing:

```sh
PYTHONPATH=src python -m windowcross examples/crossing.csv
```

Exit statuses: `0` means no crossing under this policy, `1` means at least one
crossing, and `2` means invalid input/options or an incomplete audit. Invalid
input does not emit partial report JSON. Do not treat missing output, an error,
or an unrecognized status as a pass. Output delivery can itself fail, so consumers
must also successfully parse a complete report.

## Input and exact scope

```csv
id,entity,split,start_at,end_at
p1,account-7,train,2026-01-01T00:00:00Z,2026-01-03T00:00:00Z
p2,account-7,test,2026-01-02T00:00:00Z,2026-01-04T00:00:00Z
p3,account-7,test,2026-01-04T00:00:00Z,2026-01-05T00:00:00Z
```

The first two rows overlap for one day. The second and third only touch; they do
not overlap. Rows in the same split are not violations even when they overlap.

- Header names and order must match exactly. No extra columns.
- IDs must be globally unique. Entity and split comparisons use exact strings,
  with no numeric conversion, case folding, trimming or Unicode normalization.
  A leading/trailing space is significant; whitespace-only fields are invalid.
- Each interval is positive and half-open: `[start_at, end_at)`. Empty and reversed
  intervals are errors. Equal end/start boundaries do not overlap.
- Compare only rows with the **same entity and different splits**, symmetrically.
  The entity is a caller-declared comparison scope. If every row should be
  compared, use one constant entity. Different entities are never compared;
  this is not evidence they are independent.
- Timestamps require `YYYY-MM-DDTHH:MM:SS`, optional 1-6 fractional digits, and
  `Z` or a numeric `+HH:MM`/`-HH:MM` offset. They are converted to integer UTC
  microseconds, never floats. Numeric offsets denote a known fixed offset
  (`-00:00` is treated as zero), not a timezone or unknown-local-offset marker.
  Leap seconds, more than six fractional digits, missing offsets, invalid dates,
  and instants outside Python's UTC year 1-9999 range are rejected.
- UTF-8 CSV only, with an optional UTF-8 BOM. Quoted commas, newlines and Unicode
  identifiers are allowed. NUL is rejected. At least one data row is required.
  Blank records are errors, not ignored rows.

## Report and evidence

```python
from windowcross import audit, Limits, AuditError

try:
    report = audit("examples/crossing.csv", examples=2,
                   limits=Limits(max_records=100_000))
except AuditError:
    raise  # Not a clean audit.
print(report["counts"]["cross_split_pairs"])
```

Schema version 1 includes:

- `passed`: true only when cross-split pair count is zero.
- `counts`: records, distinct entities, overlapping cross-split pairs, distinct
  affected records and affected entities. A record with many partners counts
  once as affected. Pair counts are unordered, not doubled.
- `splits`: total and affected records for every split, including clean ones.
- `split_pairs`: nonzero pair counts, ordered by lexical split names.
- `input`: SHA-256 and byte length of the exact bytes read, including BOM and
  newline choices. This receipt identifies input bytes, not their truth or source.
- `settings`: effective limits and requested evidence cap.
- `examples` and `examples_omitted`: bounded witnesses and exact remaining pair
  count. Default cap is zero. Counts are still complete when evidence is capped.

Evidence ordering is deterministic, not a ranking of severity. Rows are scanned
by `(entity, UTC start, UTC end, id)`. For each current row, prior active split
names are visited lexically; records in that split retain their scan/insertion
order. The first requested pairs in that order are emitted. `earlier`/`later`
refer to this scan order, including tie-breaking, not strict time inequality.
Evidence has entity, both IDs, split names, UTC start/end microseconds, and exact
overlap duration. Reordering input rows preserves all report contents except the
byte receipt. For timestamps before 1970, epoch microseconds are negative.

**Privacy:** the default omits record IDs, entity values and timestamps from the
report. Split names, sizes, overlap counts and a hash remain visible. This is not
an anonymization promise. `--examples` explicitly includes potentially sensitive
record-level evidence. Error messages avoid echoing field contents or the path;
the invoked shell command and filesystem can still expose the path. Keep reports
and source manifests in an appropriate location.

## Limits and cost

Defaults: 16 MiB input bytes, 100,000 records, 1,024 characters per field and 100
distinct splits. Set `--max-bytes`, `--max-records`, `--max-field-chars`, and
`--max-splits` to positive integers. `--examples` accepts 0 through 1000. The API
uses the same `Limits` defaults and rejects booleans for integer settings.

The file is read up to the byte cap plus one, decoded and fully parsed, then
sorted in memory. This is **not streaming**, and these acceptance caps are **not
hard RAM or runtime bounds**. Python's CSV parser field limit can also reject a
large field, even if the configured field cap would allow it; the audit fails
rather than modifying the process-wide CSV limit.

For N rows, S splits, and E emitted examples, sorting plus the sweep costs
`O(N log N + N S log S + E)` worst case. The S term matters when increasing
`max_splits`. Sorting active split labels is included in that bound. Expired splits are removed
from that index as soon as their live count reaches zero, then reinserted if
they return. Each row scans only currently live split labels rather than every
split previously seen for the entity. This can save work on sparse histories
with many split labels, but does not improve the dense worst-case bound.
Deleting and reinserting labels adds work, so it is not a universal speedup. Memory is
`O(input bytes + N + S² + E)`, including the per-split-pair report. Counts are
Python integers. Split multiplicities and an end heap avoid materializing all
crossing pairs. Per-record active start/end witness maps are omitted when
`examples=0`, and dropped once the evidence cap is filled. Unfilled evidence
requests retain those maps. The end heap, parsed rows and pending affected-record
IDs still take memory; this is not a hard RAM guarantee or a claim of lower
whole-process peak memory. Every newly affected prior record is cleared from a pending map
at most once; dense overlap still produces exact affected counts. This does not
make large inputs or large split counts cheap.

## What a pass does not mean

This is not a leakage certificate, statistical independence test, or validation
of a model's evaluation procedure. It does not infer label horizons, build or
purge folds, add embargoes or gaps, choose entity scope, inspect feature
availability, find duplicate content, or check dependencies between different
entities. A contaminated manifest can omit the relevant windows or assign
misleading scopes and still pass. Select boundaries and scopes from the actual
meaning of the data before using this check.

## Related work and boundaries

This is a narrow audit format, not a claim of a new interval algorithm or better
cross-validation method. Existing tools cover broader or different workflows:

- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
  creates time-ordered folds and offers a sample-count `gap`; its documentation
  discusses equally spaced samples for comparable fold metrics.
- [purged-cross-validation](https://eslazarev.github.io/purged-cross-validation/api/splitters/)
  already offers label-horizon-aware splitters, purging and embargoes. If you need
  fold construction, inspect it rather than treating this audit as a substitute.
- [bedtools intersect](https://bedtools.readthedocs.io/en/latest/content/tools/intersect.html)
  already uses a sorted sweep for interval intersection in genomic workflows.
- [pandas Interval.overlaps](https://pandas.pydata.org/docs/reference/api/pandas.Interval.overlaps.html)
  documents open/closed boundary behavior. This tool fixes one convention and
  rejects empty windows rather than offering all closure types.

Boundary conventions and purge direction differ across published workflows.
This tool's symmetric positive half-open policy must not be assumed equivalent
to them. See [EVIDENCE.md](EVIDENCE.md) for the checked sources and limits.

## Development

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
ruff check src tests proof
ruff format --check src tests proof
python -m build
```

The suite compares complete reports against a separate pair-enumerating oracle,
including deterministic witness order, dense counts, invalid inputs, UTC bounds,
privacy defaults and CLI exit behavior. See [VALIDATION.md](VALIDATION.md) for
what has actually been run. No dependency, registry or Marketplace publication
is implied by this repository.
