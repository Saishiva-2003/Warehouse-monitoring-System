# pipeline/evaluate_lot_exposure.py
# Independent second opinion: for every alarm-lot pair, recompute from the RAW readings,
# door events and gaps whether the lot really breached its storage limits, then compare
# with the links the rule engine saved. Reads only output/data (never ground truth).

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from pathlib import Path

import numpy as np
import pandas as pd

from config import DATA_DIR, REPORT_DIR


# =========================================================
# CONFIGURATION
# =========================================================

DATA_DIR = Path(DATA_DIR)
REPORT_DIR = Path(REPORT_DIR)

REPORT_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_FILES = [
    "alarm",
    "alarm_affected_lot",
    "inventory_lot",
    "lot_zone_assignment",
    "storage_requirement",
    "sensor",
    "sensor_zone_map",
    "sensor_reading",
    "door_event",
    "sensor_gap",
]


# =========================================================
# FILE LOADING
# =========================================================

def load_csv(name, date_columns=None):

    path = DATA_DIR / f"{name}.csv"

    if not path.exists():
        raise FileNotFoundError(
            f"Required file not found: {path}"
        )

    df = pd.read_csv(path)

    if date_columns:
        for column in date_columns:
            if column in df.columns:
                df[column] = pd.to_datetime(
                    df[column],
                    errors="coerce"
                )

    return df


def load_all_data():

    for name in REQUIRED_FILES:
        path = DATA_DIR / f"{name}.csv"

        if not path.exists():
            raise FileNotFoundError(
                f"Missing required file: {path}"
            )

    return {

        "alarms": load_csv(
            "alarm",
            ["start_ts", "end_ts"]
        ),

        "links": load_csv(
            "alarm_affected_lot",
            ["overlap_start", "overlap_end"]
        ),

        "lots": load_csv(
            "inventory_lot"
        ),

        "assignments": load_csv(
            "lot_zone_assignment",
            ["stored_from", "stored_until"]
        ),

        "requirements": load_csv(
            "storage_requirement",
            ["effective_from", "effective_to"]
        ),

        "sensors": load_csv(
            "sensor"
        ),

        "sensor_map": load_csv(
            "sensor_zone_map",
            ["effective_from", "effective_to"]
        ),

        "readings": load_csv(
            "sensor_reading",
            ["reading_ts"]
        ),

        "doors": load_csv(
            "door_event",
            ["opened_ts", "closed_ts"]
        ),

        "gaps": load_csv(
            "sensor_gap",
            ["gap_start", "gap_end"]
        ),
    }


# =========================================================
# GENERAL HELPERS
# =========================================================

def safe_float(value):

    try:
        return float(value)

    except (TypeError, ValueError):
        return np.nan


def minutes_between(start, end):

    if pd.isna(start) or pd.isna(end):
        return 0.0

    return max(
        0.0,
        (end - start).total_seconds() / 60
    )


def intervals_overlap(
    start_a,
    end_a,
    start_b,
    end_b
):

    if pd.isna(start_a) or pd.isna(end_a):
        return False

    if pd.isna(start_b) or pd.isna(end_b):
        return False

    return (
        start_a < end_b
        and end_a > start_b
    )


def longest_consecutive_run(flags):

    longest = 0
    current = 0

    for value in flags:

        if value:
            current += 1
            longest = max(longest, current)

        else:
            current = 0

    return longest


def active_mapping_rows(
    sensor_map,
    zone_id,
    start,
    end
):

    mappings = sensor_map[
        sensor_map["zone_id"].eq(zone_id)
    ].copy()

    if mappings.empty:
        return mappings

    active = (
        (
            mappings["effective_from"].isna()
            |
            (mappings["effective_from"] < end)
        )
        &
        (
            mappings["effective_to"].isna()
            |
            (mappings["effective_to"] > start)
        )
    )

    return mappings[active]


# =========================================================
# SENSOR TELEMETRY EVALUATION
# =========================================================

