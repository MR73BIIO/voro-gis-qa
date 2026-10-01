"""
VORO - 1.3d krok 6: Reasoning liczony osobno dla kazdej konkurujacej hipotezy.

Uruchom w /root/VORO:  python3 /root/gis_qa/voro_adapter/patch_step6_reasoning.py

Wzor ReasoningEngine NIE jest zmieniany. Organ uruchamia go raz na hipoteze, na WIDOKU
kontekstu, w ktorym:
  - interpretacje = tylko interpretacje tej hipotezy,
  - dowody = kopie z support/contradiction wzietymi z relacji tej hipotezy
    (SUPPORTS -> support 1.0, CONTRADICTS -> contradiction 1.0, QUALIFIES -> 0/0).
Wybierana jest hipoteza o najwyzszej gotowosci; remis rozstrzyga pack.TIE_ORDER.
outputs["reasoning"] (payload)      = rozumowanie wybranej hipotezy (Decision dziala jak dotad)
outputs["reasoning_by_hypothesis"]  = {klucz: ReasoningRecord}
outputs["reasoning_selected_key"]   = klucz wybranej hipotezy
Bez jawnych relacji (Ekstraklasa) organ dziala dokladnie jak dotad.
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "organism" / "runtime.py").exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")
FILE = ROOT / "reasoning" / "reasoning_organ.py"

METHOD = '''
    # --------------------------------------------------
    # Competing hypotheses (explicit relations only)
    # --------------------------------------------------

    def _reason_per_hypothesis(
        self,
        context: LifeContext,
        engine: ReasoningEngine,
        pack,
    ):

        import dataclasses

        keys = context.outputs["hypothesis_keys"]
        hypotheses = context.outputs["hypotheses"]

        by_key = {}

        for key, hypothesis in zip(keys, hypotheses):

            mine = [
                item
                for item in context.interpretations
                if getattr(item, "hypothesis", None) == hypothesis.statement
            ]

            relation = {
                item.evidence_id: item.relation
                for item in mine
            }

            evidence = [
                dataclasses.replace(
                    item,
                    support=(
                        1.0 if relation.get(item.evidence_id) == "SUPPORTS" else 0.0
                    ),
                    contradiction=(
                        1.0 if relation.get(item.evidence_id) == "CONTRADICTS" else 0.0
                    ),
                )
                for item in context.evidence
            ]

            view = dataclasses.replace(
                context,
                evidence=evidence,
                interpretations=mine,
            )

            by_key[key] = engine.run(view)

        best = max(
            record.readiness
            for record in by_key.values()
        )

        selected = next(
            key
            for key in pack.TIE_ORDER
            if key in by_key and by_key[key].readiness == best
        )

        context.outputs["reasoning_by_hypothesis"] = by_key
        context.outputs["reasoning_selected_key"] = selected

        return by_key[selected]
'''

PATCHES = [
    (re.compile(r"(\nfrom reasoning\.reasoning_engine import ReasoningEngine\n)"),
     lambda m: m.group(1) + "\nfrom domains import get_pack\n"),
    (re.compile(r"\n    def run\("),
     lambda m: "\n" + METHOD + "\n    def run("),
    (re.compile(r"\n([ \t]*)record = engine\.run\(context\)"),
     lambda m: ("\n{i}pack = get_pack(context.observation)\n\n"
                "{i}if (\n"
                "{i}    getattr(pack, \"RELATIONS\", None)\n"
                "{i}    and context.outputs.get(\"hypothesis_keys\")\n"
                "{i}):\n\n"
                "{i}    record = self._reason_per_hypothesis(\n"
                "{i}        context, engine, pack\n"
                "{i}    )\n\n"
                "{i}else:\n\n"
                "{i}    record = engine.run(context)").format(i=m.group(1))),
]

src = FILE.read_text(encoding="utf-8")
if "_reason_per_hypothesis" in src:
    sys.exit("Juz zaaplikowane - nic nie robie.")
for rx, _ in PATCHES:
    n = len(rx.findall(src))
    if n != 1:
        sys.exit(f"BLAD: wzorzec {rx.pattern[:60]!r} pasuje {n} razy. NIC nie zmieniono.")
for rx, fn in PATCHES:
    src = rx.sub(fn, src, count=1)
compile(src, str(FILE), "exec")
FILE.write_text(src, encoding="utf-8")
print("OK: reasoning_organ.py liczy rozumowanie dla kazdej hipotezy.")
