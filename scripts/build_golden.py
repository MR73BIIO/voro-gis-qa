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
TARGET_CRS = "EPSG:2180"
KNOWN_UNCOVERED_MIN_M2 = 1_000_000  # 1 km2: morze tak, paski przy granicy (max ~32 m2) nie          # metryczny - wszystkie powierzchnie i odleglosci
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


def read_state():
    """Warstwa granicy panstwa z tej samej paczki PRG (A00), jako jeden obiekt w EPSG:2180."""
    hits = [p for p in (BASE / "data" / "raw" / "prg").rglob("*.shp") if "panstw" in p.name.lower()]
    if len(hits) != 1:
        return None
    st = gpd.read_file(hits[0]).to_crs(TARGET_CRS)
    geom = shapely.union_all(st.geometry.values)
    return gpd.GeoDataFrame({"name": ["Polska"]}, geometry=[geom], crs=TARGET_CRS)


def state_hash(gdf) -> str:
    return hashlib.sha256(shapely.to_wkb(shapely.normalize(gdf.geometry.iloc[0]))).hexdigest()


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
    state = read_state()
    if state is not None:
        state.to_file(GOLDEN, layer="panstwo", driver="GPKG")
        # Znane obszary bez gmin (morze): kawalki panstwa bez gmin wieksze niz 1 km2.
        # Zapisane jako geometria odniesienia, zeby nowa dziura przy brzegu byla osobnym kawalkiem.
        diff = state.geometry.iloc[0].difference(shapely.union_all(gminy.geometry.values))
        big = [p for p in getattr(diff, "geoms", [diff]) if p.area > KNOWN_UNCOVERED_MIN_M2]
        if big:
            ref = gpd.GeoDataFrame({"name": ["known uncovered"]},
                                   geometry=[shapely.union_all(big)], crs=TARGET_CRS)
            ref.to_file(GOLDEN, layer="known_uncovered", driver="GPKG")
            print(f"Znane obszary bez gmin: {len(big)}, razem {ref.area.iloc[0]:,.1f} m2")
    else:
        print("UWAGA: brak warstwy granicy panstwa (A00) - C7 nie bedzie dzialac")

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
    if state is not None:
        s_back = gpd.read_file(GOLDEN, layer="panstwo")
        manifest["golden"]["content_hash"]["panstwo"] = state_hash(s_back)
        try:
            r_back = gpd.read_file(GOLDEN, layer="known_uncovered")
            manifest["golden"]["content_hash"]["known_uncovered"] = state_hash(r_back)
        except Exception:
            pass
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK. Zloty zbior: {len(g_back)} gmin, {len(p_back)} powiatow")
    print(f"    hash gmin: {manifest['golden']['content_hash']['gminy'][:16]}...")


def verify() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = manifest["golden"]["content_hash"]
    ok = True
    for layer in expected:
        gdf = gpd.read_file(GOLDEN, layer=layer)
        if layer in ("panstwo", "known_uncovered"):
            actual = state_hash(gdf)
        else:
            actual = content_hash(gdf.sort_values("teryt").reset_index(drop=True))
        status = "OK" if actual == expected[layer] else "ZMIENIONY!"
        ok &= actual == expected[layer]
        print(f"{layer}: {status}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    (verify if ap.parse_args().verify else build)()
