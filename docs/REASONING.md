# Reasoning: why the project is built this way

This page explains the problem, the assumptions, the main decisions and their trade-offs, how the project was tested, and how we know it works. Numbers are for seed 20261022 at full scale.

## 1. The problem

A warehouse has zones (frozen, cold, ambient, hot). Each zone has sensors for temperature, humidity, occupancy and doors, and holds lots of products with storage limits. The system must notice when a risk condition happens, raise an alarm, say which lots were affected, and record inspection and remediation.

There is no real data, so the project has to **create realistic data**, **damage it in known ways**, and show that the detection logic finds the damage. The required scale is 10 warehouses, 100 zones, 500 sensors, 1,000,000 readings and 10,000 lots, plus four labelled edge cases, a separate answer key, validation, exports and a reproducibility proof.

## 2. Assumptions

The brief does not settle these, so they were decided and written down:

- All timestamps are UTC. Readings arrive every 5 minutes from 2026-01-01 for about 8.7 days.
- A zone's temperature alarm uses the **strictest limit of any product that can be stored in that zone type**, because a lot in that zone must stay safe.
- A temperature alarm needs **both** temperature sensors of the zone to be out of range for at least 10 minutes. One sensor alone is not trusted.
- A sensor silent for more than 3 intervals (more than 15 minutes) is an outage.
- A sensor belongs to **one zone for the whole study**.
- A lot is affected by an alarm if it was stored in that zone while the alarm was active.
- Everything is synthetic. No outside data is used.

## 3. Key decisions and trade-offs

| Decision | Why | What it costs |
| --- | --- | --- |
| Steps pass CSV files to each other; SQL and JSON are only exports | Easy to open, check and compare byte by byte. No database server is needed to run it. | Not as realistic as a live database; no queries during the run. |
| One generator for starter and full scale; only the size setting changes | The small version really tests the same code as the big one, and runs in about 4 seconds. | None of significance. |
| Fixed seed, and `run_all.py` stops if another seed is given | The result must be the same every time. | You cannot explore other seeds without editing `config.py`. |
| Run the rule engine on **clean** data first and require 0 alarms | Proves the engine does not invent problems before any fault is planted. | One extra step in every run. |
| Answer key stored separately; the validator never reads it | Otherwise the detectors could cheat and the score would mean nothing. | The answer key has its own layout, not the one in the design. |
| Faults are planted by two modules: `inject_faults` damages the data, `inject_defects` damages the rule engine's own output | Edge cases 010 and 011 are about missing alarms and missing links, which only exist after the engine has run. | A bit harder to follow at first. |
| Two checkers: the rule engine finds operational problems, the validator finds data-quality problems | Each is judged on what it is meant to find. | Two sets of logic to maintain. |
| A second, independent program recomputes lot verdicts from the raw readings | A check that shares code with the thing it checks proves little. | More code, and a slightly longer run. |
| Drift blames the sensor that moved away from its **own usual level** | Blaming the one that looked "higher" could pick the wrong sensor. | Needs a few more lines than the simple rule. |
| One sensor is mapped to one zone for the whole study | Keeps the rules simple and the data clear. | Sensors that move between zones over time are not supported (see section 6). |

## 4. How it was tested

Testing is built into the run, in this order:

1. **Clean-data check.** Before any fault is planted: 0 alarms, 0 gaps. If not, the run stops.
2. **Fault detection.** The rule engine must find the seven operational faults (FAULT-001 to 007).
3. **Validation.** 107 integrity checks (keys, required fields, foreign keys, allowed values, ranges, dates, business rules) plus four data-quality detectors for the four edge cases. If an integrity check fails, the run stops with an error code.
4. **Scoring against the answer key.** Precision, recall and F1, with one-to-one matching, for the rule engine, the validator and both together.
5. **Independent cross-check** of the 330 expected alarm-to-lot links.
6. **SQL check.** The SQL export is loaded into SQLite with foreign keys on; the row counts of all 15 tables must match the CSVs.
7. **Reproducibility.** The whole project is built twice and every output file is compared by row count and SHA-256 checksum.

Testing also found real problems, which were fixed:
- At starter scale the drift fault blamed the wrong sensor. This led to the "own usual level" rule above.
- A review found that a lot's exposure could be larger than its time in the zone, that a discarded lot kept its old status, that the validator did not return an error code on failure, and that some value checks were missing. All four were fixed, including a new group of business-rule checks in the validator.

## 5. How we know it works

- Clean data gives 0 alarms and 0 gaps.
- Rule engine: 7 found, 0 false, 0 missed. Validator: 4 found, 0 false, 0 missed.
- 107 of 107 integrity checks pass.
- 330 alarm-to-lot links are expected; 299 are present and 31 are missing, which are exactly the lots of the planted FAULT-011.
- Two complete builds give 47 of 47 identical files.
- The SQL loads with no foreign-key violations.

The reports are saved in `evidence/` so they can be read without running anything.

## 6. Limitations

- The 100% score applies to **clear, planted faults**. It does not show that subtle real-world problems would be caught.
- A sensor has one zone for the whole study. If a sensor has several mappings, the first is used. The validator reports unjustified ones, but the rule engine does not change zone by time.
- `sensor_gap.gap_cause` is always UNKNOWN.
- A lot has no status history. A discarded lot just ends with the status DISCARDED.
- `alarm_affected_lot` has one extra column, `exposure_min`.
- Alarm IDs are not consecutive because the FAULT-010 alarm is deleted on purpose.

More detail is in `docs/IMPLEMENTATION_NOTES.md`. The README explains how to run everything.