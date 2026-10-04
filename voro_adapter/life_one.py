#!/usr/bin/env python3
"""
VORO - jedno prawdziwe zycie na wskazanym zbiorze (oddech L1 i nastepne).

Nie zmienia organizmu: uzywa one_life() i counts() z life_gis_s2.py.
Odmawia, jesli plik wyniku juz istnieje (jedno zycie = jeden raz).

Uruchom W /root/VORO interpreterem z gis_qa:
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_one.py \
        --subject seed_201 --tag L1 --nr 01
Wynik: /root/VORO/docs/life_<tag>_<nr>.json
"""
import argparse
import json
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--subject", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--nr", required=True)
a = ap.parse_args()

out = Path("/root/VORO/docs") / f"life_{a.tag}_{a.nr}.json"
if out.exists():
    sys.exit(f"ODMOWA: {out} juz istnieje - to zycie zostalo przezyte.")

sys.path.insert(0, str(Path(__file__).resolve().parent))
argv, sys.argv = sys.argv, [sys.argv[0]]
try:
    from life_gis_s2 import counts, one_life
except SystemExit:
    sys.exit("ODMOWA: import life_gis_s2 zakonczyl program - sprawdz jego blok glowny.")
finally:
    sys.argv = argv

before = counts()
life = one_life(a.nr, a.subject, a.tag)
after = counts()
result = {
    "subject": a.subject,
    "tag": a.tag,
    "nr": a.nr,
    "life": life,
    "counts_before": before,
    "counts_after": after,
    "delta": {k: after[k] - before[k] for k in before},
}
out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
print(f"zapisano: {out}")
