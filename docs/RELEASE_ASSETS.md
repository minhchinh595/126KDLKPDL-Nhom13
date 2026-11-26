# Release asset manifest

Checksums are SHA-256, uppercase hexadecimal. “Packaged” means the file is intended to be tracked in this repository; “local candidate” means it remains ignored and is not part of the cloneable runtime.

## Database handoff

| Path | Size (bytes) | SHA-256 | Role/status |
|---|---:|---|---|
| `backups/electricity_analytics_nem_handoff_sanitized.dump` | 374,249 | `14719EC9BB454E9D03A18BC4FC1A1CC1628CA3D1A388DCD00958D71AC84F6C82` | Packaged; PostgreSQL custom format; restored successfully into a second empty database in an isolated PostgreSQL 16 container. |

The restored handoff contains 10,472 NEM observations, 101 ModelRun rows, one Open Electricity NEM dataset (ID 4), 24 NEM dataset-import history rows, and Alembic revision `20261125_0003`. Observation coverage at snapshot time: daily metrics `demand`, `demand_energy`, `generation_renewable`, `price`, and `renewable_proportion` each have 367 rows from `2025-11-24T14:00:00Z` through `2026-11-25T14:00:00Z`; 5-minute `demand` has 8,637 rows from `2026-10-26T08:30:00Z` through `2026-11-25T08:25:00Z`. The sanitized copy has zero rows in `users` and `electricity_consumption`, and retains the NEM dataset/import metadata and all ModelRun history. The unsanitized source dump remains local and is not packaged.

## Active NEM model artifacts

These local artifacts were loaded in a network-isolated container with a read-only artifact mount. Model class and non-secret provenance matched the NEM dataset identity and the expected model purpose. H2 artifacts declare horizon 2 and feature schema `nem_daily_demand_h2_v1`.

| Path | Size (bytes) | SHA-256 | Model/provenance | Status |
|---|---:|---|---|---|
| `BE/artifacts/electricity_nem_daily_kmeans.joblib` | 7,825 | `1A61E1F519C030C2067F39B2B319996207CFD4F8744BFDA922519C8BA61D614B` | `sklearn.cluster.KMeans`; dataset ID 4, Open Electricity NEM, NEM, daily | Packaged; daily clustering |
| `BE/artifacts/electricity_nem_daily_demand_rf_h2.joblib` | 1,755,130 | `E62F8AEF7475E2D8E569F905B5DE08F1F5C020EEADA437C8D2BD525394DABC8A` | `RandomForestRegressor`; NEM demand, 1d, MW; H2 | Packaged; prediction |
| `BE/artifacts/electricity_nem_daily_demand_classifier_h2.joblib` | 1,819,777 | `C92210FC040C363EE97814932E4CCCFD648D3655D90A1C45BB0F0183BD93FF73` | `RandomForestClassifier`; NEM demand, 1d, MW; H2 | Packaged; classification |
| `BE/artifacts/electricity_nem_daily_demand_rf.joblib` | 1,757,282 | `E4CAFC0B25CD7A9BB37B9ABF74C9FDB802DFEA745BE9FD6D570E05DDBBE778A7` | `RandomForestRegressor`; NEM daily demand, H1 | Local only; H1 is not an H2 substitute |
| `BE/artifacts/electricity_nem_daily_demand_classifier.joblib` | 1,465,644 | `D456EF24856EAED23A45E1C6FE8D95E30F44D9EA931D457F0B643E455000158E` | `RandomForestClassifier`; NEM daily demand, H1 | Local only; H1 is not an H2 substitute |

The three packaged model files are under 2 MB each, so Git LFS is not required. Legacy VNM artifacts remain tracked separately and are not modified by this handoff.

## Local NEM data candidates (not packaged)

These files are explicitly unverified references. They remain excluded by `.gitignore`; the database handoff above is the reproducible source for the active runtime snapshot. Their names, checksums and sizes are recorded so local copies can be identified without treating them as canonical data.

