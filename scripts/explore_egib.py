"""
VORO gis_qa - rozpoznanie R0: dzialki z powiatowej uslugi WFS EGiB a obreby z PRG.
Sam pomiar, bez regul i progow.

Uzycie (po explore_gdansk.py, ktory zapisuje out/r0_<teryt>.gpkg):
    python scripts/explore_egib.py
    python scripts/explore_egib.py --obreby 0001,0011,0144,0715
    python scripts/explore_egib.py --refresh        # pobierz jeszcze raz mimo kopii na dysku

Dla kazdego wskazanego obrebu:
  - bierze okno (BBOX) obrebu z PRG, pyta usluge o liczbe dzialek w oknie (resultType=hits)
    i pobiera je kaflami po 2 km; odpowiedzi zostaja w data/raw/egib/ i kolejne uruchomienie
    czyta je z dysku. Filtr po atrybucie nie jest uzywany: usluga odpowiada na niego bledem 500
    (zmierzone 2026-11-15). Okno podawane jest w kolejnosci polnoc,wschod.
  - kazdy kafel (tez z dysku) jest sprawdzany z licznikiem uslugi. Zmierzone 2026-11-15:
    licznik = liczba oddanych obiektow + 1 w 9 z 9 kafli, a usluga potrafi oddac pusta,
    poprawnie zamknieta odpowiedz mimo licznika 1021. Kafel niezgodny jest pobierany ponownie
    (do 3 razy); jesli dalej sie nie zgadza, obreb nie dostaje pomiaru pokrycia.
  - dzieli dzialki z okna na wlasne (NUMER_OBREBU = numer obrebu) i sasiednie
  - mierzy atrybuty: ksztalt identyfikatora, powtorzenia, zgodnosc identyfikatora z numerem obrebu,
    nazwy obrebu i gminy, puste pola, zakres dat
  - sprawdza, ile obiektow po przeliczeniu lezy w gminie (kontrola kolejnosci osi)
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
SRC = "EPSG:2177"
ATTRS = ("ID_DZIALKI", "NUMER_DZIALKI", "NAZWA_OBREBU", "NUMER_OBREBU", "NUMER_JEDNOSTKI",
         "NAZWA_GMINY", "POLE_EWIDENCYJNE", "KLASOUZYTKI_EGIB", "GRUPA_REJESTROWA", "DATA")
HEADERS = {"User-Agent": "voro-gis-qa R0 (github.com/MR73BIIO/voro-gis-qa)"}
TILE_M = 2000          # bok kafla pobierania
MAX_WINDOW_HITS = 40000  # wieksze okno jest tylko liczone, nie pobierane
MAX_TILES = 16           # okno z wieksza liczba kafli tez tylko liczone (np. obreb ZATOKA)
HITS_OFFSET = 1          # licznik uslugi minus liczba oddanych obiektow, zmierzone 2026-11-15
ATTEMPTS = 3


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


def ask(url, bbox, hits=False):
    """Jedno zapytanie GetFeature oknem. bbox = (polnoc_min, wschod_min, polnoc_max, wschod_max)."""
    params = {"service": "WFS", "version": "1.1.0", "request": "GetFeature", "typeName": LAYER,
              "BBOX": ",".join(str(v) for v in bbox) + "," + SRC}
    if hits:
        params["resultType"] = "hits"
    r = requests.get(url, params=params, headers=HEADERS, timeout=600)
    r.raise_for_status()
    time.sleep(2)
    return r.content


def count_hits(content):
    m = re.search(rb'numberOfFeatures="(\d+)"', content)
    return int(m.group(1)) if m else None


def tiles(bbox):
    n0, e0, n1, e1 = bbox
    out = []
    n = n0
    while n < n1:
        e = e0
        while e < e1:
            out.append((n, e, min(n + TILE_M, n1), min(e + TILE_M, e1)))
            e += TILE_M
        n += TILE_M
    return out


def tile_ok(n, h):
    """Czy kafel jest kompletny wzgledem licznika uslugi."""
    return h is not None and n == max(h - HITS_OFFSET, 0)


def fetch(url, nr, bbox, refresh):
    """Zwraca (lista obiektow bez powtorzen, opis, lista kafli niezgodnych)."""
    RAW.mkdir(parents=True, exist_ok=True)
    feats, seen, bad = [], set(), []
    stats = Counter()
    for t in tiles(bbox):
        path = RAW / f"dzialki_{nr}_{t[0]}_{t[1]}_{t[2]}_{t[3]}.gml"
        h = count_hits(ask(url, t, hits=True))
        content = path.read_bytes() if path.exists() and not refresh else None
        n = len(parse(content)) if content is not None else None
        if content is not None and tile_ok(n, h):
            stats["z dysku, zgodne"] += 1
        else:
            if content is not None:
                stats["z dysku, niezgodne -> ponownie"] += 1
            for attempt in range(ATTEMPTS):
                content = ask(url, t)
                n = len(parse(content))
                if tile_ok(n, h):
                    break
                h = count_hits(ask(url, t, hits=True))
                if tile_ok(n, h):
                    break
                time.sleep(5)
            path.write_bytes(content)
            stats["z uslugi, zgodne" if tile_ok(n, h) else "z uslugi, NIEZGODNE"] += 1
        if not tile_ok(n, h):
            bad.append((t, n, h))
        for f in parse(content):
            if f[2] not in seen:
                seen.add(f[2])
                feats.append(f)
    note = f"kafli: {dict(stats)} | po usunieciu powtorzen: {len(feats)}"
    return feats, note, bad


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
        gid = next((v for k, v in el.attrib.items() if loc(k) == "id"), None) or f"brak-id-{len(feats)}"
        feats.append((attrs, polys, gid))
    return feats


def build(feats, swap, src_crs):
    """Obiekty -> GeoDataFrame w EPSG:2180. swap=True: pierwsza liczba to polnoc (Y), druga wschod (X)."""
    def fix(r):
        return [(b, a) for a, b in r] if swap else r
    rows, geoms = [], []
    for attrs, polys, _ in feats:
        shp = [Polygon(fix(e), [fix(h) for h in hs]) for e, hs in polys]
        geoms.append(None if not shp else shp[0] if len(shp) == 1 else MultiPolygon(shp))
        rows.append(attrs)
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs=src_crs)
    for a in ATTRS:
        if a not in gdf.columns:
            gdf[a] = ""
    return gdf.to_crs(CRS)


def measure_obreb(nr, gdf, others, prg, teryt, rows):
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
    if len(ref) == 1 and len(others):
        og = ref.geometry.iloc[0]
        ok = others[~(others.geometry.isna() | others.geometry.is_empty)]
        alien = ok[ok.geometry.representative_point().within(og)]
        print(f"  dzialki o innym numerze obrebu z punktem w tym obrebie PRG: {len(alien)} "
              f"{dict(Counter(alien['NUMER_OBREBU']).most_common(5))} {alien['ID_DZIALKI'].tolist()[:5]}")
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

    global SRC
    SRC = args.src_crs
    all_gdf, rows = [], []
    for nr in [n.strip() for n in args.obreby.split(",") if n.strip()]:
        print(f"\n== Obreb {nr} ==")
        code = f"{args.teryt[:6]}_{args.teryt[6]}.{nr}"
        ref = prg[prg["code"] == code]
        if len(ref) != 1:
            print(f"  PRG: obiektow o kodzie {code}: {len(ref)} - okna nie ma, pomijam")
            continue
        e0, n0, e1, n1 = ref.to_crs(args.src_crs).total_bounds
        bbox = (int(n0) - 5, int(e0) - 5, int(n1) + 6, int(e1) + 6)
        km2 = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / 1e6
        hits = count_hits(ask(args.url, bbox, hits=True))
        print(f"  PRG: nazwa '{ref['name'].iloc[0]}' | okno {km2:,.1f} km2 | dzialek w oknie wg uslugi: {hits}")
        n_tiles = len(tiles(bbox))
        if hits is None or hits > MAX_WINDOW_HITS or n_tiles > MAX_TILES:
            print(f"  okno nie jest pobierane (kafli {n_tiles}, prog {MAX_TILES}; "
                  f"prog obiektow {MAX_WINDOW_HITS}) - tylko liczba")
            continue
        feats, note, bad = fetch(args.url, nr, bbox, args.refresh)
        print(f"  {note}")
        for t, n, h in bad:
            print(f"  NIEZGODNY KAFEL {t}: w pliku {n}, licznik uslugi {h}")
        if not feats:
            continue
        gdf = build(feats, True, args.src_crs)
        inside = int(gdf.geometry.representative_point().within(gmina_geom.buffer(5000)).sum())
        print(f"  po przeliczeniu (polnoc,wschod) w gminie lezy {inside} z {len(gdf)} obiektow")
        pairs = Counter(zip(gdf["NUMER_OBREBU"], gdf["NAZWA_OBREBU"]))
        print(f"  obreby w oknie (numer, nazwa w ewidencji): liczba dzialek -> {dict(pairs.most_common(12))}")
        own = gdf[gdf["NUMER_OBREBU"] == nr].reset_index(drop=True)
        others = gdf[gdf["NUMER_OBREBU"] != nr].reset_index(drop=True)
        print(f"  dzialki wlasne (NUMER_OBREBU = {nr}): {len(own)} | sasiednie w oknie: {len(others)}")
        if own.empty:
            continue
        if bad:
            print("  pomiar pokrycia pominiety: dane niekompletne, wynik bylby artefaktem pobierania")
            continue
        measure_obreb(nr, own, others, prg, args.teryt, rows)
        own["obreb"] = nr
        all_gdf.append(own)

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
