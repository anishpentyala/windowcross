# Scope evidence

Pages fetched and read on November 14, 2026. These sources motivate the narrow
contract; they do not endorse this tool or prove its implementation correct.

## Existing fold and horizon tools

- scikit-learn, official TimeSeriesSplit API:
  https://scikit-learn.org/stable/modules/generated/sklearn.model%5Fselection.TimeSeriesSplit.html
  defines `gap` as "Number of samples to exclude from the end of each train set
  before the test set." The documentation also says samples must be equally
  spaced for comparable metrics across folds. A sample-count gap is not a
  supplied variable label-horizon audit.
- purged-cross-validation, official splitter documentation:
  https://eslazarev.github.io/purged-cross-validation/api/splitters/
  documents prediction and evaluation times, half-open label horizons, purging
  and embargoes. It already provides richer split construction. This project
  does not claim to invent overlap-based contamination checks or replace it.

## Interval and boundary behavior

- bedtools, official intersect documentation:
  https://bedtools.readthedocs.io/en/latest/content/tools/intersect.html
  documents its sorted sweep workflow. Sorted interval sweeping is established
  prior work, not a new algorithm introduced here.
- pandas, official Interval.overlaps reference:
  https://pandas.pydata.org/docs/reference/api/pandas.Interval.overlaps.html
  says intervals that "only have an open endpoint in common do not overlap."
  This audit uses positive half-open windows only; it rejects empty windows.

## Important differences between workflows

- python.financial concept explainer:
  https://python.financial/concepts/purged-cross-validation/
  describes financial cross-validation with overlapping label horizons, including
  a closed-boundary convention. Secondary explanation, not a universal boundary
  definition or proof that purging eliminates every form of leakage.
- 3Jane implementation discussion:
  https://3jane.com/blog/financial-cross-validation/
  discusses an asymmetric workflow filtering test observations by prior training
  label ends. Practitioner discussion, not an equivalent symmetric audit.

These conventions differ. The tool checks exactly the caller-supplied
same-entity, different-split positive half-open intervals and nothing more.
There is no inference that independent entities, feature availability,
statistical independence, model evaluation quality or all data leakage were
checked. No uniqueness, speed superiority, real-world adoption or registry
availability claim is made.
