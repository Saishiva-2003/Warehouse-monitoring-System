
from pathlib import Path


SEED = 20261022   # same seed = same "random" data every run

SCALES = {
    "starter": {"warehouses": 2,  "zones_per_wh": 5,  "readings": 20_000,    "lots": 200},
    "full":    {"warehouses": 10, "zones_per_wh": 10, "readings": 1_000_000, "lots": 10_000},
}


ZONE_TYPE_MIX = {"FROZEN": 0.10, "COLD": 0.30, "AMBIENT": 0.45, "HOT": 0.15}


ZONE_BANDS = {
    "FROZEN":  {"min": -25, "max": -15, "target": -20},
    "COLD":    {"min": 2,   "max": 8,   "target": 5},
    "AMBIENT": {"min": 15,  "max": 30,  "target": 22},
    "HOT":     {"min": 30,  "max": 45,  "target": 36},
}

# Humidity (percent) safe range and normal middle, same for all rooms for now
HUMIDITY = {"min": 30, "max": 70, "target": 50}

# ---------- Product rules (StorageRequirement) ----------
# (requirement_id, product, room type, min temp, max temp,
#  max bad minutes allowed, max door-open minutes, how common)
PRODUCTS = [
    ("REQ-0001", "VACCINE",     "COLD",     2,   8,  10,  5, 0.05),
    ("REQ-0002", "DAIRY",       "COLD",     2,   6,  20,  8, 0.15),
    ("REQ-0003", "ICE_CREAM",   "FROZEN", -25, -18, 15,  5, 0.08),
    ("REQ-0004", "FROZEN_MEAT", "FROZEN", -25, -18, 20,  6, 0.07),
    ("REQ-0005", "BISCUITS",    "AMBIENT", 15,  30, 120, 15, 0.25),
    ("REQ-0006", "BEVERAGES",   "AMBIENT", 15,  30, 90,  15, 0.20),
    ("REQ-0007", "PAINT",       "HOT",     30,  40, 180, 20, 0.12),
    ("REQ-0008", "CHEMICALS",   "HOT",     30,  42, 120, 15, 0.08),
]

# ---------- Sensors in every zone ----------
# (sensor type, how many per zone, unit)
SENSORS_PER_ZONE = [
    ("TEMP", 2, "C"),
    ("HUM",  1, "PCT_RH"),
    ("OCC",  1, "COUNT"),
    ("DOOR", 1, "BOOL"),
]

# ---------- Time rules ----------
READING_INTERVAL_MIN = 5    # one reading every 5 minutes
OUTAGE_MULTIPLIER = 3       # silence longer than 3 x interval counts as an outage
STUDY_START = "2026-01-01 00:00:00"

# ---------- Folders ----------
ROOT = Path(__file__).parent
OUTPUT = ROOT / "output"
DATA_DIR = OUTPUT / "data"
GT_DIR = OUTPUT / "ground_truth"
REPORT_DIR = OUTPUT / "reports"
JSON_DIR = OUTPUT / "json"
SQL_DIR = OUTPUT / "sql"


def get_scale(name):
    """Return the size settings for 'starter' or 'full'."""
    return SCALES[name]


if __name__ == "__main__":
    # Runs only when you type: python config.py
    print("Seed:", SEED)
    print("Starter scale:", SCALES["starter"])
    print("Zone mix adds up to:", sum(ZONE_TYPE_MIX.values()))
    print("Product weights add up to:", round(sum(p[7] for p in PRODUCTS), 2))
    print("Data folder:", DATA_DIR)