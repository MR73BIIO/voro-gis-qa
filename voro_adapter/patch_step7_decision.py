"""
VORO - 1.3d krok 7: Decision nazywa hipoteze wybrana przez Reasoning.

Uruchom w /root/VORO:  python3 /root/gis_qa/voro_adapter/patch_step7_decision.py

Gdy Reasoning wybral jedna z konkurujacych hipotez (outputs["reasoning_selected_key"]),
DecisionRecord.selected_hypothesis = tresc TEJ hipotezy (np. "REJECT: ...").
Status ACCEPT/ABSTAIN ustala nadal niezmieniona DecisionPolicy.
Bez konkurujacych hipotez (Ekstraklasa) Decision dziala dokladnie jak dotad.
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "organism" / "runtime.py").exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")
FILE = ROOT / "decision" / "decision_engine.py"

BLOCK = '''
{i}#
{i}# Competing hypotheses: Decision names the hypothesis
{i}# selected by Reasoning instead of the reasoning conclusion.
{i}# Control status (ACCEPT/ABSTAIN) is unchanged.
{i}#

{i}selected_key = context.outputs.get("reasoning_selected_key")

{i}if selected_key:

{i}    import dataclasses

{i}    statements = dict(
{i}        zip(
{i}            context.outputs.get("hypothesis_keys") or (),
{i}            (
{i}                h.statement
{i}                for h in context.outputs.get("hypotheses") or []
{i}            ),
{i}        )
{i}    )

{i}    decision = dataclasses.replace(
{i}        decision,
{i}        selected_hypothesis=statements.get(selected_key, selected_key),
{i}    )
'''

RX = re.compile(r"(\n([ \t]*)decision = self\.decide\(\s*reasoning\s*\)\n)")

src = FILE.read_text(encoding="utf-8")
if "reasoning_selected_key" in src:
    sys.exit("Juz zaaplikowane - nic nie robie.")
n = len(RX.findall(src))
if n != 1:
    sys.exit(f"BLAD: wzorzec pasuje {n} razy. NIC nie zmieniono.")
src = RX.sub(lambda m: m.group(1) + BLOCK.format(i=m.group(2)), src, count=1)
compile(src, str(FILE), "exec")
FILE.write_text(src, encoding="utf-8")
print("OK: decision_engine.py nazywa hipoteze wybrana przez Reasoning.")
