# pipeline/evaluate.py
# Stage: EVALUATE. Compare what the detectors found with what was planted.
# This is the ONLY stage that reads the ground truth next to the detectors' output.
#
# Reads : alarm tables, sensor_gap, detected_issues.csv, fault_ground_truth*.csv
# Writes: output/reports/ scenario_detection_results.csv, evaluation_metrics.csv,
#         lot_linkage_summary.csv, alarm_lot_linkage_details.csv, evaluation_report.md

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import DATA_DIR, GT_DIR, REPORT_DIR
from utils import save_table

SENSOR_CODES = ("SENSOR_OUTAGE", "SENSOR_DRIFT")
EDGE_CASE_NAME = {                      # the four edge cases named in the problem statement
    "INCOMPATIBLE_LOT_ZONE": "Lot assigned to incompatible zone",
    "SENSOR_MULTI_ZONE_WITHOUT_RATIONALE": "Sensor mapped to multiple zones without rationale",
    "READING_GAP_TREATED_AS_NORMAL": "Reading gap treated as normal",
    "ALARM_NOT_LINKED_TO_LOTS": "Alarm not linked to affected lots",
}
MIN = pd.Timedelta(minutes=1)


# ---------------------------------------------------------
# COMMON FUNCTIONS
# ---------------------------------------------------------
def read(name, folder=DATA_DIR, dates=()):
    path = folder / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}. Run the earlier stages first.")
    df = pd.read_csv(path)
    for c in dates:
        df[c] = pd.to_datetime(df[c])
    return df


def as_bool(series):
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def calculate_metrics(expected, matched, predictions):
    """TP = planted and found. FN = planted and missed. FP = predictions with no planted fault.
    If nothing was expected or predicted, the matching score is 1.0 (nothing was wrong)."""
    tp = matched
    fn = expected - tp
    fp = predictions - tp
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1_score": round(f1, 4)}


def md_table(df):
    if df.empty:
        return "_none_"
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep] + body)


# ---------------------------------------------------------
# RULE ENGINE MATCHING (one alarm can explain only one planted fault)
# ---------------------------------------------------------
def evaluate_rule_engine(gt, alarm, gaps, hist):
    expected = gt[gt["expected_detected_by"] == "RULE_ENGINE"].sort_values("scenario_id")
    open_ts = hist[hist["to_status"] == "OPEN"].set_index("alarm_id")["changed_ts"]
    used, results = set(), []

    for g in expected.itertuples():
        cand = alarm[(~alarm["alarm_id"].isin(used))
                     & (alarm["rule_code"] == g.expected_detection)
                     & (alarm["zone_id"] == g.zone_id)
                     & (alarm["start_ts"] < g.end_ts) & (alarm["end_ts"] > g.start_ts)]
        if g.expected_detection in SENSOR_CODES:
            cand = cand[cand["sensor_id"].isin(str(g.entity_id).split(","))]
        hit = cand.sort_values(["start_ts", "alarm_id"]).iloc[0] if len(cand) else None
        if hit is not None:
            used.add(hit["alarm_id"])

        gap_id = ""
        if g.expected_detection == "SENSOR_OUTAGE":          # the gap must be recorded explicitly too
            sg = gaps[(gaps["sensor_id"] == g.entity_id) & (gaps["gap_start"] < g.end_ts) & (gaps["gap_end"] > g.start_ts)]
            gap_id = sg["gap_id"].iloc[0] if len(sg) else ""

        results.append({
            "scenario_id": g.scenario_id, "fault_type": g.fault_type,
            "expected_detection": g.expected_detection, "expected_detected_by": "RULE_ENGINE",
            "zone_id": g.zone_id, "detected": hit is not None,
            "matched_prediction_id": hit["alarm_id"] if hit is not None else "",
            "supporting_gap_id": gap_id,
            "start_error_min": round((hit["start_ts"] - g.start_ts) / MIN, 1) if hit is not None else "",
            "end_error_min": round((hit["end_ts"] - g.end_ts) / MIN, 1) if hit is not None else "",
            "minutes_until_alarm_raised": round((open_ts[hit["alarm_id"]] - g.start_ts) / MIN, 1) if hit is not None else "",
            "match_reason": "Rule, zone and time matched" if hit is not None else "No matching alarm found"})
    unmatched = alarm[~alarm["alarm_id"].isin(used)]
    return results, unmatched


