# pipeline/generate_readings.py
# Stage 3: make the NORMAL (healthy) sensor readings and door events.
# Reads : zone.csv, sensor.csv, sensor_zone_map.csv
# Writes: sensor_reading.csv, door_event.csv

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import argparse

import numpy as np
import pandas as pd

from config import SEED, READING_INTERVAL_MIN, HUMIDITY
from utils import make_rng, make_id, save_table, load_table
from pipeline.timeline import study_window

# Normal behaviour of the temperature in each room type:
#   (middle value, daily wave size, noise size)
# These are chosen so that healthy readings stay inside even the STRICTEST
# product rule (for example DAIRY needs 2 to 6 degrees in a COLD room).
NORMAL_TEMP = {
    "FROZEN":  (-20.0, 0.4, 0.2),
    "COLD":    (4.5,   0.3, 0.2),
    "AMBIENT": (22.0,  1.5, 0.4),
    "HOT":     (36.0,  1.5, 0.4),
}

# Door openings per day, by room type
DOOR_OPENS_PER_DAY = {"FROZEN": 6, "COLD": 10, "AMBIENT": 14, "HOT": 8}


def bounded_noise(rng, sd, n):
    """Random wiggle that can never go beyond 3 x sd (keeps healthy data healthy)."""
    return np.clip(rng.normal(0, sd, n), -3 * sd, 3 * sd)


def make_readings(sensors, sensor_zone, zones, times, rng):
    """Build one column of values per sensor and stack them into one table."""
    steps = len(times)
    hours = (times.hour + times.minute / 60).to_numpy()
    wave = np.sin(2 * np.pi * (hours - 9) / 24)          # peaks at 15:00, lowest at 03:00
    working = (hours >= 8) & (hours < 18)                # working hours

    zone_type = dict(zip(zones["zone_id"], zones["zone_type"]))
    max_occ = dict(zip(zones["zone_id"], zones["max_occupancy"]))

    sensor_ids, value_blocks = [], []
    for s in sensors.sort_values("sensor_id").itertuples():
        z = sensor_zone[s.sensor_id]
        if s.sensor_type == "TEMP":
            target, amp, sd = NORMAL_TEMP[zone_type[z]]
            offset = float(np.clip(rng.normal(0, 0.1), -0.2, 0.2))      # each sensor reads a tiny bit differently
            values = target + offset + amp * wave + bounded_noise(rng, sd, steps)
        elif s.sensor_type == "HUM":
            offset = float(np.clip(rng.normal(0, 1.0), -2, 2))
            values = HUMIDITY["target"] + offset - 3.0 * wave + bounded_noise(rng, 1.0, steps)
        else:  # OCC: people in the room
            lam = 0.25 * max_occ[z]
            people = rng.poisson(lam, steps)
            values = np.where(working, np.minimum(people, max_occ[z]), 0)
        sensor_ids.append(s.sensor_id)
        value_blocks.append(np.round(values.astype(float), 2))

    n = len(sensor_ids)
    sid_col = np.repeat(sensor_ids, steps)
    ts_col = np.tile(times.to_numpy(), n)
    stamp = times.strftime("%Y%m%dT%H%M%SZ").to_numpy()
    rid = "RDG-" + pd.Series(sid_col) + "-" + pd.Series(np.tile(stamp, n))
    return pd.DataFrame({
        "reading_id": rid,
        "sensor_id": sid_col,
        "reading_ts": ts_col,
        "value": np.concatenate(value_blocks),
        "quality_flag": "GOOD",
    })


