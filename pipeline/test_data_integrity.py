
from pathlib import Path

import pandas as pd


DATA_DIR = Path("output/data")
CLEAN_DATA_DIR = Path("output/clean_data")

FILES = {
    "warehouse": "warehouse.csv",
    "zone": "zone.csv",
    "sensor": "sensor.csv",
    "sensor_zone_map": "sensor_zone_map.csv",
    "sensor_reading": "sensor_reading.csv",
    "inventory_lot": "inventory_lot.csv",
    "lot_zone_assignment": "lot_zone_assignment.csv",
    "storage_requirement": "storage_requirement.csv",
    "door_event": "door_event.csv",
    "alarm": "alarm.csv",
    "alarm_affected_lot": "alarm_affected_lot.csv",
    "alarm_status_history": "alarm_status_history.csv",
    "inspection": "inspection.csv",
    "remediation": "remediation.csv",
    "sensor_gap": "sensor_gap.csv",
}


def load_data():
    data = {}

    for name, filename in FILES.items():
        path = DATA_DIR / filename

        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

        data[name] = pd.read_csv(path)

    return data


def check_primary_keys(data):
    primary_keys = {
        "warehouse": "warehouse_id",
        "zone": "zone_id",
        "sensor": "sensor_id",
        "sensor_zone_map": "map_id",
        "sensor_reading": "reading_id",
        "inventory_lot": "lot_id",
        "lot_zone_assignment": "assignment_id",
        "storage_requirement": "requirement_id",
        "door_event": "door_event_id",
        "alarm": "alarm_id",
        "alarm_affected_lot": None,
        "alarm_status_history": "history_id",
        "inspection": "inspection_id",
        "remediation": "remediation_id",
        "sensor_gap": "gap_id",
    }

    for table, column in primary_keys.items():
        if column is None:
            continue

        df = data[table]

        duplicates = df[column].duplicated().sum()
        nulls = df[column].isna().sum()

        print(
            f"{table}: "
            f"duplicate_keys={duplicates}, "
            f"null_keys={nulls}"
        )


def check_mandatory_nulls(data):
    mandatory_columns = {
        "warehouse": ["warehouse_id", "name"],
        "zone": ["zone_id", "warehouse_id"],
        "sensor": ["sensor_id", "sensor_type"],
        "sensor_zone_map": ["map_id", "sensor_id", "zone_id"],
        "sensor_reading": [
            "reading_id", "sensor_id", "reading_ts", "value"
        ],
        "inventory_lot": ["lot_id", "requirement_id"],
        "lot_zone_assignment": ["assignment_id", "lot_id", "zone_id"],
        "storage_requirement": ["requirement_id"],
        "door_event": ["door_event_id", "zone_id"],
        "alarm": ["alarm_id", "zone_id", "rule_code"],
        "alarm_affected_lot": ["alarm_id", "lot_id"],
        "alarm_status_history": ["history_id", "alarm_id"],
        "inspection": ["inspection_id", "alarm_id", "lot_id"],
        "remediation": ["remediation_id", "inspection_id", "lot_id"],
        "sensor_gap": ["gap_id", "sensor_id"],
    }

    for table, columns in mandatory_columns.items():
        df = data[table]

        for column in columns:
            count = df[column].isna().sum()

            if count > 0:
                print(
                    f"NULL FINDING: {table}.{column} "
                    f"contains {count} null values"
                )


def check_foreign_keys(data):
    relationships = [
        ("zone", "warehouse_id", "warehouse", "warehouse_id"),
        ("sensor_zone_map", "sensor_id", "sensor", "sensor_id"),
        ("sensor_zone_map", "zone_id", "zone", "zone_id"),
        ("sensor_reading", "sensor_id", "sensor", "sensor_id"),
        ("inventory_lot", "requirement_id", "storage_requirement", "requirement_id"),
        ("lot_zone_assignment", "lot_id", "inventory_lot", "lot_id"),
        ("lot_zone_assignment", "zone_id", "zone", "zone_id"),
        ("alarm", "zone_id", "zone", "zone_id"),
        ("alarm", "sensor_id", "sensor", "sensor_id"),
        ("alarm_affected_lot", "alarm_id", "alarm", "alarm_id"),
        ("alarm_affected_lot", "lot_id", "inventory_lot", "lot_id"),
        ("alarm_status_history", "alarm_id", "alarm", "alarm_id"),
        ("inspection", "alarm_id", "alarm", "alarm_id"),
        ("inspection", "lot_id", "inventory_lot", "lot_id"),
        ("remediation", "inspection_id", "inspection", "inspection_id"),
        ("remediation", "lot_id", "inventory_lot", "lot_id"),
        ("sensor_gap", "sensor_id", "sensor", "sensor_id"),
    ]

    for child, child_col, parent, parent_col in relationships:
        child_values = set(data[child][child_col].dropna())
        parent_values = set(data[parent][parent_col].dropna())

        invalid = child_values - parent_values

        print(
            f"{child}.{child_col} -> "
            f"{parent}.{parent_col}: "
            f"invalid_references={len(invalid)}"
        )


