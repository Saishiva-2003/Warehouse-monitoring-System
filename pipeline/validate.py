# pipeline/validate.py
# Stage: VALIDATE the dataset. Two jobs:
#   1. Integrity checks   (keys, joins, enums, dates, arithmetic, lifecycles, duplicates)
#   2. Data-quality detectors (find the 4 edge cases using ONLY the data tables)
# It never opens the ground truth folder.
#
# Writes: output/reports/validation_report.md, output/reports/detected_issues.csv

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import DATA_DIR, REPORT_DIR, OUTAGE_MULTIPLIER, READING_INTERVAL_MIN
from utils import save_table

STEP = pd.Timedelta(minutes=READING_INTERVAL_MIN)
TOL_MIN = 0.011          # rounding tolerance for minutes / hours / money

DATE_COLS = {
    "sensor_zone_map": ["effective_from", "effective_to"],
    "inventory_lot": ["received_ts", "expiry_date"],
    "lot_zone_assignment": ["stored_from", "stored_until"],
    "sensor_reading": ["reading_ts"],
    "door_event": ["opened_ts", "closed_ts"],
    "sensor_gap": ["gap_start", "gap_end"],
    "alarm": ["start_ts", "end_ts"],
    "alarm_status_history": ["changed_ts"],
    "alarm_affected_lot": ["overlap_start", "overlap_end"],
    "inspection": ["inspected_ts"],
    "remediation": ["action_ts"],
}
TABLE_NAMES = ["warehouse", "zone", "sensor", "sensor_zone_map", "storage_requirement",
               "inventory_lot", "lot_zone_assignment", "sensor_reading", "door_event",
               "sensor_gap", "alarm", "alarm_status_history", "alarm_affected_lot",
               "inspection", "remediation"]

PKS = {  # table: (column, ID format)
    "warehouse": ("warehouse_id", r"^WH-\d{3}$"),
    "zone": ("zone_id", r"^ZONE-WH-\d{3}-\d{3}$"),
    "sensor": ("sensor_id", r"^SNS-ZONE-WH-\d{3}-\d{3}-(TEMP|HUM|OCC|DOOR)-\d{2}$"),
    "sensor_zone_map": ("map_id", r"^MAP-\d{6}$"),
    "storage_requirement": ("requirement_id", r"^REQ-\d{4}$"),
    "inventory_lot": ("lot_id", r"^LOT-2026-\d{6}$"),
    "lot_zone_assignment": ("assignment_id", r"^ASG-\d{6}$"),
    "sensor_reading": ("reading_id", r"^RDG-SNS-ZONE-WH-\d{3}-\d{3}-(TEMP|HUM|OCC)-\d{2}-\d{8}T\d{6}Z$"),
    "door_event": ("door_event_id", r"^DOR-\d{6}$"),
    "sensor_gap": ("gap_id", r"^GAP-\d{6}$"),
    "alarm": ("alarm_id", r"^ALM-\d{6}$"),
    "alarm_status_history": ("history_id", r"^AST-\d{6}$"),
    "inspection": ("inspection_id", r"^INS-\d{6}$"),
    "remediation": ("remediation_id", r"^REM-\d{6}$"),
}

FKS = [  # (child table, child column, parent table, parent column, null allowed)
    ("zone", "warehouse_id", "warehouse", "warehouse_id", False),
    ("sensor_zone_map", "sensor_id", "sensor", "sensor_id", False),
    ("sensor_zone_map", "zone_id", "zone", "zone_id", False),
    ("sensor_reading", "sensor_id", "sensor", "sensor_id", False),
    ("door_event", "zone_id", "zone", "zone_id", False),
    ("inventory_lot", "requirement_id", "storage_requirement", "requirement_id", False),
    ("lot_zone_assignment", "lot_id", "inventory_lot", "lot_id", False),
    ("lot_zone_assignment", "zone_id", "zone", "zone_id", False),
    ("sensor_gap", "sensor_id", "sensor", "sensor_id", False),
    ("alarm", "zone_id", "zone", "zone_id", False),
    ("alarm", "sensor_id", "sensor", "sensor_id", True),
    ("alarm_status_history", "alarm_id", "alarm", "alarm_id", False),
    ("alarm_affected_lot", "alarm_id", "alarm", "alarm_id", False),
    ("alarm_affected_lot", "lot_id", "inventory_lot", "lot_id", False),
    ("inspection", "alarm_id", "alarm", "alarm_id", False),
    ("inspection", "lot_id", "inventory_lot", "lot_id", False),
    ("remediation", "inspection_id", "inspection", "inspection_id", False),
    ("remediation", "lot_id", "inventory_lot", "lot_id", False),
]

