# pipeline/rule_engine.py
# Stage 4: the DETECTOR. It reads the data tables and decides where alarms belong.
# It never opens the ground truth file.
#
# Reads : sensor_reading, sensor, sensor_zone_map, zone, door_event,
#         inventory_lot, lot_zone_assignment, storage_requirement
# Writes: sensor_gap, alarm, alarm_status_history, alarm_affected_lot,
#         inspection, remediation

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import argparse

import numpy as np
import pandas as pd

from config import SEED, READING_INTERVAL_MIN, OUTAGE_MULTIPLIER
from utils import make_rng, make_id, save_table, load_table

# ---------- The detection rules (all in one place) ----------
INTERVAL = READING_INTERVAL_MIN            # minutes between readings
STEP = np.timedelta64(INTERVAL, "m")
ALARM_MIN_MINUTES = 10                     # out of range this long (or longer) = alarm
DRIFT_DIFF_C = 1.0                         # two temp sensors in a room differ by more than this ...
DRIFT_MIN_MINUTES = 60                     # ... for this long = drift
RESULT_FACTOR = 3                          # up to 3 x the limit = CONDITIONAL, beyond = FAIL

REMEDIATION_FOR = {"PASS": "RELEASE", "CONDITIONAL": "RELOCATE_LOT", "FAIL": "DISCARD_LOT"}
OWNER_FOR = {"RELEASE": "QUALITY_ENGINEER", "RELOCATE_LOT": "PRODUCTION_PLANNER",
             "DISCARD_LOT": "QUALITY_ENGINEER"}


# ---------- small helpers ----------
def run_bounds(flags):
    """Find runs of consecutive True values. Returns (starts, ends), ends inclusive."""
    padded = np.concatenate(([0], flags.astype(np.int8), [0]))
    d = np.diff(padded)
    return np.where(d == 1)[0], np.where(d == -1)[0] - 1


def longest_run(flags):
    s, e = run_bounds(flags)
    return 0 if len(s) == 0 else int((e - s + 1).max())


def zone_mean(A):
    """Average of the sensors that reported (ignores silent ones)."""
    count = (~np.isnan(A)).sum(axis=0)
    total = np.nansum(A, axis=0)
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def agreed_flags(A, low, high):
    """A reading time counts as too high / too low only if ALL reporting sensors agree."""
    avail = ~np.isnan(A)
    n = avail.sum(axis=0)
    with np.errstate(invalid="ignore"):
        hi = ((A > high) & avail).sum(axis=0)
        lo = ((A < low) & avail).sum(axis=0)
    return (n > 0) & (hi == n), (n > 0) & (lo == n)


def severity(duration_min, deviation):
    if duration_min >= 60 or deviation >= 5:
        return "CRITICAL"
    if duration_min >= 30 or deviation >= 3:
        return "HIGH"
    if duration_min >= 20 or deviation >= 1.5:
        return "MEDIUM"
    return "LOW"


def result_for(longest, limit):
    if longest <= limit:
        return "PASS"
    if longest <= RESULT_FACTOR * limit:
        return "CONDITIONAL"
    return "FAIL"


