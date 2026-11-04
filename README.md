# Warehouse Monitoring – Synthetic Data Generator and Alarm Pipeline

An end-to-end Python-based Warehouse Monitoring System that generates synthetic warehouse data, monitors temperature, humidity, occupancy and door events, detects risk conditions, generates alarms and validates data quality.

The project also evaluates detection results against a separate ground-truth dataset and produces CSV, JSON and SQL outputs.

**Data source:** 100% synthetic. No external or public datasets are downloaded or redistributed. This is documented in `output/manifest.json` (`external_data: none`).

---

## 1. Project Objectives

The main objectives are to:

- Generate realistic synthetic warehouse master and transaction data.
- Monitor temperature, humidity, occupancy and door events.
- Identify abnormal conditions using predefined business rules.
- Generate alarms and identify affected inventory lots.
- Maintain alarm history, inspections and remediation records.
- Introduce controlled faults and data-quality edge cases.
- Validate data integrity and detect data-quality issues.
- Evaluate detection performance using ground truth.
- Export datasets into CSV, JSON and SQL formats.
- Verify deterministic and reproducible data generation.

---

## 2. Technology Stack

| Component            | Technology     |
| -------------------- | -------------- |
| Programming Language | Python 3.10+   |
| Data Processing      | Pandas         |
| Numerical Operations | NumPy          |
| Data Storage         | CSV            |
| Data Export          | JSON, SQL      |
| SQL Validation       | SQLite         |
| Reproducibility      | SHA-256        |
| Version Control      | Git and GitHub |

---

## 3. System Requirements

Before running the project, make sure you have:

- Python 3.10 or newer.
- Git installed.
- Internet access for the initial repository clone and package installation.
- At least 2 GB of free disk space (one full build writes about 400 MB; the reproducibility check builds twice).

No external database server is required.

---

## 4. How to Download and Run the Project

Follow these steps to execute the complete project.

### Step 1: Clone the GitHub Repository

Open PowerShell or Command Prompt and execute:

```powershell
git clone https://github.com/Saishiva-2003/Warehouse-monitoring-System.git
```

Navigate to the project directory:

```powershell
cd Warehouse-monitoring-System
```

### Step 2: Create a Python Virtual Environment

Create an isolated Python environment:

```powershell
python -m venv venv
```

Activate the environment.

**Windows PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

**Windows Command Prompt:**

```cmd
venv\Scripts\activate.bat
```

**Linux / macOS:**

```bash
source venv/bin/activate
```

### Step 3: Install Required Dependencies

Install the required Python libraries:

```powershell
pip install -r requirements.txt
```

The project primarily uses:

- pandas
- numpy

### Step 4: Execute the Complete Pipeline

Run the following command from the project root directory:

```powershell
python run_all.py --seed 20261022 --scale full
```

This command executes the complete warehouse monitoring pipeline.

**Full-scale configuration:**

| Entity                     | Generated volume |
| -------------------------- | ---------------: |
| Warehouses                 |               10 |
| Zones                      |              100 |
| Sensors                    |              500 |
| Sensor readings (baseline) |        1,000,000 |
| Inventory lots             |           10,000 |
| Storage requirements       |                8 |

The full-scale execution generally takes approximately 30–50 seconds, depending on the system.

**Important:** The project uses the fixed seed `20261022`. The generator stops if a different seed is supplied.

### Step 5: Show the Total Warehouses, Zones, Sensors and Readings

After the run finishes, execute:

```powershell
python -m pipeline.show_summary
```

It prints the number of warehouses, zones, sensors, readings, door events and lots, the zone and sensor types, and the first and last reading time.

### Step 6: Generate a Smaller Dataset (Optional)

For a quick trial, use the starter configuration:

```powershell
python run_all.py --seed 20261022 --scale starter
```

Starter configuration:

| Entity                     | Generated volume |
| -------------------------- | ---------------: |
| Warehouses                 |                2 |
| Zones                      |               10 |
| Sensors                    |               50 |
| Sensor readings (baseline) |           20,000 |
| Inventory lots             |              200 |

Both starter and full configurations use the same generation logic. Only the dataset scale changes.

### Step 7: Verify the Generated Output

After successful execution, open the `output/` directory.

The pipeline generates:

- CSV datasets.
- JSON exports.
- SQL schema and seed scripts.
- Ground-truth files.
- Validation reports.
- Evaluation reports.
- Lot-exposure cross-check reports.
- Dataset manifest.
- Reproducibility report.

Refer to the Folder Structure section below for the output locations.

---

## 5. Complete Pipeline Execution

The `run_all.py` script executes the following 11 steps in sequence.