ENUMS = [  # (table, column, allowed values)
    ("warehouse", "status", {"ACTIVE", "MAINTENANCE", "CLOSED"}),
    ("zone", "zone_type", {"FROZEN", "COLD", "AMBIENT", "HOT"}),
    ("sensor", "sensor_type", {"TEMP", "HUM", "OCC", "DOOR"}),
    ("sensor", "unit", {"C", "PCT_RH", "COUNT", "BOOL"}),
    ("sensor", "status", {"ACTIVE", "FAULTY", "RETIRED"}),
    ("sensor_reading", "quality_flag", {"GOOD", "SUSPECT", "IMPUTED"}),
    ("door_event", "event_type", {"NORMAL", "PROLONGED", "FORCED", "AJAR"}),
    ("inventory_lot", "lot_status", {"RECEIVED", "STORED", "ON_HOLD", "QUARANTINED", "SHIPPED", "DISCARDED"}),
    ("sensor_gap", "gap_cause", {"POWER", "NETWORK", "SENSOR_FAULT", "MAINTENANCE", "UNKNOWN"}),
    ("alarm", "rule_code", {"TEMP_HIGH", "TEMP_LOW", "HUM_HIGH", "HUM_LOW", "OCCUPANCY_HIGH",
                            "DOOR_OPEN_LONG", "SENSOR_OUTAGE", "SENSOR_DRIFT"}),
    ("alarm", "severity", {"LOW", "MEDIUM", "HIGH", "CRITICAL"}),
    ("alarm", "status", {"OPEN", "ACKNOWLEDGED", "UNDER_INSPECTION", "REMEDIATED", "CLOSED"}),
    ("alarm_status_history", "to_status", {"OPEN", "ACKNOWLEDGED", "UNDER_INSPECTION", "REMEDIATED", "CLOSED"}),
    ("alarm_status_history", "changed_by_role", {"SYSTEM", "PLANT_OPERATOR", "QUALITY_ENGINEER",
                                                  "PRODUCTION_PLANNER", "OT_ADMIN"}),
    ("inspection", "result", {"PASS", "CONDITIONAL", "FAIL"}),
    ("inspection", "inspector_role", {"QUALITY_ENGINEER", "PLANT_OPERATOR"}),
    ("remediation", "action_type", {"RELEASE", "RELOCATE_LOT", "DISCARD_LOT", "REPAIR_EQUIPMENT",
                                    "RECALIBRATE_SENSOR", "REPLACE_SENSOR"}),
    ("remediation", "status", {"PLANNED", "IN_PROGRESS", "DONE"}),
    ("remediation", "owner_role", {"MAINTENANCE", "QUALITY_ENGINEER", "PRODUCTION_PLANNER", "OT_ADMIN"}),
]
UNIT_FOR = {"TEMP": "C", "HUM": "PCT_RH", "OCC": "COUNT", "DOOR": "BOOL"}
LEGAL = {"": {"OPEN"}, "OPEN": {"ACKNOWLEDGED"}, "ACKNOWLEDGED": {"UNDER_INSPECTION", "CLOSED"},
         "UNDER_INSPECTION": {"REMEDIATED"}, "REMEDIATED": {"CLOSED"}}

RESULTS = []


