import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from srbh_prep.audit import score

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/score_audit.py <marked_audit_sheet.csv>")
    result = score(pd.read_csv(sys.argv[1], keep_default_na=False))
    print(json.dumps(result, indent=2))