def make_door_events(zones, times, rng):
    """Normal door openings: short (20 seconds to 4 minutes), more during the day."""
    steps = len(times)
    grid = times.to_numpy()
    day_slot = (times.hour >= 7) & (times.hour < 19)
    p = np.where(day_slot, 5.0, 1.0)
    p = p / p.sum()
    days = steps * READING_INTERVAL_MIN / 1440

    rows = []
    for z in zones.sort_values("zone_id").itertuples():
        n = int(rng.poisson(DOOR_OPENS_PER_DAY[z.zone_type] * days))
        if n == 0:
            continue
        slots = rng.choice(steps, size=n, p=p)
        starts = grid[slots] + rng.integers(0, READING_INTERVAL_MIN * 60, n).astype("timedelta64[s]")
        starts = np.sort(starts)
        dur = np.clip(rng.lognormal(np.log(90), 0.5, n), 20, 240).astype(int)   # seconds
        door_no = rng.integers(1, 3, n)
        prev_close = None
        for i in range(n):
            start = starts[i]
            if prev_close is not None and start < prev_close + np.timedelta64(10, "s"):
                start = prev_close + np.timedelta64(10, "s")     # never overlap in one zone
            close = start + np.timedelta64(int(dur[i]), "s")
            prev_close = close
            rows.append({
                "zone_id": z.zone_id,
                "door_id": f"D{door_no[i]}",
                "opened_ts": pd.Timestamp(start),
                "closed_ts": pd.Timestamp(close),
                "open_duration_min": round(int(dur[i]) / 60, 2),
                "event_type": "NORMAL",
            })
    doors = pd.DataFrame(rows).sort_values(["zone_id", "opened_ts"], kind="mergesort").reset_index(drop=True)
    doors.insert(0, "door_event_id", [make_id("DOR", i + 1) for i in range(len(doors))])
    return doors


def main(scale_name="starter"):
    zones = load_table("zone")
    sensors = load_table("sensor")
    smap = load_table("sensor_zone_map")
    sensor_zone = dict(zip(smap["sensor_id"], smap["zone_id"]))

    start, end, steps = study_window(scale_name)
    times = pd.date_range(start, periods=steps, freq=f"{READING_INTERVAL_MIN}min")

    readings = make_readings(sensors[sensors["sensor_type"] != "DOOR"], sensor_zone,
                             zones, times, make_rng(SEED + 2))
    doors = make_door_events(zones, times, make_rng(SEED + 3))

    save_table(readings, "sensor_reading", sort_by=["sensor_id", "reading_ts"])
    save_table(doors, "door_event", sort_by="door_event_id")

    # ----- quick self-checks -----
    zt = dict(zip(zones["zone_id"], zones["zone_type"]))
    mo = dict(zip(zones["zone_id"], zones["max_occupancy"]))
    r = readings.merge(sensors[["sensor_id", "sensor_type"]], on="sensor_id")
    r["zone_id"] = r["sensor_id"].map(sensor_zone)
    r["zone_type"] = r["zone_id"].map(zt)
    temp = r[r["sensor_type"] == "TEMP"]
    hum = r[r["sensor_type"] == "HUM"]
    occ = r[r["sensor_type"] == "OCC"]
    z_min = zones.set_index("zone_id")["design_temp_min_c"]
    z_max = zones.set_index("zone_id")["design_temp_max_c"]
    strictest_max = {"FROZEN": -18, "COLD": 6, "AMBIENT": 30, "HOT": 40}

    print(f"Scale: {scale_name}")
    print("Time steps per sensor      :", steps)
    print("Sensors sending readings   :", readings["sensor_id"].nunique())
    print("Readings                   :", len(readings))
    print("Door events                :", len(doors))
    print("Duplicate (sensor, time)   :", readings.duplicated(["sensor_id", "reading_ts"]).sum())
    print("Duplicate reading ids      :", readings["reading_id"].duplicated().sum())
    print("Unknown sensor             :", (~readings["sensor_id"].isin(sensors["sensor_id"])).sum())
    print("Temp outside zone range    :",
          ((temp["value"] < temp["zone_id"].map(z_min)) | (temp["value"] > temp["zone_id"].map(z_max))).sum())
    print("Temp above strictest limit :",
          (temp["value"] > temp["zone_type"].map(strictest_max)).sum())
    print("Humidity outside 30 to 70  :", ((hum["value"] < 30) | (hum["value"] > 70)).sum())
    print("Occupancy above max        :", (occ["value"] > occ["zone_id"].map(mo)).sum())
    print("Temp range by zone type    :")
    for t, g in temp.groupby("zone_type"):
        print(f"   {t:8s} min {g['value'].min():7.2f}   max {g['value'].max():7.2f}")
    print("Door: longest opening (min):", doors["open_duration_min"].max())
    print("Door: close before open    :", (doors["closed_ts"] <= doors["opened_ts"]).sum())
    d = doors.sort_values(["zone_id", "opened_ts"])
    same = d["zone_id"].values[1:] == d["zone_id"].values[:-1]
    print("Door: overlapping in a zone:", int((same & (d["opened_ts"].values[1:] < d["closed_ts"].values[:-1])).sum()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="starter", choices=["starter", "full"])
    args = parser.parse_args()
    main(args.scale)
    