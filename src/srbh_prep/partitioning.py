"""Stage S8: stratified train / validation / test split and the partition-ID table.

Partition IDs identify each record by `raw_row`, its 0-based row number in the
released SR-BH 2020 file. A short SHA-1 of the input string sits beside it, so a
user can check that the same raw file and the same input string were used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .utilities import text_hash

PARTITIONS = ("train", "val", "test")


def split(df: pd.DataFrame, seed: int, test_fraction: float, val_fraction_of_rest: float) -> dict:
    """Two stratified splits with one seed: test first, then validation from the rest."""
    idx = np.arange(len(df))
    y = df["label_encoded"].values
    pool, test = train_test_split(idx, test_size=test_fraction, stratify=y, random_state=seed)
    train, val = train_test_split(pool, test_size=val_fraction_of_rest, stratify=y[pool], random_state=seed)
    return {"train": train, "val": val, "test": test}


def partition_table(df: pd.DataFrame, parts: dict) -> pd.DataFrame:
    """One row per final record: raw_row, partition, label, label_encoded, text_sha1_16.
    Rows keep the order in which the split returns them."""
    rows = []
    out = df.reset_index(drop=True)
    for name in PARTITIONS:
        sub = out.iloc[parts[name]]
        rows.append(pd.DataFrame({"raw_row": sub["raw_row"].values, "partition": name,
                                  "label": sub["label"].values, "label_encoded": sub["label_encoded"].values,
                                  "text_sha1_16": [text_hash(t) for t in sub["text"].values]}))
    return pd.concat(rows, ignore_index=True)


def partition_frames(df: pd.DataFrame, parts: dict) -> dict:
    out = df.reset_index(drop=True)
    cols = ["text", "label", "label_encoded", "raw_row"]
    return {name: out.iloc[parts[name]][cols].reset_index(drop=True) for name in PARTITIONS}


def apply_partition_ids(raw_csv_frame: pd.DataFrame, table: pd.DataFrame, text_builder) -> dict:
    """Rebuild the three partitions straight from the published partition IDs, without rerunning
    S1 to S8. `text_builder` must be preprocessing.build_input_string."""
    sub = raw_csv_frame.set_index("raw_row").loc[table["raw_row"]].reset_index()
    text, _ = text_builder(sub)
    sub = sub.assign(text=text.values)
    frames = {}
    for name in PARTITIONS:
        m = (table["partition"] == name).values
        f = pd.DataFrame({"text": sub.loc[m, "text"].values, "label": table.loc[m, "label"].values,
                          "label_encoded": table.loc[m, "label_encoded"].values, "raw_row": table.loc[m, "raw_row"].values})
        frames[name] = f
    return frames
