#!/usr/bin/env python3
"""Score a completed S5 precision-audit sheet.

Fill the column `attack_payload_present` of outputs/audit/s5_precision_audit_sample.csv
with yes or no for every row, then run:
    python scripts/score_audit.py outputs/audit/s5_precision_audit_sample.csv
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from srbh_prep.audit import score  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    result = score(pd.read_csv(sys.argv[1], keep_default_na=False))
    print(json.dumps(result, indent=2))
