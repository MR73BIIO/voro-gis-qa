# Note for step 1.6: change of design after the synthetic test

Written after the synthetic test, before the first run on real data. Date: 2026-10-01.

## What happened

The prediction (prediction_1.6_border.md) said: the sea is a known exception matched by its area. If a gap is cut at the coast, the sea piece grows, the exception does not match and C7 reports it.

On a synthetic world with a "sea" strip this produced 7 false alarms. A hole left by another error near the coast joined the sea into one piece. The piece no longer matched the exception, and it was reported at every coastal municipality, not only at the place of the error. On real data this would hit dozens of coastal municipalities.

## Change

- The sea is stored in the golden dataset as a reference geometry (layer `known_uncovered`): all pieces of the state without municipalities larger than 1 km2. On the golden dataset this is only the sea.
- The measurement splits the uncovered area into the reference part (one piece, compared with the known exception by area) and everything else.
- A new hole at the coast is now a separate piece, next to its own municipalities.

## What did not change

The rule (150 m2, severity high) and all expected results from prediction_1.6_border.md stay as written.

On 4 synthetic seeds after the change: every E9 found, 0 C7 false alarms.
