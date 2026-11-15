# Outcome of step 1.7: cadastral districts (PRG) vs parcels (EGiB), Gdańsk

Prediction: [`prediction_1.7_egib_gdansk.md`](prediction_1.7_egib_gdansk.md), committed before the code (3450e44).
Run: `scripts/check_egib.py`, 2026-11-15. Result files: `out/c8_20261115_165556.json` and `.gpkg` (not in git).

## Verdict: REFUTED

Two of the six expectations failed. Both are conditions that the prediction named as refuting.

| Expectation | Expected | Measured | |
|---|---|---|---|
| Districts with NO DATA | 0 | 0 | as expected |
| District names different | 0 | 0 | as expected |
| Parcels in a district with another number | 0 | **10** | refuted |
| Overlaps between parcels above 1 m2 | 0 | 0 | as expected |
| Duplicate IDs or IDs with a wrong district code | 0 | 0 | as expected |
| Districts with a coverage piece above 150 m2 (without 0144) | at most 5 | **41** | refuted |

## What was measured

- Download: 378 tiles, all complete on the counter check, 93,804 parcels. The counter offset of +1 held in every tile.
- 294,430 neighbour pairs of parcels, 0 with any overlap.
- 182 of 182 district names equal in both registers.
- `POLE_EWIDENCYJNE` and `KLASOUZYTKI_EGIB` are empty in 93,804 of 93,804 parcels.
- 1 parcel lies outside all PRG districts of Gdańsk.

### Parcels in a district with another number (10)

| Parcel (EGiB) | Its district in EGiB | Lies in PRG district |
|---|---|---|
| 226101_1.0303.1266 | 0303 | 0670 |
| 226101_1.0136.16/1 | 0136 | 0301 |
| 226101_1.0051.68 | 0051 | 0049 |
| 226101_1.0051.67 | 0051 | 0049 |
| 226101_1.0051.19/7 | 0051 | 0037 |
| 226101_1.0044.1266/3 | 0044 | 0056 |
| 226101_1.0023.33/7 | 0023 | 0003 |
| 226101_1.0059.66 | 0059 | 0060 |
| 226101_1.0144.54 | 0144 | 0046 |
| 226101_1.0144.52 | 0144 | 0062 |

### Coverage: 57 pieces above 150 m2 in 41 districts

27 pieces of a district without any parcel, 30 pieces of parcels outside their district. The 10 districts with the largest pieces:

| District | Largest piece without parcel m2 | Largest parcel piece outside m2 |
|---|---|---|
| 0312 (312S) | 54.1 | 21,667.0 |
| 0062 | 6,536.7 | 53.1 |
| 0049 Jasień | 4,837.2 | 249.3 |
| 0051 | 502.4 | 4,837.2 |
| 0036 Kiełpino Górne | 168.2 | 3,189.1 |
| 0002 Barniewice | 63.8 | 2,111.9 |
| 0070 | 1,049.8 | 1,094.2 |
| 0071 | 1,094.2 | 1,049.8 |
| 0007 | 1,087.2 | 17.9 |
| 0008 | 6.3 | 1,087.2 |

## What the numbers already show

- The pieces come in mirrored pairs. 0049 has 4,837.2 m2 without a parcel and 0051 has exactly 4,837.2 m2 of parcels outside, and two 0051 parcels lie in 0049. The same for 0070 and 0071 (1,049.8 and 1,094.2 crossed) and for 0007 and 0008 (1,087.2). This is not noise between two lines. It is land that EGiB gives to one district and PRG to the neighbour.
- So one cause is counted up to three times: a parcel in the wrong district, a piece without a parcel in one district and a piece outside in the other. 41 districts is not 41 problems. The number of separate cases is not counted yet.
- The 3 districts measured in R0 were quiet. The threshold of 150 m2 came from them and stays correct for noise: 0 overlaps and the mirrored pairs are far above it. What was wrong is the expectation that the rest of the city looks the same.
- Which register is right in each case is not checked. A difference is not an error of one side until it is looked at.

## Consequence (written in the prediction before the run)

> More than 5 districts with coverage findings: I look at the 5 largest pieces in QGIS before anything else. The threshold changes only with a new prediction written before the next run.

The threshold stays at 150 m2. Next step: look at the 5 largest cases in QGIS against the city's cadastral map and orthophoto, and group the 57 pieces and 10 parcels into separate cases.
