# Warehouse Monitoring: ER Diagram and Data Dictionary

Synthetic dataset design. Seed: 20261022. Scale (warehouses, zones, sensors, readings, lots) is a parameter.

## 1. How to read this

- **PK** = primary key, **FK** = foreign key, **1:N** = one-to-many, **N:M** = many-to-many (needs a bridge table).
- 10 required entities plus 4 supporting tables (bridges, history, gaps) that the rules require.
- Ground truth lives in its own file and is never joined into input tables.

## 2. ER diagram

```
Warehouse (1) ----< (N) Zone (1) ----< (N) SensorZoneMap >---- (1) Sensor
                          |                                          |
                          |                                          +----< SensorReading
                          |                                          +----< SensorGap
                          +----< DoorEvent
                          |
                          +----< LotZoneAssignment >---- InventoryLot >---- (N:1) StorageRequirement
                          |
                          +----< Alarm (1) ----< AlarmStatusHistory
                                  |
                                  +----< AlarmAffectedLot >---- InventoryLot
                                  |
                                  +----< Inspection (1) ----< Remediation
                                                |
                                                +-- inspects a specific InventoryLot

GroundTruth (separate file): references zone_id / sensor_id / lot_id / alarm_id by value only.
```

## 3. Relationships and cardinality

| Parent | Child | Cardinality | Optional? | Notes |
| --- | --- | --- | --- | --- |
| Warehouse | Zone | 1:N | No | Zone must belong to one warehouse |
| Zone | Sensor (via SensorZoneMap) | N:M | No | Normally 1 sensor : 1 zone. Mapping to 2+ zones is allowed only with a rationale (edge case if missing) |
| Sensor | SensorReading | 1:N | No | One reading = one sensor, one metric, one timestamp |
| Sensor | SensorGap | 1:N | Yes | Explicit record of every outage |
| Zone | DoorEvent | 1:N | Yes | Door belongs to a zone |
| StorageRequirement | InventoryLot | 1:N | No | Lot must follow one requirement |
| InventoryLot | Zone (via LotZoneAssignment) | N:M over time | No | Lot can move; each stay has start and end |
| Zone | Alarm | 1:N | No | Alarm is raised for one zone |
| Sensor | Alarm | 1:N | Yes | Null for door or occupancy alarms driven by DoorEvent |
| Alarm | InventoryLot (via AlarmAffectedLot) | N:M | Yes | Empty only in the labelled edge case |
| Alarm | Inspection | 1:N | Yes | One inspection per affected lot |
| Inspection | Remediation | 1:N | Yes | A failed inspection leads to one or more actions |

## 4. ID conventions

| Entity | Format | Example |
| --- | --- | --- |
| Warehouse | WH-NNN | WH-001 |
| Zone | ZONE-\<warehouse\_id>-NNN | ZONE-WH-001-001 |
| Sensor | SNS-\<zone\_id>-\<TYPE>-NN (TYPE = TEMP, HUM, OCC, DOOR) | SNS-ZONE-WH-001-001-TEMP-01 |
| SensorReading | RDG-\<sensor\_id>-\<YYYYMMDDTHHMMSSZ> | RDG-SNS-ZONE-WH-001-001-TEMP-01-20261022T100500Z |
| InventoryLot | LOT-2026-NNNNNN | LOT-2026-000001 |
| Others | PREFIX-NNNNNN | REQ-0001, DOR-000001, ALM-000001, INS-000001, REM-000001 |

IDs are zero-padded, immutable, and must match exactly across every file. All timestamps are UTC, ISO 8601.

## 5. Data dictionary

### 5.1 Warehouse

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| warehouse\_id | string | Y | WH-NNN | PK | Regex ^WH-\\d{3}$ |
| name | string | Y | free text | Y | Not empty |
| city | string | Y | free text | N | Not empty |
| timezone | string | Y | IANA name, e.g. Asia/Kolkata | N | Valid tz |
| status | enum | Y | ACTIVE, MAINTENANCE, CLOSED | N | In list |
| opened\_date | date | Y | YYYY-MM-DD | N | Not in future |

