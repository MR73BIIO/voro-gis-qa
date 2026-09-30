"""
VORO - lata 1.3c: Runtime przyjmuje provider z zewnatrz.

Uruchom w /root/VORO:  python3 /root/gis_qa/patch_runtime_provider.py
- robi kopie organism/runtime.py.bak_1_3c
- zmienia TYLKO: sygnature live() (+ provider=None) i miejsce tworzenia Observation
- bez provider zachowanie jest identyczne jak dotad (Ekstraklasa)
- jesli nie znajdzie dokladnie jednego dopasowania, NIC nie zmienia
"""
import re
import shutil
import sys
from pathlib import Path

path = Path("organism/runtime.py")
if not path.exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")
src = path.read_text(encoding="utf-8")

if "provider.observe(subject_id)" in src:
    sys.exit("Juz zaaplikowane - nic nie robie.")

sig_re = re.compile(r"(\n([ \t]*)cycle:\s*int\s*=\s*1,\n)(\s*\):\n\s*\n\s*self\.load_registry\(\))")
obs_re = re.compile(
    r"\n([ \t]*)from observation\.providers\.master_observation_provider import \(\s*"
    r"MasterObservationProvider\s*\)\s*observation = \(\s*MasterObservationProvider\(\)\s*"
    r"\.observe\(subject_id\)\s*\)")

if len(sig_re.findall(src)) != 1 or len(obs_re.findall(src)) != 1:
    sys.exit("BLAD: nie znalazlem dokladnie jednego miejsca do zmiany - plik NIETKNIETY.")

new = sig_re.sub(lambda m: m.group(1) + m.group(2) + "provider=None,  # ObservationProvider; None = Ekstraklasa\n" + m.group(3), src)
new = obs_re.sub(lambda m: (
    "\n{i}if provider is None:\n"
    "{i}    # zgodnosc wstecz: domyslnie swiat Ekstraklasy\n"
    "{i}    from observation.providers.master_observation_provider import (\n"
    "{i}        MasterObservationProvider\n"
    "{i}    )\n"
    "{i}    provider = MasterObservationProvider()\n"
    "{i}observation = provider.observe(subject_id)").format(i=m.group(1)), new)

compile(new, str(path), "exec")
shutil.copy2(path, path.with_name("runtime.py.bak_1_3c"))
path.write_text(new, encoding="utf-8")
print("OK: runtime.py zmieniony, kopia w organism/runtime.py.bak_1_3c")
