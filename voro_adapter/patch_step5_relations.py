"""
VORO - 1.3d krok 5: jawne relacje dowod -> hipoteza (gis_qa).

Uruchom w /root/VORO:  python3 /root/gis_qa/voro_adapter/patch_step5_relations.py

Zmienia:
1. domains/gis_qa_params.json  - progi i znane wyjatki staja sie WIEDZA organizmu (kopiowane z /root/gis_qa)
2. domains/gis_qa.py           - DOPISUJE (nie zmienia tabeli z kroku 3): relacje slowne + evaluate_evidence + interpret_all
3. evidence/evidence_organ.py  - gdy pakiet ma RELATIONS: 3 dowody z oceny pomiarow; inaczej jak dotad
4. interpretation/interpretation_organ.py - gdy pakiet ma RELATIONS: dowod x hipoteza; inaczej jak dotad
5. organism/life_flow.py       - lista interpretacji jest dolaczana element po elemencie
Ekstraklasa (RELATIONS = None, pojedynczy rekord) idzie dokladnie dotychczasowa sciezka.
Jesli ktorykolwiek fragment nie pasuje DOKLADNIE raz, NIC nie jest zmieniane.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
GIS_QA = Path("/root/gis_qa")
if not (ROOT / "organism" / "runtime.py").exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")

PACK_FILE = ROOT / "domains" / "gis_qa.py"
PARAMS_FILE = ROOT / "domains" / "gis_qa_params.json"
EV_FILE = ROOT / "evidence" / "evidence_organ.py"
IN_FILE = ROOT / "interpretation" / "interpretation_organ.py"
LF_FILE = ROOT / "organism" / "life_flow.py"

PACK_ADDITION = '''

# ================================================================ KROK 5
# Wykonanie tabeli z kroku 3. Liczby RELATIONS powyzej sa NIEZMIENIONE;
# dochodzi tylko nazwa relacji z InterpretationContract.

GIS_QA_SCRIPTS = "/root/gis_qa/scripts"

# Jedyna neutralna komorka tabeli: znaleziska niekrytyczne nie popieraja
# ani nie przecza hipotezie REJECT (REJECT rozstrzygaja znaleziska krytyczne).
NEUTRAL = {("findings_noncritical", "REJECT")}


def relation_word(source: str, result: str, hypothesis_key: str) -> str:
    if (source, hypothesis_key) in NEUTRAL:
        return "QUALIFIES"
    return "CONTRADICTS" if RELATIONS[source][result][hypothesis_key] >= 1.0 else "SUPPORTS"


def _knowledge():
    """Progi i znane wyjatki = wiedza organizmu (domains/gis_qa_params.json)."""
    import json
    from pathlib import Path
    data = json.loads(Path(__file__).with_name("gis_qa_params.json").read_text(encoding="utf-8"))
    return data["params"], data["known_exceptions"]


def evaluate_evidence(observation, knowledge, life_id: str) -> list:
    """Ocena pomiarow z Observation wedlug wiedzy -> 3 dowody rozstrzygajace."""
    import sys
    from contracts.evidence_record import EvidenceRecord
    if GIS_QA_SCRIPTS not in sys.path:
        sys.path.insert(0, GIS_QA_SCRIPTS)
    from checks import judge

    params, exceptions = _knowledge()
    findings, diagnostics = judge(observation.payload["measurements"], params, exceptions)

    per_check = {}
    for f in findings:
        per_check[f["check"]] = per_check.get(f["check"], 0) + 1
    counts = {
        "findings_total": len(findings),
        "findings_critical": sum(per_check.get(c, 0) for c in CRITICAL_CHECKS),
        "findings_noncritical": sum(per_check.get(c, 0) for c in NONCRITICAL_CHECKS),
    }
    records = []
    for source in EVIDENCE_SOURCES:
        n = counts[source]
        records.append(EvidenceRecord(
            life_id=life_id,
            source=source,
            statement=f"{source} = {n}",
            confidence=1.0,
            support=0.0,
            contradiction=0.0,
            uncertainty=0.0,
            provenance=getattr(knowledge, "knowledge_id", ""),
            metadata={
                "feature": source,
                "value": n,
                "outcome": outcome(n),
                "per_check": per_check,
                "diagnostics": diagnostics,
                "params": params,
                "interpretation": "explicit_relation",
            },
        ))
    return records


def interpret_all(evidence, hypotheses, keys, engine, life_id: str) -> list:
    """Kazdy dowod x kazda hipoteza -> InterpretationRecord wedlug tabeli."""
    if not keys or len(keys) != len(hypotheses):
        raise ValueError("gis_qa: brak kluczy hipotez albo zla ich liczba")
    out = []
    for e in evidence:
        result = e.metadata["outcome"]
        for key, h in zip(keys, hypotheses):
            out.append(engine.interpret(
                evidence_id=e.evidence_id,
                hypothesis=h.statement,
                relation=relation_word(e.source, result, key),
                confidence=1.0,
                life_id=life_id,
            ))
    return out
'''

EV_PATCHES = [
    (re.compile(r"(\nfrom knowledge\.knowledge_engine import Knowledge\n)"),
     lambda m: m.group(1) + "\nfrom domains import get_pack\n"),
    (re.compile(r"\n([ \t]*)evidence = self\.engine\.evaluate\(\s*knowledge=knowledge,\s*life_id=context\.life_id,\s*\)"),
     lambda m: ("\n{i}pack = get_pack(context.observation)\n\n"
                "{i}if getattr(pack, \"RELATIONS\", None):\n\n"
                "{i}    evidence = pack.evaluate_evidence(\n"
                "{i}        observation=context.observation,\n"
                "{i}        knowledge=knowledge,\n"
                "{i}        life_id=context.life_id,\n"
                "{i}    )\n\n"
                "{i}else:\n\n"
                "{i}    evidence = self.engine.evaluate(\n"
                "{i}        knowledge=knowledge,\n"
                "{i}        life_id=context.life_id,\n"
                "{i}    )").format(i=m.group(1))),
]

IN_PATCHES = [
    (re.compile(r"(\nfrom interpretation\.interpretation_engine import \(\s*InterpretationEngine,\s*\)\n)"),
     lambda m: m.group(1) + "\nfrom domains import get_pack\n"),
    (re.compile(r"\n([ \t]*)first = evidence\[0\]\n"),
     lambda m: ("\n{i}pack = get_pack(context.observation)\n\n"
                "{i}if getattr(pack, \"RELATIONS\", None):\n\n"
                "{i}    #\n"
                "{i}    # Explicit relations from the domain pack:\n"
                "{i}    # every Evidence x every competing Hypothesis.\n"
                "{i}    #\n\n"
                "{i}    interpretations = pack.interpret_all(\n"
                "{i}        evidence=evidence,\n"
                "{i}        hypotheses=context.outputs.get(\"hypotheses\") or [],\n"
                "{i}        keys=context.outputs.get(\"hypothesis_keys\") or (),\n"
                "{i}        engine=self.engine,\n"
                "{i}        life_id=context.life_id,\n"
                "{i}    )\n\n"
                "{i}    relations = {{}}\n"
                "{i}    for item in interpretations:\n"
                "{i}        relations[item.relation] = relations.get(item.relation, 0) + 1\n\n"
                "{i}    return OrganResult(\n"
                "{i}        organ=self.name,\n"
                "{i}        success=True,\n"
                "{i}        record_ids=[item.interpretation_id for item in interpretations],\n"
                "{i}        message=f\"Interpretations created: {{len(interpretations)}} {{relations}}\",\n"
                "{i}        payload=interpretations,\n"
                "{i}    )\n\n"
                "{i}first = evidence[0]\n").format(i=m.group(1))),
]

LF_PATCHES = [
    (re.compile(r"\n([ \t]*)context\.interpretations\.append\(\s*result\.payload\s*\)"),
     lambda m: ("\n{i}if isinstance(result.payload, list):\n"
                "{i}    context.interpretations.extend(result.payload)\n"
                "{i}else:\n"
                "{i}    context.interpretations.append(result.payload)").format(i=m.group(1))),
]


def prepare(path: Path, patches, marker: str) -> str:
    src = path.read_text(encoding="utf-8")
    if marker in src:
        sys.exit(f"{path.relative_to(ROOT)}: juz zaaplikowane - nic nie robie.")
    for rx, _ in patches:
        n = len(rx.findall(src))
        if n != 1:
            sys.exit(f"BLAD: {path.relative_to(ROOT)}: wzorzec {rx.pattern[:60]!r} pasuje {n} razy. NIC nie zmieniono.")
    for rx, fn in patches:
        src = rx.sub(fn, src, count=1)
    compile(src, str(path), "exec")
    return src


pack_src = PACK_FILE.read_text(encoding="utf-8")
if "evaluate_evidence" in pack_src:
    sys.exit("domains/gis_qa.py: krok 5 juz dopisany - nic nie robie.")
if "RELATIONS = {" not in pack_src:
    sys.exit("BLAD: domains/gis_qa.py nie ma tabeli z kroku 3.")
# __main__ z kroku 3 zostaje na koncu pliku: dopisek wstawiamy PRZED nim
main_at = pack_src.index('\nif __name__ == "__main__":')
new_pack = pack_src[:main_at] + PACK_ADDITION + pack_src[main_at:]
compile(new_pack, str(PACK_FILE), "exec")

new_ev = prepare(EV_FILE, EV_PATCHES, "evaluate_evidence")
new_in = prepare(IN_FILE, IN_PATCHES, "interpret_all")
new_lf = prepare(LF_FILE, LF_PATCHES, "interpretations.extend")

params = json.loads((GIS_QA / "params.json").read_text(encoding="utf-8"))
exceptions = json.loads((GIS_QA / "known_exceptions.json").read_text(encoding="utf-8"))
knowledge = {
    "_comment": "Wiedza organizmu VORO o jakosci danych gis_qa. Zrodlo poczatkowe: /root/gis_qa "
                "(params.json, known_exceptions.json). Od etapu 3 zmienia ja Reflection.",
    "params": params,
    "known_exceptions": exceptions,
}

PARAMS_FILE.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")
PACK_FILE.write_text(new_pack, encoding="utf-8")
EV_FILE.write_text(new_ev, encoding="utf-8")
IN_FILE.write_text(new_in, encoding="utf-8")
LF_FILE.write_text(new_lf, encoding="utf-8")
print("OK: krok 5 zaaplikowany (pakiet, wiedza, Evidence, Interpretation, LifeFlow).")