def add(group, name, violations):
    RESULTS.append({"group": group, "check": name, "violations": int(violations),
                    "status": "PASS" if violations == 0 else "FAIL"})


def load_all():
    T = {}
    for name in TABLE_NAMES:
        df = pd.read_csv(DATA_DIR / f"{name}.csv")
        for c in DATE_COLS.get(name, []):
            df[c] = pd.to_datetime(df[c])
        T[name] = df
    return T


# ---------------------------------------------------------
# JOB 1: integrity checks
# ---------------------------------------------------------
def integrity_checks(T):
    for name, (col, rx) in PKS.items():
        df = T[name]
        add("Primary keys", f"{name}.{col} is unique and not empty",
            df[col].duplicated().sum() + df[col].isna().sum())
        add("ID format", f"{name}.{col} follows {rx}", (~df[col].astype(str).str.match(rx)).sum())
    add("Primary keys", "alarm_affected_lot (alarm_id, lot_id) is unique",
        T["alarm_affected_lot"].duplicated(["alarm_id", "lot_id"]).sum())
    add("Primary keys", "sensor_reading (sensor_id, reading_ts) is unique",
        T["sensor_reading"].duplicated(["sensor_id", "reading_ts"]).sum())

    z = T["zone"]
    add("ID format", "zone_id starts with its warehouse_id",
        (~z.apply(lambda r: r["zone_id"].startswith(f"ZONE-{r['warehouse_id']}-"), axis=1)).sum())
    rd = T["sensor_reading"]
    stamp = rd["reading_ts"].dt.strftime("%Y%m%dT%H%M%SZ")
    add("ID format", "reading_id timestamp equals reading_ts",
        (rd["reading_id"] != "RDG-" + rd["sensor_id"] + "-" + stamp).sum())

    for ct, cc, pt, pc, null_ok in FKS:
        col = T[ct][cc]
        if null_ok:
            col = col.dropna()
        add("Foreign keys", f"{ct}.{cc} exists in {pt}.{pc}", (~col.isin(T[pt][pc])).sum())
    ins, links = T["inspection"], T["alarm_affected_lot"]
    pairs = set(zip(links["alarm_id"], links["lot_id"]))
    add("Foreign keys", "every inspection (alarm, lot) pair exists in alarm_affected_lot",
        sum((a, l) not in pairs for a, l in zip(ins["alarm_id"], ins["lot_id"])))
    rem = T["remediation"].merge(ins[["inspection_id", "lot_id"]], on="inspection_id", suffixes=("", "_ins"))
    add("Foreign keys", "remediation.lot_id equals its inspection's lot_id", (rem["lot_id"] != rem["lot_id_ins"]).sum())

    for t, c, allowed in ENUMS:
        add("Allowed values", f"{t}.{c} is one of {sorted(allowed)}", (~T[t][c].isin(allowed)).sum())
    s = T["sensor"]
    add("Allowed values", "sensor.unit matches sensor_type",
        (s["unit"] != s["sensor_type"].map(UNIT_FOR)).sum())
    types = rd[["sensor_id", "value"]].merge(s[["sensor_id", "sensor_type"]], on="sensor_id")
    add("Allowed values", "readings come only from TEMP, HUM or OCC sensors (never DOOR)",
        (types["sensor_type"] == "DOOR").sum())
    add("Allowed values", "temperature readings are between -40 and 60",
        ((types["sensor_type"] == "TEMP") & ~types["value"].between(-40, 60)).sum())
    add("Allowed values", "humidity readings are between 0 and 100",
        ((types["sensor_type"] == "HUM") & ~types["value"].between(0, 100)).sum())
    add("Allowed values", "occupancy readings are 0 or more",
        ((types["sensor_type"] == "OCC") & (types["value"] < 0)).sum())

    a, g, d = T["lot_zone_assignment"], T["sensor_gap"], T["door_event"]
    al, lots = T["alarm"], T["inventory_lot"]
    add("Date ordering", "lot_zone_assignment: stored_until is after stored_from", (a["stored_until"] <= a["stored_from"]).sum())
    add("Date ordering", "door_event: closed_ts is after opened_ts", (d["closed_ts"] <= d["opened_ts"]).sum())
    add("Date ordering", "sensor_gap: gap_end is after gap_start", (g["gap_end"] <= g["gap_start"]).sum())
    add("Date ordering", "alarm: end_ts is after start_ts", (al["end_ts"] <= al["start_ts"]).sum())
    add("Date ordering", "alarm_affected_lot: overlap_end is after overlap_start", (links["overlap_end"] <= links["overlap_start"]).sum())
    add("Date ordering", "inventory_lot: expiry_date is after received_ts", (lots["expiry_date"] <= lots["received_ts"]).sum())
    im = ins.merge(al[["alarm_id", "start_ts"]], on="alarm_id")
    add("Date ordering", "inspection happens after the alarm started", (im["inspected_ts"] <= im["start_ts"]).sum())
    rm = T["remediation"].merge(ins[["inspection_id", "inspected_ts"]], on="inspection_id")
    add("Date ordering", "remediation happens after its inspection", (rm["action_ts"] <= rm["inspected_ts"]).sum())

    lot_price = lots.set_index("lot_id")
    add("Arithmetic", "lot_value = quantity_units x unit_value",
        ((lots["lot_value"] - lots["quantity_units"] * lots["unit_value"]).abs() > TOL_MIN).sum())
    add("Arithmetic", "dwell_hours = (stored_until - stored_from) in hours",
        ((a["dwell_hours"] - (a["stored_until"] - a["stored_from"]) / pd.Timedelta(hours=1)).abs() > TOL_MIN).sum())
    add("Arithmetic", "open_duration_min = (closed_ts - opened_ts) in minutes",
        ((d["open_duration_min"] - (d["closed_ts"] - d["opened_ts"]) / pd.Timedelta(minutes=1)).abs() > TOL_MIN).sum())
    add("Arithmetic", "alarm.duration_min = (end_ts - start_ts) in minutes",
        ((al["duration_min"] - (al["end_ts"] - al["start_ts"]) / pd.Timedelta(minutes=1)).abs() > TOL_MIN).sum())
    add("Arithmetic", "gap_minutes = (gap_end - gap_start) in minutes",
        ((g["gap_minutes"] - (g["gap_end"] - g["gap_start"]) / pd.Timedelta(minutes=1)).abs() > TOL_MIN).sum())
    add("Arithmetic", "overlap_minutes = (overlap_end - overlap_start) in minutes",
        ((links["overlap_minutes"] - (links["overlap_end"] - links["overlap_start"]) / pd.Timedelta(minutes=1)).abs() > TOL_MIN).sum())
    rv = rem.merge(T["remediation"][["remediation_id", "units_affected", "value_at_risk"]], on="remediation_id", suffixes=("_x", ""))
    price = rv["lot_id"].map(lot_price["unit_value"])
    add("Arithmetic", "value_at_risk = units_affected x unit_value",
        ((rv["value_at_risk"] - rv["units_affected"] * price).abs() > 0.02).sum())
    chk = a.merge(lots[["lot_id", "requirement_id"]], on="lot_id").merge(
        T["storage_requirement"][["requirement_id", "required_zone_type"]], on="requirement_id").merge(
        T["zone"][["zone_id", "zone_type"]], on="zone_id")
    add("Arithmetic", "compatible_flag = (zone_type equals required_zone_type)",
        (chk["compatible_flag"].astype(bool) != (chk["zone_type"] == chk["required_zone_type"])).sum())

    # ---- business rules: quantities, values and exposure must make sense ----
    add("Business rules", "inventory_lot: quantity_units, unit_value and lot_value are all above 0",
        ((lots["quantity_units"] <= 0) | (lots["unit_value"] <= 0) | (lots["lot_value"] <= 0)).sum())
    rm_ = T["remediation"]
    add("Business rules", "remediation: units_affected and value_at_risk are 0 or more (above 0 unless the lot is simply RELEASED)",
        ((rm_["units_affected"] < 0) | (rm_["value_at_risk"] < 0)
         | ((rm_["action_type"] != "RELEASE") & (rm_["units_affected"] <= 0))).sum())
    add("Business rules", "alarm_affected_lot: exposure_min is 0 or more",
        (links["exposure_min"] < 0).sum())
    add("Business rules", "alarm_affected_lot: exposure_min never exceeds overlap_minutes",
        (links["exposure_min"] > links["overlap_minutes"] + TOL_MIN).sum())
    done_discard = T["remediation"][(T["remediation"]["action_type"] == "DISCARD_LOT") & (T["remediation"]["status"] == "DONE")]
    add("Business rules", "a lot with a completed DISCARD_LOT action has lot_status DISCARDED",
        (~done_discard["lot_id"].map(lot_price["lot_status"]).eq("DISCARDED")).sum())

    jl = links.merge(al[["alarm_id", "zone_id", "start_ts", "end_ts"]], on="alarm_id").merge(
        a[["lot_id", "zone_id", "stored_from", "stored_until"]], on="lot_id", suffixes=("_alarm", "_lot"))
    add("Joins", "every alarm-lot link is in the alarm's zone", (jl["zone_id_alarm"] != jl["zone_id_lot"]).sum())
    exp_s = jl[["start_ts", "stored_from"]].max(axis=1)
    exp_e = jl[["end_ts", "stored_until"]].min(axis=1)
    add("Joins", "overlap window = overlap of alarm time and lot stay",
        ((jl["overlap_start"] != exp_s) | (jl["overlap_end"] != exp_e)).sum())
    exposed_ok = ins.merge(links[["alarm_id", "lot_id", "exposure_min"]], on=["alarm_id", "lot_id"])
    add("Joins", "every inspected lot had exposure_min above 0", (exposed_ok["exposure_min"] <= 0).sum())

    h = T["alarm_status_history"].sort_values(["alarm_id", "history_id"])
    h["from_status"] = h["from_status"].fillna("")
    bad = 0
    for _, grp in h.groupby("alarm_id"):
        for frm, to in zip(grp["from_status"], grp["to_status"]):
            bad += to not in LEGAL.get(frm, set())
        bad += int(grp["from_status"].iloc[0] != "")
        bad += int((grp["changed_ts"].diff().dropna() < pd.Timedelta(0)).sum())
    add("Lifecycles", "alarm status changes follow OPEN > ACK > INSPECTION > REMEDIATED > CLOSED, in time order", bad)
    last = h.groupby("alarm_id")["to_status"].last()
    add("Lifecycles", "alarm.status equals its last history row",
        (al.set_index("alarm_id")["status"] != last.reindex(al["alarm_id"]).values).sum())
    add("Lifecycles", "every alarm has a history row", (~al["alarm_id"].isin(h["alarm_id"])).sum())

    for tbl, key, s_col, e_col, label in [("lot_zone_assignment", "lot_id", "stored_from", "stored_until", "a lot is never stored twice at once"),
                                          ("door_event", "zone_id", "opened_ts", "closed_ts", "doors in one zone never overlap")]:
        t = T[tbl].sort_values([key, s_col])
        same = t[key].values[1:] == t[key].values[:-1]
        add("Duplicates and overlaps", label, int((same & (t[s_col].values[1:] < t[e_col].values[:-1])).sum()))

    # every silent stretch in the readings must be recorded in sensor_gap (and nothing invented)
    r = rd[["sensor_id", "reading_ts"]].sort_values(["sensor_id", "reading_ts"]).reset_index(drop=True)
    gmin, gmax = r["reading_ts"].min(), r["reading_ts"].max()
    prev = r.groupby("sensor_id")["reading_ts"].shift(1).fillna(gmin - STEP)
    big = (r["reading_ts"] - prev) / pd.Timedelta(minutes=1) > OUTAGE_MULTIPLIER * READING_INTERVAL_MIN
    found = set(zip(r.loc[big, "sensor_id"], prev[big] + STEP))
    tail = r.groupby("sensor_id")["reading_ts"].max()
    for sid, last_ts in tail.items():
        if (gmax + STEP - last_ts) / pd.Timedelta(minutes=1) > OUTAGE_MULTIPLIER * READING_INTERVAL_MIN:
            found.add((sid, last_ts + STEP))
    recorded = set(zip(g["sensor_id"], g["gap_start"]))
    add("Sensor gaps", "every silent stretch in the readings is recorded in sensor_gap", len(found - recorded))
    add("Sensor gaps", "every sensor_gap row is a real silent stretch", len(recorded - found))


