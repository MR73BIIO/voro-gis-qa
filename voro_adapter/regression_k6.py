"""
VORO - test regresji zycia K6 (Ekstraklasa). Krok 1 planu 1.3d.

Uruchom W KATALOGU /root/VORO systemowym pythonem:
    cd /root/VORO && python3 /root/gis_qa/voro_adapter/regression_k6.py --record   # zapis punktu odniesienia
    cd /root/VORO && python3 /root/gis_qa/voro_adapter/regression_k6.py            # porownanie

Gwarancje:
- przed zyciem kopiuje CALE VORO (bez .git), po zyciu przywraca kazdy zmieniony,
  usuniety lub nowy plik -> pamiec organizmu, liczniki ID i LifeTrace sa nietkniete,
- porownuje tylko wartosci, ktore powinny byc stale (metryki, statusy, tresci),
  identyfikatory i znaczniki czasu sa zamieniane na <ID>.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

VORO = Path.cwd()
if not (VORO / "organism" / "runtime.py").exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")
sys.path.insert(0, str(VORO))

OUT_DIR = VORO / "tests" / "regression"
BASELINE = OUT_DIR / "baseline_k6.json"
LAST = OUT_DIR / "last_k6.json"
SUBJECT = "K6_widzew-lodz__lech-poznan"
QUESTION = "Czy sedzia meczu K6 zapowiada wysoka liczbe kartek?"
SKIP = {".git", "__pycache__"}
ID_RE = re.compile(r"\b(?:[A-Z]{3}-[0-9A-F]{12}|[A-Z]{3}\d{6,}|PCT-REGRESSION-K6|LIFE-REGRESSION-K6)\b")


def file_hashes() -> dict:
    out = {}
    for root, dirs, files in os.walk(VORO):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            if name.endswith(".pyc"):
                continue
            p = Path(root) / name
            out[str(p.relative_to(VORO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def restore(before: dict, copy_root: Path) -> dict:
    after = file_hashes()
    changed = [p for p in after if p in before and after[p] != before[p]]
    created = [p for p in after if p not in before]
    deleted = [p for p in before if p not in after]
    for p in changed + deleted:
        (VORO / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(copy_root / p, VORO / p)
    for p in created:
        (VORO / p).unlink()
    return {"przywrocone": sorted(changed + deleted), "usuniete_nowe": sorted(created)}


def norm(x):
    return ID_RE.sub("<ID>", x) if isinstance(x, str) else x


def extract(context, trace) -> dict:
    o = context.outputs
    r, d, v = o.get("reasoning"), o.get("decision"), o.get("verification")
    h, k = o.get("hypothesis"), o.get("knowledge")
    return {
        "reasoning": {
            **{f: round(float(getattr(r, f)), 6)
               for f in ("confidence", "consistency", "completeness", "readiness")},
            "conclusion": norm(r.conclusion),
            "n_evidence_used": len(r.evidence_used),
        },
        "decision": {
            "status": d.status,
            "control_reason": d.control_reason,
            "selected_hypothesis": norm(d.selected_hypothesis),
            "confidence": round(float(d.confidence), 6),
        },
        "verification": getattr(v, "verification_result", None),
        "hypothesis": norm(getattr(h, "statement", str(h))),
        "knowledge_facts": {kk: round(float(vv), 6) for kk, vv in getattr(k, "facts", {}).items()},
        "n_evidence": len(context.evidence or []),
        "events": [norm(e) for e in trace.events],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="zapisz punkt odniesienia")
    args = ap.parse_args()

    before = file_hashes()
    tmp = Path(tempfile.mkdtemp(prefix="voro_regress_"))
    copy_root = tmp / "voro"
    shutil.copytree(VORO, copy_root, ignore=shutil.ignore_patterns(*SKIP))
    try:
        from organism.runtime import OrganismRuntime
        context, trace = OrganismRuntime().live(
            subject_id=SUBJECT,
            question=QUESTION,
            interpretation_relation="SUPPORTS",
            life_id="LIFE-REGRESSION-K6",
            pulse_id="PCT-REGRESSION-K6",
        )
        result = extract(context, trace)
    finally:
        report = restore(before, copy_root)
        shutil.rmtree(tmp)

    print("\n=========== REGRESJA K6 ===========")
    print("Stan organizmu przywrocony:", len(report["przywrocone"]), "plikow,",
          "usuniete nowe:", len(report["usuniete_nowe"]))
    for p in report["przywrocone"] + report["usuniete_nowe"]:
        print("   ", p)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    r = result["reasoning"]
    print(f"readiness {r['readiness']}  completeness {r['completeness']}  "
          f"status {result['decision']['status']}  dowody {result['n_evidence']}")

    if args.record:
        BASELINE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print("ZAPISANO punkt odniesienia:", BASELINE)
        return
    if not BASELINE.exists():
        sys.exit("Brak punktu odniesienia - uruchom najpierw z --record")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    if base == result:
        print("REGRESJA OK: wynik identyczny z punktem odniesienia")
        return
    print("REGRESJA NIEZGODNA:")
    for key in base:
        if base[key] != result.get(key):
            print(f"  {key}:\n    bylo:   {base[key]}\n    jest:   {result.get(key)}")
    sys.exit(1)


if __name__ == "__main__":
    main()