# ---------- Stage A: find problems ----------
def find_candidates(readings, sensors, smap, zones, doors, reqs):
    grid0 = readings["reading_ts"].min().to_datetime64()
    last = readings["reading_ts"].max().to_datetime64()
    T = int((last - grid0) / STEP) + 1
    grid = grid0 + np.arange(T) * STEP

    # first mapping of each sensor decides its zone (a sensor in two zones is a data-quality issue)
    smap = smap.sort_values(["sensor_id", "map_id"]).drop_duplicates("sensor_id", keep="first")
    sensor_zone = dict(zip(smap["sensor_id"], smap["zone_id"]))
    sensor_type = dict(zip(sensors["sensor_id"], sensors["sensor_type"]))

    # one array per sensor on the full time grid; NaN where the sensor was silent
    arrs = {}
    for sid, g in readings.groupby("sensor_id"):
        idx = ((g["reading_ts"].values - grid0) / STEP).astype(int)
        a = np.full(T, np.nan)
        a[idx] = g["value"].values
        arrs[sid] = a

    zone_sensors = {}
    for sid in sorted(arrs):
        zone_sensors.setdefault(sensor_zone[sid], {}).setdefault(sensor_type[sid], []).append(sid)

    # alarm limits per room type = the strictest product rule that can be stored there
    band = {}
    for t, g in reqs.groupby("required_zone_type"):
        band[t] = {"tmin": g["temp_min_c"].max(), "tmax": g["temp_max_c"].min(),
                   "door": g["max_door_open_min"].min()}
    zrow = zones.set_index("zone_id")

    min_steps = ALARM_MIN_MINUTES // INTERVAL
    cands, gaps = [], []
    series = {"TEMP": {}, "HUM": {}}

    def add(zone, sensor, code, s, e, peak, thr, dev, kind, stype=""):
        cands.append({"zone_id": zone, "sensor_id": sensor, "rule_code": code,
                      "start": grid0 + s * STEP, "end": grid0 + (e + 1) * STEP,
                      "peak": float(peak), "threshold": float(thr), "dev": float(dev),
                      "kind": kind, "sensor_type": stype})

    for zone in sorted(zone_sensors):
        z = zrow.loc[zone]
        b = band[z["zone_type"]]
        types = zone_sensors[zone]

        # RULE 1: temperature too high / too low (all temp sensors must agree)
        if "TEMP" in types:
            A = np.vstack([arrs[s] for s in types["TEMP"]])
            mean = zone_mean(A)
            series["TEMP"][zone] = mean
            hi, lo = agreed_flags(A, b["tmin"], b["tmax"])
            for flags, code in ((hi, "TEMP_HIGH"), (lo, "TEMP_LOW")):
                s_, e_ = run_bounds(flags)
                for s, e in zip(s_, e_):
                    if e - s + 1 >= min_steps:
                        seg = mean[s:e + 1]
                        peak = np.nanmax(seg) if code == "TEMP_HIGH" else np.nanmin(seg)
                        thr = b["tmax"] if code == "TEMP_HIGH" else b["tmin"]
                        add(zone, "", code, s, e, peak, thr, abs(peak - thr), "TEMP")

            # RULE 2: drift = the two temp sensors in one room disagree for a long time
            if len(types["TEMP"]) == 2:
                a, bb = types["TEMP"]
                diff = arrs[a] - arrs[bb]
                with np.errstate(invalid="ignore"):
                    flag = np.abs(diff) > DRIFT_DIFF_C
                s_, e_ = run_bounds(flag)
                usual_a = np.nanmedian(arrs[a])                 # each sensor's own normal level
                usual_b = np.nanmedian(arrs[bb])
                for s, e in zip(s_, e_):
                    if e - s + 1 >= DRIFT_MIN_MINUTES // INTERVAL:
                        da = abs(np.nanmean(arrs[a][s:e + 1]) - usual_a)
                        db = abs(np.nanmean(arrs[bb][s:e + 1]) - usual_b)
                        bad = a if da > db else bb              # the one that moved away from its own normal
                        add(zone, bad, "SENSOR_DRIFT", s, e, np.nanmax(np.abs(diff[s:e + 1])),
                            DRIFT_DIFF_C, 0, "DRIFT", "TEMP")

        # RULE 3: humidity out of the room's design range
        if "HUM" in types:
            A = np.vstack([arrs[s] for s in types["HUM"]])
            series["HUM"][zone] = zone_mean(A)
            hi, lo = agreed_flags(A, z["design_hum_min_pct"], z["design_hum_max_pct"])
            for flags, code in ((hi, "HUM_HIGH"), (lo, "HUM_LOW")):
                s_, e_ = run_bounds(flags)
                for s, e in zip(s_, e_):
                    if e - s + 1 >= min_steps:
                        seg = series["HUM"][zone][s:e + 1]
                        peak = np.nanmax(seg) if code == "HUM_HIGH" else np.nanmin(seg)
                        thr = z["design_hum_max_pct"] if code == "HUM_HIGH" else z["design_hum_min_pct"]
                        add(zone, "", code, s, e, peak, thr, 0, "HUM")

        # RULE 4: too many people in the room
        if "OCC" in types:
            A = np.vstack([arrs[s] for s in types["OCC"]])
            mean = zone_mean(A)
            with np.errstate(invalid="ignore"):
                flags = mean > z["max_occupancy"]
            s_, e_ = run_bounds(flags)
            for s, e in zip(s_, e_):
                if e - s + 1 >= min_steps:
                    add(zone, "", "OCCUPANCY_HIGH", s, e, np.nanmax(mean[s:e + 1]),
                        z["max_occupancy"], 0, "OCC")

    # RULE 5: sensor silent too long (gap) -> gap record + outage alarm
    gap_n = 1
    for sid in sorted(arrs):
        have = np.where(~np.isnan(arrs[sid]))[0]
        padded = np.concatenate(([-1], have, [T]))
        for prev, nxt in zip(padded[:-1], padded[1:]):
            if nxt - prev > OUTAGE_MULTIPLIER:
                gs, ge = grid0 + (prev + 1) * STEP, grid0 + nxt * STEP
                gaps.append({"gap_id": make_id("GAP", gap_n), "sensor_id": sid,
                             "gap_start": pd.Timestamp(gs), "gap_end": pd.Timestamp(ge),
                             "gap_minutes": (nxt - prev - 1) * INTERVAL, "gap_cause": "UNKNOWN"})
                gap_n += 1
                add(sensor_zone[sid], sid, "SENSOR_OUTAGE", prev + 1, nxt - 1,
                    (nxt - prev - 1) * INTERVAL, OUTAGE_MULTIPLIER * INTERVAL, 0,
                    "GAP", sensor_type[sid])

    # RULE 6: a door open too long
    for d in doors.itertuples():
        limit = band[zrow.loc[d.zone_id, "zone_type"]]["door"]
        if d.open_duration_min > limit:
            cands.append({"zone_id": d.zone_id, "sensor_id": "", "rule_code": "DOOR_OPEN_LONG",
                          "start": d.opened_ts.to_datetime64(), "end": d.closed_ts.to_datetime64(),
                          "peak": float(d.open_duration_min), "threshold": float(limit),
                          "dev": 0.0, "kind": "DOOR", "sensor_type": ""})

    ctx = {"grid0": grid0, "grid": grid, "arrs": arrs, "series": series,
           "zone_sensors": zone_sensors, "T": T}
    return cands, pd.DataFrame(gaps), ctx


