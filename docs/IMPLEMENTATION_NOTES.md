# Implementation notes

`data_dictionary_and_er_diagram.md` is the design written before the code. The finished project follows it with the differences below. All of them were checked against the generated files (`output/data`, `output/ground_truth`).

## What matches
All 15 input tables have exactly the columns, keys and relationships described in the data dictionary, except for the two points below.

## Differences

| Area | Design document | Implementation |
|---|---|---|
| `alarm_affected_lot` | 6 columns | 7 columns: the extra column `exposure_min` is the number of minutes the lot was actually exposed (never more than `overlap_minutes`). `breaches_requirement` is judged from it. |
| Ground truth (answer key) | One table `GroundTruth` with `gt_id`, `issue_type`, `sensor_id`, `lot_id`, `alarm_id`, `expected_decision`, ... | Stored as `output/ground_truth/fault_ground_truth.csv` with the columns `scenario_id`, `fault_type`, `entity_id`, `zone_id`, `start_ts`, `end_ts`, `expected_detection`, `expected_detected_by`, `details`. The lots of the alarm-without-links case are listed in `fault_ground_truth_lots.csv`. It is still a separate file that no detector reads. |
| Alarm status path | OPEN, ACKNOWLEDGED, UNDER_INSPECTION, REMEDIATED, CLOSED | The same path is used. Some alarms go ACKNOWLEDGED to CLOSED without an inspection, and alarms still open at the end of the study window stay open (no date is later than the window). |
| `sensor_gap.gap_cause` | POWER, NETWORK, SENSOR_FAULT, MAINTENANCE, UNKNOWN | Only UNKNOWN is generated, because the cause of a silent sensor is not known from the data. |
| Timestamps | UTC, ISO 8601 | UTC, written as `YYYY-MM-DD HH:MM:SS` (a space instead of `T`, no `Z`). Reading IDs use the compact form `RDG-<sensor>-<YYYYMMDDTHHMMSSZ>` as designed. |
| `inventory_lot.lot_status` | Lifecycle with DISCARDED | A lot whose DISCARD_LOT action is DONE ends with `lot_status = DISCARDED`. The status is the final one after remediation; there is no separate status-history table. |
| Alarm timing | not specified | An alarm's `end_ts` is the end of the last bad 5-minute slot, and alarms are raised when the bad period ends. |
| Alarm IDs | consecutive | Not consecutive: the outage alarm of the "gap treated as normal" case (FAULT-010) is deleted on purpose. |

## Known limitation
A sensor belongs to one zone for the whole study. If a sensor has several mappings, the rule engine uses the first one (lowest `map_id`) and does not resolve mappings by reading timestamp. The validator reports unjustified multi-zone sensors (FAULT-009). Sensors that move between zones over time are not generated or supported.