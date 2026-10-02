"""
VORO - etap 2.0: VORO poznaje granice panstwa (C7).

Uruchom w /root/VORO:  python3 /root/gis_qa/voro_adapter/patch_step20_c7.py

1. domains/gis_qa.py: C7 do NONCRITICAL_CHECKS; 3 nowe fakty w FACT_KEYS (zgodne z providerem).
   Tabela RELATIONS (krok 3) bez zmian.
2. domains/gis_qa_params.json: progi i wyjatki z /root/gis_qa (z C7 i morzem).
3. observation/providers/gis_qa_provider.py: kopia z /root/gis_qa/voro_adapter.
Jesli ktorykolwiek fragment nie pasuje DOKLADNIE raz, NIC nie jest zmieniane.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
GIS_QA = Path("/root/gis_qa")
if not (ROOT / "organism" / "runtime.py").exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")

PACK = ROOT / "domains" / "gis_qa.py"
PARAMS = ROOT / "domains" / "gis_qa_params.json"
PROVIDER_SRC = GIS_QA / "voro_adapter" / "gis_qa_provider.py"
PROVIDER_DST = ROOT / "observation" / "providers" / "gis_qa_provider.py"

src = PACK.read_text(encoding="utf-8")
if '"C7"' in src:
    sys.exit("domains/gis_qa.py: C7 juz jest - nic nie robie.")

patches = [
    (re.compile(r'NONCRITICAL_CHECKS = \("C5", "C6"\)'),
     'NONCRITICAL_CHECKS = ("C5", "C6", "C7")'),
    (re.compile(r'("n_gaps", "max_gap_m2",\n)(\))'),
     None),
]
n1 = len(patches[0][0].findall(src))
n2 = len(patches[1][0].findall(src))
if n1 != 1 or n2 != 1:
    sys.exit(f"BLAD: wzorce pasuja {n1} i {n2} razy (oczekiwano 1 i 1). NIC nie zmieniono.")
src = patches[0][0].sub(patches[0][1], src, count=1)
src = patches[1][0].sub(
    lambda m: m.group(1) + '    "n_border_pieces", "max_border_piece_m2", "known_uncovered_m2",\n' + m.group(2),
    src, count=1)
compile(src, str(PACK), "exec")

params = json.loads((GIS_QA / "params.json").read_text(encoding="utf-8"))
exceptions = json.loads((GIS_QA / "known_exceptions.json").read_text(encoding="utf-8"))
if "c7_border_tol_m2" not in params:
    sys.exit("BLAD: /root/gis_qa/params.json nie ma c7_border_tol_m2 - zrob git pull w /root/gis_qa")
knowledge = json.loads(PARAMS.read_text(encoding="utf-8"))
knowledge["params"] = params
knowledge["known_exceptions"] = exceptions

# provider: FACT_KEYS w pakiecie i w providerze musza byc zgodne
prov = PROVIDER_SRC.read_text(encoding="utf-8")
if "known_uncovered_m2" not in prov:
    sys.exit("BLAD: provider w /root/gis_qa nie jest zaktualizowany - zrob git pull")

PACK.write_text(src, encoding="utf-8")
PARAMS.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")
shutil.copy2(PROVIDER_SRC, PROVIDER_DST)
print("OK: C7 w pakiecie (niekrytyczne), 3 nowe fakty, wiedza z C7 i morzem, nowy provider.")