### 5.2 Zone

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| zone\_id | string | Y | ZONE-\<wh>-NNN | PK | Prefix equals warehouse\_id |
| warehouse\_id | string | Y | existing Warehouse | N | FK |
| zone\_name | string | Y | free text | N | Not empty |
| zone\_type | enum | Y | FROZEN, COLD, AMBIENT, HOT | N | In list |
| design\_temp\_min\_c | float | Y | degrees C | N | Less than design\_temp\_max\_c |
| design\_temp\_max\_c | float | Y | degrees C | N | Matches zone\_type band |
| design\_hum\_min\_pct | float | Y | percent RH | N | 0 to 100 |
| design\_hum\_max\_pct | float | Y | percent RH | N | Greater than min |
| max\_occupancy | int | Y | people | N | Greater than 0 |
| area\_sqm | float | Y | square metres | N | Greater than 0 |
| effective\_from | date | Y | YYYY-MM-DD | N | Not before warehouse opened\_date |
| effective\_to | date | N | YYYY-MM-DD | N | Null or after effective\_from |

Zone type bands: FROZEN -25 to -15, COLD 2 to 8, AMBIENT 15 to 30, HOT 30 to 45 (degrees C).

### 5.3 Sensor

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| sensor\_id | string | Y | SNS-\<zone>-\<TYPE>-NN | PK | Regex matches type |
| sensor\_type | enum | Y | TEMP, HUM, OCC, DOOR | N | In list |
| unit | enum | Y | C, PCT\_RH, COUNT, BOOL | N | Must match sensor\_type |
| sample\_interval\_sec | int | Y | seconds, e.g. 300 | N | Greater than 0 |
| install\_date | date | Y | YYYY-MM-DD | N | Not in future |
| status | enum | Y | ACTIVE, FAULTY, RETIRED | N | In list |
| drift\_bias\_per\_day | float | N | unit per day | N | Used only by the generator; null for healthy sensors |

Home zone is stored in SensorZoneMap, not here, so mapping history is preserved.

### 5.4 SensorZoneMap (bridge)

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| map\_id | string | Y | MAP-NNNNNN | PK | Regex |
| sensor\_id | string | Y | existing Sensor | N | FK |
| zone\_id | string | Y | existing Zone | N | FK |
| effective\_from | datetime | Y | UTC | N | Not null |
| effective\_to | datetime | N | UTC | N | Null (open) or after effective\_from |
| rationale | string | N | e.g. SHARED\_AISLE | N | Required if the sensor has 2+ overlapping active zones. Missing rationale = edge case |

### 5.5 SensorReading

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| reading\_id | string | Y | RDG-\<sensor>-\<ts> | PK | Embedded ts equals reading\_ts |
| sensor\_id | string | Y | existing Sensor | N | FK |
| reading\_ts | datetime | Y | UTC | N | Within study window |
| value | float | Y | unit per sensor | N | Temp -40 to 60, humidity 0 to 100, occupancy 0 or more |
| quality\_flag | enum | Y | GOOD, SUSPECT, IMPUTED | N | In list |

Unique constraint: (sensor\_id, reading\_ts). Missing intervals are NOT filled in; they appear in SensorGap.

### 5.6 SensorGap

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| gap\_id | string | Y | GAP-NNNNNN | PK | Regex |
| sensor\_id | string | Y | existing Sensor | N | FK |
| gap\_start | datetime | Y | UTC | N | Before gap\_end |
| gap\_end | datetime | Y | UTC | N | After gap\_start |
| gap\_minutes | float | Y | minutes | N | Equals (gap\_end - gap\_start) in minutes |
| gap\_cause | enum | Y | POWER, NETWORK, SENSOR\_FAULT, MAINTENANCE, UNKNOWN | N | In list |

