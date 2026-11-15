"""
VORO gis_qa - rozpoznanie R0: dzialki z powiatowej uslugi WFS EGiB a obreby z PRG.
Sam pomiar, bez regul i progow.

Uzycie (po explore_gdansk.py, ktory zapisuje out/r0_<teryt>.gpkg):
    python scripts/explore_egib.py
    python scripts/explore_egib.py --obreby 0001,0011,0144,0715
    python scripts/explore_egib.py --refresh        # pobierz jeszcze raz mimo kopii na dysku

Dla kazdego wskazanego obrebu:
  - pyta usluge o liczbe dzialek (resultType=hits), potem pobiera je jednym zapytaniem z filtrem
    NUMER_OBREBU; odpowiedz zostaje w data/raw/egib/ i kolejne uruchomienie czyta ja z dysku
  - mierzy atrybuty: ksztalt identyfikatora, powtorzenia, zgodnosc identyfikatora z numerem obrebu,
    nazwy obrebu i gminy, puste pola, zakres dat
  - mierzy kolejnosc osi wspolrzednych (ktora daje polozenie w gminie)
  - porownuje z obrebem PRG o tym samym numerze: nazwa, ile dzialek lezy w obrebie,
    kawalki obrebu bez dzialki, kawalki dzialek poza obrebem, nakladanie dzialek

GML czytany jest wprost (bez sterownika GDAL), zeby kolejnosc osi byla mierzona, a nie zgadywana.
Zapisuje out/egib_r0_<teryt>.gpkg do obejrzenia w QGIS. Niczego nie ocenia.
"""
import argparse
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import geopandas as gpd
import requests
import shapely
from shapely.geometry import MultiPolygon, Polygon

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw" / "egib"
OUT = BASE / "out"
CRS = "EPSG:2180"
URL = "https://ewid-wms.gdansk.gda.pl/iip/ows"
LAYER = "ms:dzialki"
ATTRS = ("ID_DZIALKI", "NUMER_DZIALKI", "NAZWA_OBREBU", "NUMER_OBREBU", "NUMER_JEDNOSTKI",
         "NAZWA_GMINY", "POLE_EWIDENCYJNE", "KLASOUZYTKI_EGIB", "GRUPA_REJESTROWA", "DATA")
HEADERS = {"User-Agent": "voro-gis-qa R0 (github.com/MR73BIIO/voro-gis-qa)"}
ROUND_LIMITS = {100, 500, 1000, 2000, 5000, 10000, 20000, 50000}


def loc(tag):
    return tag.rsplit("}", 1)[-1]


def pieces(geom):
    if geom is None or geom.is_empty:
        return []
    return [g for g in getattr(geom, "geoms", [geom]) if g.area > 0]


def pattern(code):
    return re.sub(r"[^\W\d_]", "A", re.sub(r"\d", "9", code))


def top(values, n=5):
    return [round(float(v), 2) for v in sorted(values, reverse=True)[:n]]


def wfs_filter(nr):
    return ("<ogc:Filter xmlns:ogc=\"http://www.opengis.net/ogc\"><ogc:PropertyIsEqualTo>"
            "<ogc:PropertyName>NUMER_OBREBU</ogc:PropertyName>"
            f"<ogc:Literal>{nr}</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>")


def fetch(url, nr, refresh):
    """Zwraca (bajty GML, liczba wg uslugi albo None, skad). Kopia na dysku ma pierwszenstwo."""
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"dzialki_{nr}.gml"
    if path.exists() and not refresh:
        return path.read_bytes(), None, f"z dysku ({path.name})"
    base = {"service": "WFS", "version": "1.1.0", "request": "GetFeature",
            "typeName": LAYER, "FILTER": wfs_filter(nr)}
    hits = None
    r = requests.get(url, params={**base, "resultType": "hits"}, headers=HEADERS, timeout=120)
    m = re.search(rb'numberOfFeatures="(\d+)"', r.content)
    if m:
        hits = int(m.group(1))
    time.sleep(2)
    r = requests.get(url, params=base, headers=HEADERS, timeout=600)
    r.raise_for_status()
    path.write_bytes(r.content)
    time.sleep(2)
    return r.content, hits, f"z uslugi, {len(r.content):,} bajtow, HTTP {r.status_code}"


def ring(el):
    """Lista par liczb w kolejnosci z pliku (bez zamiany osi)."""
    for child in el.iter():
        if loc(child.tag) in ("posList", "coordinates") and child.text:
            nums = [float(v) for v in re.split(r"[\s,]+", child.text.strip()) if v]
            return list(zip(nums[0::2], nums[1::2]))
    return []