| Step | Module                     | Description                                                                                                         |
| ---- | -------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 1    | `generate_master.py`       | Generates warehouses, zones, sensors, sensor-zone mappings and storage requirements.                                |
| 2    | `generate_lots.py`         | Generates inventory lots and assigns them to compatible storage zones.                                              |
| 3    | `generate_readings.py`     | Generates healthy sensor readings at five-minute intervals and normal door events.                                  |
| 4    | `rule_engine.py`           | Runs the rule engine on clean data. The expected result is zero alarms and zero sensor gaps.                        |
| 5    | `inject_faults.py`         | Introduces labelled fault scenarios and creates ground-truth records.                                               |
| 6    | `rule_engine.py`           | Processes the fault-injected data and generates alarms, alarm history, affected lots, inspections and remediations. |
| 7    | `inject_defects.py`        | Deliberately removes the FAULT-010 outage alarm and the FAULT-011 affected-lot links.                               |
| 8    | `validate.py`              | Performs 107 integrity checks and four data-quality detections without accessing ground truth.                      |
| 9    | `evaluate.py`              | Compares detected faults against the ground-truth records.                                                          |
| 10   | `evaluate_lot_exposure.py` | Independently recomputes lot exposure and compares the results with saved alarm-lot relationships.                  |
| 11   | `export.py`                | Generates JSON, SQL and manifest exports.                                                                           |

The pipeline follows this execution sequence:

```text
Generate Clean Data
        |
        v
Rule Engine on Clean Data
        |
        v
Clean Data Verification
        |
        v
Inject Labelled Faults
        |
        v
Rule Engine on Fault-Injected Data
        |
        v
Inject Monitoring Defects
        |
        v
Data Integrity Validation
        |
        v
Evaluate Against Ground Truth
        |
        v
Independent Lot Exposure Check
        |
        v
Export CSV / JSON / SQL
        |
        v
Generate Final Reports
```

Alarm outcomes are derived from business rules and source records. They are not randomly assigned.

---

## 6. Labelled Fault Scenarios

The project includes 11 labelled fault scenarios.

| Fault ID  | Scenario                                               | Detection method |
| --------- | ------------------------------------------------------ | ---------------- |
| FAULT-001 | Temperature excursion                                  | Rule engine      |
| FAULT-002 | Humidity excursion                                     | Rule engine      |
| FAULT-003 | Door left open                                         | Rule engine      |
| FAULT-004 | Temperature sensor outage                              | Rule engine      |
| FAULT-005 | Humidity sensor outage                                 | Rule engine      |
| FAULT-006 | Temperature sensor drift                               | Rule engine      |
| FAULT-007 | High occupancy                                         | Rule engine      |
| FAULT-008 | Lot assigned to an incompatible zone                   | Data validator   |
| FAULT-009 | Sensor mapped to multiple zones without rationale      | Data validator   |
| FAULT-010 | Reading gap with its outage alarm deliberately missing | Data validator   |
| FAULT-011 | Alarm not linked to affected inventory lots            | Data validator   |

The ground-truth dataset is stored separately from the input data and is used for evaluation, not by the detection logic.

---

## 7. Generated Output and Folder Structure

After execution, the project generates the following output structure:

```text
Warehouse-monitoring-System/
│
├── config.py
├── utils.py
├── run_all.py
├── requirements.txt
├── README.md
│
├── pipeline/
│   ├── timeline.py
│   ├── generate_master.py
│   ├── generate_lots.py
│   ├── generate_readings.py
│   ├── rule_engine.py
│   ├── inject_faults.py
│   ├── inject_defects.py
│   ├── validate.py
│   ├── evaluate.py
│   ├── evaluate_lot_exposure.py
│   ├── export.py
│   ├── repro_check.py
│   ├── test_data_integrity.py
│   └── show_summary.py
│
├── docs/
│   ├── data_dictionary_and_er_diagram.md
│   └── IMPLEMENTATION_NOTES.md
│
├── evidence/
│   └── Previous full-run reports
│
├── output/
│   ├── data/
│   │   └── Generated CSV datasets
│   │
│   ├── clean_data/
│   │   └── Clean baseline datasets
│   │
│   ├── ground_truth/
│   │   └── Fault ground-truth files
│   │
│   ├── json/
│   │   └── JSON exports
│   │
│   ├── sql/
│   │   ├── schema.sql
│   │   └── seed.sql
│   │
│   ├── reports/
│   │   ├── validation_report.md
│   │   ├── evaluation_report.md
│   │   └── Independent lot exposure reports
│   │
│   ├── manifest.json
│   └── reproducibility_report.md
│
├── AI_USE.md
└── PROMPT_HISTORY.md
```

**Note:** The `output/` directory is generated when the pipeline runs and is not included in the Git repository. The `evidence/` directory contains retained reports from the full-scale execution.

---

## 8. How to Check the Results

After executing:

```powershell
python run_all.py --seed 20261022 --scale full
```

Review the following reports.

| Report                 | Location                                              | Purpose                                                                      |
| ---------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| Validation Report      | `output/reports/validation_report.md`                 | Displays integrity checks and data-quality findings.                         |
| Evaluation Report      | `output/reports/evaluation_report.md`                 | Shows which injected faults were detected.                                   |
| Lot Exposure Report    | `output/reports/independent_lot_exposure_summary.csv` | Shows independent lot-exposure verification.                                 |
| Manifest               | `output/manifest.json`                                | Records seed, scale, versions, row counts, file sizes and SHA-256 checksums. |
| Reproducibility Report | `output/reproducibility_report.md`                    | Shows the results of the two-run comparison.                                 |

