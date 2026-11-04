# Reproducibility report

The whole pipeline was run twice with seed 20261022 and scale full. Row counts and SHA-256 checksums (first 16 characters shown) were compared for every output file.

**Result: ALL 47 FILES IDENTICAL**

| File | Rows run 1 | Rows run 2 | SHA-256 run 1 | SHA-256 run 2 | Identical |
|---|---|---|---|---|---|
| data/alarm.csv | 7 | 7 | 08f32c3523be1a38 | 08f32c3523be1a38 | yes |
| data/alarm_affected_lot.csv | 299 | 299 | 6aebe400cf58ce3a | 6aebe400cf58ce3a | yes |
| data/alarm_status_history.csv | 24 | 24 | f251e041e8d26031 | f251e041e8d26031 | yes |
| data/door_event.csv | 9361 | 9361 | 657f5ac64b1363a6 | 657f5ac64b1363a6 | yes |
| data/inspection.csv | 74 | 74 | 6431290e7e443ff5 | 6431290e7e443ff5 | yes |
| data/inventory_lot.csv | 10000 | 10000 | 7b8db1cfe58b34f0 | 7b8db1cfe58b34f0 | yes |
| data/lot_zone_assignment.csv | 10000 | 10000 | 35ddbe2326c33b5c | 35ddbe2326c33b5c | yes |
| data/remediation.csv | 74 | 74 | 364e49d3fb9d2e82 | 364e49d3fb9d2e82 | yes |
| data/sensor.csv | 500 | 500 | 34a78629b58e0b26 | 34a78629b58e0b26 | yes |
| data/sensor_gap.csv | 3 | 3 | a1b6aace7974a195 | a1b6aace7974a195 | yes |
| data/sensor_reading.csv | 999970 | 999970 | 734de44002ee775d | 734de44002ee775d | yes |
| data/sensor_zone_map.csv | 501 | 501 | 8d1f6ee59c962853 | 8d1f6ee59c962853 | yes |
| data/storage_requirement.csv | 8 | 8 | 9a1ec585c51d6ea9 | 9a1ec585c51d6ea9 | yes |
| data/warehouse.csv | 10 | 10 | f4bd10939b17dab6 | f4bd10939b17dab6 | yes |
| data/zone.csv | 100 | 100 | 9ec98203e7edfb85 | 9ec98203e7edfb85 | yes |
| ground_truth/fault_ground_truth.csv | 11 | 11 | cdd1517b17c63337 | cdd1517b17c63337 | yes |
| ground_truth/fault_ground_truth_lots.csv | 31 | 31 | 16d7ebdbfa2fc828 | 16d7ebdbfa2fc828 | yes |
| json/alarm.json |  |  | 8ecd86e66d023dae | 8ecd86e66d023dae | yes |
| json/alarm_affected_lot.json |  |  | c23ab9b96657ecc5 | c23ab9b96657ecc5 | yes |
| json/alarm_status_history.json |  |  | eff9d6e0f8c8a7e7 | eff9d6e0f8c8a7e7 | yes |
| json/door_event.json |  |  | 3c4ec2483b8598fc | 3c4ec2483b8598fc | yes |
| json/ground_truth/fault_ground_truth.json |  |  | 5621201b9189865d | 5621201b9189865d | yes |
| json/ground_truth/fault_ground_truth_lots.json |  |  | bd26da86f512d799 | bd26da86f512d799 | yes |
| json/inspection.json |  |  | 6d2a9e9fe8b27f4e | 6d2a9e9fe8b27f4e | yes |
| json/inventory_lot.json |  |  | 542cbfb3170efce7 | 542cbfb3170efce7 | yes |
| json/lot_zone_assignment.json |  |  | 4ec6c73ce3c3d68d | 4ec6c73ce3c3d68d | yes |
| json/remediation.json |  |  | 8e0901baab449ea4 | 8e0901baab449ea4 | yes |
| json/sensor.json |  |  | cb1800606fa9f675 | cb1800606fa9f675 | yes |
| json/sensor_gap.json |  |  | 56cc0e24923cb0e7 | 56cc0e24923cb0e7 | yes |
| json/sensor_reading.json |  |  | f821a4e0ea84e803 | f821a4e0ea84e803 | yes |
| json/sensor_zone_map.json |  |  | d36a02d2995b80d7 | d36a02d2995b80d7 | yes |
| json/storage_requirement.json |  |  | e8b7ece1c79cc5ed | e8b7ece1c79cc5ed | yes |
| json/warehouse.json |  |  | a22e4885d7775dfa | a22e4885d7775dfa | yes |
| json/zone.json |  |  | d114831662f08afd | d114831662f08afd | yes |
| manifest.json |  |  | d26d563b44517004 | d26d563b44517004 | yes |
| reports/alarm_lot_link_reconciliation.csv | 31 | 31 | 4536a4a0ddb7bc27 | 4536a4a0ddb7bc27 | yes |
| reports/alarm_lot_linkage_details.csv | 7 | 7 | e7bedf29af57ec71 | e7bedf29af57ec71 | yes |
| reports/detected_issues.csv | 4 | 4 | 655a3863b2c12db6 | 655a3863b2c12db6 | yes |
| reports/evaluation_metrics.csv | 3 | 3 | a3ebe991c68af682 | a3ebe991c68af682 | yes |
| reports/evaluation_report.md |  |  | f1c4569d69aafa89 | f1c4569d69aafa89 | yes |
| reports/independent_lot_exposure_results.csv | 330 | 330 | 59a3d0718580aa53 | 59a3d0718580aa53 | yes |
| reports/independent_lot_exposure_summary.csv | 10 | 10 | 64974149f779361a | 64974149f779361a | yes |
| reports/lot_linkage_summary.csv | 1 | 1 | 24b14efe5e166f00 | 24b14efe5e166f00 | yes |
| reports/scenario_detection_results.csv | 11 | 11 | 1f4b7e046597319b | 1f4b7e046597319b | yes |
| reports/validation_report.md |  |  | b0d935ec37523742 | b0d935ec37523742 | yes |
| sql/schema.sql |  |  | 462fef29d2cd2749 | 462fef29d2cd2749 | yes |
| sql/seed.sql |  |  | 9d8a679944f60175 | 9d8a679944f60175 | yes |