def parse(content):
    """GML -> lista (atrybuty, lista wielokatow jako (zewnetrzny, [wewnetrzne])). Bez zamiany osi."""
    root = ET.fromstring(content)
    if loc(root.tag) != "FeatureCollection":
        raise SystemExit(f"Usluga nie zwrocila obiektow: {content[:400].decode('utf-8', 'replace')}")
    feats = []
    for el in root.iter():
        if loc(el.tag) != LAYER.split(":")[-1] or loc(el.tag) == "FeatureCollection":
            continue
        attrs = {loc(c.tag): (c.text or "").strip() for c in el if loc(c.tag) in ATTRS}
        polys = []
        for p in el.iter():
            if loc(p.tag) != "Polygon":
                continue
            ext, holes = [], []
            for part in p:
                if loc(part.tag) in ("exterior", "outerBoundaryIs"):
                    ext = ring(part)
                elif loc(part.tag) in ("interior", "innerBoundaryIs"):
                    holes.append(ring(part))
            if len(ext) >= 4:
                polys.append((ext, [h for h in holes if len(h) >= 4]))
        feats.append((attrs, polys))
    return feats


def build(feats, swap, src_crs):
    """Obiekty -> GeoDataFrame w EPSG:2180. swap=True: pierwsza liczba to polnoc (Y), druga wschod (X)."""
    def fix(r):
        return [(b, a) for a, b in r] if swap else r
    rows, geoms = [], []
    for attrs, polys in feats:
        shp = [Polygon(fix(e), [fix(h) for h in hs]) for e, hs in polys]
        geoms.append(None if not shp else shp[0] if len(shp) == 1 else MultiPolygon(shp))
        rows.append(attrs)
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=src_crs)
    for a in ATTRS:
        if a not in gdf.columns:
            gdf[a] = ""
    return gdf.to_crs(CRS)


def axis_order(feats, src_crs, gmina_geom):
    """Mierzy, przy ktorej kolejnosci osi pierwsze obiekty trafiaja w gmine (pas 5 km)."""
    sample = [f for f in feats if f[1]][:20]
    zone = gmina_geom.buffer(5000)
    res = {}
    for swap in (True, False):
        try:
            g = build(sample, swap, src_crs)
            res[swap] = int(g.geometry.representative_point().within(zone).sum())
        except Exception:
            res[swap] = 0
    print(f"  kolejnosc osi (na {len(sample)} obiektach): polnoc,wschod -> {res[True]} w gminie | "
          f"wschod,polnoc -> {res[False]} w gminie")
    return res[True] >= res[False]


