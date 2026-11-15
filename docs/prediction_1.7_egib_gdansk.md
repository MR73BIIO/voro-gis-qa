# Prediction for step 1.7: cadastral districts (PRG) vs parcels (EGiB), Gdańsk

Written before the code of step 1.7. Date: 2026-11-15.

## Why this step

PRG agrees with itself. In R0 the municipality of Gdańsk (`2261011`) and its 182 cadastral districts (obręby) cover each other exactly, with no gaps and no overlaps. So a check of PRG against PRG finds nothing. Errors appear between registers.

The second register here is the parcel layer of the city's land register (EGiB), published by the city as a WFS service.

## What R0 measured

Scripts: `scripts/explore_gdansk.py`, `scripts/explore_egib.py`.

### PRG, layer A06 (cadastral districts)

- 182 districts with codes `226101_1.NNNN`. No duplicate codes, no empty names, all geometries valid.
- The districts cover the municipality exactly: 0 m2 without a district, 0 m2 outside, 506 neighbour pairs without overlaps.
- District `0144` ZATOKA has 420.4 km2 of the 682.0 km2 of the municipality (62 %). It is water. A rule like "a district is not larger than X" would fail on correct data.
- Districts `07NN` are named `2NNS` (`0715` is `215S`, `0714` is `214S`). Both registers do it the same way. It is a naming rule, not an error.

### EGiB service

`https://ewid-wms.gdansk.gda.pl/iip/ows`, layer `ms:dzialki`, EPSG:2177.

- A filter by attribute returns HTTP 500, even for 5 parcels. Only a spatial window (BBOX) works.
- The window works only in north,east order. In east,north order the service returns 0 parcels and no error.
- The counter (`resultType=hits`) is always the number of returned parcels + 1: 9 of 9 tiles, and the whole windows of 3 districts.
- Twice the service returned an empty, correctly closed response for a tile whose counter said 1021 and 86. A downloader that does not compare each tile with the counter gets a hole that does not exist. In my first run this hole was 1.43 km2 in Osowa. Once the counter returned 1 for a window that holds 1,354 parcels; asked again, it returned 1,355.
- `POLE_EWIDENCYJNE` and `KLASOUZYTKI_EGIB` are empty in 6,118 of 6,118 parcels. The service schema has these fields, but they are not filled.
- `DATA` is the same for every parcel (2026-11-13 23:28:22), so it is the time of the export, not the date of a change.

### Three districts compared, 6,118 parcels

| District | Parcels | PRG area m2 | Parcels area m2 | Largest piece without parcel m2 | Largest parcel piece outside m2 |
|---|---|---|---|---|---|
| 0001 Osowa | 5,964 | 6,009,180.0 | 6,009,347.6 | 53.6 | 75.5 |
| 0011 | 55 | 7,057,243.0 | 7,057,305.1 | 25.7 | 48.1 |
| 0715 (215S) | 99 | 74,377.1 | 74,345.9 | 25.6 | 8.0 |

- District names are equal in both registers.
- 0 parcels lie in a district with another number. 0 duplicate parcel IDs. Every ID starts with its district code.
- 0 overlaps between parcels in 19,063 neighbour pairs.
- Between the registers there are only thin pieces along the district borders, the largest 75.5 m2. Probable cause: the two registers draw the same line slightly differently. Not checked in detail.

## Rules (check C8)

- A piece of a district without any parcel, or a piece of parcels outside their district, larger than 150 m2 is a finding. 150 m2 is about two times the largest measured noise (75.5 m2).
- A parcel whose representative point lies in a PRG district with another number is a finding.
- An overlap of two parcels larger than 1 m2 is a finding (same tolerance as C5).
- A district name in EGiB different from PRG is a finding.
- A parcel ID that does not start with its district code is a finding.
- A tile whose number of parcels does not match the counter (minus 1) after 3 attempts gives the district NO DATA. NO DATA is never a finding and never a pass.
- District `0144` ZATOKA is a known exception for coverage only: the water without parcels is not judged. All other rules apply to it.
- Empty `POLE_EWIDENCYJNE` and `KLASOUZYTKI_EGIB` are reported as a fact about the service, not as a data error. Whether the WFS service must fill them is not checked yet.

## Expected results

The whole city is downloaded once, in a grid of tiles, and every district is measured from that one set.

- Districts with NO DATA: 0.
- District names equal: 182 of 182.
- Parcels in a district with another number: 0.
- Overlaps between parcels larger than 1 m2: 0.
- Duplicate parcel IDs and IDs with a wrong district code: 0.
- Districts with a coverage piece larger than 150 m2: at most 5 of 181 (without 0144). Not 0, because R0 covered 3 quiet districts, and the rest includes the port, the river and the coast, where border lines come from different surveys.
- Counter offset +1 in every complete tile.

The prediction is refuted by any parcel in a district with another number, any overlap, any name difference, or more than 5 districts with a coverage piece above 150 m2.

## What I do with each result

- More than 5 districts with coverage findings: I look at the 5 largest pieces in QGIS before anything else. The threshold changes only with a new prediction written before the next run.
- NO DATA in any district: the list of incomplete tiles is the result. It means the service cannot be used for an automated control without a completeness check.
- Everything as expected: the same check goes to the next city with a public EGiB WFS.
