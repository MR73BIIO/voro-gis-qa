"""
VORO gis_qa - rozpoznanie R0 dla jednej gminy (domyslnie Gdansk): sam pomiar, bez regul.

Uzycie (po download_data.py i build_golden.py):
    python scripts/explore_gdansk.py
    python scripts/explore_gdansk.py --teryt 2261011

Trzy pomiary:
  1. Jakie warstwy sa w paczce PRG (nazwa pliku, liczba obiektow, kolumny).
  2. Gmina w zlotym zbiorze: nazwa PRG i TERC, pole, sasiedzi i ich nazwy.
  3. Warstwy ewidencyjne (jednostki, obreby) w granicy gminy: kody, nazwy, geometria,
     pokrycie granicy gminy (kawalki bez obrebu, kawalki poza gmina), nakladanie.

Niczego nie ocenia i nie ma progow. Zapisuje out/r0_<teryt>.gpkg do obejrzenia w QGIS.
Progi i przewidywanie powstaja dopiero po tym pomiarze.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

import geopandas as gpd
import pyogrio
import shapely

from checks import load_terc_gminy

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / "manifest.json"
GOLDEN = BASE / "data" / "golden" / "golden.gpkg"
PRG_DIR = BASE / "data" / "raw" / "prg"
OUT = BASE / "out"
CRS = "EPSG:2180"
CODE_COL, NAME_COL = "JPT_KOD_JE", "JPT_NAZWA_"
EWID_KEYS = ("ewidenc", "obreb", "obręb")


def pieces(geom):
    if geom is None or geom.is_empty:
        return []
    return [g for g in getattr(geom, "geoms", [geom]) if g.area > 0]


def pattern(code: str) -> str:
    """Ksztalt kodu: cyfry -> 9, litery -> A, reszta bez zmian (np. 999999_9.9999)."""
    return re.sub(r"[^\W\d_]", "A", re.sub(r"\d", "9", code))


def top(values, n=5):
    return [round(float(v), 2) for v in sorted(values, reverse=True)[:n]]


def read_pl(path, **kw):
    """Czyta SHP i pilnuje polskich znakow, jak build_golden.read_layer, ale bez przerywania."""
    last = None
    for enc in (None, "utf-8", "cp1250"):
        try:
            gdf = gpd.read_file(path, encoding=enc, **kw) if enc else gpd.read_file(path, **kw)
        except Exception as e:  # zle kodowanie potrafi wywrocic odczyt
            last = e
            continue
        last = gdf
        if NAME_COL not in gdf.columns or "�" not in "".join(gdf[NAME_COL].fillna("").astype(str)):
            return gdf
    if isinstance(last, Exception):
        raise last
    return last


def list_layers():
    print("== 1. Warstwy w paczce PRG ==")
    shp = sorted(PRG_DIR.rglob("*.shp"))
    if not shp:
        raise SystemExit(f"Brak plikow .shp w {PRG_DIR} (uruchom download_data.py)")
    for p in shp:
        info = pyogrio.read_info(p)
        print(f"  {p.name} | obiektow: {info['features']} | crs: {info['crs']} | "
              f"kolumny: {', '.join(map(str, info['fields']))}")
    return shp


def gmina_section(teryt):
    print(f"\n== 2. Gmina {teryt} w zlotym zbiorze ==")
    gminy = gpd.read_file(GOLDEN, layer="gminy")
    gminy["teryt"] = gminy["teryt"].astype(str)
    row = gminy[gminy["teryt"] == teryt]
    if len(row) != 1:
        raise SystemExit(f"W zlotym zbiorze jest {len(row)} gmin o kodzie {teryt}, oczekiwano 1")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    terc = load_terc_gminy(BASE / manifest["terc"]["path"])
    geom = row.geometry.iloc[0]
    print(f"  nazwa PRG: '{row['name'].iloc[0]}' | nazwa TERC: '{terc.get(teryt)}'")
    print(f"  pole: {geom.area / 1e6:,.3f} km2 | czesci: {len(pieces(geom))} | "
          f"poprawna: {bool(geom.is_valid)} | wierzcholkow: {shapely.get_num_coordinates(geom)}")
    idx = gminy.sindex.query(geom.buffer(1.0), predicate="intersects")
    near = gminy.iloc[idx]
    near = near[near["teryt"] != teryt].sort_values("teryt")
    same = 0
    print(f"  sasiedzi (do 1 m): {len(near)}")
    for t, n, g in zip(near["teryt"], near["name"], near.geometry):
        ref = terc.get(t)
        same += n == ref
        shared = geom.buffer(1.0).intersection(g.boundary).length
        mark = "" if n == ref else f"  <- TERC: '{ref}'"
        print(f"    {t} {n} | wspolna granica ok. {shared / 1000:,.2f} km{mark}")
    print(f"  nazwy sasiadow zgodne z TERC: {same} z {len(near)}")
    return row, geom


def ewid_section(path, teryt, gmina_geom, saved):
    print(f"\n== 3. {path.name} w granicy gminy {teryt} ==")
    info = pyogrio.read_info(path)
    fields = [str(f) for f in info["fields"]]
    if CODE_COL not in fields:
        print(f"  pominiete: brak kolumny {CODE_COL}; kolumny: {', '.join(fields)}")
        return
    # okno odczytu: obwiednia gminy + 2 km, przeliczona na uklad warstwy
    box = gpd.GeoSeries([shapely.box(*gmina_geom.buffer(2000).bounds)], crs=CRS)
    bbox = tuple(box.to_crs(info["crs"]).total_bounds) if info["crs"] else tuple(box.total_bounds)
    gdf = read_pl(path, bbox=bbox)
    if gdf.crs is None:
        print("  pominiete: warstwa bez ukladu wspolrzednych")
        return
    gdf = gdf.to_crs(CRS)
    gdf["code"] = gdf[CODE_COL].fillna("").astype(str).str.strip()
    gdf["name"] = gdf[NAME_COL].fillna("").astype(str).str.strip() if NAME_COL in gdf.columns else ""
    print(f"  obiektow w oknie: {len(gdf)}")

    by_code = gdf["code"].str.startswith(teryt[:6])
    inside = gdf.geometry.representative_point().within(gmina_geom)
    print(f"  wybor po kodzie (zaczyna sie od {teryt[:6]}): {int(by_code.sum())}")
    print(f"  wybor po polozeniu (punkt wewnatrz gminy):  {int(inside.sum())}")
    only_code = gdf[by_code & ~inside]
    only_geom = gdf[~by_code & inside]
    print(f"  kod gminy, ale lezy poza gmina: {len(only_code)} {only_code['code'].tolist()[:10]}")
    print(f"  lezy w gminie, ale inny kod:    {len(only_geom)} {only_geom['code'].tolist()[:10]}")

    sel = gdf[by_code].sort_values("code").reset_index(drop=True)
    if sel.empty:
        print("  brak obiektow o kodzie tej gminy - dalszych pomiarow nie ma")
        return
    print(f"  ksztalty kodow: {dict(Counter(sel['code'].map(pattern)))}")
    print(f"  przyklady: {sel['code'].head(3).tolist()} | nazwy: {sel['name'].head(3).tolist()}")
    dup = sorted(c for c, n in Counter(sel["code"]).items() if n > 1)
    print(f"  powtorzone kody: {len(dup)} {dup[:10]}")
    empty = sel[sel["name"].isin(["", "nan", "None"])]
    print(f"  puste nazwy: {len(empty)} {empty['code'].tolist()[:10]}")
    dupn = sorted(n for n, k in Counter(sel["name"]).items() if k > 1 and n not in ("", "nan", "None"))
    print(f"  nazwy uzyte wiecej niz raz: {len(dupn)} {dupn[:10]}")
    bad = sel[~sel.geometry.is_valid | sel.geometry.is_empty]
    print(f"  zle lub puste geometrie: {len(bad)} {bad['code'].tolist()[:10]}")
    print(f"  pole obiektu m2: min {sel.area.min():,.1f} | mediana {sel.area.median():,.1f} | "
          f"max {sel.area.max():,.1f}")

    good = sel[sel.geometry.is_valid & ~sel.geometry.is_empty]
    cover = shapely.union_all(good.geometry.values)
    print(f"  pole gminy: {gmina_geom.area:,.1f} m2 | suma pol: {good.area.sum():,.1f} m2 | "
          f"pole zlaczenia: {cover.area:,.1f} m2")
    rows = []
    for label, parts in (("bez_obiektu", pieces(gmina_geom.difference(cover))),
                         ("poza_gmina", pieces(cover.difference(gmina_geom)))):
        areas = [p.area for p in parts]
        print(f"  {label}: {len(parts)} kawalkow, razem {sum(areas):,.1f} m2, "
              f"najwieksze m2: {top(areas)}")
        rows += [{"layer": path.stem, "kind": label, "area_m2": round(p.area, 2), "geometry": p}
                 for p in parts]

    a, b = good.sindex.query(good.geometry, predicate="intersects")
    over = []
    for i, j in zip(a, b):
        if i < j:
            inter = good.geometry.iloc[i].intersection(good.geometry.iloc[j])
            if inter.area > 0:
                over.append((inter.area, good["code"].iloc[i], good["code"].iloc[j], inter))
    over.sort(key=lambda r: r[0], reverse=True)
    print(f"  par sasiadow: {int((a < b).sum())} | par z nakladaniem > 0: {len(over)} | "
          f"razem {sum(o[0] for o in over):,.1f} m2 | najwieksze m2: {top([o[0] for o in over])}")
    for area, c1, c2, _ in over[:5]:
        print(f"    {c1} x {c2}: {area:,.2f} m2")
    rows += [{"layer": path.stem, "kind": "nakladanie", "area_m2": round(o[0], 2), "geometry": o[3]}
             for o in over]
    saved.append((path.stem, sel[["code", "name", "geometry"]], rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teryt", default="2261011", help="kod gminy, 7 cyfr (domyslnie Gdansk)")
    args = ap.parse_args()

    shp = list_layers()
    row, geom = gmina_section(args.teryt)
    saved = []
    ewid = [p for p in shp if any(k in p.name.lower() for k in EWID_KEYS)]
    if not ewid:
        print("\n== 3. Brak warstw ewidencyjnych w paczce (szukalem: ewidenc, obreb) ==")
    for p in ewid:
        ewid_section(p, args.teryt, geom, saved)

    OUT.mkdir(exist_ok=True)
    target = OUT / f"r0_{args.teryt}.gpkg"
    if target.exists():
        target.unlink()
    row.to_file(target, layer="gmina", driver="GPKG")
    for stem, sel, rows in saved:
        sel.to_file(target, layer=stem[:40], driver="GPKG")
        if rows:
            gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS).to_file(
                target, layer=f"{stem[:30]}_kawalki", driver="GPKG")
    print(f"\nZapisano: {target}")
    print("To jest pomiar. Zadnych progow ani ocen.")


if __name__ == "__main__":
    main()
