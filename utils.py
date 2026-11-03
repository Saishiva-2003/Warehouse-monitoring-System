# utils.py
# Small helper tools that every other file will borrow.

import hashlib

import numpy as np
import pandas as pd

from config import SEED, DATA_DIR, GT_DIR, REPORT_DIR, JSON_DIR, SQL_DIR


# ---------- Random numbers ----------
def make_rng(seed=SEED):
    """Create THE random number generator. Create it once and pass it around."""
    return np.random.default_rng(seed)


# ---------- Folders ----------
def make_folders():
    """Create all output folders if they do not exist yet."""
    for folder in [DATA_DIR, GT_DIR, REPORT_DIR, JSON_DIR, SQL_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


# ---------- ID makers ----------
# The :03d part means "pad with zeros to 3 digits", so 1 becomes 001.
def wh_id(n):
    return f"WH-{n:03d}"                              # WH-001


def zone_id(wh, n):
    return f"ZONE-{wh}-{n:03d}"                       # ZONE-WH-001-001


def sensor_id(zone, sensor_type, n):
    return f"SNS-{zone}-{sensor_type}-{n:02d}"        # SNS-ZONE-WH-001-001-TEMP-01


def lot_id(n):
    return f"LOT-2026-{n:06d}"                        # LOT-2026-000001


def reading_id(sensor, ts):
    stamp = pd.Timestamp(ts).strftime("%Y%m%dT%H%M%SZ")
    return f"RDG-{sensor}-{stamp}"                    # RDG-<sensor>-20260101T001000Z


def make_id(prefix, n, width=6):
    """Generic maker: make_id('ALM', 1) gives ALM-000001."""
    return f"{prefix}-{n:0{width}d}"


# ---------- Saving and loading tables ----------
def save_table(df, name, folder=DATA_DIR, sort_by=None):
    """Sort the rows, then write a CSV the same way every time."""
    make_folders()
    if sort_by is not None:
        df = df.sort_values(sort_by, kind="mergesort")    # stable sort = repeatable
    df = df.reset_index(drop=True)
    path = folder / f"{name}.csv"
    df.to_csv(path, index=False, lineterminator="\n", float_format="%.4f")
    return path


def load_table(name, folder=DATA_DIR, dates=None):
    """Read a CSV back. 'dates' is a list of columns that hold date/times."""
    return pd.read_csv(folder / f"{name}.csv", parse_dates=dates)


# ---------- Checksum (used for the reproducibility proof) ----------
def file_checksum(path):
    """A fingerprint of a file. Same file content = same fingerprint."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- Quick self-test ----------
if __name__ == "__main__":
    wh = wh_id(1)
    zn = zone_id(wh, 1)
    sn = sensor_id(zn, "TEMP", 1)
    print(wh)
    print(zn)
    print(sn)
    print(lot_id(1))
    print(reading_id(sn, "2026-01-01 00:10:00"))
    print(make_id("ALM", 1))

    # Save and reload a tiny table, then delete it
    test = pd.DataFrame({"b": [2, 1], "a": [0.5, 1.25]})
    path = save_table(test, "_utils_test", sort_by="b")
    print(load_table("_utils_test"))
    print("Checksum starts with:", file_checksum(path)[:12])
    path.unlink()
    print("Test file removed.")