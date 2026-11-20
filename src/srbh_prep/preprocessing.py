from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .filtering import payload_type
from .utilities import LOG

REQUIRED_COLUMNS = ["request_http_method", "request_http_request", "request_body"]
LABEL_COLUMN = re.compile(r"^\d+ - ")


@dataclass
class StageLog:
    rows: list = field(default_factory=list)

    def add(self, stage: str, rule: str, records: int, removed: int | None = None) -> None:
        self.rows.append({"stage": stage, "rule": rule, "records_after": int(records),
                          "removed": None if removed is None else int(removed)})
        LOG.info("%-3s %-78s %9s", stage, rule[:78], "{:,}".format(records))


def load_raw(path: str) -> tuple[pd.DataFrame, list[str]]:
    try:
        raw = pd.read_csv(path, low_memory=False)
    except FileNotFoundError as exc:
        raise FileNotFoundError("SR-BH 2020 file not found at %s. See README, 'Dataset acquisition'." % path) from exc
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError("Raw file lacks required columns: %s" % missing)
    label_cols = [c for c in raw.columns if LABEL_COLUMN.match(c)]
    if len(label_cols) != 14:
        raise ValueError("Expected 14 SR-BH label columns, found %d" % len(label_cols))
    bad = raw[label_cols].isin([0, 1]) | raw[label_cols].isna()
    if not bad.values.all():
        raise ValueError("Label columns hold values other than 0, 1 or empty")
    raw[label_cols] = raw[label_cols].fillna(0).astype(int)
    raw.insert(0, "raw_row", np.arange(len(raw)))
    return raw, label_cols


def build_input_string(df: pd.DataFrame, include_body: bool = True) -> tuple[pd.Series, pd.Series]:
    method = df["request_http_method"].fillna("").astype(object).map(str)
    url = df["request_http_request"].fillna("").astype(object).map(str)
    text = method + " " + url
    body = df["request_body"].fillna("").astype(object).map(str).str.strip()
    has_body = body != ""
    if include_body:
        text = pd.Series(np.where(has_body, text + " " + body, text), index=df.index)
    return text, has_body


