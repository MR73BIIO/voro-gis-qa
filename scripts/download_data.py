"""
VORO gis_qa - krok 1.0: pobranie danych zrodlowych + manifest.

Uzycie:
    python scripts/download_data.py
    python scripts/download_data.py --terc sciezka/do/TERC.csv
    python scripts/download_data.py --skip-download   # zip juz pobrany

Wynik:
    data/raw/prg_jednostki_administracyjne.zip
    data/raw/prg/...            (rozpakowane SHP)
    manifest.json               (zrodlo, data pobrania, hashe)
"""
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw"
ZIP_PATH = RAW / "prg_jednostki_administracyjne.zip"
UNZIP_DIR = RAW / "prg"
MANIFEST = BASE / "manifest.json"

PRG_URL = "https://opendata.geoportal.gov.pl/prg/granice/00_jednostki_administracyjne.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    print(f"Pobieram {url}")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB", end="")
    print()
    tmp.replace(dest)


def find_layer(root: Path, keyword: str) -> Path:
    hits = [p for p in root.rglob("*.shp") if keyword.lower() in p.name.lower()]
    if len(hits) != 1:
        sys.exit(f"BLAD: szukalem jednej warstwy '{keyword}', znalazlem: {hits}")
    return hits[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--terc", type=Path, help="plik TERC pobrany recznie z eteryt.stat.gov.pl")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()

    previous = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    downloaded_now = not args.skip_download or not ZIP_PATH.exists()
    if downloaded_now:
        download(PRG_URL, ZIP_PATH)

    print("Licze hash paczki...")
    zip_hash = sha256_file(ZIP_PATH)

    # Data pobrania = chwila pobrania przez TEN skrypt, nie data pliku na dysku
    # (data pliku zmienia sie przy kopiowaniu). Przy --skip-download bierzemy date
    # z poprzedniego manifestu, ale tylko jesli to ta sama paczka (ten sam hash).
    prev_prg = previous.get("prg", {})
    same_package = prev_prg.get("zip_sha256") == zip_hash
    if downloaded_now:
        downloaded_at = datetime.now(timezone.utc).isoformat()
    elif same_package:
        downloaded_at = prev_prg.get("downloaded_at_utc")
    else:
        downloaded_at = None

    if UNZIP_DIR.exists():
        shutil.rmtree(UNZIP_DIR)
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(UNZIP_DIR)

    gminy = find_layer(UNZIP_DIR, "gmin")
    powiaty = find_layer(UNZIP_DIR, "powiat")

    manifest = {
        "environment": "gis_qa",
        "prg": {
            "url": PRG_URL,
            "downloaded_at_utc": downloaded_at,
            "zip_sha256": zip_hash,
            "zip_size_mb": round(ZIP_PATH.stat().st_size / 1e6, 1),
            "layers": {
                "gminy": {"path": str(gminy.relative_to(BASE)), "sha256": sha256_file(gminy)},
                "powiaty": {"path": str(powiaty.relative_to(BASE)), "sha256": sha256_file(powiaty)},
            },
        },
    }

    if downloaded_at is None:
        manifest["prg"]["download_note"] = (
            "paczka skopiowana, nie pobrana tym skryptem; data pobrania nieznana")
    # zloty zbior z poprzedniego manifestu zostaje tylko przy tej samej paczce
    if same_package and "golden" in previous:
        manifest["golden"] = previous["golden"]

    if args.terc:
        if not args.terc.exists():
            sys.exit(f"BLAD: brak pliku TERC {args.terc}")
        target = RAW / args.terc.name
        if args.terc.resolve() != target.resolve():
            shutil.copy2(args.terc, target)
        manifest["terc"] = {
            "path": str(target.relative_to(BASE)),
            "sha256": sha256_file(target),
            "added_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    else:
        print("UWAGA: bez --terc. TERC bedzie potrzebny dopiero w sprawdzeniu C6.")

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK. Gminy:   {gminy.name}")
    print(f"    Powiaty: {powiaty.name}")
    print(f"    Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
