"""
VORO - bramka 2.1 (prawda po Decision).

Uruchom W /root/VORO interpreterem z gis_qa:
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/test_2_1.py

Stan organizmu jest przywracany (jak life_gis.py) - to PROBA, nie zycie do pamieci.

Bramka:
  A) golden, seed_42, seed_7, seed_9 -> 4x CONFIRMED
  B) test kontrolny: seed_42 z ZLA prawda -> REFUTED
  C) szczelnosc: kolejnosc zdarzen Decision -> Outcome -> Verification,
     a decyzja jest IDENTYCZNA przy dobrej i zlej prawdzie
     (czyli prawda nie mogla na nia wplynac)
Regresja K6 osobno: python3 /root/gis_qa/voro_adapter/regression_k6.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regression_k6 import SKIP, VORO, file_hashes, restore  # noqa: E402

SUBJECTS = ["golden", "seed_42", "seed_7", "seed_9"]


def life(subject, outcome_provider, tag):
    from observation.providers.gis_qa_provider import GisQaObservationProvider
    from organism.runtime import OrganismRuntime
    return OrganismRuntime().live(
        subject_id=subject,
        question=f"Czy zbior danych '{subject}' nadaje sie do uzycia?",
        interpretation_relation="SUPPORTS",
        life_id=f"LIFE-GIS-T21-{tag}-{subject}",
        pulse_id=f"PCT-GIS-T21-{tag}-{subject}",
        provider=GisQaObservationProvider(),
        outcome_provider=outcome_provider,
    )


def order_ok(events):
    def first(prefix):
        return next((i for i, e in enumerate(events) if e.startswith(prefix)), None)
    d, o, v = first("Decision:"), first("Outcome observed"), first("Verification:")
    return None not in (d, o, v) and d < o < v, (d, o, v)


def decision_view(context):
    d = context.outputs["decision"]
    return (d.status, d.selected_hypothesis, d.confidence)


before = file_hashes()
tmp = Path(tempfile.mkdtemp(prefix="voro_t21_"))
shutil.copytree(VORO, tmp / "voro", ignore=shutil.ignore_patterns(*SKIP))
rows, fails = [], []
try:
    from contracts.outcome_record import OutcomeRecord
    from observation.providers.gis_qa_outcome_provider import GisQaOutcomeProvider

    class WrongOutcome:
        """Celowo zla prawda: zawsze PASS."""
        def observe_outcome(self, subject_id):
            return OutcomeRecord(subject_id=subject_id, expected="PASS",
                                 source="TEST KONTROLNY (zla prawda)")

    # A) 4 zycia z prawdziwa prawda
    real = {}
    for s in SUBJECTS:
        ctx, tr = life(s, GisQaOutcomeProvider(), "A")
        v = ctx.outputs.get("verification")
        ok, idx = order_ok(tr.events)
        real[s] = ctx
        rows.append((s, ctx.outputs["decision"].status, getattr(v, "selected_key", None),
                     getattr(ctx.outcome, "expected", None),
                     getattr(v, "verification_result", None),
                     getattr(ctx.outcome, "details", {}).get("codes"), ok))
        if getattr(v, "verification_result", None) != "CONFIRMED":
            fails.append(f"A {s}: oczekiwano CONFIRMED")
        if not ok:
            fails.append(f"C {s}: zla kolejnosc zdarzen {idx}")

    # B) test kontrolny + C) niezaleznosc decyzji od prawdy
    ctx_w, tr_w = life("seed_42", WrongOutcome(), "B")
    vw = ctx_w.outputs.get("verification")
    if getattr(vw, "verification_result", None) != "REFUTED":
        fails.append("B seed_42 + zla prawda: oczekiwano REFUTED")
    if decision_view(ctx_w) != decision_view(real["seed_42"]):
        fails.append("C seed_42: decyzja ROZNI SIE przy zlej prawdzie (wyciek!)")
finally:
    report = restore(before, tmp / "voro")
    shutil.rmtree(tmp)

print("\n=============== BRAMKA 2.1 ===============")
print("Stan organizmu przywrocony:", len(report["przywrocone"]),
      "plikow, usuniete nowe:", len(report["usuniete_nowe"]))
print(f"{'zbior':<8} {'status':<8} {'wybrano':<8} {'prawda':<8} {'wynik':<10} kolejnosc  kody")
for s, st, sel, exp, res, codes, ok in rows:
    print(f"{s:<8} {st:<8} {str(sel):<8} {str(exp):<8} {str(res):<10} {'OK' if ok else 'ZLE':<9}  {codes}")
print(f"kontrola seed_42 (zla prawda PASS): {getattr(vw, 'verification_result', None)}; "
      f"decyzja identyczna: {decision_view(ctx_w) == decision_view(real['seed_42'])}")
print("BRAMKA:", "PASS" if not fails else "FAIL")
for f in fails:
    print("  -", f)
sys.exit(0 if not fails else 1)