def check_sensor_values(data):
    allowed_types = {"TEMP", "HUM", "OCC", "DOOR"}
    allowed_statuses = {"ACTIVE", "RETIRED", "FAULTY"}

    sensors = data["sensor"]
    readings = data["sensor_reading"]

    print(
        "Invalid sensor types:",
        (~sensors["sensor_type"].isin(allowed_types)).sum()
    )

    print(
        "Invalid sensor statuses:",
        (~sensors["status"].isin(allowed_statuses)).sum()
    )

    print(
        "Negative sample intervals:",
        (sensors["sample_interval_sec"] <= 0).sum()
    )

    print(
        "Invalid sensor reading timestamps:",
        pd.to_datetime(
            readings["reading_ts"], errors="coerce"
        ).isna().sum()
    )

    print(
        "Invalid sensor reading values:",
        pd.to_numeric(
            readings["value"], errors="coerce"
        ).isna().sum()
    )


def check_inventory_values(data):
    lots = data["inventory_lot"]

    expected_value = lots["quantity_units"] * lots["unit_value"]

    mismatches = (
        (expected_value - lots["lot_value"]).abs() > 0.01
    ).sum()

    print("Lot value calculation mismatches:", mismatches)

    print(
        "Non-positive inventory quantities:",
        (lots["quantity_units"] <= 0).sum()
    )

    print(
        "Negative inventory unit values:",
        (lots["unit_value"] < 0).sum()
    )


def find_overlapping_sensor_mappings(mapping_df):
    mappings = mapping_df.copy()

    mappings["effective_from"] = pd.to_datetime(
        mappings["effective_from"], errors="coerce"
    )

    mappings["effective_to"] = pd.to_datetime(
        mappings["effective_to"], errors="coerce"
    )

    overlaps = []

    for sensor_id, group in mappings.groupby("sensor_id"):
        records = list(group.iterrows())

        for i in range(len(records)):
            _, first = records[i]

            for j in range(i + 1, len(records)):
                _, second = records[j]

                if pd.isna(first["effective_from"]) or pd.isna(
                    second["effective_from"]
                ):
                    continue

                first_end = (
                    first["effective_to"]
                    if pd.notna(first["effective_to"])
                    else pd.Timestamp.max
                )

                second_end = (
                    second["effective_to"]
                    if pd.notna(second["effective_to"])
                    else pd.Timestamp.max
                )

                overlap = (
                    first["effective_from"] <= second_end
                    and second["effective_from"] <= first_end
                )

                if overlap:
                    overlaps.append({
                        "sensor_id": sensor_id,
                        "map_id_1": first["map_id"],
                        "map_id_2": second["map_id"],
                        "zone_id_1": first["zone_id"],
                        "zone_id_2": second["zone_id"],
                        "rationale_1": first["rationale"],
                        "rationale_2": second["rationale"],
                    })

    return overlaps


def check_sensor_mapping_integrity(data):
    print("\nClean baseline mapping check:")

    clean_path = CLEAN_DATA_DIR / "sensor_zone_map.csv"

    if not clean_path.exists():
        raise FileNotFoundError(f"Missing clean baseline file: {clean_path}")

    clean_mappings = pd.read_csv(clean_path)
    clean_overlaps = find_overlapping_sensor_mappings(clean_mappings)

    print("Clean baseline overlapping mappings:", len(clean_overlaps))

    print("\nFault-injected dataset mapping check:")

    injected_mappings = data["sensor_zone_map"]
    injected_overlaps = find_overlapping_sensor_mappings(injected_mappings)

    print("Fault-injected overlapping mappings:", len(injected_overlaps))

    for overlap in injected_overlaps:
        print(
            f"OVERLAP: Sensor={overlap['sensor_id']} | "
            f"Mapping 1={overlap['map_id_1']} "
            f"Zone 1={overlap['zone_id_1']} | "
            f"Mapping 2={overlap['map_id_2']} "
            f"Zone 2={overlap['zone_id_2']}"
        )

        rationale_1 = overlap["rationale_1"]
        rationale_2 = overlap["rationale_2"]

        if (
            pd.isna(rationale_1) or str(rationale_1).strip() == ""
        ) and (
            pd.isna(rationale_2) or str(rationale_2).strip() == ""
        ):
            print("  Classification: OVERLAPPING MAPPING WITHOUT RATIONALE")


def main():
    print("\nWAREHOUSE DATA INTEGRITY TESTING")
    print("--------------------------------")

    data = load_data()

    print("\n1. PRIMARY KEY CHECKS")
    check_primary_keys(data)

    print("\n2. MANDATORY NULL CHECKS")
    check_mandatory_nulls(data)

    print("\n3. FOREIGN KEY CHECKS")
    check_foreign_keys(data)

    print("\n4. SENSOR DATA CHECKS")
    check_sensor_values(data)

    print("\n5. INVENTORY DATA CHECKS")
    check_inventory_values(data)

    print("\n6. SENSOR MAPPING INTEGRITY CHECKS")
    check_sensor_mapping_integrity(data)

    print("\nDATA INTEGRITY TEST EXECUTION COMPLETED")


if __name__ == "__main__":
    main()
