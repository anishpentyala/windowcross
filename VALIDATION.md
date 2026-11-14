# Validation record

Local developer checks on November 14, 2026, before public submission:

- 25 unittest methods passed on CPython 3.9.25, 3.10.12, 3.11.17, 3.13.17,
  3.14.9 and 3.15.1 on Linux. This is not every platform or interpreter.
- A pair-enumerating oracle compared complete reports, including bounded witness
  order, for 400 seeded random manifests at four evidence caps (0, 1, 7, 1000).
  Input receipts were separately calculated from raw bytes. The oracle uses
  production timestamp conversion only to render integer dates in these small
  generated cases; separate timestamp tests cover rejection, offsets and bounds.
- Dense fixture: 10,000 rows, two balanced splits, 25,000,000 exact crossing
  pairs, 10,000 affected records and two emitted examples. No portable speed
  or memory claim follows from this fixture.
- Ruff 0.17.5 check and format verification passed over source, tests and proof.
- Wheel and sdist built locally. Neutral directories using installed wheels on
  Python 3.9 and 3.14 passed all 25 methods, including module subprocess tests.
- `proof/mutations.py` reran the same-target intact suite (25 methods passing),
  then a deliberate bad assertion (one failure, zero errors), followed by eight
  isolated code faults. Actual assertion failures, zero test errors: closed
  boundary 530; same-split counting 1451; lost pair multiplicity 1283; lost prior
  affected records 1486; lost current affected record 1486; expired pending
  records retained 438; empty windows accepted 1; entity scoping removed 1543.
  Counts include generated subtest failures, not independent test methods.
  The script requires assertion failures and rejects error-only results.
- An initial I/O-error test incorrectly mocked its own fixture write as well as
  the read under test. It was fixed to invoke the audited read directly. It is
  not counted as product failure evidence.

No independent review, hosted CI, public merge, downstream adoption, Windows or
macOS result is implied by these developer checks. Publication and final-state
checks are separate from this local record.

## Fractional timestamp consistency correction

Independent review identified that Python 3.9/3.10's `datetime.fromisoformat`
accepts only three or six fractional digits, unlike newer interpreters. The
original grammar promised one through six, so valid short fractions failed
closed on older supported interpreters. This was an input-acceptance contract
bug, not an incorrect overlap count.

The fix right-pads a regex-validated fractional component to six digits before
conversion, with no floating-point conversion or rounding. A regression method
covers all six lengths, Z/positive/negative-zero offsets, negative epoch times
and CSV-to-report acceptance. The original implementation with this method
failed on Python 3.10.12 with four errors: inspected tracebacks show valid
fraction strings rejected by `instant`, not fixture or import failures. This
expected API-error baseline is separate from the assertion-only mutation gate.
After the fix all 26 methods passed on the six interpreters listed above; the
same eight mutation checks and deliberate bad assertion retained the recorded
assertion-failure counts with zero errors. A current wheel/sdist rebuild and
neutral installed-wheel 3.9/3.14 run also passed all 26 methods.

## Counts-only active-state change (0.1.1)

Developer checks on November 14, 2026:

- All original 26 methods remain unchanged; three new methods check that default
  counts-only mode writes no active witness tuples, a filled cap stops retaining
  metadata, and an unfilled cap keeps the witness path. All 29 methods passed
  on the six Linux CPython versions listed above and neutral installed wheels
  on 3.9/3.14. Ruff check/format, wheel and sdist builds passed.
- The same 29-method target on the unchanged 0.1.0 core has two assertion
  failures and zero errors: 100 witness writes instead of zero at cap 0, and
  100 instead of one at cap 1. These are operation/storage regression checks,
  not a claim that the previous output counts were incorrect.
- 3,000 complete 0.1.0/candidate report comparisons over 600 additional seeded
  manifests and caps 0/1/2/7/1000 matched exactly. The existing independent
  pair-enumerating report oracle remains active in the suite.