### Expected Evaluation Results

For the full-scale dataset using seed `20261022`:

| Detector       | True Positives | False Positives | False Negatives |
| -------------- | -------------: | --------------: | --------------: |
| Rule Engine    |              7 |               0 |               0 |
| Data Validator |              4 |               0 |               0 |
| Combined       |             11 |               0 |               0 |

The expected detection precision, recall and F1 score are 100% for these deliberately planted scenarios.

### Data Integrity Results

- 107 out of 107 integrity checks pass.
- Four data-quality findings are identified.
- All four labelled edge cases are detected.
- The clean baseline produces zero alarms and zero sensor gaps.

### Alarm-to-Lot Link Verification

| Description                 | Count |
| --------------------------- | ----: |
| Expected alarm-to-lot links |   330 |
| Present links               |   299 |
| Deliberately missing links  |    31 |

The 31 missing links are intentionally introduced for FAULT-011.

The independent lot-exposure process independently recomputes the 330 expected links and verifies the breach verdicts for saved links.

### SQL Export Verification

The SQL export is loaded into SQLite with foreign-key enforcement enabled.

- 15 table row counts are compared with the CSV datasets.
- No foreign-key violations are expected.
- Primary and foreign keys are defined in `schema.sql`.

---

## 9. Reproducibility Verification

To verify that the same seed produces identical results, run:

```powershell
python -m pipeline.repro_check --scale full
```

The reproducibility module builds the dataset twice and compares the generated files using row counts and SHA-256 checksums.

**Expected result:** 47 out of 47 output files are identical.

This demonstrates deterministic generation for the tested configuration.

---

## 10. Additional Validation Command

An optional standalone data integrity check can be executed using:

```powershell
python -m pipeline.test_data_integrity
```

This checks data integrity aspects such as:

- Primary key uniqueness.
- Mandatory fields.
- Foreign-key relationships.
- Inventory lot calculations.
- Sensor mapping overlaps.
- Data consistency.

Run it from the project root directory.

---

## 11. Additional Execution Options

The pipeline supports the following execution options:

**Skip JSON and SQL exports:**

```powershell
python run_all.py --seed 20261022 --scale full --skip-export
```

**Display detailed execution logs:**

```powershell
python run_all.py --seed 20261022 --scale full --verbose
```

**Run the reproducibility test:**

```powershell
python -m pipeline.repro_check --scale full
```

---

## 12. Business Rules and Assumptions

- Sensor readings are generated every five minutes.
- All timestamps use UTC.
- Temperature alarms require both temperature sensors in a zone to be out of range for at least 10 minutes.
- Sensor drift is detected when paired temperature sensors differ by more than 1°C for at least 60 minutes.
- Sensor outages are identified when a sensor is silent for more than three reading intervals.
- Door alarms are generated when a door remains open longer than the applicable zone limit.
- Affected inventory lots are determined by the overlap between alarm periods and lot storage periods.
- Lot exposure and verdicts are calculated using product-specific storage requirements.
- Alarm state changes are recorded through alarm history.
- The monitoring system uses predefined rules to determine alarm outcomes.

For detailed implementation differences and limitations, refer to `docs/IMPLEMENTATION_NOTES.md`.

---

## 13. Known Limitations

- The detection score reflects deliberately strong planted faults and does not guarantee the same performance on subtle real-world anomalies.
- `alarm_affected_lot` includes an additional `exposure_min` field.
- Some alarms transition from ACKNOWLEDGED to CLOSED without inspection.
- Alarm IDs are not consecutive because the FAULT-010 outage alarm is deliberately deleted.
- `sensor_gap.gap_cause` is currently recorded as UNKNOWN.
- Sensors moving between zones over time are not supported by the current rule engine.
- The answer key uses a separate ground-truth file structure.

Additional details are documented in `docs/IMPLEMENTATION_NOTES.md`.

---

## 14. Development Documentation

The following documents provide additional project information:

- `PROMPT_HISTORY.md` – Key prompts used during AI-assisted project planning and development.
- `AI_USE.md` – Explanation of how AI assistance was used.
- `docs/data_dictionary_and_er_diagram.md` – Entity and attribute definitions and the ER diagram.
- `docs/IMPLEMENTATION_NOTES.md` – Implementation deviations and known limitations.

---

## 15. Important Note Before Rebuilding

The `run_all.py` pipeline recreates its output directories during execution. Keep a backup of any generated results you want to retain before starting another build.

To rebuild the complete dataset:

```powershell
python run_all.py --seed 20261022 --scale full
```

---

## 16. Conclusion

The Warehouse Monitoring Synthetic Data Generator provides an end-to-end implementation for synthetic warehouse data generation, rule-based monitoring, fault injection, data-quality validation, alarm evaluation, independent lot-exposure verification and reproducible exports.

The project demonstrates how warehouse monitoring requirements can be translated into structured data models, automated business rules, validation mechanisms and measurable evaluation results.

**Repository:** [https://github.com/Saishiva-2003/Warehouse-monitoring-System](https://github.com/Saishiva-2003/Warehouse-monitoring-System)

**Data provenance:** Entirely synthetic.