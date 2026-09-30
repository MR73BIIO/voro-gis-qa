"""
Test dymny providera - uruchom W KATALOGU /root/VORO interpreterem z gis_qa:
    cd /root/VORO && /root/gis_qa/.venv/bin/python /root/gis_qa/voro_adapter/smoke_provider.py golden
Nie uruchamia organow. Sprawdza tylko Observation i czy ocena z samej Observation zgadza sie z run_checks.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from observation.providers.gis_qa_provider import GisQaObservationProvider  # noqa: E402

subject = sys.argv[1] if len(sys.argv) > 1 else "golden"
obs = GisQaObservationProvider().observe(subject)

assert "truth" not in json.dumps(obs.payload), "WYCIEK: prawda w Observation!"
assert "truth" not in json.dumps(obs.metadata), "WYCIEK: prawda w metadanych!"

print("OBSERVATION :", obs.observation_id, "|", obs.source, "|", obs.subject)
print("AS OF       :", obs.as_of_timestamp)
print("DOMAIN      :", obs.metadata["domain"])
for k in obs.metadata["fact_keys"]:
    print(f"  {k:<26} {obs.payload[k]}")
print("PAYLOAD KB  :", round(len(json.dumps(obs.payload)) / 1024))

from checks import judge  # noqa: E402  (sciezke dodal provider)
root = Path("/root/gis_qa")
params = json.loads((root / "params.json").read_text(encoding="utf-8"))
exc = json.loads((root / "known_exceptions.json").read_text(encoding="utf-8"))
findings, diag = judge(obs.payload["measurements"], params, exc)
crit = any(f["severity"] == "krytyczna" for f in findings)
status = "REJECT" if crit else ("REVIEW" if findings else "PASS")
print("OCENA Z SAMEJ OBSERVATION:", status, "| znalezisk:", len(findings))
