"""
VORO gis_qa - krok 1.0: zbudowanie i zwalidowanie ZLOTEGO ZBIORU.

Uzycie:
    python scripts/build_golden.py            # buduje data/golden/golden.gpkg
    python scripts/build_golden.py --verify   # sprawdza, czy zloty zbior jest nietkniety

Zloty zbior nie jest naprawiany automatycznie. Jesli PRG ma problem,
skrypt go pokazuje i konczy sie bledem - decyzje podejmujesz Ty.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import shapely

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / "manifest.json"
GOLDEN = BASE / "data" / "golden" / "golden.gpkg"
TARGET_CRS = "EPSG:2180"          # metryczny - wszystkie powierzchnie i odleglosci
EXPECTED = {"gminy": 2479, "powiaty": 380}   # stan PRG z 2026; zmiana = ostrzezenie, nie blad
PL_CHARS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")


def read_layer(path: Path) -> gpd.GeoDataFrame:
    """Czyta SHP i pilnuje polskich znakow (PRG bywa w roznych kodowaniach)."""
    for enc in (None, "utf-8", "cp1250"):
        gdf = gpd.read_file(path, encoding=enc) if enc else gpd.read_file(path)
        names = "".join(gdf["JPT_NAZWA_"].astype(str))
        if PL_CHARS & set(names) and "\ufffd" not in names:
            return gdf
    sys.exit(f"BLAD: nie udalo sie odczytac polskich znakow w {path.name}")


def prepare(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf[["JPT_KOD_JE", "JPT_NAZWA_", "geometry"]].rename(
        columns={"JPT_KOD_JE": "teryt", "JPT_NAZWA_": "name"}
    )
    out["teryt"] = out["teryt"].astype(str).str.strip()
    out["name"] = out["name"].astype(str).str.strip()
    out = out.to_crs(TARGET_CRS)
    return out.sort_values("teryt").reset_index(drop=True)


def content_hash(gdf: gpd.GeoDataFrame) -> str:
    """Hash tresci, nie pliku: teryt + nazwa + geometria w postaci kanonicznej."""
    h = hashlib.sha256()
    for teryt, name, geom in zip(gdf["teryt"], gdf["name"], gdf.geometry):
        h.update(teryt.encode())
        h.update(name.encode("utf-8"))
        h.update(shapely.to_wkb(shapely.normalize(geom)))
    return h.hexdigest()


def validate(gminy, powiaty) -> list[str]:
    errors, warnings = [], []

    for label, gdf, n in (("gminy", gminy, 7), ("powiaty", powiaty, 4)):
        if len(gdf) != EXPECTED[label]:
            warnings.append(f"{label}: {len(gdf)} rekordow, oczekiwano {EXPECTED[label]}")
        bad_fmt = gdf[~gdf["teryt"].str.fullmatch(rf"\d{{{n}}}")]
        if len(bad_fmt):
            errors.append(f"{label}: zly format TERYT: {bad_fmt['teryt'].tolist()[:10]}")
        dup = gdf[gdf["teryt"].duplicated(keep=False)]
        if len(dup):
            errors.append(f"{label}: zduplikowane TERYT: {sorted(set(dup['teryt']))[:10]}")
        empty = gdf[gdf["name"].isin(["", "nan", "None"])]
        if len(empty):
            errors.append(f"{label}: puste nazwy: {empty['teryt'].tolist()[:10]}")
        invalid = gdf[~gdf.geometry.is_valid | gdf.geometry.is_empty]
        if len(invalid):
            reasons = [shapely.is_valid_reason(g) for g in invalid.geometry[:5]]
            errors.append(f"{label}: {len(invalid)} zlych geometrii, np. "
                          f"{list(zip(invalid['teryt'][:5], reasons))}")

    bad_type = gminy[~gminy["teryt"].str[-1].isin(list("123"))]
    if len(bad_type):
        errors.append(f"gminy: rodzaj gminy spoza 1/2/3: {bad_type['teryt'].tolist()[:10]}")

    orphans = gminy[~gminy["teryt"].str[:4].isin(set(powiaty["teryt"]))]
    if len(orphans):
        errors.append(f"gminy bez powiatu: {orphans['teryt'].tolist()[:10]}")

    for w in warnings:
        print(f"OSTRZEZENIE: {w}")
    return errors


def build() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    layers = manifest["prg"]["layers"]
    raw_g = read_layer(BASE / layers["gminy"]["path"])
    raw_p = read_layer(BASE / layers["powiaty"]["path"])
    source_crs = str(raw_g.crs)

    gminy, powiaty = prepare(raw_g), prepare(raw_p)
    errors = validate(gminy, powiaty)
    if errors:
        print("ZLOTY ZBIOR NIE JEST ZLOTY:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    if GOLDEN.exists():
        GOLDEN.unlink()
    gminy.to_file(GOLDEN, layer="gminy", driver="GPKG")
    powiaty.to_file(GOLDEN, layer="powiaty", driver="GPKG")

    # hash liczony z tego, co faktycznie zapisano (odczyt zwrotny)
    g_back = gpd.read_file(GOLDEN, layer="gminy").sort_values("teryt").reset_index(drop=True)
    p_back = gpd.read_file(GOLDEN, layer="powiaty").sort_values("teryt").reset_index(drop=True)

    manifest["golden"] = {
        "path": str(GOLDEN.relative_to(BASE)),
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_crs": source_crs,
        "crs": TARGET_CRS,
        "counts": {"gminy": len(g_back), "powiaty": len(p_back)},
        "content_hash": {"gminy": content_hash(g_back), "powiaty": content_hash(p_back)},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK. Zloty zbior: {len(g_back)} gmin, {len(p_back)} powiatow")
    print(f"    hash gmin: {manifest['golden']['content_hash']['gminy'][:16]}...")


def verify() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = manifest["golden"]["content_hash"]
    ok = True
    for layer in ("gminy", "powiaty"):
        gdf = gpd.read_file(GOLDEN, layer=layer).sort_values("teryt").reset_index(drop=True)
        actual = content_hash(gdf)
        status = "OK" if actual == expected[layer] else "ZMIENIONY!"
        ok &= actual == expected[layer]
        print(f"{layer}: {status}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    (verify if ap.parse_args().verify else build)()