| Path | Size (bytes) | SHA-256 | Known rows/coverage from local inspection | Status |
|---|---:|---|---|---|
| `data/raw/openelectricity/nem/market/history_30days_demand_5m.csv` | 413,706 | `B3F599C4C00DDDCF5BC57BA4A690C04582E6DB502110E56D9D7AEE9C7B319C08` | 8,640 rows; 2026-10-25 through 2026-11-23, 5m | Candidate; CSV lacks source metadata |
| `data/raw/openelectricity/nem/market/history_7days_demand_5m.json` | 547,366 | `5DDEF9BEDE4D88467A82A932ED76AC266F2CDFB87708D8AFF52A3688C438ABD2` | 2,016 points; 2026-11-17 through 2026-11-23, 5m | Candidate; overlaps 30-day file |
| `data/raw/openelectricity/nem/market/latest_available_unverified.json` | 71,362 | `9BB2C7046AAAB2ED3A3B3DBEF1A95CB2882D210DD0ED8CB64E2BE98BC38C084A` | 438 points; through 2026-11-25 12:25 local | Unverified envelope/provenance |
| `data/raw/openelectricity/nem/market/snapshot_2026-11-23_demand_5m.json` | 79,249 | `401E6CB339280BB5D823DAA4D70FA8DFCC857BD25CC47E18047A715CAECE8E5F` | 288 points; 2026-11-23 | Candidate snapshot |
| `data/raw/openelectricity/nem/market/snapshot_2026-11-24_demand_5m.json` | 79,251 | `873ED49679F6277B89281BBC7E9B7720CACDA64983D8E8C454F88C8F1B896739` | 288 points; 2026-11-24 | Candidate snapshot |
| `data/processed/openelectricity/nem/daily/demand_1year_candidate.csv` | 10,573 | `45179AF51C027E9365E800A029D3889B0E886BC19DDAE6103A488D0B7ACA61A0` | 365 rows; 2025-11-25 through 2026-11-24 | Candidate; source metadata absent |
| `data/processed/openelectricity/nem/daily/multivariate_1year_candidate.csv` | 28,395 | `22A8070CF7062295CCD073324B01F84393857429D20DDCC678C019FAD14EF140` | 365 rows; 2025-11-25 through 2026-11-24 | Candidate; metric definitions not independently verified |
| `data/processed/openelectricity/nem/daily/multivariate_30days_candidate.csv` | 2,441 | `BA841FEDD13DEF6AC90CE67E263F74A4C380A665043F7AADA3E46FBBCD23666D` | 30 rows; 2026-10-25 through 2026-11-23 | Candidate; overlaps one-year file |
| `data/experiments/openelectricity/nem/history_30days_clean_unverified.csv` | 413,729 | `A0543B65587396E4D2A5FB52356B6703C04A733AE245474439E0A32A50F04AB2` | 8,640 rows | Experimental; three values differ from raw without verified rationale |
| `data/experiments/openelectricity/nem/classification/classification_feature_importance.csv` | 265 | `A2C85F1D52EAA80D3A2F4F618E50C459065E64031BFC101F8891D1687A4EB480` | 7 data rows | Experiment |
| `data/experiments/openelectricity/nem/classification/classification_relative_feature_importance.csv` | 329 | `546F027E4C50D2FADB671272A4CC0CA48F3E17D2717D2B161992FEC3F61C9040` | 9 data rows | Experiment |
| `data/experiments/openelectricity/nem/classification/classification_relative_test_results.csv` | 3,668 | `E039AB5550AFE4025D1E0BAF78542F0FA4228E76F4AA3907A536F5747A15C505` | 55 data rows | Experiment |
| `data/experiments/openelectricity/nem/classification/classification_relative_walk_forward.csv` | 237 | `418370B94089B3BF14C0C39BF8ED03F92B6095DE008C893FC8ECAFE662B374AC` | 4 data rows | Experiment |
| `data/experiments/openelectricity/nem/classification/classification_rolling90_feature_importance.csv` | 331 | `AB144EA1969668BD60470D79ED95A02E8C8B22AED9AF9A709774035F96A8D9EF` | 9 data rows | Experiment |
| `data/experiments/openelectricity/nem/classification/classification_rolling90_test_results.csv` | 3,639 | `609DAF0777680838DDC46B1FBA0A210EA10D039B4D197100A8266A3FAA7CF4D3` | 55 data rows | Experiment |
| `data/experiments/openelectricity/nem/classification/classification_test_results.csv` | 2,422 | `45AA4EEB148734E188076DC9ACF649C18D10D27EE4ECFB446D78C410D255EDF1` | 71 data rows | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_cluster_profile.csv` | 683 | `548A3E15697297D02895CDC0C7B8CF5A9BEFEDFA6A784994A0882828AAE46B15` | 4 data rows | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_daily_results.csv` | 37,177 | `5C5887E4471FE89D2C753A22AB814C4B88EC1AFB01848FB98813F87DAAFCB0A5` | 365 data rows | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_distribution.csv` | 114 | `991DB04817F1E423CD3EE164F5A785EFE73F83C96C5EBD7E45880D5366ED2F2D` | 2 data rows | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_distribution.png` | 92,699 | `ED7B27BFC8A7124C84E62B01C4F96012A281C04485BE6F00DB124D2EF37E9D8D` | Binary image | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_feature_comparison.png` | 236,563 | `EDEC073848EAE1A44B3D3ED0CC381ABA3D39998FDEA71005644A0EF2179F69B9` | Binary image | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_k_evaluation.csv` | 314 | `6658E276065F2D13C8B0A1709E15276DC57C4F575B98B849C1AD5D981AE0E32B` | 7 data rows | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_monthly_distribution.csv` | 245 | `284F05B762D09421E6B79291A16AF27F6FCB1C31B6DE2DA995C2DF5206A373C7` | 13 data rows | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_monthly_distribution.png` | 139,627 | `426D4EAE3D399963C5EE9535D587668B977FEC6C065D110EE1E1631A320AAB80` | Binary image | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_pca_2d.png` | 365,405 | `EEAC8EC219C3B4151A22B2C6873FF88075BFF82D20E4978EC70F2F510AED9C52` | Binary image | Experiment |
| `data/experiments/openelectricity/nem/clustering/clustering_scaler_comparison.csv` | 25,502 | `4DCDE25E5B20E206EE47748B67793CC40F51111620D527CC653E5E870BEFD9F0` | 365 data rows | Experiment |
| `data/experiments/openelectricity/nem/prediction/prediction_backtest_results.csv` | 2,345 | `DA80D669FDC89D0B74D14D545EBBBB9F6C59C07E7360B5880C34DF80259CEB93` | 30 data rows | Experiment |
| `data/experiments/openelectricity/nem/prediction/prediction_evaluation_results.csv` | 106 | `279B13AA5C60DA38F566230DF2C5B183001557405174D9641B2E38C3ADEAAC70` | 2 data rows | Experiment |
| `data/experiments/openelectricity/nem/prediction/prediction_feature_ablation.csv` | 429 | `6DB1820986180ACEF2390D53FFDA17DAD3899A628CD5DCDB83AEFD07DD4F8015` | 8 data rows | Experiment |
| `data/experiments/openelectricity/nem/prediction/prediction_feature_importance.csv` | 401 | `ED6B38212F8BB425B9E8FDC0D4BE5D852B3352615E8A4CAA87FF2B443318A6CB` | 10 data rows | Experiment |
| `data/experiments/openelectricity/nem/prediction/prediction_final_test_metrics.csv` | 116 | `F03D143D1349CB13CBD13EBFBA1971EBD4DD8959C2809930CC1105783C74C7A9` | 2 data rows | Experiment |
| `data/experiments/openelectricity/nem/prediction/prediction_final_test_results.csv` | 4,076 | `E8878DDDC620EC45C17AA8DA88DAE866BF346F3BB5952E4364DDCFFFC5CDCEA1` | 71 data rows | Experiment |
| `data/experiments/openelectricity/nem/prediction/prediction_walk_forward_results.csv` | 284 | `108DDEE85EC20039468BCC8BAAE1114A96A1A029DF853E9754CA264D9455148E` | 4 data rows | Experiment |

Candidate/reference data and experiment files above remain local-only and are not needed to restore the active database snapshot. Their provenance and reproducibility remain unverified; see `data/openelectricity_manifest.md`.
