from __future__ import annotations

import math

import pandas as pd

from .filtering import decode_twice

AUDIT_COLUMN = "attack_payload_present"


def draw_sample(removed: pd.DataFrame, size: int, seed: int) -> pd.DataFrame:
    if size > len(removed):
        raise ValueError("Audit sample size %d exceeds the %d removed records" % (size, len(removed)))
    s = removed.sample(size, random_state=seed).sort_values("raw_row").reset_index(drop=True)
    return pd.DataFrame({"audit_id": range(1, size + 1), "raw_row": s["raw_row"].values,
                         "matched_signature": s["payload"].values, "input_string": s["text"].values,
                         "decoded_twice": [decode_twice(t) for t in s["text"].values], AUDIT_COLUMN: ""})


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        raise ValueError("Empty audit")
    p = successes / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def score(sheet: pd.DataFrame) -> dict:
    marks = sheet[AUDIT_COLUMN].astype(str).str.strip().str.lower()
    if not marks.isin(["yes", "no"]).all():
        bad = sheet.loc[~marks.isin(["yes", "no"]), "audit_id"].tolist()
        raise ValueError("Audit rows without a yes/no mark: %s" % bad[:20])
    k, n = int((marks == "yes").sum()), len(marks)
    lo, hi = wilson_interval(k, n)
    return {"sample_size": n, "attack_payload_present": k, "precision": k / n, "wilson95_low": lo, "wilson95_high": hi}
