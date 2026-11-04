# pipeline/repro_check.py
# Proof of reproducibility: build the whole dataset twice with the same seed and compare
# the row counts and SHA-256 checksum of every output file.
#   python -m pipeline.repro_check --scale full

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import argparse
import subprocess
import time

import pandas as pd

from config import SEED, OUTPUT
from utils import file_checksum

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"reproducibility_report.md"}


def snapshot():
    snap = {}
    for p in sorted(OUTPUT.rglob("*")):
        if p.is_file() and p.name not in SKIP and "clean_data" not in p.parts:
            rows = ""
            if p.suffix == ".csv":
                with open(p, "rb") as fh:
                    rows = sum(1 for _ in fh) - 1
            snap[str(p.relative_to(OUTPUT)).replace("\\", "/")] = (rows, file_checksum(p))
    return snap


def run(scale, skip_export):
    cmd = [sys.executable, "run_all.py", "--scale", scale] + (["--skip-export"] if skip_export else [])
    t = time.time()
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit("A run failed:\n" + res.stdout[-1500:] + res.stderr[-3000:])
    return time.time() - t


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", default="full", choices=["starter", "full"])
    p.add_argument("--skip-export", action="store_true", help="faster: compare only CSV and report files")
    a = p.parse_args()

    print(f"Run 1 of 2 (seed {SEED}, scale {a.scale}) ...")
    t1 = run(a.scale, a.skip_export)
    s1 = snapshot()
    print(f"  finished in {t1:.0f} s, {len(s1)} files")
    print("Run 2 of 2 ...")
    t2 = run(a.scale, a.skip_export)
    s2 = snapshot()
    print(f"  finished in {t2:.0f} s, {len(s2)} files")

    rows = []
    for f in sorted(set(s1) | set(s2)):
        a1, a2 = s1.get(f), s2.get(f)
        same = a1 is not None and a1 == a2
        rows.append({"file": f, "rows_run1": a1[0] if a1 else "-", "rows_run2": a2[0] if a2 else "-",
                     "sha256_run1": a1[1][:16] if a1 else "-", "sha256_run2": a2[1][:16] if a2 else "-",
                     "identical": "yes" if same else "NO"})
    df = pd.DataFrame(rows)
    ok = bool((df["identical"] == "yes").all())

    L = ["# Reproducibility report", "",
         f"The whole pipeline was run twice with seed {SEED} and scale {a.scale}. "
         "Row counts and SHA-256 checksums (first 16 characters shown) were compared for every output file.", "",
         f"**Result: {'ALL ' + str(len(df)) + ' FILES IDENTICAL' if ok else 'DIFFERENCES FOUND'}**", "",
         "| File | Rows run 1 | Rows run 2 | SHA-256 run 1 | SHA-256 run 2 | Identical |", "|---|---|---|---|---|---|"]
    L += [f"| {r.file} | {r.rows_run1} | {r.rows_run2} | {r.sha256_run1} | {r.sha256_run2} | {r.identical} |"
          for r in df.itertuples()]
    (OUTPUT / "reproducibility_report.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    print(f"\nFiles compared: {len(df)} | identical: {int((df['identical'] == 'yes').sum())}")
    print("RESULT:", "REPRODUCIBLE (all files identical)" if ok else "NOT REPRODUCIBLE")
    for r in df[df["identical"] != "yes"].itertuples():
        print("  differs:", r.file)
    print(f"Report: {OUTPUT / 'reproducibility_report.md'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()