# ---------------------------------------------------------
# DATA VALIDATOR MATCHING
# ---------------------------------------------------------
def evaluate_data_validator(gt, issues):
    expected = gt[gt["expected_detected_by"] == "DATA_VALIDATOR"].sort_values("scenario_id")
    used, results = set(), []
    for g in expected.itertuples():
        cand = issues[(issues["issue_type"] == g.expected_detection)
                      & (issues["entity_id"].astype(str) == str(g.entity_id))
                      & (~issues["issue_id"].isin(used))]
        hit = cand.iloc[0] if len(cand) else None
        if hit is not None:
            used.add(hit["issue_id"])
        results.append({
            "scenario_id": g.scenario_id, "fault_type": g.fault_type,
            "expected_detection": g.expected_detection, "expected_detected_by": "DATA_VALIDATOR",
            "zone_id": g.zone_id, "detected": hit is not None,
            "matched_prediction_id": hit["issue_id"] if hit is not None else "",
            "supporting_gap_id": "", "start_error_min": "", "end_error_min": "",
            "minutes_until_alarm_raised": "",
            "match_reason": "Issue type and entity matched" if hit is not None else "No matching finding"})
    unmatched = issues[~issues["issue_id"].isin(used)]
    return results, unmatched


# ---------------------------------------------------------
# ALARM-TO-LOT LINKAGE (expected links recomputed from zone + time overlap)
# ---------------------------------------------------------
def evaluate_lot_linkage(alarm, links, asg, gt_lots):
    exp = alarm[["alarm_id", "zone_id", "start_ts", "end_ts"]].merge(
        asg[["lot_id", "zone_id", "stored_from", "stored_until"]], on="zone_id")
    exp = exp[(exp["stored_from"] < exp["end_ts"]) & (exp["stored_until"] > exp["start_ts"])]
    expected_pairs = set(zip(exp["alarm_id"], exp["lot_id"]))
    linked_pairs = set(zip(links["alarm_id"], links["lot_id"]))
    missing = expected_pairs - linked_pairs
    extra = linked_pairs - expected_pairs
    breach = as_bool(links["breaches_requirement"])

    rows = []
    for a in alarm.sort_values("alarm_id").itertuples():
        e = {l for (x, l) in expected_pairs if x == a.alarm_id}
        k = {l for (x, l) in linked_pairs if x == a.alarm_id}
        if not e:
            status = "NO_LOTS_IN_ZONE"
        elif e <= k:
            status = "COMPLETE"
        elif k & e:
            status = "INCOMPLETE"
        else:
            status = "NO_LINKS"
        rows.append({"alarm_id": a.alarm_id, "zone_id": a.zone_id, "rule_code": a.rule_code,
                     "expected_lot_count": len(e), "linked_lot_count": len(k & e),
                     "missing_lot_count": len(e - k),
                     "breach_link_count": int(breach[links["alarm_id"] == a.alarm_id].sum()),
                     "link_status": status})
    details = pd.DataFrame(rows)
    with_lots = int((details["expected_lot_count"] > 0).sum())
    complete = int((details["link_status"] == "COMPLETE").sum())
    planted_missing = set(zip(gt_lots["alarm_id"], gt_lots["lot_id"]))
    summary = pd.DataFrame([{
        "total_alarms": len(alarm), "alarms_with_lots_in_zone": with_lots,
        "alarms_fully_linked": complete, "alarms_not_fully_linked": with_lots - complete,
        "linkage_coverage_pct": round(100.0 * complete / with_lots, 2) if with_lots else 100.0,
        "expected_links": len(expected_pairs), "present_links": len(linked_pairs & expected_pairs),
        "missing_links": len(missing), "links_without_basis": len(extra),
        "orphan_links": int((~links["alarm_id"].isin(alarm["alarm_id"])).sum()),
        "duplicate_alarm_lot_pairs": int(links.duplicated(["alarm_id", "lot_id"]).sum()),
        "distinct_affected_lots": links["lot_id"].nunique(), "breach_links": int(breach.sum()),
        "missing_links_equal_planted": missing == planted_missing}])
    return summary, details


