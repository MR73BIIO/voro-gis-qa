"""
VORO - seria zyc GIS (krok 2.3). Plan, przewidywania i konsekwencje: docs/prediction_2_3.md.

Uruchom W /root/VORO interpreterem z gis_qa:
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_gis_series.py --kontrola
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_gis_series.py --proba
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_gis_series.py --zycie

--kontrola : K0 - czy truth.json kazdego zbioru ma DOKLADNIE zaplanowane kody (bez zycia).
--proba    : 10 zyc S2P-xx, pamiec rosnie jak naprawde, na koncu stan PRZYWRACANY.
--zycie    : 10 PRAWDZIWYCH zyc S2-05..14 (odmowa, jesli slad juz istnieje albo nie bylo proby),
             porownanie z proba, diagnoza warstwy przy kazdej porazce (K2 pomiar / K3 decyzja),
             bilans nauki na typ bledu (S2-01..14): kandydat = >=2 CONFIRMED i 0 REFUTED.
Wymaga lat 2.1, 2.2, 2.2b. Kopia stanu przed seria: voro_state_po_2_2_*.tgz
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regression_k6 import SKIP, VORO, file_hashes, restore  # noqa: E402

SERIES = [
    ("05", "seed_101", ["E1"]),
    ("06", "seed_102", ["E2"]),
    ("07", "seed_103", ["E3"]),
    ("08", "seed_104", ["E4"]),
    ("09", "seed_105", ["E5"]),
    ("10", "seed_106", ["E6"]),
    ("11", "seed_107", ["E7"]),
    ("12", "seed_108", ["E8"]),
    ("13", "seed_109", ["E9"]),
    ("14", "seed_110", ["E1", "E9"]),
]
EARLIER = [("01", "golden"), ("02", "seed_42"), ("03", "seed_7"), ("04", "seed_9")]
CRITICAL = {"E1", "E2", "E3", "E4"}
BACKUP_HINT = "/root/backups/voro_state_po_2_2_*.tgz"


def counts() -> dict:
    from memory.memory_loader import PersistentMemoryLoader

    def n(rel):
        return len(json.loads((VORO / rel).read_text(encoding="utf-8")))

    return {
        "memory": n("memory/memory.json"),
        "canonical": len(PersistentMemoryLoader().load()),
        "evidence": n("evidence/evidence.json"),
        "knowledge": n("knowledge/knowledge.json"),
        "lifetraces": len(list((VORO / "data" / "lifetraces").glob("*.json"))),
    }


def truth_codes(subject: str) -> dict:
    from observation.providers.gis_qa_outcome_provider import GisQaOutcomeProvider
    if subject == "golden":
        return {}
    return GisQaOutcomeProvider().observe_outcome(subject).details.get("codes", {})


def kontrola() -> int:
    bad = []
    print("=========== K0: prawda zgodna z planem ===========")
    for nr, subject, types in SERIES:
        try:
            codes = truth_codes(subject)
        except Exception as exc:
            bad.append(f"{nr} {subject}: {exc}")
            print(f"{nr} {subject:<9} BLAD  {exc}")
            continue
        ok = sorted(codes) == sorted(types)
        print(f"{nr} {subject:<9} plan {types}  truth {codes}  {'OK' if ok else 'NIEZGODNE'}")
        if not ok:
            bad.append(f"{nr} {subject}: plan {types}, truth {sorted(codes)}")
    print("K0:", "OK - mozna zyc" if not bad else "ODRZUCIC zbiory przed zyciem")
    for b in bad:
        print("  -", b)
    return 0 if not bad else 1


def findings(evidence: list) -> dict:
    out = {}
    for s in evidence:
        if " = " in s:
            k, v = s.split(" = ", 1)
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
    return out


def diagnose(life: dict) -> str:
    """Warstwa porazki wg prediction_2_3.md (prawda -> pomiar -> decyzja)."""
    if life.get("verification_result") == "CONFIRMED":
        return "OK"
    f = findings(life["evidence"])
    expected = life.get("outcome_expected")
    if expected == "REJECT" and f.get("findings_critical", 0) == 0:
        return "K2 pomiar (blad krytyczny niewykryty)"
    if expected == "REVIEW" and f.get("findings_total", 0) == 0:
        return "K2 pomiar (blad niewykryty)"
    return "K3 decyzja (wykryte, zla hipoteza)"


def one_life(nr: str, subject: str, tag: str) -> dict:
    from observation.providers.gis_qa_provider import GisQaObservationProvider
    from observation.providers.gis_qa_outcome_provider import GisQaOutcomeProvider
    from organism.runtime import OrganismRuntime

    context, trace = OrganismRuntime().live(
        subject_id=subject,
        question=f"Czy zbior danych '{subject}' nadaje sie do uzycia?",
        interpretation_relation="SUPPORTS",
        life_id=f"LIFE-GIS-{tag}-{nr}",
        pulse_id=f"PCT-GIS-{tag}-{nr}",
        provider=GisQaObservationProvider(),
        outcome_provider=GisQaOutcomeProvider(),
    )
    d = context.outputs.get("decision")
    life = {
        "nr": nr,
        "subject": subject,
        "status": getattr(d, "status", None),
        "selected": str(getattr(d, "selected_hypothesis", "")).split(":")[0].strip(),
        "evidence": [getattr(e, "statement", "?") for e in (context.evidence or [])],
        **trace.trace_metadata.get("life_audit", {}),
        "counts_after": counts(),
    }
    life["diagnoza"] = diagnose(life)
    return life


def table(start: dict, lives: list) -> None:
    print(f"\nstart: {start}")
    print(f"{'nr':<3} {'zbior':<9} {'prawda':<7} {'wybrano':<7} {'wynik':<10} {'nauka':<6} "
          f"{'pam':<4} {'hist':<4} {'kryt':<5} {'wsz':<5} diagnoza")
    for x in lives:
        f = findings(x["evidence"])
        print(f"{x['nr']:<3} {x['subject']:<9} {str(x.get('outcome_expected')):<7} {x['selected']:<7} "
              f"{str(x.get('verification_result')):<10} {str(x.get('eligible_for_learning')):<6} "
              f"{str(x.get('memory_loaded')):<4} {str(x.get('historical_relevant')):<4} "
              f"{int(f.get('findings_critical', -1)):<5} {int(f.get('findings_total', -1)):<5} {x['diagnoza']}")
    if lives:
        print(f"koniec: {lives[-1]['counts_after']}")


def deltas(start: dict, lives: list) -> dict:
    end = lives[-1]["counts_after"]
    return {k: end[k] - start[k] for k in start}


def bilans(new_lives: list) -> dict:
    """Bilans nauki na typ bledu: S2-01..04 (z docs/lives_2_2_zycie.json) + seria."""
    rows = []
    earlier = json.loads((VORO / "docs" / "lives_2_2_zycie.json").read_text(encoding="utf-8"))
    for x in earlier["lives"]:
        rows.append((f"S2-{x['nr']}", x["subject"], x.get("verification_result")))
    for x in new_lives:
        rows.append((f"S2-{x['nr']}", x["subject"], x.get("verification_result")))
    per_type = {f"E{i}": {"confirmed": [], "refuted": []} for i in range(1, 10)}
    for life_id, subject, result in rows:
        for code in truth_codes(subject):
            key = "confirmed" if result == "CONFIRMED" else "refuted"
            per_type[code][key].append(life_id)
    for code, v in per_type.items():
        v["kandydat_do_nauki"] = len(v["confirmed"]) >= 2 and not v["refuted"]
    return per_type


def proba() -> int:
    before = file_hashes()
    tmp = Path(tempfile.mkdtemp(prefix="voro_s23p_"))
    shutil.copytree(VORO, tmp / "voro", ignore=shutil.ignore_patterns(*SKIP))
    lives = []
    try:
        start = counts()
        for nr, subject, _ in SERIES:
            lives.append(one_life(nr, subject, "S2P"))
    finally:
        report = restore(before, tmp / "voro")
        shutil.rmtree(tmp)
    print("\n=============== PROBA 2.3 (stan przywrocony) ===============")
    print("Przywrocone:", len(report["przywrocone"]), "| usuniete nowe:", len(report["usuniete_nowe"]))
    table(start, lives)
    out = {"start": start, "lives": lives, "deltas": deltas(start, lives)}
    print("przyrosty:", out["deltas"])
    (VORO / "docs" / "lives_2_3_proba.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("zapisano docs/lives_2_3_proba.json; stan po probie:", counts())
    return 0


def zycie() -> int:
    traces = VORO / "data" / "lifetraces"
    exists = [nr for nr, _, _ in SERIES if (traces / f"PCT-GIS-S2-{nr}.json").exists()]
    if exists:
        print("ODMOWA: zycia juz byly (slady istnieja):", exists)
        return 1
    proba_path = VORO / "docs" / "lives_2_3_proba.json"
    if not proba_path.exists():
        print("ODMOWA: najpierw --proba")
        return 1
    ref = json.loads(proba_path.read_text(encoding="utf-8"))

    lives = []
    start = counts()
    try:
        for nr, subject, _ in SERIES:
            lives.append(one_life(nr, subject, "S2"))
    except Exception as exc:
        print("\nK5 BLAD TECHNICZNY W TRAKCIE ZYC:", repr(exc))
        print("Stop serii. Powrot z kopii sprzed serii:")
        print(f"  cd /root/VORO && tar xzf {BACKUP_HINT}")
        raise

    print("\n=============== ZYCIA 2.3 (PRAWDZIWE) ===============")
    table(start, lives)
    out = {"start": start, "lives": lives, "deltas": deltas(start, lives)}
    print("przyrosty:", out["deltas"])

    diffs = []
    for real, rp in zip(lives, ref["lives"]):
        for key in ("subject", "status", "selected", "verification_result", "eligible_for_learning",
                    "knowledge_hash", "historical_relevant", "evidence",
                    "memory_loaded", "memory_stored_this_life"):
            if real.get(key) != rp.get(key):
                diffs.append(f"{real['nr']} {key}: proba={rp.get(key)} zycie={real.get(key)}")
    if out["deltas"] != ref["deltas"]:
        diffs.append(f"przyrosty: proba={ref['deltas']} zycie={out['deltas']}")
    out["zgodnosc_z_proba"] = diffs or "PELNA"

    out["bilans_nauki"] = bilans(lives)
    confirmed = sum(1 for x in lives if x.get("verification_result") == "CONFIRMED")
    failures = [f"S2-{x['nr']} {x['subject']}: {x['diagnoza']}" for x in lives if x["diagnoza"] != "OK"]
    out["konsekwencja"] = ("K1 (10/10 CONFIRMED) - jesli K6 i bramka 2.1 OK" if not failures
                           else "patrz porazki: K2 pomiar / K3 decyzja")
    (VORO / "docs" / "lives_2_3_zycie.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print("zgodnosc z proba:", "PELNA" if not diffs else "ROZNICE")
    for d in diffs:
        print("  -", d)
    print(f"\nCONFIRMED: {confirmed}/10")
    for f in failures:
        print("  porazka:", f)
    print("\nBILANS NAUKI (typ: CONFIRMED / REFUTED -> kandydat)")
    for code, v in out["bilans_nauki"].items():
        print(f"  {code}: {len(v['confirmed'])} / {len(v['refuted'])} -> "
              f"{'KANDYDAT' if v['kandydat_do_nauki'] else 'nie'}   {v['confirmed']}")
    print("\nKONSEKWENCJA:", out["konsekwencja"])
    print("zapisano docs/lives_2_3_zycie.json")
    return 0


if __name__ == "__main__":
    if "--kontrola" in sys.argv:
        sys.exit(kontrola())
    if "--proba" in sys.argv:
        sys.exit(proba())
    if "--zycie" in sys.argv:
        sys.exit(zycie())
    print(__doc__)
    sys.exit(2)
