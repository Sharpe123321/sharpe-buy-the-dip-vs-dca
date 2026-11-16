"""
One command reruns everything:

    python run_all.py              # use cached data if present, else fetch it
    python run_all.py --refresh    # re-download every input first

Steps (stops at the first failure so no number is published from bad data or failing tests):
  1. data audit          scripts/audit_data.py      -> results/data_audit.md, data_audit_checks.csv
  2. unit tests          pytest                     (no look-ahead, cash accounting, dividends, engine == reference)
  3. sanity check        scripts/sanity_check.py    -> results/sanity_check_maggiulli.csv
  4. main study          scripts/run_study.py       -> results/*.csv
  5. charts              scripts/make_charts.py     -> charts/*.png
  6. tables for the docs scripts/make_tables.py     -> results/tables.md
  7. SPY-only 25-year run scripts/spy_25y.py        -> results/spy_25y.csv
  8. SPY vs XIU           scripts/why_canada.py     -> results/why_canada*.csv
  9. newsletter charts    scripts/newsletter_charts.py -> charts/chart_*.png
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

STEPS = [
    ("data audit", [PY, "scripts/audit_data.py"]),
    ("unit tests", [PY, "-m", "pytest", "-q", "tests"]),
    ("sanity check vs Maggiulli", [PY, "scripts/sanity_check.py"]),
    ("main study", [PY, "scripts/run_study.py"]),
    ("charts", [PY, "scripts/make_charts.py"]),
    ("tables", [PY, "scripts/make_tables.py"]),
    ("SPY-only 25-year run", [PY, "scripts/spy_25y.py"]),
    ("SPY vs XIU: why Canada", [PY, "scripts/why_canada.py"]),
    ("newsletter charts", [PY, "scripts/newsletter_charts.py"]),
]


def main() -> int:
    if "--refresh" in sys.argv:
        cache = ROOT / "data" / "cache"
        if cache.exists():
            for f in cache.iterdir():
                if f.is_file():
                    f.unlink()
            print("cleared data/cache - all inputs will be re-downloaded")
    t0 = time.time()
    for name, cmd in STEPS:
        print(f"\n===== {name} =====", flush=True)
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            print(f"\nSTOPPED: step '{name}' failed (exit {r.returncode}).")
            return r.returncode
    print(f"\nAll steps passed in {time.time() - t0:.0f}s. Results in results/, charts in charts/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
