# run_all.py
# One command that builds the whole project from scratch:
#   python run_all.py --seed 20261022 --scale full
#
# Order:  master data > lots > readings > rule engine on CLEAN data (must give 0 alarms)
#         > inject faults > rule engine > inject defects > validate > evaluate > export

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from config import SEED, OUTPUT, DATA_DIR, GT_DIR, REPORT_DIR, JSON_DIR, SQL_DIR

ROOT = Path(__file__).parent


def reset_outputs():
    for folder in (DATA_DIR, GT_DIR, REPORT_DIR, JSON_DIR, SQL_DIR, OUTPUT / "clean_data"):
        if folder.exists():
            shutil.rmtree(folder)
    for f in (OUTPUT / "manifest.json",):
        if f.exists():
            f.unlink()


def step(label, module, args, verbose):
    t = time.time()
    cmd = [sys.executable, "-m", module] + args
    res = subprocess.run(cmd, cwd=ROOT, capture_output=not verbose, text=True)
    if res.returncode != 0:
        print(f"\nFAILED: {label}")
        if not verbose:
            print(res.stdout[-1500:], res.stderr[-3000:])
        sys.exit(res.returncode)
    print(f"  done  {label:55s} {time.time() - t:6.1f} s")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--scale", default="full", choices=["starter", "full"])
    p.add_argument("--skip-export", action="store_true")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()
    if a.seed != SEED:
        sys.exit(f"The seed is fixed in config.py (SEED = {SEED}). Change it there if you really want another one.")

    scale, v = ["--scale", a.scale], a.verbose
    print(f"Building the dataset: seed {SEED}, scale {a.scale}")
    t0 = time.time()
    reset_outputs()
    step("1  master data (warehouses, zones, sensors)", "pipeline.generate_master", scale, v)
    step("2  inventory lots and zone assignments", "pipeline.generate_lots", scale, v)
    step("3  normal readings and door events", "pipeline.generate_readings", scale, v)
    step("4  rule engine on CLEAN data", "pipeline.rule_engine", scale, v)
    n_alarm = len(pd.read_csv(DATA_DIR / "alarm.csv"))
    n_gap = len(pd.read_csv(DATA_DIR / "sensor_gap.csv"))
    if n_alarm or n_gap:
        sys.exit(f"STOP: clean data produced {n_alarm} alarms and {n_gap} gaps. It must produce 0.")
    print(f"        clean data check: 0 alarms, 0 gaps")
    step("5  inject faults and write ground truth", "pipeline.inject_faults", [], v)
    step("6  rule engine on damaged data", "pipeline.rule_engine", scale, v)
    step("7  inject defects (gap without alarm, alarm without lots)", "pipeline.inject_defects", [], v)
    step("8  validate", "pipeline.validate", [], v)
    step("9  evaluate against ground truth", "pipeline.evaluate", [], v)
    step("10 independent lot-exposure cross-check", "pipeline.evaluate_lot_exposure", [], v)
    if not a.skip_export:
        step("11 export JSON, SQL and manifest", "pipeline.export", scale, v)

    m = pd.read_csv(REPORT_DIR / "evaluation_metrics.csv")
    print("\nResult:")
    print(m[["detector", "true_positive", "false_positive", "false_negative", "precision", "recall"]].to_string(index=False))
    print(f"\nFinished in {time.time() - t0:.0f} s. Output folder: {OUTPUT}")


if __name__ == "__main__":
    main()