def evaluate_sensor_exposure(
    zone_id,
    sensor_type,
    start,
    end,
    lower_limit,
    upper_limit,
    max_excursion_min,
    data
):
    """
    Independently evaluates temperature or humidity readings.

    Each sensor is evaluated separately.
    Missing readings from one sensor cannot be hidden by another.
    An excursion is recorded when any valid sensor is out of range.
    """

    sensor_map = data["sensor_map"]
    sensors = data["sensors"]
    readings = data["readings"]

    mappings = active_mapping_rows(
        sensor_map,
        zone_id,
        start,
        end
    )

    if mappings.empty:

        return {
            "telemetry_status": "NO_SENSOR_MAPPING",
            "expected_readings": 0,
            "observed_readings": 0,
            "missing_readings": 0,
            "out_of_range_readings": 0,
            "exposure_min": 0,
            "longest_excursion_min": 0,
            "mapping_ambiguous": True,
            "breach": False
        }

    sensor_ids = set(
        mappings["sensor_id"].astype(str)
    )

    # Select sensors of the requested type first.

    sensor_types = sensors[
        sensors["sensor_id"].astype(str).isin(sensor_ids)
    ][
        [
            "sensor_id",
            "sensor_type",
            "sample_interval_sec"
        ]
    ].copy()

    sensor_types["sensor_id"] = (
        sensor_types["sensor_id"].astype(str)
    )

    sensor_types = sensor_types[
        sensor_types["sensor_type"].eq(sensor_type)
    ]

    valid_sensor_ids = set(
        sensor_types["sensor_id"]
    )

    if not valid_sensor_ids:

        return {
            "telemetry_status": "NO_MATCHING_SENSOR",
            "expected_readings": 0,
            "observed_readings": 0,
            "missing_readings": 0,
            "out_of_range_readings": 0,
            "exposure_min": 0,
            "longest_excursion_min": 0,
            "mapping_ambiguous": False,
            "breach": False
        }

    # Check overlapping mappings only for the requested sensor type.

    mapping_ambiguous = False

    all_maps = sensor_map[
        sensor_map["sensor_id"].astype(str).isin(
            valid_sensor_ids
        )
    ].copy()

    for sensor_id in valid_sensor_ids:

        sensor_rows = all_maps[
            all_maps["sensor_id"].astype(str).eq(sensor_id)
        ]

        active_zones = set()

        for row in sensor_rows.itertuples():

            map_start = (
                row.effective_from
                if pd.notna(row.effective_from)
                else pd.Timestamp.min
            )

            map_end = (
                row.effective_to
                if pd.notna(row.effective_to)
                else pd.Timestamp.max
            )

            if intervals_overlap(
                start,
                end,
                map_start,
                map_end
            ):
                active_zones.add(row.zone_id)

        if len(active_zones) > 1:
            mapping_ambiguous = True

    # Determine expected sample interval.

    interval_values = pd.to_numeric(
        sensor_types["sample_interval_sec"],
        errors="coerce"
    ).dropna()

    interval_min = (
        max(
            1,
            int(round(interval_values.median() / 60))
        )
        if not interval_values.empty
        else 5
    )

    # Select readings from the requested sensors.

    all_readings = readings[
        readings["sensor_id"].astype(str).isin(
            valid_sensor_ids
        )
    ].copy()

    all_readings["sensor_id"] = (
        all_readings["sensor_id"].astype(str)
    )

    all_readings["value"] = pd.to_numeric(
        all_readings["value"],
        errors="coerce"
    )

    all_readings = all_readings[
        (all_readings["reading_ts"] >= start)
        &
        (all_readings["reading_ts"] < end)
    ]

    all_readings = all_readings.dropna(
        subset=["reading_ts", "value"]
    )

    # Construct the expected timestamp grid.

    anchor = readings["reading_ts"].min()

    if pd.isna(anchor):

        return {
            "telemetry_status": "NO_VALID_TIMESTAMP",
            "expected_readings": 0,
            "observed_readings": 0,
            "missing_readings": 0,
            "out_of_range_readings": 0,
            "exposure_min": 0,
            "longest_excursion_min": 0,
            "mapping_ambiguous": mapping_ambiguous,
            "breach": False
        }

    offset = (
        start - anchor
    ).total_seconds() / 60

    steps = int(
        np.ceil(offset / interval_min)
    )

    first_expected = anchor + pd.Timedelta(
        minutes=steps * interval_min
    )

    expected_grid = pd.date_range(
        start=first_expected,
        end=end - pd.Timedelta(seconds=1),
        freq=f"{interval_min}min"
    )

    expected_grid = expected_grid[
        (expected_grid >= start)
        &
        (expected_grid < end)
    ]

    if len(expected_grid) == 0:

        return {
            "telemetry_status": "NO_EXPECTED_GRID",
            "expected_readings": 0,
            "observed_readings": 0,
            "missing_readings": 0,
            "out_of_range_readings": 0,
            "exposure_min": 0,
            "longest_excursion_min": 0,
            "mapping_ambiguous": mapping_ambiguous,
            "breach": False
        }

    # Evaluate each sensor independently.

    expected_count = 0
    observed_count = 0
    missing_count = 0

    out_of_range_timestamps = set()

    for sensor_id in valid_sensor_ids:

        sensor_readings = all_readings[
            all_readings["sensor_id"].eq(sensor_id)
        ]

        observed = (
            sensor_readings
            .groupby("reading_ts")["value"]
            .mean()
            .reindex(expected_grid)
        )

        missing_mask = observed.isna().to_numpy()

        out_mask = (
            (observed < lower_limit)
            |
            (observed > upper_limit)
        ).fillna(False).to_numpy()

        expected_count += len(expected_grid)

        observed_count += int(
            (~missing_mask).sum()
        )

        missing_count += int(
            missing_mask.sum()
        )

        # Record timestamps where at least one sensor
        # reports an out-of-range value.

        for timestamp in expected_grid[out_mask]:

            out_of_range_timestamps.add(timestamp)

    # Exposure duration is based on unique timestamps,
    # not the number of sensors.

    out_mask = np.array([
        timestamp in out_of_range_timestamps
        for timestamp in expected_grid
    ])

    out_count = int(
        out_mask.sum()
    )

    exposure_min = (
        out_count * interval_min
    )

    longest_min = (
        longest_consecutive_run(out_mask)
        * interval_min
    )

    if mapping_ambiguous:

        status = "AMBIGUOUS_SENSOR_MAPPING"

    elif missing_count > 0:

        status = "INCOMPLETE_TELEMETRY"

    else:

        status = "COMPLETE_TELEMETRY"

    return {
        "telemetry_status": status,
        "expected_readings": expected_count,
        "observed_readings": observed_count,
        "missing_readings": missing_count,
        "out_of_range_readings": out_count,
        "exposure_min": exposure_min,
        "longest_excursion_min": longest_min,
        "mapping_ambiguous": mapping_ambiguous,
        "breach": (
            longest_min > max_excursion_min
        )
    }


