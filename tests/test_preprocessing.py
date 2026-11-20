import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srbh_prep import audit, filtering, partitioning, preprocessing, validation
from srbh_prep.utilities import load_config, md5sum, text_hash

CFG = load_config(ROOT / "configs" / "config.yaml", ROOT)
RAW = Path(CFG["paths"]["raw_csv"])
needs_raw = pytest.mark.skipif(not RAW.exists(), reason="raw SR-BH 2020 file not present")


@pytest.mark.parametrize("text,expected", [
    ("GET /index.php?q=1%3B%20cat%20/etc/passwd", "OS command"),
    ("GET /x?id=1%20UNION%20SELECT%20pass%20FROM%20users", "SQL"),
    ("GET /static/..%252f..%252fwin.ini", "Path traversal"),
    ("GET /search?q=%3Cscript%3Ealert(1)%3C/script%3E", "Script injection"),
    ("GET /wp-login.php", None),
])
def test_core_signatures(text, expected):
    assert filtering.payload_type(text, "core") == expected


def test_decode_twice_handles_double_encoding():
    assert filtering.decode_twice("%252e%252e%252f") == "../"


def test_input_string_keeps_encoding_and_adds_body():
    df = pd.DataFrame({"request_http_method": ["GET", "POST"], "request_http_request": ["/a?x=%41", "/login"],
                       "request_body": [None, " user=admin "]})
    text, has_body = preprocessing.build_input_string(df, include_body=True)
    assert text.tolist() == ["GET /a?x=%41", "POST /login user=admin"]
    assert has_body.tolist() == [False, True]


def test_wilson_interval_known_values():
    lo, hi = audit.wilson_interval(100, 100)
    assert hi == 1.0 and abs(lo - 0.9630) < 1e-3
    lo, hi = audit.wilson_interval(200, 200)
    assert abs(lo - 0.9812) < 1e-3


def test_audit_score_rejects_unmarked_rows():
    sheet = pd.DataFrame({"audit_id": [1, 2], audit.AUDIT_COLUMN: ["yes", ""]})
    with pytest.raises(ValueError):
        audit.score(sheet)


def test_split_is_deterministic_and_stratified():
    df = pd.DataFrame({"label_encoded": np.repeat(np.arange(3), 200)})
    a = partitioning.split(df, 42, 0.15, 0.15)
    b = partitioning.split(df, 42, 0.15, 0.15)
    assert all((a[k] == b[k]).all() for k in a)
    assert not (set(a["train"]) & set(a["test"])) and not (set(a["val"]) & set(a["test"]))
    counts = df.iloc[a["test"]]["label_encoded"].value_counts()
    assert counts.max() - counts.min() <= 1


def test_config_values_match_paper_setting():
    assert CFG["caps"]["per_class"] == {"Normal": 52000, "SQL Injection": 42000}
    assert CFG["split"] == {"seed": 42, "test_fraction": 0.15, "validation_fraction_of_rest": 0.15}
    assert CFG["precision_audit"]["sample_size"] == 200
    assert len(CFG["labels"]["class_names"]) == 9


@pytest.fixture(scope="module")
def built():
    final, log, notes, removed, _ = preprocessing.run_stages(CFG)
    parts = partitioning.split(final, 42, 0.15, 0.15)
    return final, pd.DataFrame(log.rows), notes, removed, parts


@needs_raw
def test_raw_file_is_the_papers_file():
    assert md5sum(RAW) == CFG["source"]["expected_md5"]


@needs_raw
def test_every_paper_statistic_matches(built):
    final, stages, notes, _, parts = built
    stages.loc[len(stages)] = {"stage": "S8", "rule": "", "records_after": len(final), "removed": 0}
    frames = partitioning.partition_frames(final, parts)
    expected = json.load(open(ROOT / "configs" / "expected_paper_statistics.json", encoding="utf-8"))
    cmp_ = validation.compare_with_paper(expected, stages, notes, final, frames)
    assert (cmp_["status"] == "Match").all(), cmp_[cmp_["status"] != "Match"].to_string()


@needs_raw
def test_no_leakage_and_ids_unique(built):
    final, _, _, _, parts = built
    frames = partitioning.partition_frames(final, parts)
    table = partitioning.partition_table(final, parts)
    checks = validation.integrity_checks(frames, table, CFG["labels"]["class_names"])
    assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]


@needs_raw
def test_published_partition_ids_are_reproduced(built):
    final, _, _, _, parts = built
    table = partitioning.partition_table(final, parts)
    published = pd.read_csv(ROOT / "data" / "partitions" / "partition_ids.csv")
    assert table["raw_row"].tolist() == published["raw_row"].tolist()
    assert table["partition"].tolist() == published["partition"].tolist()
    assert table["text_sha1_16"].tolist() == published["text_sha1_16"].tolist()


@needs_raw
def test_audit_sample_size_and_source(built):
    _, _, _, removed, _ = built
    s = audit.draw_sample(removed, CFG["precision_audit"]["sample_size"], CFG["precision_audit"]["seed"])
    assert len(s) == 200 and set(s["raw_row"]) <= set(removed["raw_row"])
    assert s["raw_row"].is_unique


def test_text_hash_is_stable():
    assert text_hash("GET /") == text_hash("GET /") and len(text_hash("GET /")) == 16
