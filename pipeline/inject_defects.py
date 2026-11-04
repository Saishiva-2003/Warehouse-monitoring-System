# pipeline/inject_defects.py
# Stage: plant the last two edge cases. They can only be planted AFTER the rule engine has
# created alarms, because they damage the engine's own output tables.
#
#   FAULT-010  reading gap treated as normal : the gap stays in sensor_gap, its alarm is deleted
#   FAULT-011  alarm not linked to lots      : an alarm stays, its lot links (and everything
#                                              that depended on them) are deleted
#
# Reads : alarm tables from the rule engine + fault_ground_truth.csv
# Writes: the same tables (damaged) + more ground truth

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from config import GT_DIR, SEED
from utils import save_table, load_table

DEFECT_SEED = SEED + 20
GT_NAME = "fault_ground_truth"
LOT_DAMAGE_RULES = ("TEMP_HIGH", "TEMP_LOW", "HUM_HIGH", "HUM_LOW", "DOOR_OPEN_LONG")


def main():
    rng = np.random.default_rng(DEFECT_SEED)

    gt = load_table(GT_NAME, folder=GT_DIR)
    if "FAULT-011" in set(gt["scenario_id"]):
        raise RuntimeError("The defects were already applied. Run inject_faults, then the "
                           "rule engine, then this file again.")
    gap_fault = gt[gt["scenario_id"] == "FAULT-010"]
    if gap_fault.empty:
        raise RuntimeError("FAULT-010 is missing. Use the newest inject_faults.py and re-run it.")

    alarm = load_table("alarm", dates=["start_ts", "end_ts"])
    hist = load_table("alarm_status_history", dates=["changed_ts"])
    links = load_table("alarm_affected_lot", dates=["overlap_start", "overlap_end"])
    ins = load_table("inspection", dates=["inspected_ts"])
    rem = load_table("remediation", dates=["action_ts"])
    gaps = load_table("sensor_gap", dates=["gap_start", "gap_end"])

    # ---------------------------------------------------------
    # FAULT-010: reading gap treated as normal
    # ---------------------------------------------------------
    sid = gap_fault["entity_id"].iloc[0]
    g_start = pd.Timestamp(gap_fault["start_ts"].iloc[0])
    gap_row = gaps[(gaps["sensor_id"] == sid) & (gaps["gap_start"] == g_start)]
    target = alarm[(alarm["rule_code"] == "SENSOR_OUTAGE") & (alarm["sensor_id"] == sid)
                   & (alarm["start_ts"] == g_start)]
    if len(gap_row) != 1 or len(target) != 1:
        raise RuntimeError("Could not find the planted gap and its outage alarm. "
                           "Run the rule engine on the injected data first.")
    dead = target["alarm_id"].iloc[0]

    dead_ins = ins.loc[ins["alarm_id"] == dead, "inspection_id"]
    n_h = int((hist["alarm_id"] == dead).sum())
    n_l = int((links["alarm_id"] == dead).sum())
    n_i, n_r = len(dead_ins), int(rem["inspection_id"].isin(dead_ins).sum())
    rem = rem[~rem["inspection_id"].isin(dead_ins)]
    ins = ins[ins["alarm_id"] != dead]
    links = links[links["alarm_id"] != dead]
    hist = hist[hist["alarm_id"] != dead]
    alarm = alarm[alarm["alarm_id"] != dead]
    gt.loc[gt["scenario_id"] == "FAULT-010", "details"] = (
        f"Gap {gap_row['gap_id'].iloc[0]} is recorded in sensor_gap, but its outage alarm {dead} "
        f"was deleted (with {n_h} history, {n_l} lot-link, {n_i} inspection and {n_r} remediation rows).")

    # ---------------------------------------------------------
    # FAULT-011: alarm not linked to the lots it affected
    # ---------------------------------------------------------
    exposed = links[links["exposure_min"] > 0].groupby("alarm_id").size()
    ok_status = alarm.set_index("alarm_id")["status"]
    ok_rule = alarm.set_index("alarm_id")["rule_code"]
    eligible = sorted(a for a in exposed.index
                      if ok_rule.get(a) in LOT_DAMAGE_RULES and ok_status.get(a) not in (None, "OPEN"))
    if not eligible:
        raise RuntimeError("No alarm with exposed lots is available for FAULT-011.")
    victim = str(eligible[int(rng.integers(0, len(eligible)))])
    v = alarm[alarm["alarm_id"] == victim].iloc[0]

    lost = links[links["alarm_id"] == victim][["alarm_id", "lot_id", "overlap_minutes"]].copy()
    lost.insert(0, "scenario_id", "FAULT-011")

    v_ins = ins.loc[ins["alarm_id"] == victim, "inspection_id"]
    n_l = int((links["alarm_id"] == victim).sum())
    n_i, n_r = len(v_ins), int(rem["inspection_id"].isin(v_ins).sum())
    rem = rem[~rem["inspection_id"].isin(v_ins)]
    ins = ins[ins["alarm_id"] != victim]
    links = links[links["alarm_id"] != victim]
    # nobody inspected anything, so the alarm never got past ACKNOWLEDGED
    keep = (hist["alarm_id"] != victim) | hist["to_status"].isin(["OPEN", "ACKNOWLEDGED"])
    hist = hist[keep]
    alarm.loc[alarm["alarm_id"] == victim, "status"] = "ACKNOWLEDGED"

    gt = pd.concat([gt, pd.DataFrame([{
        "scenario_id": "FAULT-011", "fault_type": "ALARM_NOT_LINKED_TO_LOTS",
        "entity_id": victim, "zone_id": v["zone_id"],
        "start_ts": v["start_ts"], "end_ts": v["end_ts"],
        "expected_detection": "ALARM_LOT_LINK_MISSING", "expected_detected_by": "DATA_VALIDATOR",
        "details": (f"{n_l} lots were in the zone during {victim}, but their links were deleted "
                    f"(also {n_i} inspections and {n_r} remediations). The alarm stays at ACKNOWLEDGED.")}])],
        ignore_index=True)

    # ---------------- lot status follows the final remediation table ----------------
    lots = load_table("inventory_lot")
    discarded = set(rem.loc[(rem["action_type"] == "DISCARD_LOT") & (rem["status"] == "DONE"), "lot_id"])
    lots.loc[lots["lot_id"].isin(discarded), "lot_status"] = "DISCARDED"
    save_table(lots, "inventory_lot", sort_by="lot_id")

    # ---------------- save ----------------
    save_table(alarm, "alarm", sort_by="alarm_id")
    save_table(hist, "alarm_status_history", sort_by="history_id")
    save_table(links, "alarm_affected_lot", sort_by=["alarm_id", "lot_id"])
    save_table(ins, "inspection", sort_by="inspection_id")
    save_table(rem, "remediation", sort_by="remediation_id")
    save_table(gt, GT_NAME, folder=GT_DIR, sort_by="scenario_id")
    save_table(lost, "fault_ground_truth_lots", folder=GT_DIR, sort_by=["alarm_id", "lot_id"])

    print("\n======================================")
    print("       DEFECT INJECTION COMPLETED")
    print("======================================")
    print(f"FAULT-010 | gap treated as normal  | sensor {sid} | alarm {dead} deleted")
    print(f"FAULT-011 | alarm not linked       | {victim} ({v['rule_code']}) | {n_l} lot links deleted")
    print(f"Alarms now          : {len(alarm)}")
    print(f"Alarm-lot links now : {len(links)}")
    print("\nNext step: run the validator.")


if __name__ == "__main__":
    main()