# Prediction for step 1.6: state border (C7)

Written before the code of check C7. Date: 2026-10-01.

## What the exploration showed (scripts/explore_border.py, golden dataset)

- State layer (A00, PRG): 322,508.2 km2. Sum of municipalities: 313,731.2 km2.
- One uncovered piece of 8,776.99 km2 next to the coastal municipalities: the sea. Not a data error, the two layers describe different things.
- 3,708 other uncovered pieces, all at the state border, largest 31.7 m2.
- 3,709 pieces of municipalities outside the state layer, all at the border, largest 73.6 m2, together under 0.001 km2.
- Probable cause of the small pieces: the two layers draw the same border with slightly different lines. Not checked in detail.

## Rule

- C7 finding: every piece of the state without a municipality, and every piece of a municipality outside the state, larger than 150 m2.
- 150 m2 is about two times the largest measured noise (73.6 m2).
- Severity: high (same kind of error as C5).
- The sea is a known exception: uncovered piece of 8,776,989,565 m2, matched with a tolerance of 1 m2. If a gap is cut at the coast, the sea piece grows, the exception does not match and C7 reports it.

## Expected results

- Golden dataset: 0 C7 findings, the sea exception applied once, status still PASS.
- C1 to C6 results on seed_42 do not change.
- C7 findings on seed_42 only on municipalities touched by an injected error (target or neighbour), 0 elsewhere.
- New injected error E9 (gap cut at the state border, radius 20 to 100 m): every E9 found by C7.