# ---------- Stage B: judge each (alarm, lot) pair ----------
def judge(alarm, lot, ov_s, ov_e, ctx):
    """Return (exposure_min, longest_min, limit_min) for one lot hit by one alarm."""
    code, grid = alarm["rule_code"], ctx["grid"]
    overlap_min = (ov_e - ov_s) / np.timedelta64(1, "m")

    if code in ("TEMP_HIGH", "TEMP_LOW", "HUM_HIGH", "HUM_LOW"):
        kind = "TEMP" if code.startswith("TEMP") else "HUM"
        lo, hi = ((lot["temp_min_c"], lot["temp_max_c"]) if kind == "TEMP"
                  else (lot["hum_min_pct"], lot["hum_max_pct"]))
        v = ctx["series"][kind][alarm["zone_id"]]
        i0, i1 = np.searchsorted(grid, ov_s), np.searchsorted(grid, ov_e)
        with np.errstate(invalid="ignore"):
            out = (v[i0:i1] < lo) | (v[i0:i1] > hi)
        exposure = min(int(out.sum()) * INTERVAL, overlap_min)       # never more than the lot's real overlap
        longest = min(longest_run(out) * INTERVAL, overlap_min)
        return exposure, longest, lot["max_excursion_min"]

    if code == "DOOR_OPEN_LONG":
        limit = lot["max_door_open_min"]
        return overlap_min, overlap_min, limit        # only the minutes the door was open while THIS lot was there

    if code == "SENSOR_OUTAGE" and alarm["sensor_type"] in ("TEMP", "HUM"):
        partners = [s for s in ctx["zone_sensors"][alarm["zone_id"]][alarm["sensor_type"]]
                    if s != alarm["sensor_id"]]
        i0, i1 = np.searchsorted(grid, ov_s), np.searchsorted(grid, ov_e)
        covered = bool(partners) and all(not np.isnan(ctx["arrs"][p][i0:i1]).any() for p in partners)
        limit = lot["max_excursion_min"]
        if not covered:
            return (overlap_min if overlap_min > limit else 0), overlap_min, limit
        return 0, 0, limit

    return 0, 0, lot["max_excursion_min"]        # drift, occupancy: no direct lot damage


