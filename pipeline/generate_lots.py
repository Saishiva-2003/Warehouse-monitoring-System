# pipeline/generate_lots.py
# Stage 2: decide what is stored, where, and for how long.
# Reads : zone.csv, storage_requirement.csv
# Writes: inventory_lot.csv, lot_zone_assignment.csv

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import argparse

import numpy as np
import pandas as pd

from config import SEED, get_scale, PRODUCTS
from utils import make_rng, lot_id, make_id, save_table, load_table
from pipeline.timeline import study_window

# Typical price range per unit for each product (currency units)
UNIT_VALUE = {
    "VACCINE": (200, 800), "DAIRY": (2, 8), "ICE_CREAM": (3, 10),
    "FROZEN_MEAT": (8, 25), "BISCUITS": (1, 4), "BEVERAGES": (1, 5),
    "PAINT": (15, 60), "CHEMICALS": (20, 90),
}
QTY_RANGE = {          # how many units in a lot
    "VACCINE": (100, 2000), "DAIRY": (200, 3000), "ICE_CREAM": (200, 3000),
    "FROZEN_MEAT": (100, 2000), "BISCUITS": (500, 8000), "BEVERAGES": (500, 8000),
    "PAINT": (50, 1000), "CHEMICALS": (50, 800),
}


def main(scale_name="starter"):
    size = get_scale(scale_name)
    rng = make_rng(SEED + 1)          # own stream, so changing other stages does not change lots
    n_lots = size["lots"]

    zones = load_table("zone")
    reqs = load_table("storage_requirement")
    win_start, win_end, _ = study_window(scale_name)
    win_start, win_end = pd.Timestamp(win_start), pd.Timestamp(win_end)
    window_min = (win_end - win_start).total_seconds() / 60

    # 1. choose a product rule for every lot (common products are picked more often)
    weights = np.array([p[7] for p in PRODUCTS], dtype=float)
    weights = weights / weights.sum()
    req_pos = rng.choice(len(PRODUCTS), size=n_lots, p=weights)
    req_ids = [PRODUCTS[i][0] for i in req_pos]
    products = [PRODUCTS[i][1] for i in req_pos]
    need_type = [PRODUCTS[i][2] for i in req_pos]

    # 2. quantity and value (lot_value is CALCULATED, not generated)
    qty, unit_val = [], []
    for p in products:
        lo, hi = QTY_RANGE[p]
        qty.append(int(rng.integers(lo, hi + 1)))
        vlo, vhi = UNIT_VALUE[p]
        unit_val.append(round(float(rng.uniform(vlo, vhi)), 2))
    lot_value = [round(q * u, 2) for q, u in zip(qty, unit_val)]

    # 3. when the lot arrives and how long it stays (dwell)
    #    arrival: from half a window before the study starts to 90% of the way through
    arrive_offset = rng.uniform(-0.5 * window_min, 0.9 * window_min, n_lots)
    #    dwell: 10% to 150% of the window, skewed toward shorter stays
    dwell_min = window_min * np.clip(rng.lognormal(mean=-0.7, sigma=0.6, size=n_lots), 0.1, 1.5)
    received = [(win_start + pd.Timedelta(minutes=float(m))).floor("min") for m in arrive_offset]
    stored_until = [(r + pd.Timedelta(minutes=float(d))).floor("min") for r, d in zip(received, dwell_min)]
    expiry = [(r + pd.Timedelta(days=int(rng.integers(90, 366)))).strftime("%Y-%m-%d") for r in received]

    # 4. pick a room whose type matches what the product needs
    zones_by_type = {t: zones.loc[zones["zone_type"] == t, "zone_id"].tolist()
                     for t in zones["zone_type"].unique()}
    zone_type_of = dict(zip(zones["zone_id"], zones["zone_type"]))
    chosen_zone = []
    for t in need_type:
        options = zones_by_type[t]
        chosen_zone.append(options[int(rng.integers(0, len(options)))])

    # 5. build the two tables
    lots, assigns = [], []
    for i in range(n_lots):
        lid = lot_id(i + 1)
        status = "SHIPPED" if stored_until[i] <= win_end else "STORED"
        lots.append({
            "lot_id": lid,
            "requirement_id": req_ids[i],
            "quantity_units": qty[i],
            "unit_value": unit_val[i],
            "lot_value": lot_value[i],
            "received_ts": received[i],
            "expiry_date": expiry[i],
            "lot_status": status,
        })
        assigns.append({
            "assignment_id": make_id("ASG", i + 1),
            "lot_id": lid,
            "zone_id": chosen_zone[i],
            "stored_from": received[i],
            "stored_until": stored_until[i],
            "dwell_hours": round((stored_until[i] - received[i]).total_seconds() / 3600, 2),
            "compatible_flag": zone_type_of[chosen_zone[i]] == need_type[i],
        })
    lots = pd.DataFrame(lots)
    assigns = pd.DataFrame(assigns)

    save_table(lots, "inventory_lot", sort_by="lot_id")
    save_table(assigns, "lot_zone_assignment", sort_by="assignment_id")

    # ----- quick self-checks -----
    print(f"Scale: {scale_name}")
    print("Study window       :", win_start, "to", win_end)
    print("Lots               :", len(lots))
    print("Assignments        :", len(assigns))
    print("Lots by product    :", pd.Series(products).value_counts().to_dict())
    print("Unknown requirement:", (~lots["requirement_id"].isin(reqs["requirement_id"])).sum())
    print("Unknown zone       :", (~assigns["zone_id"].isin(zones["zone_id"])).sum())
    print("Unknown lot        :", (~assigns["lot_id"].isin(lots["lot_id"])).sum())
    print("Incompatible zones :", (~assigns["compatible_flag"]).sum())
    print("End before start   :", (assigns["stored_until"] <= assigns["stored_from"]).sum())
    print("Value mismatches   :",
          (abs(lots["lot_value"] - lots["quantity_units"] * lots["unit_value"]) > 0.01).sum())
    print("Duplicate lot ids  :", lots["lot_id"].duplicated().sum())
    print("Lots still stored  :", (lots["lot_status"] == "STORED").sum())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="starter", choices=["starter", "full"])
    args = parser.parse_args()
    main(args.scale)