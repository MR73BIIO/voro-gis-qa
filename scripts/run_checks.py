"""
VORO gis_qa - krok 1.1: uruchomienie C1-C6 na zbiorze + status PASS/REVIEW/REJECT.

Uzycie:
    python scripts/run_checks.py                          # na zlotym zbiorze
    python scripts/run_checks.py --data sciezka/zbior.gpkg

Wynik: out/findings_<czas>.json + podsumowanie w terminalu.
Na zlotym zbiorze oczekujemy 0 znalezisk - to mierzy "szum" sprawdzen.
"""
import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd

from checks import judge, load_terc_gminy
from incidents import build_incidents
from measures import measure

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / "manifest.json"
PARAMS = BASE / "params.json"
EXCEPTIONS = BASE / "known_exceptions.json"
OUT = BASE / "out"


def status_for(severities: set) -> str:
    if "krytyczna" in severities:
        return "REJECT"
    if severities:
        return "REVIEW"
    return "PASS"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=BASE / "data" / "golden" / "golden.gpkg")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    if "terc" not in manifest:
        sys.exit("BLAD: w manifescie brak TERC (uruchom download_data.py --terc ...)")
    terc = load_terc_gminy(BASE / manifest["terc"]["path"])

    exceptions = json.loads(EXCEPTIONS.read_text(encoding="utf-8")) if EXCEPTIONS.exists() else []

    t0 = time.time()
    gminy = gpd.read_file(args.data, layer="gminy")
    powiaty = gpd.read_file(args.data, layer="powiaty")
    try:
        state = gpd.read_file(args.data, layer="panstwo")
    except Exception:
        state = None
    try:
        reference = gpd.read_file(args.data, layer="known_uncovered")
    except Exception:
        reference = None
    m = measure(gminy, powiaty, terc, state, reference)
    findings, diagnostics = judge(m, params, exceptions)
    incidents = build_incidents(m, findings, params)
    elapsed = time.time() - t0

    per_feature = {}
    for f in findings:
        if f["teryt"] is not None:
            per_feature.setdefault(f["teryt"], set()).add(f["severity"])
    dataset_level = {f["severity"] for f in findings if f["teryt"] is None}
    # status liczony per WIERSZ (nie per kod) - duplikaty TERYT to dwie gminy
    statuses = [status_for(per_feature.get(t, set())) for t in gminy["teryt"].astype(str)]
    counts = Counter(statuses)
    dataset_status = status_for(dataset_level | {s for v in per_feature.values() for s in v})

    # test spojnosci: statusy musza sumowac sie do liczby gmin
    assert sum(counts.values()) == len(gminy), "statusy nie sumuja sie do liczby gmin"

    result = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "data": str(args.data),
        "params": params,
        "known_exceptions": exceptions,
        "n_features": len(gminy),
        "crs": m["crs"],
        "dataset_status": dataset_status,
        "status_counts": {k: counts.get(k, 0) for k in ("PASS", "REVIEW", "REJECT")},
        "findings_per_check": dict(Counter(f["check"] for f in findings)),
        "diagnostics": diagnostics,
        "elapsed_s": round(elapsed, 1),
        "n_incidents": len(incidents),
        "incidents": incidents,
        "findings": findings,
    }
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = OUT / f"findings_{stamp}.json"
    n = 1
    while path.exists():  # dwa przebiegi w tej samej sekundzie nie nadpisuja sie
        n += 1
        path = OUT / f"findings_{stamp}_{n}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Zbior: {args.data.name}  |  gmin: {len(gminy)}  |  czas: {elapsed:.1f} s")
    print(f"Status zbioru: {dataset_status}")
    print(f"PASS {counts.get('PASS', 0)}  REVIEW {counts.get('REVIEW', 0)}  REJECT {counts.get('REJECT', 0)}")
    for c in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
        print(f"  {c}: {result['findings_per_check'].get(c, 0)} znalezisk")
    print("Diagnostyka:", json.dumps(diagnostics, ensure_ascii=False))
    print(f"Incydenty: {len(incidents)} (znalezisk: {len(findings)})")
    for f in findings[:15]:
        print(f"  - {f['check']} {f['teryt']}: {f['detail']}")
    if len(findings) > 15:
        print(f"  ... i {len(findings) - 15} wiecej w pliku")
    print(f"Zapisano: {path}")


if __name__ == "__main__":
    main()