Rule: any silence longer than 3 x sample\_interval\_sec must have a SensorGap row. A gap treated as normal is an edge case.

### 5.7 DoorEvent

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| door\_event\_id | string | Y | DOR-NNNNNN | PK | Regex |
| zone\_id | string | Y | existing Zone | N | FK |
| door\_id | string | Y | e.g. D1, D2 | N | Not empty |
| opened\_ts | datetime | Y | UTC | N | Before closed\_ts |
| closed\_ts | datetime | N | UTC | N | Null only if event is still open |
| open\_duration\_min | float | Y | minutes | N | Derived: (closed\_ts - opened\_ts) |
| event\_type | enum | Y | NORMAL, PROLONGED, FORCED, AJAR | N | PROLONGED if duration exceeds limit |

### 5.8 StorageRequirement

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| requirement\_id | string | Y | REQ-NNNN | PK | Regex |
| product\_category | string | Y | e.g. VACCINE, DAIRY, FROZEN\_FOOD, BISCUITS | Y | Not empty |
| required\_zone\_type | enum | Y | FROZEN, COLD, AMBIENT, HOT | N | In list |
| temp\_min\_c | float | Y | degrees C | N | Less than temp\_max\_c |
| temp\_max\_c | float | Y | degrees C | N | Within the zone type band |
| hum\_min\_pct | float | N | percent RH | N | 0 to 100 |
| hum\_max\_pct | float | N | percent RH | N | Greater than hum\_min\_pct |
| max\_excursion\_min | int | Y | minutes allowed out of range | N | 0 or more |
| max\_door\_open\_min | int | Y | minutes | N | Greater than 0 |
| effective\_from | date | Y | YYYY-MM-DD | N | Not null |
| effective\_to | date | N | YYYY-MM-DD | N | Null or after effective\_from |

### 5.9 InventoryLot

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| lot\_id | string | Y | LOT-2026-NNNNNN | PK | Regex |
| requirement\_id | string | Y | existing StorageRequirement | N | FK |
| quantity\_units | int | Y | units | N | Greater than 0 |
| unit\_value | float | Y | currency per unit | N | Greater than 0 |
| lot\_value | float | Y | currency | N | Derived: quantity\_units x unit\_value |
| received\_ts | datetime | Y | UTC | N | Before or equal to first assignment start |
| expiry\_date | date | Y | YYYY-MM-DD | N | After received\_ts |
| lot\_status | enum | Y | RECEIVED, STORED, ON\_HOLD, QUARANTINED, SHIPPED, DISCARDED | N | Lifecycle rules in section 6 |

### 5.10 LotZoneAssignment (bridge with dwell time)

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| assignment\_id | string | Y | ASG-NNNNNN | PK | Regex |
| lot\_id | string | Y | existing InventoryLot | N | FK |
| zone\_id | string | Y | existing Zone | N | FK |
| stored\_from | datetime | Y | UTC | N | Not null |
| stored\_until | datetime | N | UTC | N | Null (still stored) or after stored\_from |
| dwell\_hours | float | N | hours | N | Derived: (stored\_until - stored\_from) |
| compatible\_flag | bool | Y | true / false | N | Derived: zone\_type equals requirement.required\_zone\_type |

Rule: a lot cannot have two overlapping assignments. compatible\_flag = false is the edge case "lot in incompatible zone".