# ---------------------------------------------------------
# JOB 2: data-quality detectors (the 4 edge cases)
# ---------------------------------------------------------
def quality_detectors(T):
    issues = []

    def issue(kind, entity, zone, start, end, details):
        issues.append({"issue_type": kind, "entity_id": entity, "zone_id": zone,
                       "start_ts": start, "end_ts": end, "details": details})

    # 1. lot in a zone of the wrong type (worked out from the rules, not from compatible_flag)
    chk = T["lot_zone_assignment"].merge(T["inventory_lot"][["lot_id", "requirement_id"]], on="lot_id").merge(
        T["storage_requirement"][["requirement_id", "required_zone_type"]], on="requirement_id").merge(
        T["zone"][["zone_id", "zone_type"]], on="zone_id")
    for r in chk[chk["zone_type"] != chk["required_zone_type"]].itertuples():
        issue("INCOMPATIBLE_LOT_ZONE", r.lot_id, r.zone_id, r.stored_from, r.stored_until,
              f"needs a {r.required_zone_type} zone but is stored in a {r.zone_type} zone")

    # 2. a sensor mapped to 2+ zones at the same time, without a rationale
    m = T["sensor_zone_map"].copy()
    m["effective_to"] = m["effective_to"].fillna(pd.Timestamp.max)
    for sid, grp in m.groupby("sensor_id"):
        if len(grp) < 2:
            continue
        grp = grp.sort_values("effective_from")
        overlapping = (grp["effective_from"].iloc[1:].values < grp["effective_to"].iloc[:-1].values).any()
        no_reason = grp["rationale"].isna() | (grp["rationale"].astype(str).str.strip() == "")
        if overlapping and no_reason.any():
            issue("SENSOR_MULTI_ZONE_UNJUSTIFIED", sid, ",".join(grp["zone_id"]), pd.NaT, pd.NaT,
                  f"mapped to {len(grp)} zones at once, {int(no_reason.sum())} mapping(s) without rationale")

    # 3. a sensor gap that has no outage alarm
    al = T["alarm"]
    outage = al[al["rule_code"] == "SENSOR_OUTAGE"]
    for g in T["sensor_gap"].itertuples():
        hit = outage[(outage["sensor_id"] == g.sensor_id) & (outage["start_ts"] < g.gap_end)
                     & (outage["end_ts"] > g.gap_start)]
        if hit.empty:
            zone = T["sensor_zone_map"].loc[T["sensor_zone_map"]["sensor_id"] == g.sensor_id, "zone_id"].iloc[0]
            issue("SENSOR_OUTAGE_ALARM_MISSING", g.sensor_id, zone, g.gap_start, g.gap_end,
                  f"{g.gap_id}: sensor silent for {g.gap_minutes:.0f} min but no SENSOR_OUTAGE alarm exists")

    # 4. an alarm that does not list all the lots that were in its zone during its time window
    ex = al[["alarm_id", "zone_id", "start_ts", "end_ts"]].merge(
        T["lot_zone_assignment"][["lot_id", "zone_id", "stored_from", "stored_until"]], on="zone_id")
    ex = ex[(ex["stored_from"] < ex["end_ts"]) & (ex["stored_until"] > ex["start_ts"])]
    have = set(zip(T["alarm_affected_lot"]["alarm_id"], T["alarm_affected_lot"]["lot_id"]))
    missing = pd.Series([(a, l) not in have for a, l in zip(ex["alarm_id"], ex["lot_id"])],
                        index=ex.index, dtype=bool)
    ex = ex[missing]
    for aid, grp in ex.groupby("alarm_id"):
        row = al[al["alarm_id"] == aid].iloc[0]
        total = int(((T["lot_zone_assignment"]["zone_id"] == row["zone_id"])
                     & (T["lot_zone_assignment"]["stored_from"] < row["end_ts"])
                     & (T["lot_zone_assignment"]["stored_until"] > row["start_ts"])).sum())
        issue("ALARM_LOT_LINK_MISSING", aid, row["zone_id"], row["start_ts"], row["end_ts"],
              f"{len(grp)} of {total} lots in the zone during the alarm are not linked")

    cols = ["issue_id", "issue_type", "entity_id", "zone_id", "start_ts", "end_ts", "details"]
    df = pd.DataFrame(issues, columns=cols[1:])
    df.insert(0, "issue_id", [f"ISS-{i + 1:06d}" for i in range(len(df))])
    return df