def run_stages(cfg: dict) -> tuple[pd.DataFrame, StageLog, dict, pd.DataFrame, list[str]]:
    log, notes = StageLog(), {}
    capec_to_class = cfg["labels"]["capec_to_class"]

    raw, label_cols = load_raw(cfg["paths"]["raw_csv"])
    log.add("S0", "Raw SR-BH 2020 records", len(raw))
    notes["raw_records_per_label_column"] = raw[label_cols].sum().astype(int).to_dict()
    notes["raw_records_with_more_than_one_label"] = int((raw[label_cols].sum(axis=1) > 1).sum())

    retained = [c for c in label_cols if c in capec_to_class]
    unknown = [c for c in label_cols if c not in capec_to_class and c not in cfg["labels"]["excluded_columns"]]
    if unknown:
        raise ValueError("Label columns missing from the configuration: %s" % unknown)
    keep = raw[retained].sum(axis=1) > 0
    df = raw[keep].copy()
    log.add("S1", "Drop records whose sole labels are excluded (CAPEC 16, 153, 248, 33)", len(df), (~keep).sum())

    df["text"], df["has_body"] = build_input_string(df, cfg["input_string"]["include_body"])
    notes["S2_records_with_body"] = int(df["has_body"].sum())
    log.add("S2", "Build the input string: method + URL path and query + body", len(df), 0)

    raw_normal = df["000 - Normal"] == 1
    pay = pd.Series([payload_type(t, "core") for t in df.loc[raw_normal, "text"]], index=df.index[raw_normal])
    carry = pay.notna()
    notes["raw_normal_records"] = int(raw_normal.sum())
    notes["raw_normal_records_with_payload"] = int(carry.sum())
    sub = df.loc[carry.index[carry]]
    for col, key in (("src_ip", "payload_normal_share_top_source_ip"),
                     ("request_user_agent", "payload_normal_share_top_user_agent")):
        if col in sub.columns and len(sub):
            notes[key] = float(sub[col].astype(str).value_counts(normalize=True).iloc[0])
    if "response_http_status_code" in sub.columns and len(sub):
        notes["payload_normal_share_404"] = float((pd.to_numeric(sub["response_http_status_code"], errors="coerce") == 404).mean())

    before = len(df)
    df = df.drop_duplicates(["text"] + label_cols)
    log.add("S3", "Merge exact duplicates of (input string, full label vector)", len(df), before - len(df))

    k = df[retained].values
    df["label"] = [capec_to_class[retained[i]] for i in k.argmax(axis=1)]
    final_classes = df[retained].T.groupby([capec_to_class[c] for c in retained]).max().T
    notes["S4_label_priority"] = retained
    notes["S4_records_with_more_than_one_retained_label"] = int((df[retained].sum(axis=1) > 1).sum())
    notes["S4_records_spanning_two_or_more_final_classes"] = int((final_classes.sum(axis=1) > 1).sum())
    notes["S4_records_pairing_normal_with_attack"] = int(((df["000 - Normal"] == 1) & (df[retained].sum(axis=1) > 1)).sum())
    log.add("S4", "Single label: first retained CAPEC column in file order, 274 merged into 272", len(df), 0)

    is_normal = df["label"] == "Normal"
    df["payload"] = None
    df.loc[is_normal, "payload"] = [payload_type(t, "core") for t in df.loc[is_normal, "text"]]
    drop = is_normal & df["payload"].notna()
    if cfg["noise_filter"]["mode"] != "core":
        raise ValueError("Only the paper setting noise_filter.mode = core is supported")
    removed_s5 = df.loc[drop, ["raw_row", "text", "label", "payload"]].copy()
    notes["S5_removed_by_payload_type"] = removed_s5["payload"].value_counts().astype(int).to_dict()
    notes["S5_share_of_unique_normal_strings"] = float(drop.sum() / is_normal.sum())
    df = df[~drop]
    log.add("S5", "Label-noise filter: drop Normal records carrying an attack payload", len(df), drop.sum())

    n_labels = df.groupby("text")["label"].transform("nunique")
    conflict = n_labels > 1
    notes["S6_conflicting_strings"] = int(df.loc[conflict, "text"].nunique())
    notes["S6_conflicting_records"] = int(conflict.sum())
    df = df[~conflict]
    before = len(df)
    df = df.drop_duplicates(["text", "label"])
    notes["S6_leftover_duplicates"] = int(before - len(df))
    log.add("S6", "Drop strings with conflicting labels (%d) and leftover duplicates (%d)"
            % (notes["S6_conflicting_records"], notes["S6_leftover_duplicates"]), len(df),
            notes["S6_conflicting_records"] + notes["S6_leftover_duplicates"])

    caps, seed = cfg["caps"]["per_class"], cfg["caps"]["seed"]
    before = len(df)
    parts = []
    for label, group in df.groupby("label"):
        cap = caps.get(label)
        parts.append(group.sample(cap, random_state=seed) if cap and len(group) > cap else group)
    df = pd.concat(parts).sort_index()
    log.add("S7", "Random cap: Normal 52,000, SQL Injection 42,000 (seed %d)" % seed, len(df), before - len(df))

    names = cfg["labels"]["class_names"]
    df["label_encoded"] = df["label"].map({n: i for i, n in enumerate(names)})
    if df["label_encoded"].isna().any():
        raise ValueError("Unmapped class labels: %s" % sorted(set(df["label"]) - set(names)))
    df["label_encoded"] = df["label_encoded"].astype(int)
    notes["final_records_with_body"] = int(df["has_body"].sum())
    if "response_http_status_code" in raw.columns:
        status = raw.set_index("raw_row").loc[df.loc[df["label"] == "Normal", "raw_row"], "response_http_status_code"]
        notes["final_normal_share_404"] = float((pd.to_numeric(status, errors="coerce") == 404).mean())
    return df, log, notes, removed_s5, label_cols
