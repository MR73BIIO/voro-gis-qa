"""
VORO - jedno zycie na danych gis_qa, z ochrona stanu organizmu (jak regresja K6).

Uruchom W /root/VORO interpreterem z gis_qa (tam jest geopandas):
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_gis.py golden
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/life_gis.py seed_42

Wypisuje hipotezy, wniosek, status i metryki. Stan organizmu jest przywracany
(to jest PROBA, nie zycie do pamieci). Zapis do pamieci przyjdzie w etapie 2.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regression_k6 import SKIP, VORO, file_hashes, restore  # noqa: E402

subject = sys.argv[1] if len(sys.argv) > 1 else "golden"

before = file_hashes()
tmp = Path(tempfile.mkdtemp(prefix="voro_gis_"))
shutil.copytree(VORO, tmp / "voro", ignore=shutil.ignore_patterns(*SKIP))
try:
    from observation.providers.gis_qa_provider import GisQaObservationProvider
    from organism.runtime import OrganismRuntime
    context, trace = OrganismRuntime().live(
        subject_id=subject,
        question=f"Czy zbior danych '{subject}' nadaje sie do uzycia?",
        interpretation_relation="SUPPORTS",
        life_id=f"LIFE-GIS-{subject}",
        pulse_id=f"PCT-GIS-{subject}",
        provider=GisQaObservationProvider(),
    )
finally:
    report = restore(before, tmp / "voro")
    shutil.rmtree(tmp)

o = context.outputs
print("\n=========== ZYCIE GIS:", subject, "===========")
print("Stan organizmu przywrocony:", len(report["przywrocone"]), "plikow, usuniete nowe:",
      len(report["usuniete_nowe"]))
print("Hipotezy:", [h.statement.split(":")[0] for h in o.get("hypotheses", [])],
      "| klucze:", o.get("hypothesis_keys"))
print("Dowody:", len(context.evidence or []))
r, d = o.get("reasoning"), o.get("decision")
if r is not None:
    print(f"Reasoning: readiness {r.readiness}  consistency {r.consistency}  "
          f"completeness {r.completeness}  confidence {r.confidence}")
if d is not None:
    print("Decision:", d.status, "|", d.control_reason)
    print("Wybrano:", d.selected_hypothesis)
