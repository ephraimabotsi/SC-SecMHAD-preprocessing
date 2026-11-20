#!/usr/bin/env python3
"""Rebuild the SC-SecMHAD benchmark from the raw SR-BH 2020 file.

Usage (from the repository root):
    python scripts/rebuild.py                      # full pipeline S0 to S8, then validation
    python scripts/rebuild.py --from-partitions    # rebuild the splits from the published partition IDs
    python scripts/rebuild.py --config path/to/config.yaml --strict

Outputs:
    data/processed/{train,val,test}.csv               text, label, label_encoded, raw_row
    data/partitions/partition_ids.csv                 raw_row, partition, label, label_encoded, text_sha1_16
    outputs/statistics/stage_counts.csv               records after each stage (Table 4)
    outputs/statistics/class_distribution.csv         records per class and partition (Table 3, Fig. 2)
    outputs/statistics/preprocessing_notes.json       every count quoted in Section 3.6
    outputs/statistics/paper_comparison.{csv,md}      paper value, generated value, difference, status
    outputs/statistics/integrity_checks.csv           leakage, duplicates, labels, ID consistency
    outputs/statistics/output_checksums.json          MD5 of every generated file (run-to-run check)
    outputs/audit/s5_precision_audit_sample.csv       S5 removed records to check by hand
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from srbh_prep import __version__  # noqa: E402
from srbh_prep import audit, partitioning, preprocessing, validation  # noqa: E402
from srbh_prep.utilities import LOG, load_config, md5sum, setup_logging, write_csv, write_json  # noqa: E402


def class_distribution(frames: dict, class_names: list[str]) -> pd.DataFrame:
    t = pd.DataFrame({n: f["label"].value_counts() for n, f in frames.items()}).reindex(class_names).fillna(0).astype(int)
    t["total"] = t.sum(axis=1)
    t.loc["Total"] = t.sum()
    return t.reset_index(names="class")


def _fmt(v) -> str:
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, (int,)) or (isinstance(v, float) and v.is_integer() and abs(v) >= 1):
        return "{:,}".format(int(v))
    return str(v)


def to_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "configs" / "config.yaml"))
    ap.add_argument("--from-partitions", action="store_true",
                    help="skip S1 to S8 and rebuild the splits from data/partitions/partition_ids.csv")
    ap.add_argument("--strict", action="store_true", help="exit with status 1 on any mismatch or failed check")
    args = ap.parse_args(argv)
    setup_logging(logging.INFO)
    cfg = load_config(args.config, ROOT)
    P = {k: Path(v) for k, v in cfg["paths"].items()}
    LOG.info("srbh_prep %s | config %s", __version__, args.config)

    raw_csv = P["raw_csv"]
    if not raw_csv.exists():
        LOG.error("Raw file not found: %s. Download SR-BH 2020 first (README, 'Dataset acquisition').", raw_csv)
        return 2
    digest = md5sum(raw_csv)
    if digest != cfg["source"]["expected_md5"]:
        LOG.warning("Raw file MD5 %s differs from the paper's file %s. Counts may differ.", digest, cfg["source"]["expected_md5"])
    else:
        LOG.info("Raw file MD5 matches the paper's file: %s", digest)

    names = cfg["labels"]["class_names"]
    if args.from_partitions:
        table = pd.read_csv(P["partitions_dir"] / "partition_ids.csv")
        raw, _ = preprocessing.load_raw(str(raw_csv))
        frames = partitioning.apply_partition_ids(raw, table, preprocessing.build_input_string)
        from srbh_prep.utilities import text_hash
        built = pd.concat([frames[n] for n in partitioning.PARTITIONS], ignore_index=True)
        ok = (built["text"].map(text_hash).values == table["text_sha1_16"].values).all()
        LOG.info("Input strings match the published fingerprints: %s", ok)
        for n, f in frames.items():
            write_csv(f, P["processed_dir"] / ("%s.csv" % n))
        checks = validation.integrity_checks(frames, table, names)
        checks.append({"check": "Input strings match published fingerprints", "passed": bool(ok), "detail": ""})
        write_csv(pd.DataFrame(checks), P["statistics_dir"] / "integrity_checks_from_partitions.csv")
        return 0 if all(c["passed"] for c in checks) else 1

    final, log, notes, removed, _ = preprocessing.run_stages(cfg)
    parts = partitioning.split(final, cfg["split"]["seed"], cfg["split"]["test_fraction"],
                               cfg["split"]["validation_fraction_of_rest"])
    frames = partitioning.partition_frames(final, parts)
    table = partitioning.partition_table(final, parts)
    stages = pd.DataFrame(log.rows)
    stages.loc[len(stages)] = {"stage": "S8", "rule": "Stratified split (seed %d): train %d, validation %d, test %d"
                               % (cfg["split"]["seed"], len(frames["train"]), len(frames["val"]), len(frames["test"])),
                               "records_after": len(final), "removed": 0}

    for n, f in frames.items():
        write_csv(f, P["processed_dir"] / ("%s.csv" % n))
    write_csv(table, P["partitions_dir"] / "partition_ids.csv")
    write_csv(stages, P["statistics_dir"] / "stage_counts.csv")
    dist = class_distribution(frames, names)
    write_csv(dist, P["statistics_dir"] / "class_distribution.csv")
    notes["raw_file_md5"] = digest
    notes["package_version"] = __version__
    write_json(notes, P["statistics_dir"] / "preprocessing_notes.json")

    a = cfg["precision_audit"]
    sample = audit.draw_sample(removed, a["sample_size"], a["seed"])
    write_csv(sample, P["audit_dir"] / "s5_precision_audit_sample.csv")
    LOG.info("S5 precision-audit sample: %d of %d removed records (seed %d)", len(sample), len(removed), a["seed"])

    # validation reads the files back from disk
    disk = {n: pd.read_csv(P["processed_dir"] / ("%s.csv" % n), keep_default_na=False) for n in partitioning.PARTITIONS}
    disk_table = pd.read_csv(P["partitions_dir"] / "partition_ids.csv")
    checks = validation.integrity_checks(disk, disk_table, names)
    write_csv(pd.DataFrame(checks), P["statistics_dir"] / "integrity_checks.csv")
    expected = json.load(open(ROOT / "configs" / "expected_paper_statistics.json", encoding="utf-8"))
    cmp_ = validation.compare_with_paper(expected, stages, notes, pd.concat(disk.values()), disk)
    write_csv(cmp_, P["statistics_dir"] / "paper_comparison.csv")
    (P["statistics_dir"] / "paper_comparison.md").write_text(to_markdown(cmp_), encoding="utf-8")

    files = sorted([*P["processed_dir"].glob("*.csv"), P["partitions_dir"] / "partition_ids.csv",
                    P["statistics_dir"] / "stage_counts.csv", P["statistics_dir"] / "class_distribution.csv",
                    P["audit_dir"] / "s5_precision_audit_sample.csv"])
    write_json({str(f.relative_to(ROOT)): md5sum(f) for f in files}, P["statistics_dir"] / "output_checksums.json")

    n_mis = int((cmp_["status"] == "Mismatch").sum())
    n_fail = sum(not c["passed"] for c in checks)
    LOG.info("Paper comparison: %d metrics, %d match, %d mismatch, %d not checked",
             len(cmp_), int((cmp_["status"] == "Match").sum()), n_mis, int((cmp_["status"] == "Not checked").sum()))
    LOG.info("Integrity checks: %d of %d passed", len(checks) - n_fail, len(checks))
    return 1 if args.strict and (n_mis or n_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