def main(scale_name="starter"):
    rng = make_rng(SEED + 4)

    readings = load_table("sensor_reading", dates=["reading_ts"])
    sensors = load_table("sensor")
    smap = load_table("sensor_zone_map")
    zones = load_table("zone")
    doors = load_table("door_event", dates=["opened_ts", "closed_ts"])
    reqs = load_table("storage_requirement")
    lots = load_table("inventory_lot")
    asg = load_table("lot_zone_assignment", dates=["stored_from", "stored_until"])

    cands, gaps, ctx = find_candidates(readings, sensors, smap, zones, doors, reqs)
    cutoff = ctx["grid"][-1] + STEP                      # "now" = end of the study window

    # ----- number the alarms in a fixed order -----
    cands.sort(key=lambda c: (c["start"], c["zone_id"], c["rule_code"], c["sensor_id"]))
    alarms = []
    for n, c in enumerate(cands, start=1):
        dur = float((c["end"] - c["start"]) / np.timedelta64(1, "m"))
        alarms.append({"alarm_id": make_id("ALM", n), "zone_id": c["zone_id"],
                       "sensor_id": c["sensor_id"], "rule_code": c["rule_code"],
                       "severity": severity(dur, c["dev"] if c["kind"] == "TEMP" else 0),
                       "start": c["start"], "end": c["end"], "peak": round(c["peak"], 2),
                       "threshold": round(c["threshold"], 2), "duration_min": round(dur, 2),
                       "sensor_type": c["sensor_type"]})

    # ----- which lots were hit? (same zone AND time overlap) -----
    lot_info = lots.merge(reqs, on="requirement_id").set_index("lot_id")
    asg_by_zone = {z: g.sort_values("assignment_id") for z, g in asg.groupby("zone_id")}

    link_rows = []
    for a in alarms:
        g = asg_by_zone.get(a["zone_id"])
        if g is None:
            continue
        hit = g[(g["stored_from"].values < a["end"]) & (g["stored_until"].values > a["start"])]
        for r in hit.itertuples():
            ov_s = max(a["start"], r.stored_from.to_datetime64())
            ov_e = min(a["end"], r.stored_until.to_datetime64())
            exposure, longest, limit = judge(a, lot_info.loc[r.lot_id], ov_s, ov_e, ctx)
            link_rows.append({"alarm_id": a["alarm_id"], "lot_id": r.lot_id,
                              "overlap_start": pd.Timestamp(ov_s), "overlap_end": pd.Timestamp(ov_e),
                              "overlap_minutes": round(float((ov_e - ov_s) / np.timedelta64(1, "m")), 2),
                              "exposure_min": float(exposure),
                              "breaches_requirement": bool(longest > limit),
                              "longest_min": float(longest), "limit_min": float(limit)})
    link_cols = ["alarm_id", "lot_id", "overlap_start", "overlap_end", "overlap_minutes",
                 "exposure_min", "breaches_requirement", "longest_min", "limit_min"]
    links = pd.DataFrame(link_rows, columns=link_cols)
    links_by_alarm = {k: v for k, v in links.groupby("alarm_id")}

    # ----- timeline: alarm -> inspection -> remediation (nothing after "now") -----
    def mins(x):
        return np.timedelta64(int(round(x * 60)), "s")

    history, inspections, remeds = [], [], []
    counters = {"h": 1, "i": 1, "r": 1}

    def hist(alarm_id, frm, to, ts, role):
        history.append({"history_id": make_id("AST", counters["h"]), "alarm_id": alarm_id,
                        "from_status": frm, "to_status": to,
                        "changed_ts": pd.Timestamp(ts), "changed_by_role": role})
        counters["h"] += 1

    final_status = {}
    for a in alarms:
        aid = a["alarm_id"]
        t_open = min(a["end"], cutoff)
        hist(aid, "", "OPEN", t_open, "SYSTEM")
        status = "OPEN"

        t_ack = t_open + mins(rng.uniform(5, 30))
        if t_ack > cutoff:
            final_status[aid] = status
            continue
        hist(aid, status, "ACKNOWLEDGED", t_ack, "PLANT_OPERATOR")
        status = "ACKNOWLEDGED"

        mine = links_by_alarm.get(aid)
        todo = mine[mine["exposure_min"] > 0].sort_values("lot_id") if mine is not None else None

        if todo is None or len(todo) == 0:                       # nothing to inspect: just close it
            t_close = t_ack + mins(rng.uniform(10, 120))
            if t_close <= cutoff:
                hist(aid, status, "CLOSED", t_close, "PLANT_OPERATOR")
                status = "CLOSED"
            final_status[aid] = status
            continue

        t = t_ack + mins(rng.uniform(15, 90))
        if t > cutoff:
            final_status[aid] = status
            continue
        hist(aid, status, "UNDER_INSPECTION", t, "QUALITY_ENGINEER")
        status = "UNDER_INSPECTION"

        action_times, n_inspected = [], 0
        for r in todo.itertuples():
            t = t + mins(rng.uniform(10, 45))
            if t > cutoff:
                break
            result = result_for(r.longest_min, r.limit_min)
            if a["rule_code"] == "SENSOR_OUTAGE" and result == "FAIL":
                result = "CONDITIONAL"      # a silent sensor is not proof of damage: re-check, do not discard
            ins_id = make_id("INS", counters["i"])
            counters["i"] += 1
            n_inspected += 1
            inspections.append({
                "inspection_id": ins_id, "alarm_id": aid, "lot_id": r.lot_id,
                "inspector_role": "QUALITY_ENGINEER", "inspected_ts": pd.Timestamp(t),
                "result": result,
                "notes": f"exposure {r.exposure_min:.0f} min; longest {r.longest_min:.0f} min; limit {r.limit_min:.0f} min"})
            t_action = t + mins(rng.uniform(30, 600))
            if t_action <= cutoff:
                action = REMEDIATION_FOR[result]
                lot = lot_info.loc[r.lot_id]
                units = 0 if action == "RELEASE" else int(lot["quantity_units"])
                remeds.append({
                    "remediation_id": make_id("REM", counters["r"]), "inspection_id": ins_id,
                    "lot_id": r.lot_id, "action_type": action, "action_ts": pd.Timestamp(t_action),
                    "owner_role": OWNER_FOR[action], "units_affected": units,
                    "value_at_risk": round(units * float(lot["unit_value"]), 2), "status": "DONE"})
                counters["r"] += 1
                action_times.append(t_action)

        if n_inspected == len(todo) and len(action_times) == n_inspected:
            t_rem = max(action_times)
            hist(aid, status, "REMEDIATED", t_rem, "QUALITY_ENGINEER")
            status = "REMEDIATED"
            t_close = t_rem + mins(rng.uniform(10, 60))
            if t_close <= cutoff:
                hist(aid, status, "CLOSED", t_close, "PLANT_OPERATOR")
                status = "CLOSED"
        final_status[aid] = status

    # ----- build and save the tables -----
    alarm_cols = ["alarm_id", "zone_id", "sensor_id", "rule_code", "severity", "start_ts", "end_ts",
                  "peak_value", "threshold_value", "duration_min", "status"]
    alarm_df = pd.DataFrame([{
        "alarm_id": a["alarm_id"], "zone_id": a["zone_id"], "sensor_id": a["sensor_id"],
        "rule_code": a["rule_code"], "severity": a["severity"],
        "start_ts": pd.Timestamp(a["start"]), "end_ts": pd.Timestamp(a["end"]),
        "peak_value": a["peak"], "threshold_value": a["threshold"],
        "duration_min": a["duration_min"], "status": final_status[a["alarm_id"]]} for a in alarms],
        columns=alarm_cols)
    hist_df = pd.DataFrame(history, columns=["history_id", "alarm_id", "from_status", "to_status",
                                             "changed_ts", "changed_by_role"])
    ins_df = pd.DataFrame(inspections, columns=["inspection_id", "alarm_id", "lot_id", "inspector_role",
                                                "inspected_ts", "result", "notes"])
    rem_df = pd.DataFrame(remeds, columns=["remediation_id", "inspection_id", "lot_id", "action_type",
                                           "action_ts", "owner_role", "units_affected",
                                           "value_at_risk", "status"])
    gap_df = gaps if len(gaps) else pd.DataFrame(
        columns=["gap_id", "sensor_id", "gap_start", "gap_end", "gap_minutes", "gap_cause"])
    link_out = links.drop(columns=["longest_min", "limit_min"])

    save_table(gap_df, "sensor_gap", sort_by="gap_id")
    save_table(alarm_df, "alarm", sort_by="alarm_id")
    save_table(hist_df, "alarm_status_history", sort_by="history_id")
    save_table(link_out, "alarm_affected_lot", sort_by=["alarm_id", "lot_id"])
    save_table(ins_df, "inspection", sort_by="inspection_id")
    save_table(rem_df, "remediation", sort_by="remediation_id")

    # ----- summary -----
    print(f"Scale: {scale_name}")
    print("Sensor gaps            :", len(gap_df))
    print("Alarms                 :", len(alarm_df))
    if len(alarm_df):
        print("  by rule              :", alarm_df["rule_code"].value_counts().to_dict())
        print("  by severity          :", alarm_df["severity"].value_counts().to_dict())
        print("  by status            :", alarm_df["status"].value_counts().to_dict())
    print("Alarm-lot links        :", len(link_out),
          "| of which breach:", int(link_out["breaches_requirement"].sum()) if len(link_out) else 0)
    print("Inspections            :", len(ins_df),
          ins_df["result"].value_counts().to_dict() if len(ins_df) else "")
    print("Remediations           :", len(rem_df),
          rem_df["action_type"].value_counts().to_dict() if len(rem_df) else "")
    print("Value at risk          :", round(float(rem_df["value_at_risk"].sum()), 2) if len(rem_df) else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="starter", choices=["starter", "full"])
    args = parser.parse_args()
    main(args.scale)