"""
VORO - 1.3d krok 4: Hypothesis tworzy ZESTAW hipotez z pakietu domenowego.

Uruchom w /root/VORO:  python3 /root/gis_qa/voro_adapter/patch_step4_hypotheses.py

- outputs["hypotheses"]      = lista HypothesisRecord (wszystkie konkurujace hipotezy)
- outputs["hypothesis_keys"] = klucze hipotez z pakietu (gis_qa: PASS/REVIEW/REJECT; Ekstraklasa: None)
- payload / outputs["hypothesis"] = pierwsza hipoteza (zgodnosc wsteczna dla Interpretation)
Ekstraklasa ma jedna hipoteze -> komunikat, record_ids i payload identyczne jak dotad.
Jesli ktorykolwiek fragment nie pasuje DOKLADNIE raz, NIC nie jest zmieniane.
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "organism" / "runtime.py").exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")
if not (ROOT / "domains" / "__init__.py").exists():
    sys.exit("BLAD: brak domains/ - najpierw krok 2")

FILE = ROOT / "hypothesis" / "hypothesis_organ.py"

NEW_BODY = '''
{i}pack = get_pack(context.observation)

{i}#
{i}# Hypotheses come from the domain pack (explicit, declared
{i}# knowledge), never from Evidence. One life may test several
{i}# competing hypotheses; Ekstraklasa declares exactly one.
{i}#

{i}hypotheses = [
{i}    self.engine.formulate(
{i}        question=question,
{i}        statement=statement,
{i}        life_id=context.life_id,
{i}    )
{i}    for statement in pack.HYPOTHESES
{i}]

{i}context.outputs["hypotheses"] = hypotheses
{i}context.outputs["hypothesis_keys"] = getattr(pack, "HYPOTHESIS_IDS", None)

{i}hypothesis = hypotheses[0]

{i}if len(hypotheses) == 1:
{i}    message = (
{i}        "Hypothesis created: "
{i}        f"{{hypothesis.statement}}"
{i}    )
{i}else:
{i}    message = (
{i}        f"Hypotheses created: {{len(hypotheses)}} ("
{i}        + " | ".join(h.statement.split(":")[0] for h in hypotheses)
{i}        + ")"
{i}    )

{i}return OrganResult(

{i}    organ=self.name,

{i}    success=True,

{i}    record_ids=[h.hypothesis_id for h in hypotheses],

{i}    message=message,

{i}    payload=hypothesis,

{i})'''

PATCHES = [
    (re.compile(r"(\nfrom hypothesis\.hypothesis_engine import \(\s*HypothesisEngine,\s*\)\n)"),
     lambda m: m.group(1) + "\nfrom domains import get_pack\n"),
    (re.compile(r'\n([ \t]*)statement = \(\s*"Wyższa od ligowej.*?payload=hypothesis,\s*\)', re.S),
     lambda m: NEW_BODY.format(i=m.group(1))),
]

src = FILE.read_text(encoding="utf-8")
if "get_pack" in src:
    sys.exit("Juz zaaplikowane - nic nie robie.")
for rx, _ in PATCHES:
    n = len(rx.findall(src))
    if n != 1:
        sys.exit(f"BLAD: wzorzec {rx.pattern[:60]!r} pasuje {n} razy. NIC nie zmieniono.")
for rx, fn in PATCHES:
    src = rx.sub(fn, src, count=1)
compile(src, str(FILE), "exec")
FILE.write_text(src, encoding="utf-8")
print("OK: hypothesis_organ.py tworzy zestaw hipotez z pakietu domenowego.")
