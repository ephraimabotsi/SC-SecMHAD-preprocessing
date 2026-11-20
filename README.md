# SC-SecMHAD preprocessing: SR-BH 2020 benchmark rebuild

This repository rebuilds the nine-class SR-BH 2020 benchmark used in

> E. Abotsi, O. Kornyo, S. Alhassan, S. A. Muntaka, A. R. Owusu, J. M. Mensah, M. Asante.
> *SC-SecMHAD: Supervised Contrastive Learning with SecBERT for Fine-Grained Multi-Class HTTP Attack Detection.*
> Submitted to *Computer Networks* (manuscript COMNET-D-26-05952).

It turns the public SR-BH 2020 release file (907,815 multi-label HTTP requests) into the
train, validation and test partitions of the paper (141,525 / 24,975 / 29,383 requests), and
publishes the partition IDs that fix which raw record sits in which partition. One command runs
every stage, writes every statistic of Section 3.6, Table 3 and Table 4, and compares each one
with the value printed in the paper.

**Status of this release (v1.0.0):** all 69 dataset statistics reported in the paper are reproduced
exactly, and the generated partitions are record-for-record identical, in the same order, to the
partitions used to train and evaluate the models in the paper.

---

## Contents

1. [Pipeline](#1-pipeline)
2. [Repository structure](#2-repository-structure)
3. [Requirements](#3-requirements)
4. [Dataset acquisition](#4-dataset-acquisition)
5. [Installation](#5-installation)
6. [Running the pipeline](#6-running-the-pipeline)
7. [Generated files](#7-generated-files)
8. [Partition IDs](#8-partition-ids)
9. [Expected statistics](#9-expected-statistics)
10. [Filter-precision audit](#10-filter-precision-audit)
11. [Reproducibility](#11-reproducibility)
12. [Tests](#12-tests)
13. [Troubleshooting](#13-troubleshooting)
14. [Citation](#14-citation)
15. [License and attribution](#15-license-and-attribution)

---

## 1. Pipeline

Each stage is a function in `src/srbh_prep/preprocessing.py` or `src/srbh_prep/partitioning.py`,
run in this order. Every value below comes from `configs/config.yaml`.

| Stage | Operation | Records after |
|---|---|---:|
| S0 | Load the raw SR-BH 2020 file and validate its 14 label columns | 907,815 |
| S1 | Drop records whose only labels are excluded CAPEC columns (16, 153, 248, 33) | 905,506 |
| S2 | Build one input string per request: `method` + space + `URL path and query` + space + `body` (when present). URL encoding and letter case are kept. Headers and response fields are not used. | 905,506 |
| S3 | Merge exact duplicates of (input string, full 14-column label vector) | 378,051 |
| S4 | Single label: the first retained CAPEC column in file order wins (000, 272, 242, 88, 126, 66, 310, 274, 194, 34). CAPEC-274 merges into CAPEC-272 as *HTTP Protocol Manipulation*. | 378,051 |
| S5 | Label-noise filter: drop Normal records whose twice URL-decoded string matches a core payload signature (`src/srbh_prep/filtering.py`, Appendix A of the paper) | 347,922 |
| S6 | Drop every record of a string that carries two different labels (2,171 records, 736 strings), then 8 leftover duplicates | 345,743 |
| S7 | Random cap with seed 42: Normal 52,000, SQL Injection 42,000 | 195,883 |
| S8 | Stratified split with seed 42: 15% test, then 15% of the rest for validation | 141,525 / 24,975 / 29,383 |

The nine classes and their integer codes (`label_encoded`):

| Code | Class | SR-BH column(s) |
|---:|---|---|
| 0 | Normal | 000 |
| 1 | HTTP Protocol Manipulation | 272, 274 |
| 2 | Path Traversal | 126 |
| 3 | SQL Injection | 66 |
| 4 | Scanning for Vulnerable Software | 310 |
| 5 | OS Command Injection | 88 |
| 6 | Code Injection | 242 |
| 7 | Fake the Source of Data | 194 |
| 8 | HTTP Response Splitting | 34 |

No other preprocessing is applied: no lower-casing, decoding or normalization of the stored
input string (the SecBERT tokenizer lower-cases at training time), no feature selection beyond
the three request fields, and no resampling beyond the S7 cap.

## 2. Repository structure

```
SC-SecMHAD-preprocessing/
├── configs/
│   ├── config.yaml                      every parameter of the pipeline
│   └── expected_paper_statistics.json   values printed in the paper, with table or section
├── data/
│   ├── raw/                             place the SR-BH 2020 file here (not distributed)
│   ├── processed/                       train.csv, val.csv, test.csv (generated, not committed)
│   └── partitions/
│       └── partition_ids.csv            published partition IDs (committed)
├── outputs/
│   ├── statistics/                      stage counts, class distribution, paper comparison, checks
│   └── audit/                           S5 precision-audit sample (generated, not committed)
├── scripts/
│   ├── rebuild.py                       one-command rebuild and validation
│   └── score_audit.py                   precision and Wilson interval from a marked audit sheet
├── src/srbh_prep/
│   ├── preprocessing.py                 S0 to S7
│   ├── filtering.py                     S5 payload signatures
│   ├── partitioning.py                  S8 split and partition-ID table
│   ├── validation.py                    integrity checks and paper comparison
│   ├── audit.py                         S5 precision-audit sample and scoring
│   └── utilities.py                     configuration, logging, hashing, atomic writes
├── tests/test_preprocessing.py
├── QA_REPORT.md
├── requirements.txt
├── CITATION.cff
├── LICENSE
└── README.md
```

## 3. Requirements

* Python 3.12 or newer (tested with Python 3.13.18). The pinned NumPy release needs 3.12.
* pandas, NumPy, scikit-learn, PyYAML, and pytest for the tests (versions in `requirements.txt`)
* About 2 GB of free memory (measured peak 1.5 GB) and 1 GB of disk space. A full rebuild took 19 s on a cloud CPU.

The split depends on scikit-learn's `train_test_split`. The partition IDs were produced with
scikit-learn 1.9.1. If a future scikit-learn release changes its shuffling, use
`--from-partitions` (Section 6), which rebuilds the splits from the published IDs and does not
depend on the library's random stream.

## 4. Dataset acquisition

SR-BH 2020 is published by Sureda Riera et al. on Harvard Dataverse:
<https://doi.org/10.7910/DVN/OGOIXX>.

1. Download `data_capec_multilabel.csv` from the dataset page.
2. Place it at `data/raw/data_capec_multilabel.csv`, or set `paths.raw_csv` in `configs/config.yaml`.
3. Check the file: its MD5 should be `173ec515308bdce5aec19cfd5b792596` (907,815 records).
   The rebuild script checks this and warns when the file differs.

```bash
md5sum data/raw/data_capec_multilabel.csv        # Linux
md5 data/raw/data_capec_multilabel.csv           # macOS
```

The raw file (436 MB) and the generated partitions, which contain request text, are not part of
this repository. The partition IDs refer to raw row numbers only.

## 5. Installation

```bash
git clone https://github.com/ephraimabotsi/SC-SecMHAD-preprocessing.git
cd SC-SecMHAD-preprocessing
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 6. Running the pipeline

Full rebuild from the raw file, with validation:

```bash
python scripts/rebuild.py
python scripts/rebuild.py --strict     # exit status 1 on any mismatch with the paper or failed check
```

Rebuild the three partitions directly from the published partition IDs (no S1 to S8, no random step):

```bash
python scripts/rebuild.py --from-partitions
```

Use another configuration file:

```bash
python scripts/rebuild.py --config path/to/config.yaml
```

The log prints the record count after every stage, then one line per integrity check and a
summary of the paper comparison.

## 7. Generated files

| File | Content |
|---|---|
| `data/processed/train.csv`, `val.csv`, `test.csv` | `text`, `label`, `label_encoded`, `raw_row`. These are the inputs to model training. |
| `data/partitions/partition_ids.csv` | Partition IDs (Section 8) |
| `outputs/statistics/stage_counts.csv` | Records after each stage and records removed (Table 4) |
| `outputs/statistics/class_distribution.csv` | Records per class and partition (Table 3 and Fig. 2) |
| `outputs/statistics/preprocessing_notes.json` | Every count quoted in Section 3.6, plus raw-file MD5 and package version |
| `outputs/statistics/paper_comparison.csv` and `.md` | Paper value, generated value, difference and status for 69 statistics |
| `outputs/statistics/integrity_checks.csv` | Missing values, label codes, duplicate IDs and strings, leakage between partitions |
| `outputs/statistics/output_checksums.json` | MD5 of every generated data file, for run-to-run comparison |
| `outputs/audit/s5_precision_audit_sample.csv` | 200 S5-removed records drawn at random for the manual check (Section 10) |

## 8. Partition IDs

`data/partitions/partition_ids.csv` holds one row per final record (195,883 rows):

| Column | Meaning |
|---|---|
| `raw_row` | 0-based row number of the record in `data_capec_multilabel.csv` (header excluded). This is the record ID. |
| `partition` | `train`, `val` or `test` |
| `label`, `label_encoded` | Final class after S4 to S6 |
| `text_sha1_16` | First 16 hex digits of the SHA-1 of the input string, to confirm that the same raw file and the same S2 rule were used |

How the partitions were made: S8 calls `train_test_split` twice with `random_state = 42` and
stratification on `label_encoded`. The first call takes 15% of the 195,883 records as the test
set. The second takes 15% of the remaining 166,500 as the validation set.

Leakage control: S3 and S6 remove exact duplicates before the split, so no input string occurs
in two partitions. The rebuild verifies this on the written files. Near-duplicates can still
cross partitions. The paper measures them in Section 3.7 and reports results on low-overlap
subsets in Section 4.7.

To load a partition from the IDs in your own code:

```python
import pandas as pd
ids = pd.read_csv("data/partitions/partition_ids.csv")
test_rows = ids.loc[ids.partition == "test", "raw_row"]
```

## 9. Expected statistics

Records per class and partition, generated by the pipeline. The *Total* and *Test* columns are
printed in Table 3 of the paper, and the partition totals are printed in Table 4.

| Class | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| Normal | 37,570 | 6,630 | 7,800 | 52,000 |
| HTTP Protocol Manipulation | 5,847 | 1,032 | 1,214 | 8,093 |
| Path Traversal | 8,359 | 1,475 | 1,735 | 11,569 |
| SQL Injection | 30,345 | 5,355 | 6,300 | 42,000 |
| Scanning for Vulnerable Software | 1,705 | 301 | 354 | 2,360 |
| OS Command Injection | 4,288 | 757 | 891 | 5,936 |
| Code Injection | 8,423 | 1,486 | 1,749 | 11,658 |
| Fake the Source of Data | 31,406 | 5,542 | 6,520 | 43,468 |
| HTTP Response Splitting | 13,582 | 2,397 | 2,820 | 18,799 |
| **Total** | **141,525** | **24,975** | **29,383** | **195,883** |

Other reproduced values: 24,434 records with a body at S2 and 15,837 in the final data. At S4,
6,270 records carry more than one retained label, 5,351 of them span two or more final classes,
and none pairs Normal with an attack label. Of the 525,195 raw Normal records, 39,650 carry a
payload, and S5 removes 30,129 deduplicated records: 22,746 OS command, 5,807 SQL, 1,506 script
injection and 70 path traversal. The full list of 69 checked statistics is in
`outputs/statistics/paper_comparison.md` after a run, and in `QA_REPORT.md`.

The input is one text field per request. The pipeline produces no numeric feature matrix. The
paper's models tokenize this string themselves (at most 256 SecBERT tokens).

## 10. Filter-precision audit

The paper estimates the precision of the S5 noise filter by hand: draw a random sample of the
records S5 removed, inspect each one, and count those that really carry an attack payload.

The audit sample holds **200 records** (`precision_audit.sample_size` in `configs/config.yaml`,
seed 42), as in Section 3.6 of the paper. The audit only reads the removed records. It does not
change which records S5 removes, any count or any partition. With 200 of 200 records carrying a
payload, the precision is 1.00 with a Wilson 95% interval of 0.981 to 1.000.

To run the audit:

1. Run `python scripts/rebuild.py`. It writes `outputs/audit/s5_precision_audit_sample.csv` with
   the raw row, the matched signature, the input string and its twice-decoded form.
2. Mark the column `attack_payload_present` with `yes` or `no` for every row.
3. Run `python scripts/score_audit.py outputs/audit/s5_precision_audit_sample.csv`.
   It prints the precision and its Wilson 95% interval.

## 11. Reproducibility

* Seeds: S7 cap seed 42, S8 split seed 42, audit sample seed 42. No other step is random.
* Determinism: two full runs give byte-identical output files (`output_checksums.json`).
* Paper match: the generated `train.csv`, `val.csv` and `test.csv` equal the partitions used in the
  paper record for record and in the same order. The test labels equal the labels stored with the
  paper's trained models.
* The `--from-partitions` mode gives the same three files without any random step.

Checksums of the generated files (v1.0.0, scikit-learn 1.9.1, pandas 3.0.5):

| File | MD5 |
|---|---|
| `data/processed/train.csv` | `b7a9ca1609ef0e2870629d7f8d079bba` |
| `data/processed/val.csv` | `298d70e4c9eeb7d5dbb044db9416a519` |
| `data/processed/test.csv` | `e1e0362751e786dab9de29095348dd4c` |
| `data/partitions/partition_ids.csv` | `d5ab96dc3eca6241c69980307659f4dd` |

CSV formatting can differ slightly across pandas versions. The partition IDs and the counts do not.

## 12. Tests

```bash
python -m pytest -q
```

Unit tests check the payload signatures, the input-string rule, the split, the audit scoring and
the configuration. Integration tests run when the raw file is present: they check the raw-file
MD5, all 69 paper statistics, leakage and ID uniqueness, and that the pipeline reproduces the
published partition IDs exactly.

## 13. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Raw file not found` | Place the file at `data/raw/data_capec_multilabel.csv` or set `paths.raw_csv`. |
| `Raw file MD5 ... differs` | A different version of SR-BH 2020. Counts will not match the paper. Download version 1.2 from the DOI above. |
| `Expected 14 SR-BH label columns` | The file was opened and re-saved by a spreadsheet program, which can rename columns. Use the original download. |
| Counts match but checksums differ | A different pandas or scikit-learn version. Compare `partition_ids.csv`, or use `--from-partitions`. |
| `MemoryError` | The rebuild needs about 2 GB of memory. Close other programs or use a larger machine. |
| Paper comparison shows `Mismatch` | Do not edit the outputs. Check the raw-file MD5 and the configuration first, then open an issue. |

## 14. Citation

If you use this code or the partition IDs, cite the paper above and this software (see
`CITATION.cff`). Cite the dataset as:

> T. Sureda Riera, J. R. Bermejo Higuera, J. Bermejo Higuera, J. A. Sicilia Montalvo,
> J. J. Martínez Herráiz. SR-BH 2020 multi-label dataset [dataset]. Harvard Dataverse, 2022.
> <https://doi.org/10.7910/DVN/OGOIXX>

and its description: T. Sureda Riera et al., A new multi-label dataset for Web attacks CAPEC
classification using machine learning techniques, *Computers & Security* 120 (2022) 102788,
<https://doi.org/10.1016/j.cose.2022.102788>.

## 15. License and attribution

The code in this repository is released under the MIT License (`LICENSE`).
SR-BH 2020 is the work of Sureda Riera et al. and is not redistributed here. Harvard Dataverse
releases it under CC0 1.0 (<https://creativecommons.org/publicdomain/zero/1.0/>).
The partition IDs contain row numbers, labels and hashes, not request text.
