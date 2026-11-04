# pipeline/inject_faults.py
# Stage: BREAK the clean data on purpose and write the answer sheet (ground truth).
# Reads : clean backup of the data tables
# Writes: damaged data tables (output/data) + fault_ground_truth.csv (output/ground_truth)

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import math
import shutil

import numpy as np
import pandas as pd

from config import DATA_DIR, GT_DIR, OUTPUT, SEED, READING_INTERVAL_MIN
from utils import save_table

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
CLEAN_DIR = OUTPUT / "clean_data"
FAULT_SEED = SEED + 10
STEP = pd.Timedelta(minutes=READING_INTERVAL_MIN)

REQUIRED_FILES = [
    "sensor_reading.csv", "door_event.csv", "inventory_lot.csv",
    "lot_zone_assignment.csv", "storage_requirement.csv", "sensor.csv",
    "sensor_zone_map.csv", "zone.csv",
]

GROUND_TRUTH_COLUMNS = [
    "scenario_id", "fault_type", "entity_id", "zone_id", "start_ts", "end_ts",
    "expected_detection", "expected_detected_by", "details",
]


# ---------------------------------------------------------
# FILE AND DATA HELPERS
# ---------------------------------------------------------
def prepare_clean_backup():
    """Keep a copy of the clean dataset, and restore the working data from it every run.
    NOTE: if you regenerate the clean data (master/lots/readings), delete
    output/clean_data first, otherwise the OLD clean data is restored."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    backup_ok = all((CLEAN_DIR / n).exists() for n in REQUIRED_FILES)
    if not backup_ok:
        missing = [n for n in REQUIRED_FILES if not (DATA_DIR / n).exists()]
        if missing:
            raise FileNotFoundError(f"Missing required CSV files: {missing}")
        alarm_path, gap_path = DATA_DIR / "alarm.csv", DATA_DIR / "sensor_gap.csv"
        if not alarm_path.exists() or not gap_path.exists():
            raise RuntimeError("Run the rule engine on the clean data first "
                               "(it must show 0 alarms), then run this file.")
        if len(pd.read_csv(alarm_path)) > 0 or len(pd.read_csv(gap_path)) > 0:
            raise RuntimeError("Alarms or sensor gaps already exist, so the data is not clean. "
                               "Regenerate the clean data first.")
        for p in DATA_DIR.glob("*.csv"):
            shutil.copy2(p, CLEAN_DIR / p.name)
        print("Created clean baseline backup.")

    for p in CLEAN_DIR.glob("*.csv"):               # restore everything from the clean copy
        shutil.copy2(p, DATA_DIR / p.name)
    print(f"Clean baseline: {CLEAN_DIR}")


def read_csv(name):
    path = CLEAN_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return pd.read_csv(path)


def parse_dates(df, columns):
    for c in columns:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def get_zone_sensors(zone_id, sensor_type, sensor_map, sensors):
    m = sensor_map[sensor_map["zone_id"] == zone_id].merge(
        sensors[["sensor_id", "sensor_type"]], on="sensor_id", how="inner")
    return sorted(m[m["sensor_type"] == sensor_type]["sensor_id"].drop_duplicates().tolist())


def find_zone_window(sensor_type, sensor_count, duration_min, zones, assignments,
                     sensor_map, sensors, first_ts, last_ts, used_zones, rng,
                     preferred_types=None):
    """Pick a zone and a RANDOM start time such that:
       - the zone has enough sensors of the wanted type
       - a lot is stored in the zone during the WHOLE fault window
       - the window is at least 1 hour away from the start and end of the data
       Same seed = same choice every run."""
    need = pd.Timedelta(minutes=duration_min)
    margin = pd.Timedelta(hours=1)

    order = []
    for t in preferred_types or []:
        ids = zones.loc[zones["zone_type"] == t, "zone_id"].tolist()
        order += [str(z) for z in rng.permutation(ids)]
    rest = [z for z in zones["zone_id"] if z not in order]
    order += [str(z) for z in rng.permutation(rest)]

    for zid in order:
        if zid in used_zones:
            continue
        sensor_ids = get_zone_sensors(zid, sensor_type, sensor_map, sensors)
        if len(sensor_ids) < sensor_count:
            continue

        best = None                                   # the lot stay with the longest usable time
        for a in assignments[assignments["zone_id"] == zid].itertuples():
            until = last_ts if pd.isna(a.stored_until) else a.stored_until
            lo = max(a.stored_from, first_ts + margin)
            hi = min(until, last_ts - margin) - need
            if hi >= lo and (best is None or (hi - lo) > (best[1] - best[0])):
                best = (lo, hi)
        if best is None:
            continue

        lo, hi = best
        start0 = first_ts + math.ceil((lo - first_ts) / STEP) * STEP     # snap to the 5-minute grid
        n_steps = int((hi - start0) / STEP)
        if n_steps < 0:
            continue
        start = start0 + int(rng.integers(0, n_steps + 1)) * STEP
        return zid, sensor_ids[:sensor_count], start

    raise RuntimeError(f"Could not find a suitable zone/window for {sensor_type}, {duration_min} min.")


def add_ground_truth(records, scenario_id, fault_type, entity_id, zone_id, start_ts, end_ts,
                     expected_detection, detected_by, details):
    records.append({
        "scenario_id": scenario_id, "fault_type": fault_type, "entity_id": entity_id,
        "zone_id": zone_id, "start_ts": start_ts, "end_ts": end_ts,
        "expected_detection": expected_detection, "expected_detected_by": detected_by,
        "details": details,
    })


def window_mask(readings, sensor_id, start_ts, duration_min):
    """Readings from start (included) up to start + duration (NOT included)."""
    end_ts = start_ts + pd.Timedelta(minutes=duration_min)
    return ((readings["sensor_id"] == sensor_id)
            & (readings["reading_ts"] >= start_ts) & (readings["reading_ts"] < end_ts))


def set_sensor_window(readings, sensor_id, start_ts, duration_min, value=None, add=None):
    mask = window_mask(readings, sensor_id, start_ts, duration_min)
    n = int(mask.sum())
    if n == 0:
        raise RuntimeError(f"No readings found for sensor {sensor_id}")
    if value is not None:
        readings.loc[mask, "value"] = value
    if add is not None:
        readings.loc[mask, "value"] = readings.loc[mask, "value"] + add
    return n


def remove_sensor_window(readings, sensor_id, start_ts, duration_min):
    mask = window_mask(readings, sensor_id, start_ts, duration_min)
    n = int(mask.sum())
    if n == 0:
        raise RuntimeError(f"No readings available to remove for {sensor_id}")
    readings.drop(index=readings[mask].index, inplace=True)
    return n


# ---------------------------------------------------------
# MAIN FAULT INJECTION
# ---------------------------------------------------------
def main():
    prepare_clean_backup()
    rng = np.random.default_rng(FAULT_SEED)

    zones = read_csv("zone.csv")
    sensors = read_csv("sensor.csv")
    sensor_map = read_csv("sensor_zone_map.csv")          # kept as text: dates are not touched
    readings = parse_dates(read_csv("sensor_reading.csv"), ["reading_ts"])
    door_events = parse_dates(read_csv("door_event.csv"), ["opened_ts", "closed_ts"])
    lots = read_csv("inventory_lot.csv")
    assignments = parse_dates(read_csv("lot_zone_assignment.csv"), ["stored_from", "stored_until"])
    requirements = read_csv("storage_requirement.csv")

    first_ts, last_ts = readings["reading_ts"].min(), readings["reading_ts"].max()
    used_zones, ground_truth = set(), []

    def pick(sensor_type, count, minutes, preferred=None):
        zid, sids, start = find_zone_window(sensor_type, count, minutes, zones, assignments,
                                            sensor_map, sensors, first_ts, last_ts,
                                            used_zones, rng, preferred)
        used_zones.add(zid)
        return zid, sids, start

    def mins(m):
        return pd.Timedelta(minutes=m)

    # 1. TEMPERATURE HIGH (both temp sensors agree)
    zid, sids, start = pick("TEMP", 2, 35, ["COLD"])
    for sid in sids:
        set_sensor_window(readings, sid, start, 35, value=20.0)
    add_ground_truth(ground_truth, "FAULT-001", "TEMPERATURE_EXCURSION", ",".join(sids), zid,
                     start, start + mins(35), "TEMP_HIGH", "RULE_ENGINE",
                     "Both temperature sensors raised to 20 C for 35 minutes.")

    # 2. HUMIDITY HIGH
    zid, sids, start = pick("HUM", 1, 35)
    set_sensor_window(readings, sids[0], start, 35, value=95.0)
    add_ground_truth(ground_truth, "FAULT-002", "HUMIDITY_EXCURSION", sids[0], zid,
                     start, start + mins(35), "HUM_HIGH", "RULE_ENGINE",
                     "Humidity raised to 95 percent RH for 35 minutes.")

    # 3. DOOR LEFT OPEN (looks like any other door event: normal ID, normal door_id)
    zid, _, start = pick("TEMP", 1, 35)
    end = start + mins(35)
    overlap = door_events[(door_events["zone_id"] == zid)
                          & (door_events["opened_ts"] < end + pd.Timedelta(seconds=10))
                          & (door_events["closed_ts"] > start - pd.Timedelta(seconds=10))]
    n_removed = len(overlap)
    door_events = door_events.drop(index=overlap.index)           # no overlapping openings in one zone
    next_no = int(door_events["door_event_id"].str.extract(r"(\d+)$")[0].astype(int).max()) + 1
    door_id = f"DOR-{next_no:06d}"
    door_events = pd.concat([door_events, pd.DataFrame([{
        "door_event_id": door_id, "zone_id": zid, "door_id": "D1",
        "opened_ts": start, "closed_ts": end, "open_duration_min": 35.0,
        "event_type": "PROLONGED"}])], ignore_index=True)
    add_ground_truth(ground_truth, "FAULT-003", "DOOR_LEFT_OPEN", door_id, zid, start, end,
                     "DOOR_OPEN_LONG", "RULE_ENGINE",
                     f"Door kept open for 35 minutes (replaced {n_removed} normal openings in that window).")

    # 4. TEMPERATURE SENSOR OUTAGE (the partner sensor keeps reporting)
    zid, sids, start = pick("TEMP", 2, 60)
    removed = remove_sensor_window(readings, sids[0], start, 60)
    add_ground_truth(ground_truth, "FAULT-004", "TEMPERATURE_SENSOR_OUTAGE", sids[0], zid,
                     start, start + mins(60), "SENSOR_OUTAGE", "RULE_ENGINE",
                     f"Removed {removed} consecutive temperature readings.")

    # 5. HUMIDITY SENSOR OUTAGE (no partner sensor)
    zid, sids, start = pick("HUM", 1, 45)
    removed = remove_sensor_window(readings, sids[0], start, 45)
    add_ground_truth(ground_truth, "FAULT-005", "HUMIDITY_SENSOR_OUTAGE", sids[0], zid,
                     start, start + mins(45), "SENSOR_OUTAGE", "RULE_ENGINE",
                     f"Removed {removed} consecutive humidity readings.")

    # 6. TEMPERATURE SENSOR DRIFT (only one of the two sensors moves)
    zid, sids, start = pick("TEMP", 2, 70)
    set_sensor_window(readings, sids[0], start, 70, add=3.5)
    add_ground_truth(ground_truth, "FAULT-006", "TEMPERATURE_SENSOR_DRIFT", sids[0], zid,
                     start, start + mins(70), "SENSOR_DRIFT", "RULE_ENGINE",
                     "One paired temperature sensor increased by 3.5 C.")

    # 7. HIGH OCCUPANCY
    zid, sids, start = pick("OCC", 1, 25)
    max_occ = int(zones.loc[zones["zone_id"] == zid, "max_occupancy"].iloc[0])
    set_sensor_window(readings, sids[0], start, 25, value=max_occ + 10)
    add_ground_truth(ground_truth, "FAULT-007", "HIGH_OCCUPANCY", sids[0], zid,
                     start, start + mins(25), "OCCUPANCY_HIGH", "RULE_ENGINE",
                     f"Occupancy increased to {max_occ + 10}.")

    # 8. LOT IN AN INCOMPATIBLE ZONE (data-quality fault, found by the validator)
    check = (assignments.merge(lots[["lot_id", "requirement_id"]], on="lot_id")
             .merge(requirements[["requirement_id", "required_zone_type"]], on="requirement_id")
             .merge(zones[["zone_id", "zone_type"]], on="zone_id"))
    if (check["required_zone_type"] != check["zone_type"]).any():
        raise RuntimeError("Baseline already contains incompatible lot assignments.")
    row = check.sort_values("assignment_id").iloc[int(rng.integers(0, len(check)))]
    wrong = zones[zones["zone_type"] != row["required_zone_type"]]["zone_id"].tolist()
    new_zone = str(rng.choice(wrong))
    m = assignments["assignment_id"] == row["assignment_id"]
    assignments.loc[m, "zone_id"] = new_zone
    assignments.loc[m, "compatible_flag"] = False
    add_ground_truth(ground_truth, "FAULT-008", "INCOMPATIBLE_LOT_ZONE", row["lot_id"], new_zone,
                     None, None, "INCOMPATIBLE_LOT_ZONE", "DATA_VALIDATOR",
                     f"Lot moved from {row['zone_id']} to incompatible zone {new_zone}.")

    # 9. SENSOR MAPPED TO TWO ZONES WITHOUT A RATIONALE (data-quality fault)
    src = sensor_map.iloc[int(rng.integers(0, len(sensor_map)))].copy()
    other = [z for z in zones["zone_id"] if z != src["zone_id"]]
    alt_zone = str(rng.choice(other))
    next_map = int(sensor_map["map_id"].str.extract(r"(\d+)$")[0].astype(int).max()) + 1
    new_map = src.copy()
    new_map["map_id"] = f"MAP-{next_map:06d}"
    new_map["zone_id"] = alt_zone
    new_map["rationale"] = ""
    sensor_map = pd.concat([sensor_map, pd.DataFrame([new_map])], ignore_index=True)
    add_ground_truth(ground_truth, "FAULT-009", "SENSOR_MULTI_ZONE_WITHOUT_RATIONALE",
                     src["sensor_id"], alt_zone, None, None,
                     "SENSOR_MULTI_ZONE_UNJUSTIFIED", "DATA_VALIDATOR",
                     f"Sensor also mapped to {alt_zone}; original zone was {src['zone_id']}.")

    # 10. EXTRA SENSOR OUTAGE, used for the "gap treated as normal" defect.
    #     The rule engine will raise an outage alarm for it; inject_defects.py deletes that alarm later.
    zid, sids, start = pick("TEMP", 2, 45)
    removed = remove_sensor_window(readings, sids[1], start, 45)
    add_ground_truth(ground_truth, "FAULT-010", "READING_GAP_TREATED_AS_NORMAL", sids[1], zid,
                     start, start + mins(45), "SENSOR_OUTAGE_ALARM_MISSING", "DATA_VALIDATOR",
                     f"Removed {removed} readings; the outage alarm is deleted later by inject_defects.py.")

    # ---------------- save (same writer as every other stage) ----------------
    save_table(readings, "sensor_reading", sort_by=["sensor_id", "reading_ts"])
    save_table(door_events, "door_event", sort_by="door_event_id")
    save_table(assignments, "lot_zone_assignment", sort_by="assignment_id")
    save_table(sensor_map, "sensor_zone_map", sort_by="map_id")
    gt = pd.DataFrame(ground_truth, columns=GROUND_TRUTH_COLUMNS)
    save_table(gt, "fault_ground_truth", folder=GT_DIR, sort_by="scenario_id")

    print("\n======================================")
    print("       FAULT INJECTION COMPLETED")
    print("======================================")
    print(f"Random seed         : {FAULT_SEED}")
    print(f"Operational faults  : 7")
    print(f"Data quality faults : 3 (a 4th is added by inject_defects.py)")
    print(f"Ground truth        : {GT_DIR / 'fault_ground_truth.csv'}")
    print("\nScenario summary:")
    for r in ground_truth:
        s = "" if r["start_ts"] is None else str(r["start_ts"])
        print(f"{r['scenario_id']} | {r['fault_type']:38s} | {r['zone_id']} | {s}")
    print("\nNext step: run the rule engine again on this damaged data.")


if __name__ == "__main__":
    main()