def measure_obreb(nr, gdf, prg, teryt, rows):
    code = f"{teryt[:6]}_{teryt[6]}.{nr}"
    ids = gdf["ID_DZIALKI"]
    print(f"  ksztalty identyfikatora: {dict(Counter(ids.map(pattern)).most_common(6))}")
    dup = sorted(c for c, n in Counter(ids).items() if n > 1)
    print(f"  powtorzone identyfikatory: {len(dup)} {dup[:5]}")
    bad_prefix = gdf[~ids.str.startswith(code + ".")]
    print(f"  identyfikator nie zaczyna sie od {code}.: {len(bad_prefix)} {bad_prefix['ID_DZIALKI'].tolist()[:5]}")
    print(f"  NUMER_OBREBU: {dict(Counter(gdf['NUMER_OBREBU']).most_common(5))}")
    print(f"  NUMER_JEDNOSTKI: {dict(Counter(gdf['NUMER_JEDNOSTKI']).most_common(5))}")
    print(f"  NAZWA_OBREBU: {dict(Counter(gdf['NAZWA_OBREBU']).most_common(5))}")
    print(f"  NAZWA_GMINY: {dict(Counter(gdf['NAZWA_GMINY']).most_common(5))}")
    for a in ("POLE_EWIDENCYJNE", "KLASOUZYTKI_EGIB", "GRUPA_REJESTROWA"):
        print(f"  {a} puste: {int((gdf[a] == '').sum())} z {len(gdf)}")
    dates = sorted(d for d in gdf["DATA"] if d)
    print(f"  DATA: od {dates[0] if dates else '-'} do {dates[-1] if dates else '-'}")
    nogeom = gdf[gdf.geometry.isna() | gdf.geometry.is_empty]
    good = gdf[~(gdf.geometry.isna() | gdf.geometry.is_empty)]
    invalid = good[~good.geometry.is_valid]
    print(f"  bez geometrii: {len(nogeom)} | niepoprawna geometria: {len(invalid)} "
          f"{invalid['ID_DZIALKI'].tolist()[:5]}")
    good = good[good.geometry.is_valid]
    if good.empty:
        return

    ref = prg[prg["code"] == code]
    if len(ref) != 1:
        print(f"  PRG: obiektow o kodzie {code}: {len(ref)} - porownania nie ma")
        return
    og = ref.geometry.iloc[0]
    print(f"  PRG {code}: nazwa '{ref['name'].iloc[0]}' | pole {og.area:,.1f} m2")
    inside = good.geometry.representative_point().within(og)
    print(f"  dzialki z punktem w obrebie PRG: {int(inside.sum())} z {len(good)} | "
          f"poza: {good[~inside]['ID_DZIALKI'].tolist()[:5]}")
    cover = shapely.union_all(good.geometry.values)
    print(f"  suma pol dzialek: {good.area.sum():,.1f} m2 | pole zlaczenia: {cover.area:,.1f} m2")
    for label, parts in (("obreb_bez_dzialki", pieces(og.difference(cover))),
                         ("dzialka_poza_obrebem", pieces(cover.difference(og)))):
        areas = [p.area for p in parts]
        print(f"  {label}: {len(parts)} kawalkow, razem {sum(areas):,.1f} m2, najwieksze m2: {top(areas)}")
        rows += [{"obreb": nr, "kind": label, "area_m2": round(p.area, 2), "geometry": p} for p in parts]
    a, b = good.sindex.query(good.geometry, predicate="intersects")
    over = []
    for i, j in zip(a, b):
        if i < j:
            inter = good.geometry.iloc[i].intersection(good.geometry.iloc[j])
            if inter.area > 0:
                over.append((inter.area, good["ID_DZIALKI"].iloc[i], good["ID_DZIALKI"].iloc[j], inter))
    over.sort(key=lambda r: r[0], reverse=True)
    print(f"  par sasiednich dzialek: {int((a < b).sum())} | z nakladaniem > 0: {len(over)} | "
          f"razem {sum(o[0] for o in over):,.2f} m2 | najwieksze m2: {top([o[0] for o in over])}")
    rows += [{"obreb": nr, "kind": "nakladanie_dzialek", "area_m2": round(o[0], 2), "geometry": o[3]}
             for o in over]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teryt", default="2261011")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--src-crs", default="EPSG:2177", help="uklad wspolrzednych uslugi")
    ap.add_argument("--obreby", default="0001,0011,0144,0715", help="numery obrebow po przecinku")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    r0 = OUT / f"r0_{args.teryt}.gpkg"
    if not r0.exists():
        raise SystemExit(f"Brak {r0} - najpierw uruchom scripts/explore_gdansk.py")
    gmina_geom = gpd.read_file(r0, layer="gmina").geometry.iloc[0]
    import pyogrio
    names = [n for n in pyogrio.list_layers(r0)[:, 0] if "obreb" in n.lower() and "kawalki" not in n]
    if len(names) != 1:
        raise SystemExit(f"W {r0.name} szukalem jednej warstwy obrebow, znalazlem: {names}")
    prg = gpd.read_file(r0, layer=names[0])
    print(f"Usluga: {args.url} | warstwa: {LAYER} | uklad: {args.src_crs}")
    print(f"PRG: {len(prg)} obrebow z {r0.name}")

    swap, all_gdf, rows = None, [], []
    for nr in [n.strip() for n in args.obreby.split(",") if n.strip()]:
        print(f"\n== Obreb {nr} ==")
        content, hits, src = fetch(args.url, nr, args.refresh)
        feats = parse(content)
        note = ""
        if hits is not None and hits != len(feats):
            note = f"  <- usluga podala {hits}, pobrano {len(feats)}"
        elif len(feats) in ROUND_LIMITS:
            note = "  <- okragla liczba, mozliwy limit uslugi"
        print(f"  pobrano: {src} | dzialek: {len(feats)} | liczba wg uslugi: {hits}{note}")
        if not feats:
            continue
        if swap is None:
            swap = axis_order(feats, args.src_crs, gmina_geom)
        gdf = build(feats, swap, args.src_crs)
        measure_obreb(nr, gdf, prg, args.teryt, rows)
        gdf["obreb"] = nr
        all_gdf.append(gdf)

    if all_gdf:
        target = OUT / f"egib_r0_{args.teryt}.gpkg"
        if target.exists():
            target.unlink()
        import pandas as pd
        merged = gpd.GeoDataFrame(pd.concat(all_gdf, ignore_index=True), crs=CRS)
        merged[~merged.geometry.isna()].to_file(target, layer="dzialki", driver="GPKG")
        if rows:
            gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS).to_file(
                target, layer="kawalki", driver="GPKG")
        print(f"\nZapisano: {target}")
    print("To jest pomiar. Zadnych progow ani ocen.")


if __name__ == "__main__":
    main()
