from __future__ import annotations

import pandas as pd

from .utilities import LOG


def integrity_checks(frames: dict, table: pd.DataFrame, class_names: list[str]) -> list[dict]:
    out = []

    def add(name, ok, detail):
        out.append({"check": name, "passed": bool(ok), "detail": str(detail)})
        (LOG.info if ok else LOG.error)("%-55s %s  %s", name, "PASS" if ok else "FAIL", detail)

    allf = pd.concat([f.assign(partition=n) for n, f in frames.items()], ignore_index=True)
    add("No missing input strings", allf["text"].notna().all() and (allf["text"].str.len() > 0).all(), "")
    add("No missing labels", allf["label"].notna().all(), "")
    add("Labels are the nine configured classes", set(allf["label"]) == set(class_names), sorted(set(allf["label"])))
    add("label_encoded matches class order",
        (allf["label_encoded"] == allf["label"].map({n: i for i, n in enumerate(class_names)})).all(), "")
    add("Each raw_row appears once", allf["raw_row"].is_unique, "%d records" % len(allf))
    add("Each input string appears once (no exact duplicates)", allf["text"].is_unique, "")
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        shared = set(frames[a]["text"]) & set(frames[b]["text"])
        add("No input string shared by %s and %s (leakage)" % (a, b), len(shared) == 0, "%d shared" % len(shared))
    add("Partition-ID table matches the written partitions",
        len(table) == len(allf) and set(table["raw_row"]) == set(allf["raw_row"]), "%d IDs" % len(table))
    return out


def _row(metric, expected, generated, where, decimals=None):
    if decimals is not None:
        diff = round(generated - expected, decimals + 1)
        status = "Match" if round(generated, decimals) == round(expected, decimals) else "Mismatch"
        g = round(generated, decimals + 1)
    else:
        diff = int(generated) - int(expected)
        status = "Match" if diff == 0 else "Mismatch"
        g = int(generated)
    return {"metric": metric, "paper": expected, "generated": g, "difference": diff, "status": status, "where_in_paper": where}


def compare_with_paper(expected: dict, stages: pd.DataFrame, notes: dict, final: pd.DataFrame,
                       frames: dict) -> pd.DataFrame:
    rows = []
    st = stages.set_index("stage")
    for k, v in expected["stage_records"].items():
        rows.append(_row("Records after %s" % k, v["value"], st.loc[k, "records_after"], v["where"]))
    for k, v in expected["stage_removed"].items():
        rows.append(_row("Records removed at %s" % k, v["value"], st.loc[k, "removed"], v["where"]))
    for k, v in expected["notes"].items():
        if k in notes:
            rows.append(_row(k, v["value"], notes[k], v["where"], v.get("decimals")))
        else:
            rows.append({"metric": k, "paper": v["value"], "generated": "not computable", "difference": "",
                         "status": "Not checked", "where_in_paper": v["where"]})
    for k, v in expected["S5_removed_by_payload_type"].items():
        rows.append(_row("S5 removed, %s" % k, v["value"], notes["S5_removed_by_payload_type"].get(k, 0), v["where"]))
    for k, v in expected["raw_records_per_label_column"].items():
        rows.append(_row("Raw records, column %s" % k, v["value"], notes["raw_records_per_label_column"][k], v["where"]))
    rows.append(_row("Number of classes", expected["number_of_classes"]["value"], final["label"].nunique(),
                     expected["number_of_classes"]["where"]))
    fc = final["label"].value_counts()
    for k, v in expected["final_records_per_class"].items():
        rows.append(_row("Final records, %s" % k, v["value"], fc.get(k, 0), v["where"]))
    tc = frames["test"]["label"].value_counts()
    for k, v in expected["test_records_per_class"].items():
        rows.append(_row("Test records, %s" % k, v["value"], tc.get(k, 0), v["where"]))
    for k, v in expected["partition_sizes"].items():
        rows.append(_row("Partition size, %s" % k, v["value"], len(frames[k]), v["where"]))
    rows.append(_row("Total records in all partitions", expected["stage_records"]["S7"]["value"],
                     sum(len(f) for f in frames.values()), "Table 4"))
    return pd.DataFrame(rows, dtype=object)