# =========================================================
# DOOR EVENT EVALUATION
# =========================================================

def evaluate_door_exposure(
    zone_id,
    start,
    end,
    max_door_open_min,
    doors
):

    events = doors[
        doors["zone_id"].eq(zone_id)
    ].copy()

    events = events[
        (events["opened_ts"] < end)
        &
        (events["closed_ts"] > start)
    ]

    results = []

    for event in events.itertuples():

        event_duration = safe_float(
            getattr(
                event,
                "open_duration_min",
                np.nan
            )
        )

        if pd.isna(event_duration):

            event_duration = minutes_between(
                event.opened_ts,
                event.closed_ts
            )

        overlap_start = max(
            start,
            event.opened_ts
        )

        overlap_end = min(
            end,
            event.closed_ts
        )

        results.append({

            "door_event_id": event.door_event_id,

            "event_duration_min": event_duration,

            "lot_overlap_min": minutes_between(
                overlap_start,
                overlap_end
            ),

            "breach": (
                event_duration > max_door_open_min
            )
        })

    return results


# =========================================================
# INDEPENDENT LOT-ALARM EVALUATION
# =========================================================

def evaluate_pair(
    alarm,
    assignment,
    lot,
    requirement,
    data
):

    alarm_start = alarm["start_ts"]
    alarm_end = alarm["end_ts"]

    lot_start = assignment["stored_from"]
    lot_end = assignment["stored_until"]

    overlap_start = max(
        alarm_start,
        lot_start
    )

    overlap_end = min(
        alarm_end,
        lot_end
    )

    overlap_min = minutes_between(
        overlap_start,
        overlap_end
    )

    code = alarm["rule_code"]
    zone_id = alarm["zone_id"]

    result = {

        "alarm_id": alarm["alarm_id"],

        "lot_id": lot["lot_id"],

        "zone_id": zone_id,

        "rule_code": code,

        "overlap_start": overlap_start,

        "overlap_end": overlap_end,

        "overlap_minutes": overlap_min,

        "telemetry_status": "NOT_APPLICABLE",

        "expected_readings": 0,

        "observed_readings": 0,

        "missing_readings": 0,

        "out_of_range_readings": 0,

        "exposure_min": 0,

        "longest_excursion_min": 0,

        "permitted_excursion_min": safe_float(
            requirement["max_excursion_min"]
        ),

        "mapping_ambiguous": False,

        "door_event_count": 0,

        "door_breach_count": 0,

        "door_overlap_minutes": 0,

        "independent_breach": False,

        "independent_result": "",

        # Redundant sensor evidence fields.

        "redundant_sensor_count": 0,

        "redundant_sensor_ids": "",

        "redundant_telemetry_status": "NOT_EVALUATED",

        "redundant_expected_readings": 0,

        "redundant_observed_readings": 0,

        "redundant_missing_readings": 0,

        "redundant_out_of_range_readings": 0,

        "redundant_exposure_min": 0,

        "redundant_longest_excursion_min": 0,

        "redundant_mapping_ambiguous": False
    }

    # ---------------------------------------------
    # TEMPERATURE
    # ---------------------------------------------

    if code in ("TEMP_HIGH", "TEMP_LOW"):

        check = evaluate_sensor_exposure(

            zone_id,

            "TEMP",

            overlap_start,

            overlap_end,

            safe_float(requirement["temp_min_c"]),

            safe_float(requirement["temp_max_c"]),

            safe_float(requirement["max_excursion_min"]),

            data
        )

        result.update(check)

        if check["breach"]:

            result["independent_breach"] = True
            result["independent_result"] = "BREACH"

        elif check["telemetry_status"] != "COMPLETE_TELEMETRY":

            result["independent_result"] = "UNKNOWN"

        else:

            result["independent_result"] = "NO_BREACH"

    # ---------------------------------------------
    # HUMIDITY
    # ---------------------------------------------

    elif code in ("HUM_HIGH", "HUM_LOW"):

        check = evaluate_sensor_exposure(

            zone_id,

            "HUM",

            overlap_start,

            overlap_end,

            safe_float(requirement["hum_min_pct"]),

            safe_float(requirement["hum_max_pct"]),

            safe_float(requirement["max_excursion_min"]),

            data
        )

        result.update(check)

        if check["breach"]:

            result["independent_breach"] = True
            result["independent_result"] = "BREACH"

        elif check["telemetry_status"] != "COMPLETE_TELEMETRY":

            result["independent_result"] = "UNKNOWN"

        else:

            result["independent_result"] = "NO_BREACH"

    # ---------------------------------------------
    # DOOR OPEN
    # ---------------------------------------------

    elif code == "DOOR_OPEN_LONG":

        door_results = evaluate_door_exposure(

            zone_id,

            overlap_start,

            overlap_end,

            safe_float(
                requirement["max_door_open_min"]
            ),

            data["doors"]
        )

        result["door_event_count"] = len(
            door_results
        )

        result["door_breach_count"] = sum(
            item["breach"]
            for item in door_results
        )

        result["door_overlap_minutes"] = sum(
            item["lot_overlap_min"]
            for item in door_results
        )

        result["independent_breach"] = (
            result["door_breach_count"] > 0
        )

        result["independent_result"] = (
            "BREACH"
            if result["independent_breach"]
            else "NO_BREACH"
        )

    # ---------------------------------------------
    # SENSOR OUTAGE
    # ---------------------------------------------

    elif code == "SENSOR_OUTAGE":

        gaps = data["gaps"]

        sensors = data["sensors"]

        sensor_map = data["sensor_map"]

        sensor_id = str(
            alarm["sensor_id"]
        )

        # Find overlapping outage gaps for the failed sensor.

        overlapping_gaps = gaps[
            gaps["sensor_id"].astype(str).eq(sensor_id)
        ].copy()

        overlapping_gaps = overlapping_gaps[
            (overlapping_gaps["gap_start"] < overlap_end)
            &
            (overlapping_gaps["gap_end"] > overlap_start)
        ]

        if overlapping_gaps.empty:

            result["telemetry_status"] = "NO_RECORDED_GAP"

            result["independent_result"] = "NO_RECORDED_GAP"

        else:

            result["telemetry_status"] = "OUTAGE_OVERLAP"

            result["missing_readings"] = len(
                overlapping_gaps
            )

            # Identify the failed sensor type.

            failed_sensor = sensors[
                sensors["sensor_id"].astype(str).eq(sensor_id)
            ]

            if failed_sensor.empty:

                result["redundant_telemetry_status"] = (
                    "FAILED_SENSOR_METADATA_MISSING"
                )

                result["independent_result"] = "UNKNOWN"

            else:

                sensor_type = str(
                    failed_sensor.iloc[0]["sensor_type"]
                )

                # Only temperature and humidity can be
                # checked against lot storage requirements.

                if sensor_type == "TEMP":

                    lower_limit = safe_float(
                        requirement["temp_min_c"]
                    )

                    upper_limit = safe_float(
                        requirement["temp_max_c"]
                    )

                elif sensor_type == "HUM":

                    lower_limit = safe_float(
                        requirement["hum_min_pct"]
                    )

                    upper_limit = safe_float(
                        requirement["hum_max_pct"]
                    )

                else:

                    lower_limit = None
                    upper_limit = None

                if (
                    pd.isna(lower_limit)
                    or pd.isna(upper_limit)
                ):

                    result["redundant_telemetry_status"] = (
                        "MISSING_OR_UNSUPPORTED_STORAGE_LIMIT"
                    )

                    result["independent_result"] = "UNKNOWN"

                else:

                    # Find sensors mapped to this zone
                    # during the lot-alarm overlap.

                    active_maps = active_mapping_rows(
                        sensor_map,
                        zone_id,
                        overlap_start,
                        overlap_end
                    )

                    # Keep only active sensors of the same
                    # type, excluding the failed sensor.

                    healthy_sensors = sensors[
                        (
                            sensors["sensor_type"].astype(str)
                            == sensor_type
                        )
                        &
                        (
                            sensors["status"]
                            .astype(str)
                            .str.upper()
                            .eq("ACTIVE")
                        )
                    ].copy()

                    healthy_sensor_ids = set(
                        healthy_sensors["sensor_id"].astype(str)
                    )

                    healthy_sensor_ids.discard(sensor_id)

                    redundant_maps = active_maps[
                        active_maps["sensor_id"]
                        .astype(str)
                        .isin(healthy_sensor_ids)
                    ].copy()

                    redundant_sensor_ids = set(
                        redundant_maps["sensor_id"].astype(str)
                    )

                    result["redundant_sensor_count"] = len(
                        redundant_sensor_ids
                    )

                    result["redundant_sensor_ids"] = ";".join(
                        sorted(redundant_sensor_ids)
                    )

                    if not redundant_sensor_ids:

                        result["redundant_telemetry_status"] = (
                            "NO_REDUNDANT_SENSOR"
                        )

                        result["independent_result"] = "UNKNOWN"

                    else:

                        # Preserve all zone mappings for the
                        # redundant sensors so cross-zone mapping
                        # ambiguity can still be detected.

                        redundant_sensor_map = sensor_map[
                            sensor_map["sensor_id"]
                            .astype(str)
                            .isin(redundant_sensor_ids)
                        ].copy()

                        # Evaluate only redundant sensors.
                        # The failed sensor is excluded.

                        redundant_data = dict(data)

                        redundant_data["sensor_map"] = (
                            redundant_sensor_map
                        )

                        check = evaluate_sensor_exposure(

                            zone_id,

                            sensor_type,

                            overlap_start,

                            overlap_end,

                            lower_limit,

                            upper_limit,

                            safe_float(
                                requirement["max_excursion_min"]
                            ),

                            redundant_data
                        )

                        result["redundant_telemetry_status"] = (
                            check["telemetry_status"]
                        )

                        result["redundant_expected_readings"] = (
                            check["expected_readings"]
                        )

                        result["redundant_observed_readings"] = (
                            check["observed_readings"]
                        )

                        result["redundant_missing_readings"] = (
                            check["missing_readings"]
                        )

                        result["redundant_out_of_range_readings"] = (
                            check["out_of_range_readings"]
                        )

                        result["redundant_exposure_min"] = (
                            check["exposure_min"]
                        )

                        result["redundant_longest_excursion_min"] = (
                            check["longest_excursion_min"]
                        )

                        result["redundant_mapping_ambiguous"] = (
                            check["mapping_ambiguous"]
                        )

                        # Include redundant mapping ambiguity
                        # in the overall ambiguity summary.

                        result["mapping_ambiguous"] = (
                            check["mapping_ambiguous"]
                        )

                        # Classify only the independent evidence.
                        # An incomplete or ambiguous reading set
                        # must remain UNKNOWN.

                        if check["mapping_ambiguous"]:

                            result["independent_result"] = "UNKNOWN"

                        elif check["breach"]:

                            result["independent_breach"] = True

                            result["independent_result"] = (
                                "BREACH_REDUNDANT_SENSOR"
                            )

                        elif (
                            check["telemetry_status"]
                            == "COMPLETE_TELEMETRY"
                        ):

                            result["independent_result"] = (
                                "NO_BREACH_REDUNDANT_SENSOR"
                            )

                        else:

                            result["independent_result"] = "UNKNOWN"

    # ---------------------------------------------
    # DRIFT / OCCUPANCY / OTHER RULES
    # ---------------------------------------------

    else:

        result["independent_result"] = (
            "CONTEXT_ONLY_NO_DIRECT_LOT_BREACH_RULE"
        )

    return result


