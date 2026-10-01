"""
VORO gis_qa - krok 1.6a: rozpoznanie granicy panstwa (sam pomiar, bez regul).

Uzycie (po download_data.py i build_golden.py):
    python scripts/explore_border.py

Porownuje pokrycie gmin ze zlotego zbioru z warstwa granicy panstwa z tej samej paczki PRG:
  - "uncovered": kawalki Polski, ktorych nie pokrywa zadna gmina
  - "outside":   kawalki gmin, ktore wystaja poza granice panstwa
Dla kazdego kawalka: powierzchnia, czy dotyka granicy panstwa, polozenie, gminy obok.
Zapisuje out/border_pieces.gpkg do obejrzenia w QGIS. Niczego nie ocenia.
"""
import json
from pathlib import Path

import geopandas as gpd
import shapely

BASE = Path(__file__).resolve().parents[1]
GOLDEN = BASE / "data" / "golden" / "golden.gpkg"
PRG_DIR = BASE / "data" / "raw" / "prg"
OUT = BASE / "out"


def pieces(geom):
    if geom is None or geom.is_empty:
        return []
    return [g for g in getattr(geom, "geoms", [geom]) if g.area > 0]


def describe(parts, state_boundary, gminy, label):
    # pas 1 m wokol granicy panstwa liczony RAZ (wczesniej dla kazdego kawalka osobno)
    border_zone = state_boundary.buffer(1.0)
    shapely.prepare(border_zone)
    rows = []
    for p in parts:
        idx = gminy.sindex.query(p.buffer(1.0), predicate="intersects")
        rows.append({
            "kind": label,
            "area_m2": round(p.area, 2),
            "touches_state_border": bool(border_zone.intersects(p)),
            "near": ", ".join(gminy["teryt"].iloc[idx].astype(str).tolist()[:6]),
            "geometry": p,
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=gminy.crs) if rows else None


def main():
    hits = [p for p in PRG_DIR.rglob("*.shp") if "panstw" in p.name.lower()]
    if len(hits) != 1:
        raise SystemExit(f"Szukalem jednej warstwy granicy panstwa w {PRG_DIR}, znalazlem: {hits}")
    state = gpd.read_file(hits[0]).to_crs("EPSG:2180")
    print(f"Warstwa panstwa: {hits[0].name} | obiektow: {len(state)} | "
          f"poprawna: {bool(state.geometry.is_valid.all())}")
    state_geom = shapely.union_all(state.geometry.values)

    gminy = gpd.read_file(GOLDEN, layer="gminy")
    cover = shapely.union_all(gminy.geometry.values)

    print(f"Pole panstwa:   {state_geom.area / 1e6:,.1f} km2")
    print(f"Pole gmin:      {cover.area / 1e6:,.1f} km2")
    print("Licze kawalki...", flush=True)

    unc = describe(pieces(state_geom.difference(cover)), state_geom.boundary, gminy, "uncovered")
    out = describe(pieces(cover.difference(state_geom)), state_geom.boundary, gminy, "outside")

    summary = {}
    for name, df in (("uncovered", unc), ("outside", out)):
        if df is None:
            summary[name] = {"count": 0, "area_km2": 0}
            print(f"\n{name}: brak")
            continue
        df = df.sort_values("area_m2", ascending=False)
        summary[name] = {
            "count": len(df),
            "area_km2": round(df.area_m2.sum() / 1e6, 3),
            "touching_border": int(df.touches_state_border.sum()),
            "largest_m2": [float(a) for a in df.area_m2.head(5)],
        }
        print(f"\n{name}: {len(df)} kawalkow, razem {df.area_m2.sum() / 1e6:,.3f} km2, "
              f"przy granicy panstwa: {int(df.touches_state_border.sum())}")
        for _, r in df.head(10).iterrows():
            print(f"   {r.area_m2:>16,.1f} m2 | granica: {'tak' if r.touches_state_border else 'nie'} | obok: {r.near}")

    OUT.mkdir(exist_ok=True)
    path = OUT / "border_pieces.gpkg"
    if path.exists():
        path.unlink()
    for name, df in (("uncovered", unc), ("outside", out)):
        if df is not None:
            df.to_file(path, layer=name, driver="GPKG")
    (OUT / "border_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nZapisano: {path} (do QGIS) i out/border_summary.json")


if __name__ == "__main__":
    main()
