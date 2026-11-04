"""Print a short summary of the generated dataset: warehouses, zones, sensors and readings.

Run from the project root after run_all.py:
    python -m pipeline.show_summary
"""
import sys
from pathlib import Path

import pandas as pd

DATA = Path("output") / "data"


def main() -> int:
    if not (DATA / "sensor_reading.csv").exists():
        print("output/data not found. Run: python run_all.py --seed 20261022 --scale full")
        return 1

    warehouse = pd.read_csv(DATA / "warehouse.csv")
    zone = pd.read_csv(DATA / "zone.csv")
    sensor = pd.read_csv(DATA / "sensor.csv")
    readings = pd.read_csv(DATA / "sensor_reading.csv")
    doors = pd.read_csv(DATA / "door_event.csv")
    lots = pd.read_csv(DATA / "inventory_lot.csv")

    print("DATASET SUMMARY")
    print("-" * 40)
    print(f"Warehouses      : {len(warehouse):>9,}")
    print(f"Zones           : {len(zone):>9,}")
    print(f"Sensors         : {len(sensor):>9,}")
    print(f"Readings        : {len(readings):>9,}")
    print(f"Door events     : {len(doors):>9,}")
    print(f"Inventory lots  : {len(lots):>9,}")

    for col in ("zone_type", "sensor_type"):
        src = zone if col in zone.columns else sensor if col in sensor.columns else None
        if src is not None:
            print(f"\n{col} counts:")
            for k, v in src[col].value_counts().items():
                print(f"  {k:<14}{v:>6,}")

    ts = pd.to_datetime(readings["reading_ts"])
    print("\nREADINGS")
    print("-" * 40)
    print(f"First reading   : {ts.min()}")
    print(f"Last reading    : {ts.max()}")
    print(f"Sensors reporting: {readings['sensor_id'].nunique():,}")
    if "quality_flag" in readings.columns:
        print("Quality flags   :", {k: int(v) for k, v in readings["quality_flag"].value_counts().items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())