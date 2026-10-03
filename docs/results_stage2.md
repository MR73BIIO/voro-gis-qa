# Stage 2 results: decisions checked against the truth

Stage 1 answered: can the checks find injected errors? (160/160, 0 false alarms.)
Stage 2 answers the next question: when a decision layer reads only the measurements,
does it reach the right verdict on a dataset, and does it stay right as it remembers
more and more datasets?

The decision layer is VORO (private). It sees the measurements of one dataset,
chooses one of three hypotheses (PASS / REVIEW / REJECT) and only **after** that
it is shown the truth. The truth file is never visible before the decision.

Rule for the truth: any critical error (E1-E4) means REJECT, only non-critical
errors (E5-E9) mean REVIEW, no errors means PASS.

## How every step was run

1. Measure the data first, no rules.
2. Write the prediction into the repo and commit it **before** the code or data.
3. Rehearsal: same lives, organism state restored afterwards.
4. Real lives: irreversible, memory grows for good.
5. Compare with the prediction. Differences go into a note, nothing is corrected backwards.
6. Every step also re-runs a regression on the first domain (football, life K6):
   the result must stay identical (readiness 0.9254).

## 2.1 Truth after the decision

| Dataset | Decision | Truth | Result |
|---|---|---|---|
| golden | PASS | PASS | CONFIRMED |
| seed_42 (E1-E8, 20 each) | REJECT | REJECT | CONFIRMED |
| seed_7 (E6-E8, 10 each) | REVIEW | REVIEW | CONFIRMED |
| seed_9 (E9, 20) | REVIEW | REVIEW | CONFIRMED |

Control test: seed_42 with a deliberately wrong truth (PASS) gives REFUTED,
and the decision is identical with the right and the wrong truth.
So the verdict can be lost, and the truth does not leak into the decision.

## 2.2 Memory

The same four datasets as real lives. Each life starts with the memory of the
previous ones (74, 77, 80, 83 records) and still decides on its own evidence:
4/4 CONFIRMED. All memory records stay linked to their evidence (86/86 resolved),
and the football regression is unchanged.

## 2.3 Sensitivity: one error is enough

Ten new datasets, **one** injected error of each type among 2,479 municipalities,
plus one mixed set.

| Life | Dataset | Injected | Truth | Decision | Critical findings | All findings | Result |
|---|---|---|---|---|---|---|---|
| S2-05 | seed_101 | 1x E1 | REJECT | REJECT | 1 | 15 | CONFIRMED |
| S2-06 | seed_102 | 1x E2 | REJECT | REJECT | 2 | 3 | CONFIRMED |
| S2-07 | seed_103 | 1x E3 | REJECT | REJECT | 1 | 2 | CONFIRMED |
| S2-08 | seed_104 | 1x E4 | REJECT | REJECT | 2 | 12 | CONFIRMED |
| S2-09 | seed_105 | 1x E5 | REVIEW | REVIEW | 0 | 104 | CONFIRMED |
| S2-10 | seed_106 | 1x E6 | REVIEW | REVIEW | 0 | 4 | CONFIRMED |
| S2-11 | seed_107 | 1x E7 | REVIEW | REVIEW | 0 | 1 | CONFIRMED |
| S2-12 | seed_108 | 1x E8 | REVIEW | REVIEW | 0 | 1 | CONFIRMED |
| S2-13 | seed_109 | 1x E9 | REVIEW | REVIEW | 0 | 1 | CONFIRMED |
| S2-14 | seed_110 | 5x E1 + 5x E9 | REJECT | REJECT | 5 | 86 | CONFIRMED |

10/10 CONFIRMED, rehearsal and real lives identical.

One thing the table shows: **one error is not one finding.** A single E5 produced
104 findings, a single E1 produced 15. One broken polygon drags its neighbours in
(overlaps, gaps). This is why stage 1 groups findings into incidents: the client
needs to see one problem, not a hundred lines.

## Stage 2 in numbers

- 14 real lives, 14/14 CONFIRMED, 0 REFUTED
- 1 control test with a wrong truth: REFUTED, as it should be
- every error type E1-E9 confirmed in at least 2 independent lives
- football regression identical after every step

## What is not done yet

- Learning. Every confirmed life is marked as a possible basis for learning,
  but nothing from memory is used in decisions yet. That is stage 3,
  with its own prediction written before the code.
- Hard cases (errors near the thresholds), other regions, other sources (OSM).

---
PL · DE · RU · EN