# ---------------------------------------------------------
# MAIN EVALUATION
# ---------------------------------------------------------
def main():
    alarm = read("alarm", dates=["start_ts", "end_ts"])
    hist = read("alarm_status_history", dates=["changed_ts"])
    links = read("alarm_affected_lot")
    gaps = read("sensor_gap", dates=["gap_start", "gap_end"])
    ins = read("inspection")
    rem = read("remediation")
    asg = read("lot_zone_assignment", dates=["stored_from", "stored_until"])
    gt = read("fault_ground_truth", folder=GT_DIR, dates=["start_ts", "end_ts"])
    gt_lots = read("fault_ground_truth_lots", folder=GT_DIR)
    issues = read("detected_issues", folder=REPORT_DIR)

    rule_rows, unmatched_alarms = evaluate_rule_engine(gt, alarm, gaps, hist)
    val_rows, unmatched_issues = evaluate_data_validator(gt, issues)
    scenario_df = pd.DataFrame(rule_rows + val_rows)

    r_exp, r_hit = len(rule_rows), sum(r["detected"] for r in rule_rows)
    v_exp, v_hit = len(val_rows), sum(r["detected"] for r in val_rows)
    metrics_df = pd.DataFrame([
        {"detector": "RULE_ENGINE", "expected_scenarios": r_exp, "detected_scenarios": r_hit,
         "unmatched_predictions": len(unmatched_alarms), **calculate_metrics(r_exp, r_hit, len(alarm))},
        {"detector": "DATA_VALIDATOR", "expected_scenarios": v_exp, "detected_scenarios": v_hit,
         "unmatched_predictions": len(unmatched_issues), **calculate_metrics(v_exp, v_hit, len(issues))},
        {"detector": "COMBINED", "expected_scenarios": r_exp + v_exp, "detected_scenarios": r_hit + v_hit,
         "unmatched_predictions": len(unmatched_alarms) + len(unmatched_issues),
         **calculate_metrics(r_exp + v_exp, r_hit + v_hit, len(alarm) + len(issues))}])

    link_summary, link_details = evaluate_lot_linkage(alarm, links, asg, gt_lots)

    # business impact
    sev = alarm["severity"].value_counts().reindex(["CRITICAL", "HIGH", "MEDIUM", "LOW"]).dropna().astype(int)
    impact = rem.groupby("action_type").agg(Remediations=("remediation_id", "count"), Units=("units_affected", "sum"),
                                            Value_at_risk=("value_at_risk", "sum")).reset_index()
    impact["Value_at_risk"] = impact["Value_at_risk"].round(2)
    impact = impact.rename(columns={"action_type": "Action", "Value_at_risk": "Value at risk"})
    breached_lots = links.loc[as_bool(links["breaches_requirement"]), "lot_id"].nunique()
    value_at_risk = round(float(rem["value_at_risk"].sum()), 2)

    # ----- save -----
    save_table(scenario_df, "scenario_detection_results", folder=REPORT_DIR, sort_by="scenario_id")
    save_table(metrics_df, "evaluation_metrics", folder=REPORT_DIR)
    save_table(link_summary, "lot_linkage_summary", folder=REPORT_DIR)
    save_table(link_details, "alarm_lot_linkage_details", folder=REPORT_DIR, sort_by="alarm_id")

    rm, vm, cm = (metrics_df.iloc[i] for i in range(3))
    rule_table = scenario_df[scenario_df["expected_detected_by"] == "RULE_ENGINE"].copy()
    rule_table["detected"] = rule_table["detected"].map({True: "CAUGHT", False: "MISSED"})
    rule_table = rule_table[["scenario_id", "fault_type", "expected_detection", "detected", "matched_prediction_id",
                             "start_error_min", "end_error_min", "minutes_until_alarm_raised", "supporting_gap_id"]]
    val_table = scenario_df[scenario_df["expected_detected_by"] == "DATA_VALIDATOR"].copy()
    val_table["edge_case"] = val_table["fault_type"].map(EDGE_CASE_NAME).fillna(val_table["fault_type"])
    val_table["detected"] = val_table["detected"].map({True: "FOUND", False: "MISSED"})
    val_table = val_table[["scenario_id", "edge_case", "detected", "matched_prediction_id"]]
    ls = link_summary.iloc[0]

    L = ["# Evaluation report", "",
         "Compares the detectors' output with the ground truth. Generated by `pipeline/evaluate.py`.", "",
         "## 1. Summary", "", md_table(metrics_df[["detector", "true_positive", "false_positive", "false_negative",
                                                    "precision", "recall", "f1_score"]]), "",
         "## 2. Rule engine versus planted operational faults", "",
         f"Planted {r_exp}, caught {r_hit}, missed {r_exp - r_hit}, unmatched alarms {len(unmatched_alarms)}. "
         "One alarm can explain only one planted fault.", "", md_table(rule_table), "",
         "The engine raises an alarm when the bad period has ended, so \"minutes until alarm raised\" equals the "
         "fault duration. A streaming system would raise it earlier.", "",
         "## 3. Validator versus planted data-quality faults (the four edge cases)", "",
         f"Planted {v_exp}, found {v_hit}, unmatched findings {len(unmatched_issues)}.", "", md_table(val_table), "",
         "## 4. Affected-lot accuracy", "",
         "Expected links were recomputed from lot zone and stay times, separately from the rule engine.", "",
         f"- Expected alarm-lot links **{ls['expected_links']}**, present **{ls['present_links']}**, "
         f"missing **{ls['missing_links']}**, without basis **{ls['links_without_basis']}**",
         f"- Alarms fully linked: **{ls['alarms_fully_linked']} of {ls['alarms_with_lots_in_zone']}** "
         f"({ls['linkage_coverage_pct']}%)",
         f"- The missing links are exactly the planted FAULT-011 lots: **{'yes' if ls['missing_links_equal_planted'] else 'NO'}**", "",
         md_table(link_details[link_details["link_status"] != "COMPLETE"]), "",
         "## 5. Business impact", "",
         "- Alarms by severity: " + ", ".join(f"{k} {v}" for k, v in sev.items()),
         "- Alarms by status: " + ", ".join(f"{k} {v}" for k, v in alarm["status"].value_counts().items()),
         f"- Lots that breached their own limits: **{breached_lots}**",
         f"- Inspections: **{len(ins)}** (" + ", ".join(f"{k} {v}" for k, v in ins["result"].value_counts().items()) + ")",
         f"- Total value at risk: **{value_at_risk:,.2f}**", "", md_table(impact), ""]
    (REPORT_DIR / "evaluation_report.md").write_text("\n".join(L), encoding="utf-8")

    # ----- console -----
    print("\n======================================")
    print("          EVALUATION RESULT")
    print("======================================")
    print("\nScenario detection:")
    print(scenario_df[["scenario_id", "fault_type", "detected", "matched_prediction_id"]].to_string(index=False))
    print("\nMetrics:")
    print(metrics_df[["detector", "true_positive", "false_positive", "false_negative",
                      "precision", "recall", "f1_score"]].to_string(index=False))
    print("\nAlarm-to-lot linkage:")
    print(link_summary.T.to_string(header=False))
    print(f"\nBusiness impact: lots breached {breached_lots} | inspections {len(ins)} | "
          f"remediations {len(rem)} | value at risk {value_at_risk:,.2f}")
    print(f"\nReport: {REPORT_DIR / 'evaluation_report.md'}")


if __name__ == "__main__":
    main()