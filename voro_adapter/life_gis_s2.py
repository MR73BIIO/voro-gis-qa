"""
VORO - zycia GIS-S2 (krok 2.2). Kolejnosc i liczby: docs/prediction_2_2.md.

Uruchom W /root/VORO interpreterem z gis_qa:
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_gis_s2.py --proba
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_gis_s2.py --zycie

--proba : 4 zycia (S2P-xx), pamiec rosnie miedzy nimi jak w prawdziwym biegu,
          na koncu stan organizmu PRZYWRACANY. Wynik: docs/lives_2_2_proba.json
--zycie : 4 PRAWDZIWE zycia (S2-xx), BEZ przywracania. Odmawia, jesli ktorykolwiek
          slad PCT-GIS-S2-xx juz istnieje. Wynik: docs/lives_2_2_zycie.json
          + porownanie z proba (decyzje, przyrosty, hash wiedzy).
Kopia stanu przed 2.2: /root/backups/voro_state_przed_2_2_20261003_0906.tgz
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regression_k6 import SKIP, VORO, file_hashes, restore  # noqa: E402

LIVES = [("01", "golden"), ("02", "seed_42"), ("03", "seed_7"), ("04", "seed_9")]
BACKUP = "/root/backups/voro_state_przed_2_2_20261003_0906.tgz"


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
    audit = trace.trace_metadata.get("life_audit", {})
    return {
        "nr": nr,
        "subject": subject,
        "status": getattr(d, "status", None),
        "selected": str(getattr(d, "selected_hypothesis", "")).split(":")[0].strip(),
        "evidence": [getattr(e, "statement", "?") for e in (context.evidence or [])],
        "memory_stored": [e for e in trace.events if e.startswith("Memory:")],
        **audit,
        "counts_after": counts(),
    }


def table(start: dict, lives: list) -> None:
    print(f"\nstart: {start}")
    print(f"{'nr':<3} {'zbior':<8} {'wybrano':<7} {'wynik':<10} {'nauka':<6} "
          f"{'pam.wczyt':<9} {'hist':<4} {'readiness':<9} hash_wiedzy")
    for x in lives:
        print(f"{x['nr']:<3} {x['subject']:<8} {x['selected']:<7} {str(x.get('verification_result')):<10} "
              f"{str(x.get('eligible_for_learning')):<6} {str(x.get('memory_loaded')):<9} "
              f"{str(x.get('historical_relevant')):<4} {str(x.get('reasoning_readiness')):<9} "
              f"{str(x.get('knowledge_hash'))[:16]}")
    print(f"koniec: {lives[-1]['counts_after'] if lives else '-'}")


def deltas(start: dict, lives: list) -> dict:
    end = lives[-1]["counts_after"]
    return {k: end[k] - start[k] for k in start}


def proba() -> int:
    before = file_hashes()
    tmp = Path(tempfile.mkdtemp(prefix="voro_s2p_"))
    shutil.copytree(VORO, tmp / "voro", ignore=shutil.ignore_patterns(*SKIP))
    lives = []
    try:
        start = counts()
        for nr, subject in LIVES:
            lives.append(one_life(nr, subject, "S2P"))
    finally:
        report = restore(before, tmp / "voro")
        shutil.rmtree(tmp)
    print("\n=============== PROBA 2.2 (stan przywrocony) ===============")
    print("Przywrocone:", len(report["przywrocone"]), "| usuniete nowe:", len(report["usuniete_nowe"]))
    table(start, lives)
    out = {"start": start, "lives": lives, "deltas": deltas(start, lives)}
    print("przyrosty:", out["deltas"])
    (VORO / "docs" / "lives_2_2_proba.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("zapisano docs/lives_2_2_proba.json; stan po probie:", counts())
    return 0


def zycie() -> int:
    traces = VORO / "data" / "lifetraces"
    exists = [nr for nr, _ in LIVES if (traces / f"PCT-GIS-S2-{nr}.json").exists()]
    if exists:
        print("ODMOWA: zycia juz byly (slady istnieja):", exists)
        return 1
    proba_path = VORO / "docs" / "lives_2_2_proba.json"
    if not proba_path.exists():
        print("ODMOWA: najpierw --proba")
        return 1
    ref = json.loads(proba_path.read_text(encoding="utf-8"))

    lives = []
    start = counts()
    try:
        for nr, subject in LIVES:
            lives.append(one_life(nr, subject, "S2"))
    except Exception as exc:
        print("\nBLAD W TRAKCIE PRAWDZIWYCH ZYC:", repr(exc))
        print("Stan organizmu jest czesciowo zmieniony. Powrot:")
        print(f"  cd /root/VORO && tar xzf {BACKUP}")
        raise

    print("\n=============== ZYCIA 2.2 (PRAWDZIWE) ===============")
    table(start, lives)
    out = {"start": start, "lives": lives, "deltas": deltas(start, lives)}
    print("przyrosty:", out["deltas"])

    fails = []
    for real, rp in zip(lives, ref["lives"]):
        for key in ("subject", "status", "selected", "verification_result",
                    "eligible_for_learning", "knowledge_hash", "historical_relevant", "evidence"):
            if real.get(key) != rp.get(key):
                fails.append(f"{real['nr']} {key}: proba={rp.get(key)} zycie={real.get(key)}")
    if out["deltas"] != ref["deltas"]:
        fails.append(f"przyrosty: proba={ref['deltas']} zycie={out['deltas']}")
    out["zgodnosc_z_proba"] = fails or "PELNA"
    (VORO / "docs" / "lives_2_2_zycie.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("zgodnosc z proba:", "PELNA" if not fails else "ROZNICE")
    for f in fails:
        print("  -", f)
    print("zapisano docs/lives_2_2_zycie.json")
    return 0 if not fails else 1


if __name__ == "__main__":
    if "--proba" in sys.argv:
        sys.exit(proba())
    if "--zycie" in sys.argv:
        sys.exit(zycie())
    print(__doc__)
    sys.exit(2)
