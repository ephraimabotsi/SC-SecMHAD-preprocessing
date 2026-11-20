# Quality assurance report, release v1.0.0

Date: 2026-11-20. Environment: Python 3.13.18, pandas 3.0.5, NumPy 2.5.3, scikit-learn 1.9.1, Linux.
Raw input: `data_capec_multilabel.csv`, MD5 `173ec515308bdce5aec19cfd5b792596`, 907,815 records.

## 1. Summary

| Area | Result |
|---|---|
| Paper statistics reproduced | 69 of 69 match (0 mismatches, 0 unchecked) |
| Partitions identical to the paper's partitions | Yes: train, validation and test match record for record and in order |
| Test labels equal the labels stored with the paper's trained models | Yes (29,383 of 29,383) |
| Integrity checks on the written files | 10 of 10 pass |
| Automated tests | 17 of 17 pass (11 unit, 6 integration) |
| Run-to-run determinism | Two full runs give identical MD5 for every data file |
| Fresh clone in a new virtual environment | Install from `requirements.txt`, rebuild and tests pass, identical MD5 |
| Rebuild from published partition IDs | Byte-identical `train.csv`, `val.csv`, `test.csv`, and all fingerprints match |
| Machine-specific paths in code | None. All paths come from `configs/config.yaml`, relative to the repository root |
| Request text in the repository | None. Raw data, processed partitions and the audit sample are excluded by `.gitignore` |

## 2. Code validation

* `scripts/rebuild.py` runs end to end with no manual step (19 s, peak memory 1.5 GB).
* `scripts/rebuild.py --strict` exits with status 0, so no mismatch or failed check occurs.
* `scripts/rebuild.py --from-partitions` exits with status 0.
* Imports resolve from a fresh clone. All dependencies are listed in `requirements.txt`.
* Each file write goes through a temporary file and a rename, so an interrupted run leaves no partial file.
* Errors raise clear messages: missing raw file, wrong label columns, values outside 0 and 1, unknown label
  columns, unmapped classes, and an audit sample larger than the removed set.

## 3. Data validation

| Check | Result |
|---|---|
| Records generated | 195,883 (train 141,525, validation 24,975, test 29,383) |
| Classes | 9, codes 0 to 8 in the order of `configs/config.yaml` |
| Class distribution per partition | Matches Table 3 for totals and test counts. Train and validation counts are listed in the README. |
| Missing input strings or labels | None |
| Duplicate record IDs (`raw_row`) | None |
| Duplicate input strings | None |
| Input strings shared between partitions | 0 for train and validation, 0 for train and test, 0 for validation and test |
| Partition-ID table against written files | Same 195,883 IDs |
| Feature dimensions | One text field per record (method, URL path and query, body). No numeric feature matrix is produced. |

## 4. Reproducibility validation

* Seeds: cap 42, split 42, audit sample 42. No other step draws random numbers.
* Run 1 and run 2 MD5 values are identical for the three partitions, the partition IDs, the stage counts,
  the class distribution and the audit sample.
* An independent clone with a new virtual environment reproduced the same MD5 values.

## 5. Paper consistency

All 69 statistics in `outputs/statistics/paper_comparison.md` match the manuscript: every stage count of
Table 4, every raw column count, final class count and test class count of Table 3, the partition sizes,
and every count and percentage quoted in Section 3.6. Percentages are compared at the precision printed
in the paper (for example 97.0% against a generated 96.96%).

## 6. Filter-precision audit

`precision_audit.sample_size` is 200 with seed 42, as in Section 3.6. The rebuild writes the 200 sampled
records to `outputs/audit/s5_precision_audit_sample.csv`, and `scripts/score_audit.py` computes the
precision and its Wilson 95% interval from the marked sheet. The sample does not affect any count or partition.

## 7. Open items before publication

* SR-BH 2020 license confirmed on Harvard Dataverse: CC0 1.0.
* Publish to GitHub and archive the release on Zenodo, then add the DOI to `README.md` and `CITATION.cff`.
