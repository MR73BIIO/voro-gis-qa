# Prediction for step 1.4: incidents

Written before the code that builds incidents. Date: 2026-10-01.

## Definition

An incident is one connected group of findings. Municipalities are linked when:

- they overlap each other (C5 overlap above tolerance),
- they touch the same gap (C5 gap above tolerance),
- a municipality with broken geometry (C1) or outside the extent (C4) lies where the gap is (bounding boxes intersect).

Dataset-level findings (for example a wrong CRS for the whole layer) form one separate incident.

## Expected results

Dataset `seed_42` (160 injected errors, 2,335 findings):

- every injected error belongs to an incident: 160 of 160
- number of incidents: between 160 and 190
  - more than 160, because a municipality moved to the wrong coordinate system (E4) lands far from the hole it left, so it gives two incidents
  - a little fewer, because two errors close to each other can join into one incident
- no incident made only of municipalities that no injected error touched

Golden dataset: 0 incidents.