### 5.11 Alarm

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| alarm\_id | string | Y | ALM-NNNNNN | PK | Regex |
| zone\_id | string | Y | existing Zone | N | FK |
| sensor\_id | string | N | existing Sensor | N | FK; null for door-driven alarms |
| rule\_code | enum | Y | TEMP\_HIGH, TEMP\_LOW, HUM\_HIGH, HUM\_LOW, OCCUPANCY\_HIGH, DOOR\_OPEN\_LONG, SENSOR\_OUTAGE, SENSOR\_DRIFT | N | In list |
| severity | enum | Y | LOW, MEDIUM, HIGH, CRITICAL | N | Derived from peak deviation and duration |
| start\_ts | datetime | Y | UTC | N | Before end\_ts |
| end\_ts | datetime | N | UTC | N | Null while alarm is open |
| peak\_value | float | Y | unit per rule | N | Beyond threshold |
| threshold\_value | float | Y | unit per rule | N | Equals the limit in effect |
| duration\_min | float | Y | minutes | N | Derived: (end\_ts - start\_ts) |
| status | enum | Y | OPEN, ACKNOWLEDGED, UNDER\_INSPECTION, REMEDIATED, CLOSED | N | Current state; history in AlarmStatusHistory |

### 5.12 AlarmStatusHistory

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| history\_id | string | Y | AST-NNNNNN | PK | Regex |
| alarm\_id | string | Y | existing Alarm | N | FK |
| from\_status | enum | N | same list as Alarm.status | N | Null for first record |
| to\_status | enum | Y | same list as Alarm.status | N | Legal transition only |
| changed\_ts | datetime | Y | UTC | N | Not before previous change |
| changed\_by\_role | enum | Y | SYSTEM, PLANT\_OPERATOR, QUALITY\_ENGINEER, PRODUCTION\_PLANNER, OT\_ADMIN | N | In list |

### 5.13 AlarmAffectedLot (bridge)

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| alarm\_id | string | Y | existing Alarm | PK part | FK |
| lot\_id | string | Y | existing InventoryLot | PK part | FK |
| overlap\_start | datetime | Y | UTC | N | Later of alarm start and stored\_from |
| overlap\_end | datetime | Y | UTC | N | Earlier of alarm end and stored\_until |
| overlap\_minutes | float | Y | minutes | N | Derived: overlap\_end - overlap\_start, greater than 0 |
| breaches\_requirement | bool | Y | true / false | N | Derived by comparing the reading to the lot's own limits |

Composite PK (alarm\_id, lot\_id). A lot is listed only if it was in that zone during the alarm window.

### 5.14 Inspection

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| inspection\_id | string | Y | INS-NNNNNN | PK | Regex |
| alarm\_id | string | Y | existing Alarm | N | FK |
| lot\_id | string | Y | existing InventoryLot | N | FK; pair must exist in AlarmAffectedLot |
| inspector\_role | enum | Y | QUALITY\_ENGINEER, PLANT\_OPERATOR | N | In list |
| inspected\_ts | datetime | Y | UTC | N | After alarm start\_ts |
| result | enum | Y | PASS, CONDITIONAL, FAIL | N | PASS if overlap\_minutes within max\_excursion\_min |
| notes | string | N | free text | N | Max 500 characters |

### 5.15 Remediation

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| remediation\_id | string | Y | REM-NNNNNN | PK | Regex |
| inspection\_id | string | Y | existing Inspection | N | FK |
| lot\_id | string | Y | existing InventoryLot | N | FK; equals Inspection.lot\_id |
| action\_type | enum | Y | RELEASE, RELOCATE\_LOT, DISCARD\_LOT, REPAIR\_EQUIPMENT, RECALIBRATE\_SENSOR, REPLACE\_SENSOR | N | In list |
| action\_ts | datetime | Y | UTC | N | After inspected\_ts |
| owner\_role | enum | Y | MAINTENANCE, QUALITY\_ENGINEER, PRODUCTION\_PLANNER, OT\_ADMIN | N | In list |
| units\_affected | int | Y | units | N | At most the lot quantity |
| value\_at\_risk | float | Y | currency | N | Derived: units\_affected x unit\_value |
| status | enum | Y | PLANNED, IN\_PROGRESS, DONE | N | Legal transition only |

### 5.16 GroundTruth (separate file, never an input)