def write_report(T, issues):
    n_fail = sum(r["status"] == "FAIL" for r in RESULTS)
    lines = ["# Validation report", "",
             "Generated by `pipeline/validate.py`. It reads only the data tables, never the ground truth.", "",
             "## Table sizes", "", "| Table | Rows |", "|---|---|"]
    lines += [f"| {n} | {len(T[n]):,} |" for n in TABLE_NAMES]
    lines += ["", "## Integrity checks", "",
              f"**{len(RESULTS) - n_fail} of {len(RESULTS)} checks passed.**", "",
              "| Group | Check | Violations | Result |", "|---|---|---|---|"]
    lines += [f"| {r['group']} | {r['check'].replace('|', '/')} | {r['violations']} | {r['status']} |"
              for r in RESULTS]
    lines += ["", "## Data-quality findings", ""]
    if issues.empty:
        lines.append("No data-quality issues found.")
    else:
        lines += [f"**{len(issues)} issues found**, by type: "
                  + ", ".join(f"{k} = {v}" for k, v in issues["issue_type"].value_counts().sort_index().items()), "",
                  "| Issue | Type | Entity | Zone | Details |", "|---|---|---|---|---|"]
        lines += [f"| {r.issue_id} | {r.issue_type} | {r.entity_id} | {r.zone_id} | {r.details} |"
                  for r in issues.itertuples()]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    T = load_all()
    integrity_checks(T)
    issues = quality_detectors(T)
    save_table(issues, "detected_issues", folder=REPORT_DIR, sort_by="issue_id")
    write_report(T, issues)

    n_fail = sum(r["status"] == "FAIL" for r in RESULTS)
    print("\n======================================")
    print("          VALIDATION RESULT")
    print("======================================")
    for group in dict.fromkeys(r["group"] for r in RESULTS):
        rows = [r for r in RESULTS if r["group"] == group]
        bad = sum(r["status"] == "FAIL" for r in rows)
        print(f"{group:24s}: {len(rows) - bad}/{len(rows)} passed")
    print(f"\nIntegrity checks passed : {len(RESULTS) - n_fail} of {len(RESULTS)}")
    for r in RESULTS:
        if r["status"] == "FAIL":
            print(f"  FAIL ({r['violations']}): {r['check']}")
    print(f"Data-quality findings   : {len(issues)}")
    for r in issues.itertuples():
        print(f"  {r.issue_id} | {r.issue_type} | {r.entity_id} | {r.details}")
    print(f"\nReport: {REPORT_DIR / 'validation_report.md'}")
    if n_fail:                                   # a failed integrity check must stop the pipeline
        sys.exit(1)


if __name__ == "__main__":
    main()