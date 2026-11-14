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