| Field | Type | Req | Allowed values / unit | Unique | Validation |
| --- | --- | --- | --- | --- | --- |
| gt\_id | string | Y | GT-NNNNNN | PK | Regex |
| issue\_type | enum | Y | TEMP\_EXCURSION, DOOR\_EXCURSION, SENSOR\_OUTAGE, SENSOR\_DRIFT, INCOMPATIBLE\_LOT\_ZONE, SENSOR\_MULTI\_ZONE\_NO\_RATIONALE, GAP\_TREATED\_AS\_NORMAL, ALARM\_NOT\_LINKED\_TO\_LOTS | N | In list |
| zone\_id | string | N | zone affected | N | Value reference only |
| sensor\_id | string | N | sensor affected | N | Value reference only |
| lot\_id | string | N | lot affected | N | Value reference only |
| alarm\_id | string | N | expected alarm | N | Null if no alarm should exist |
| start\_ts | datetime | N | UTC | N | Before end\_ts |
| end\_ts | datetime | N | UTC | N | After start\_ts |
| expected\_decision | string | Y | e.g. RAISE\_ALARM, FLAG\_GAP, REJECT\_ASSIGNMENT | N | Not empty |

## 6. Lifecycles (allowed transitions)

| Object | Allowed path |
| --- | --- |
| Alarm | OPEN, then ACKNOWLEDGED, then UNDER\_INSPECTION, then REMEDIATED, then CLOSED |
| InventoryLot | RECEIVED, then STORED, then (ON\_HOLD, then QUARANTINED) optional, then SHIPPED or DISCARDED |
| Remediation | PLANNED, then IN\_PROGRESS, then DONE |
| Sensor | ACTIVE, then FAULTY, then ACTIVE or RETIRED |

Every transition writes a new history row. Old rows are never edited.

## 7. Decision rules (what creates what)

| Step | Rule |
| --- | --- |
| Temperature alarm | Reading outside the zone's limit for longer than the shortest max\_excursion\_min among lots present creates TEMP\_HIGH or TEMP\_LOW |
| Door alarm | open\_duration\_min greater than the strictest max\_door\_open\_min creates DOOR\_OPEN\_LONG |
| Outage alarm | A SensorGap longer than 3 x sample\_interval\_sec creates SENSOR\_OUTAGE |
| Affected lots | Lots in the alarm zone where time windows overlap, written to AlarmAffectedLot |
| Inspection | One per affected lot with breaches\_requirement = true |
| Remediation | FAIL leads to DISCARD\_LOT or RELOCATE\_LOT; PASS leads to RELEASE; equipment alarms also add REPAIR\_EQUIPMENT or RECALIBRATE\_SENSOR |

## 8. Edge cases and how they show up

| Edge case | How it is planted | Ground truth label |
| --- | --- | --- |
| Lot in incompatible zone | Assignment with compatible\_flag = false | INCOMPATIBLE\_LOT\_ZONE |
| Sensor in multiple zones, no rationale | Two active SensorZoneMap rows, rationale null | SENSOR\_MULTI\_ZONE\_NO\_RATIONALE |
| Reading gap treated as normal | Gap exists, no SENSOR\_OUTAGE alarm raised | GAP\_TREATED\_AS\_NORMAL |
| Alarm not linked to lots | Alarm with an overlapping lot but no AlarmAffectedLot row | ALARM\_NOT\_LINKED\_TO\_LOTS |

## 9. Validation checks to implement

1. All PKs unique and match their regex.
2. Every FK resolves to a parent row.
3. All enum values are in the allowed list.
4. start is before end on every time pair.
5. Derived fields recomputed and equal (duration, dwell, lot\_value, value\_at\_risk, overlap\_minutes).
6. Lifecycle transitions are legal.
7. No duplicate (sensor\_id, reading\_ts) and no overlapping lot assignments.
8. Every planted anomaly has a GroundTruth row, and no unlabelled anomalies exist.