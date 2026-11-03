# pipeline/generate_master.py
# Stage 1: build the physical world.
# Reads: config.py only
# Writes: warehouse.csv, zone.csv, sensor.csv, sensor_zone_map.csv, storage_requirement.csv

import argparse

import pandas as pd

from config import (SEED, get_scale, ZONE_TYPE_MIX, ZONE_BANDS, HUMIDITY,
                    PRODUCTS, SENSORS_PER_ZONE, READING_INTERVAL_MIN, STUDY_START)
from utils import make_rng, wh_id, zone_id, sensor_id, make_id, save_table

CITIES = [
    ("Hyderabad", "Asia/Kolkata"), ("Mumbai", "Asia/Kolkata"),
    ("Chennai", "Asia/Kolkata"), ("Bengaluru", "Asia/Kolkata"),
    ("Pune", "Asia/Kolkata"), ("Delhi", "Asia/Kolkata"),
    ("Kolkata", "Asia/Kolkata"), ("Ahmedabad", "Asia/Kolkata"),
    ("Jaipur", "Asia/Kolkata"), ("Visakhapatnam", "Asia/Kolkata"),
]


def zone_type_list(n_zones, rng):
    """Decide the room type of EVERY zone at once, in fixed proportions.
    Leftover rooms go to the types with the biggest fractional part."""
    raw = {t: round(n_zones * share, 6) for t, share in ZONE_TYPE_MIX.items()}
    counts = {t: int(v) for t, v in raw.items()}                 # round down first
    leftover = n_zones - sum(counts.values())
    by_fraction = sorted(raw, key=lambda t: -(raw[t] - counts[t]))
    for t in by_fraction[:leftover]:
        counts[t] += 1
    types = []
    for t, c in counts.items():
        types += [t] * c
    return [str(t) for t in rng.permutation(types)] 


def build_warehouses(n, rng):
    rows = []
    for i in range(1, n + 1):
        city, tz = CITIES[(i - 1) % len(CITIES)]
        opened = pd.Timestamp("2015-01-01") + pd.Timedelta(days=int(rng.integers(0, 3000)))
        rows.append({
            "warehouse_id": wh_id(i),
            "name": f"{city} Hub",
            "city": city,
            "timezone": tz,
            "status": "ACTIVE",
            "opened_date": opened.strftime("%Y-%m-%d"),
        })
    return pd.DataFrame(rows)


def build_zones(warehouses, zones_per_wh, rng):
    all_types = zone_type_list(len(warehouses) * zones_per_wh, rng)   # one list for all zones
    rows = []
    k = 0
    for w in warehouses.itertuples():
        for n in range(1, zones_per_wh + 1):
            ztype = all_types[k]
            k += 1
            band = ZONE_BANDS[ztype]
            rows.append({
                "zone_id": zone_id(w.warehouse_id, n),
                "warehouse_id": w.warehouse_id,
                "zone_name": f"{ztype.title()} Room {n}",
                "zone_type": ztype,
                "design_temp_min_c": band["min"],
                "design_temp_max_c": band["max"],
                "design_hum_min_pct": HUMIDITY["min"],
                "design_hum_max_pct": HUMIDITY["max"],
                "max_occupancy": int(rng.integers(5, 21)),
                "area_sqm": round(float(rng.uniform(200, 2000)), 1),
                "effective_from": w.opened_date,
                "effective_to": "",
            })
    return pd.DataFrame(rows)


def build_sensors(zones):
    """Each zone gets 2 TEMP, 1 HUM, 1 OCC, 1 DOOR sensor = 5 sensors."""
    sensor_rows, map_rows = [], []
    map_n = 1
    for z in zones.itertuples():
        for stype, count, unit in SENSORS_PER_ZONE:
            for n in range(1, count + 1):
                sid = sensor_id(z.zone_id, stype, n)
                sensor_rows.append({
                    "sensor_id": sid,
                    "sensor_type": stype,
                    "unit": unit,
                    "sample_interval_sec": READING_INTERVAL_MIN * 60,
                    "install_date": "2025-12-01",
                    "status": "ACTIVE",
                    "drift_bias_per_day": "",
                })
                map_rows.append({
                    "map_id": make_id("MAP", map_n),
                    "sensor_id": sid,
                    "zone_id": z.zone_id,
                    "effective_from": STUDY_START,
                    "effective_to": "",
                    "rationale": "",
                })
                map_n += 1
    return pd.DataFrame(sensor_rows), pd.DataFrame(map_rows)


def build_requirements():
    rows = []
    for rid, product, ztype, tmin, tmax, max_exc, max_door, _weight in PRODUCTS:
        rows.append({
            "requirement_id": rid,
            "product_category": product,
            "required_zone_type": ztype,
            "temp_min_c": tmin,
            "temp_max_c": tmax,
            "hum_min_pct": HUMIDITY["min"],
            "hum_max_pct": HUMIDITY["max"],
            "max_excursion_min": max_exc,
            "max_door_open_min": max_door,
            "effective_from": "2025-01-01",
            "effective_to": "",
        })
    return pd.DataFrame(rows)


def main(scale_name="starter"):
    size = get_scale(scale_name)
    rng = make_rng(SEED)

    warehouses = build_warehouses(size["warehouses"], rng)
    zones = build_zones(warehouses, size["zones_per_wh"], rng)
    sensors, sensor_map = build_sensors(zones)
    requirements = build_requirements()

    save_table(warehouses, "warehouse", sort_by="warehouse_id")
    save_table(zones, "zone", sort_by="zone_id")
    save_table(sensors, "sensor", sort_by="sensor_id")
    save_table(sensor_map, "sensor_zone_map", sort_by="map_id")
    save_table(requirements, "storage_requirement", sort_by="requirement_id")

    # ----- quick self-checks -----
    print(f"Scale: {scale_name}")
    print("Warehouses  :", len(warehouses))
    print("Zones       :", len(zones))
    print("Sensors     :", len(sensors))
    print("Sensor maps :", len(sensor_map))
    print("Requirements:", len(requirements))
    print("Zone types  :", {str(k): int(v) for k, v in zones["zone_type"].value_counts().items()})
    print("Zones with unknown warehouse :",
          (~zones["warehouse_id"].isin(warehouses["warehouse_id"])).sum())
    print("Maps with unknown sensor     :",
          (~sensor_map["sensor_id"].isin(sensors["sensor_id"])).sum())
    print("Maps with unknown zone       :",
          (~sensor_map["zone_id"].isin(zones["zone_id"])).sum())
    print("Duplicate sensor ids         :", sensors["sensor_id"].duplicated().sum())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="starter", choices=["starter", "full"])
    args = parser.parse_args()
    main(args.scale)