- Same-target intact 29 methods pass. A deliberate bad assertion has one failure
  and zero errors. Eleven isolated faults are caught with assertion failures,
  zero errors: enable default witness storage 1; keep metadata after full cap 1;
  retain expired active count 1341; closed boundaries 530; same-split counting
  1454; lost pair multiplicity 1285; lost prior affected count 1486; lost current
  affected count 1486; expired pending records retained 438; empty windows
  accepted 1; lost entity scope 1543. Counts include generated subtests.
- A local direct retained-state probe at the last insertion of a dense 100,000
  row fixture saw 100,000 active witness entries in 0.1.0 and zero in the
  candidate at caps 0, 1 and 1000 (the latter two already full). Both reported
  2,500,000,000 pairs. Local shallow witness-container/tuple sizes were
  10,843,312 bytes versus zero, excluding shared keys, heap, parsed input,
  pending IDs, counters and other process memory. This is not a hard memory cap.
- Whole-process peak RSS in local three-process 100,000-row runs was effectively
  unchanged (about 85 MiB) across dense, disjoint and same-split fixtures. Dense
  sweep runs were a little faster; unfilled-cap disjoint runs were slower.
  Neither memory nor speed superiority across workloads is claimed.

This section is local developer evidence, not new independent review, hosted
current-head CI, downstream use or a cross-platform guarantee.

## 0.1.2 active split index

2026-11-14 local Linux validation, not hosted CI or Windows/macOS evidence.
The previous 29-method test file is byte-unchanged. Four new methods give
33 passing on actual CPython 3.9.25, 3.10.12, 3.11.17, 3.13.17, 3.14.9 and
3.15.1. New tests inspect the actual active Counter keys passed to sorting,
including full expiry, partial expiry with a split still live, split reappearance,
equal start/end multiplicity and exact witness order. They exclude the separate
final split-total sort from that observation.

The same four methods against the original 0.1.1 core produce three assertion
failures and zero test errors; the dense multiplicity control passes. They show
expired zero-count labels still being scanned, not incorrect old report counts.
A separate seeded reference run compares 3,200 complete old/new reports from
800 random manifests at caps 0/1/3/1000, with zero differences. The existing suite
also checks reports against its literal pair-enumerating reference.

The intact suite passes all 33 methods. A deliberately wrong expected assertion
causes one assertion failure. Five production mutations fail by assertions with
zero test errors: leaving zero-count labels (3), changing half-open expiry (531),
dropping pair multiplicity (1,286), replacing rather than incrementing active
counts (1,329), and dropping prior affected counts (1,488). Counts include failing
subtests. Restoring the code and expected assertion restores all 33 methods.

Independent review separately ran Python 3.10 all 33 methods, the original
29-method baseline, the three new-test baseline failures plus dense control,
6,000 full-report equalities (1,200 manifests at five caps), 300 manifests at
three row shuffles, mutation checks, a neutral installed-wheel 33-method run,
lint and build. These checks are scoped evidence, not an exhaustive proof.

Ruff 0.17.5 checks and format checks cover `src`, `tests` and `proof` (six files).
No claim that all README fenced snippets were independently linted. Wheel and
sdist build, all packaged source bytes match the candidate, and neutral installed
wheel tests pass all 33 methods on Python 3.9 and 3.14.

A local CPython 3.14.9 fresh-process median of three runs on 50,000 rows measured
100-split disjoint histories at 0.436586 -> 0.244393 seconds without examples,
and 0.441355 -> 0.244937 with one example. Dense 100-split histories were slightly
slower (2.124706 -> 2.141069 seconds without examples), as were two-split disjoint
histories (0.230618 -> 0.236219). Peak RSS was essentially unchanged. Independent
fresh-process probes also found sparse-history savings, dense timing near neutral,
and about 3% slower two-split churn. These are local synthetic measurements, not
a portable speed or memory guarantee. Delete/reinsert work can cost more than
scanning a short split list. The dense worst-case bound and retained input, heap,
pending affected-record and optional witness data do not change.