# =========================================================
# MAIN EVALUATION
# =========================================================

def main():

    data = load_all_data()

    alarms = data["alarms"]
    links = data["links"]
    lots = data["lots"]
    assignments = data["assignments"]
    requirements = data["requirements"]

    # Merge lot information with storage requirements.

    lot_info = lots.merge(
        requirements,
        on="requirement_id",
        how="left",
        suffixes=("", "_requirement")
    )

    # -----------------------------------------------------
    # CORRECTED LOT LOOKUP
    # -----------------------------------------------------

    lot_lookup = (
        lot_info
        .set_index("lot_id")
        .to_dict("index")
    )

    # Existing alarm-lot pairs from the rule engine.

    saved_pairs = set(
        zip(
            links["alarm_id"].astype(str),
            links["lot_id"].astype(str)
        )
    )

    expected_pairs = []

    evaluated_rows = []

    # -----------------------------------------------------
    # RECONSTRUCT EXPECTED ALARM-LOT PAIRS
    # -----------------------------------------------------

    for alarm in alarms.to_dict("records"):

        for assignment in assignments.to_dict("records"):

            if assignment["zone_id"] != alarm["zone_id"]:
                continue

            if not intervals_overlap(

                assignment["stored_from"],

                assignment["stored_until"],

                alarm["start_ts"],

                alarm["end_ts"]

            ):
                continue

            lot_id = assignment["lot_id"]

            if lot_id not in lot_lookup:
                continue

            # Restore lot_id in the lot dictionary.

            lot = {
                "lot_id": lot_id,
                **lot_lookup[lot_id]
            }

            expected_pairs.append((

                str(alarm["alarm_id"]),

                str(lot_id)

            ))

            requirement = {

                "temp_min_c": lot["temp_min_c"],

                "temp_max_c": lot["temp_max_c"],

                "hum_min_pct": lot["hum_min_pct"],

                "hum_max_pct": lot["hum_max_pct"],

                "max_excursion_min": lot["max_excursion_min"],

                "max_door_open_min": lot["max_door_open_min"]

            }

            evaluated_rows.append(

                evaluate_pair(

                    alarm,

                    assignment,

                    lot,

                    requirement,

                    data

                )
            )

    expected_pairs = set(
        expected_pairs
    )

    # -----------------------------------------------------
    # LINK RECONCILIATION
    # -----------------------------------------------------

    missing_pairs = (
        expected_pairs - saved_pairs
    )

    extra_pairs = (
        saved_pairs - expected_pairs
    )

    evaluation = pd.DataFrame(
        evaluated_rows
    )

    # -----------------------------------------------------
    # COMPARE WITH RULE ENGINE RESULTS
    # -----------------------------------------------------

    if not links.empty:

        comparison = links.copy()

        comparison["alarm_id"] = (
            comparison["alarm_id"].astype(str)
        )

        comparison["lot_id"] = (
            comparison["lot_id"].astype(str)
        )

        comparison = comparison.rename(

            columns={

                "exposure_min":
                    "rule_engine_exposure_min",

                "breaches_requirement":
                    "rule_engine_breach"

            }

        )

        evaluation = evaluation.merge(

            comparison[

                [

                    "alarm_id",

                    "lot_id",

                    "rule_engine_exposure_min",

                    "rule_engine_breach"

                ]

            ],

            on=["alarm_id", "lot_id"],

            how="left"

        )

    # -----------------------------------------------------
    # SAVE INDEPENDENT EXPOSURE RESULTS
    # -----------------------------------------------------

    evaluation_path = (
        REPORT_DIR
        / "independent_lot_exposure_results.csv"
    )

    evaluation.to_csv(
        evaluation_path,
        index=False
    )

    # -----------------------------------------------------
    # SAVE LINK RECONCILIATION
    # -----------------------------------------------------

    reconciliation_rows = []

    for alarm_id, lot_id in sorted(missing_pairs):

        reconciliation_rows.append({

            "alarm_id": alarm_id,

            "lot_id": lot_id,

            "link_status": "MISSING_FROM_RULE_ENGINE"

        })

    for alarm_id, lot_id in sorted(extra_pairs):

        reconciliation_rows.append({

            "alarm_id": alarm_id,

            "lot_id": lot_id,

            "link_status": "EXTRA_RULE_ENGINE_LINK"

        })

    reconciliation = pd.DataFrame(
        reconciliation_rows,
        columns=[
            "alarm_id",
            "lot_id",
            "link_status"
        ]
    )

    reconciliation_path = (
        REPORT_DIR
        / "alarm_lot_link_reconciliation.csv"
    )

    reconciliation.to_csv(
        reconciliation_path,
        index=False
    )

    # -----------------------------------------------------
    # SUMMARY METRICS
    # -----------------------------------------------------

    summary = {

        "alarms_evaluated":
            int(len(alarms)),

        "independent_expected_alarm_lot_pairs":
            len(expected_pairs),

        "rule_engine_alarm_lot_pairs":
            len(saved_pairs),

        "missing_rule_engine_links":
            len(missing_pairs),

        "extra_rule_engine_links":
            len(extra_pairs),

        "independent_breach_pairs":
            (
                int(evaluation["independent_breach"].sum())
                if not evaluation.empty
                else 0
            ),

        "unknown_pairs":
            (
                int(
                    evaluation["independent_result"]
                    .eq("UNKNOWN")
                    .sum()
                )
                if not evaluation.empty
                else 0
            ),

        "no_breach_pairs":
            (
                int(
                    evaluation["independent_result"]
                    .isin([
                        "NO_BREACH",
                        "NO_BREACH_REDUNDANT_SENSOR"
                    ])
                    .sum()
                )
                if not evaluation.empty
                else 0
            ),

        "context_only_pairs":
            (
                int(
                    evaluation["independent_result"]
                    .eq(
                        "CONTEXT_ONLY_NO_DIRECT_LOT_BREACH_RULE"
                    )
                    .sum()
                )
                if not evaluation.empty
                else 0
            ),

        "ambiguous_mapping_pairs":
            (
                int(
                    evaluation["mapping_ambiguous"].sum()
                )
                if not evaluation.empty
                else 0
            )

    }

    summary_df = pd.DataFrame(

        [
            {
                "metric": key,
                "value": value
            }

            for key, value in summary.items()
        ]

    )

    summary_path = (
        REPORT_DIR
        / "independent_lot_exposure_summary.csv"
    )

    summary_df.to_csv(
        summary_path,
        index=False
    )

    # -----------------------------------------------------
    # TERMINAL OUTPUT
    # -----------------------------------------------------

    print("\nINDEPENDENT LOT EXPOSURE EVALUATION")

    print("----------------------------------")

    for key, value in summary.items():

        print(f"{key}: {value}")

    print("\nGenerated files:")

    print(evaluation_path)

    print(reconciliation_path)

    print(summary_path)


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()