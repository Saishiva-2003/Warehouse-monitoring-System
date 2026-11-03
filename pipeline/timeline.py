# pipeline/timeline.py
# Works out how long the study window is, from the number of readings wanted.
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta

from config import get_scale, SENSORS_PER_ZONE, READING_INTERVAL_MIN, STUDY_START


def study_window(scale_name):
    """Return (start, end, steps).
    steps = how many readings each sensor sends during the study window."""
    size = get_scale(scale_name)
    n_zones = size["warehouses"] * size["zones_per_wh"]
    per_zone = sum(count for stype, count, unit in SENSORS_PER_ZONE if stype != "DOOR")
    n_sensors = n_zones * per_zone                       # sensors that send readings
    steps = max(1, round(size["readings"] / n_sensors))
    start = datetime.strptime(STUDY_START, "%Y-%m-%d %H:%M:%S")
    end = start + timedelta(minutes=READING_INTERVAL_MIN * steps)
    return start, end, steps


if __name__ == "__main__":
    for name in ["starter", "full"]:
        s, e, n = study_window(name)
        print(name, "| start:", s, "| end:", e, "| readings per sensor:", n)