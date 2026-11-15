"""
VORO gis_qa - krok 1.7: kontrola C8, obreby PRG a dzialki EGiB dla jednej gminy (domyslnie Gdansk).

Reguly i oczekiwane wyniki: docs/prediction_1.7_egib_gdansk.md (zapisane przed tym kodem).

Uzycie (po explore_gdansk.py, ktory zapisuje out/r0_<teryt>.gpkg):
    python -u scripts/check_egib.py
    python -u scripts/check_egib.py --refresh     # pobierz cale miasto od nowa

Kroki:
  1. Pobranie calego miasta siatka kafli 2 km (funkcje z explore_egib.py), kazdy kafel
     sprawdzony z licznikiem uslugi. Kafle zostaja w data/raw/egib/ (prefiks "miasto").
  2. Pomiar i ocena kazdego obrebu PRG wedlug regul C8.
  3. Zestawienie z przewidywaniem.
Wynik: out/c8_<czas>.json, out/c8_<czas>.gpkg (znaleziska do QGIS) i podsumowanie w terminalu.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from shapely.geometry import box

from explore_egib import URL, build, fetch, pieces

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "out"
CRS = "EPSG:2180"
SRC = "EPSG:2177"

# Reguly C8 - z docs/prediction_1.7_egib_gdansk.md
COVER_TOL_M2 = 150.0          # ok. 2 x najwiekszy zmierzony szum (75.5 m2)
OVERLAP_TOL_M2 = 1.0          # jak C5
COVER_EXCEPTIONS = {"0144"}   # ZATOKA: woda bez dzialek, pokrycie nie oceniane

# Przewidywanie - z docs/prediction_1.7_egib_gdansk.md
EXPECTED = {
    "obreby_bez_danych": ("==", 0),
    "nazwy_rozne": ("==", 0),
    "dzialki_w_obcym_obrebie": ("==", 0),
    "nakladania_ponad_tol": ("==", 0),
    "identyfikatory_powtorzone_lub_zle": ("==", 0),
    "obreby_z_pokryciem_ponad_tol": ("<=", 5),
}


def obreb_layer(r0):
    names = [n for n in pyogrio.list_layers(r0)[:, 0] if "obreb" in n.lower() and "kawalki" not in n]
    if len(names) != 1:
        raise SystemExit(f"W {r0.name} szukalem jednej warstwy obrebow, znalazlem: {names}")
    return gpd.read_file(r0, layer=names[0])


def tile_poly(t):
    """Kafel (polnoc0, wschod0, polnoc1, wschod1) w EPSG:2177 -> wielokat w EPSG:2180."""
    n0, e0, n1, e1 = t
    return gpd.GeoSeries([box(e0, n0, e1, n1)], crs=SRC).to_crs(CRS).iloc[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teryt", default="2261011")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    prefix = f"{args.teryt[:6]}_{args.teryt[6]}."

    r0 = OUT / f"r0_{args.teryt}.gpkg"
    if not r0.exists():
        raise SystemExit(f"Brak {r0} - najpierw uruchom scripts/explore_gdansk.py")
    gmina = gpd.read_file(r0, layer="gmina")
    prg = obreb_layer(r0)
    prg["nr"] = prg["code"].str.split(".").str[-1]
    if prg["nr"].duplicated().any():
        raise SystemExit(f"PRG: powtorzone numery obrebow {prg[prg['nr'].duplicated()]['nr'].tolist()}")
    print(f"PRG: {len(prg)} obrebow | usluga: {args.url}")

    # 1. Pobranie calego miasta
    e0, n0, e1, n1 = gmina.to_crs(SRC).total_bounds
    bbox = (int(n0) - 5, int(e0) - 5, int(n1) + 6, int(e1) + 6)
    print("Pobieram miasto siatka kafli (kazdy kafel sprawdzany z licznikiem)...", flush=True)
    feats, note, bad = fetch(args.url, "miasto", bbox, args.refresh)
    print(f"  {note}")
    for t, n, h in bad:
        print(f"  NIEZGODNY KAFEL {t}: w pliku {n}, licznik {h}")
    gdf = build(feats, True, SRC)
    gdf = gdf[~(gdf.geometry.isna() | gdf.geometry.is_empty)].reset_index(drop=True)
    print(f"  dzialek z geometria: {len(gdf)}")

    # obreby dotkniete niekompletnym kaflem = brak danych
    no_data = set()
    for t, _, _ in bad:
        tp = tile_poly(t)
        no_data |= set(prg[prg.intersects(tp)]["nr"])
    findings = []

    def add(rule, nr, detail, geom=None):
        findings.append({"rule": rule, "obreb": nr, "detail": detail, "geometry": geom})

    # 2a. Identyfikatory
    dup_ids = sorted(k for k, v in Counter(gdf["ID_DZIALKI"]).items() if v > 1)
    for i in dup_ids:
        add("id_powtorzony", i.split(".")[1] if i.count(".") >= 2 else None, f"ID {i} wystepuje wiecej niz raz")
    bad_prefix = gdf[~gdf.apply(lambda r: r["ID_DZIALKI"].startswith(f"{prefix}{r['NUMER_OBREBU']}."), axis=1)]
    for _, r in bad_prefix.iterrows():
        add("id_zly_obreb", r["NUMER_OBREBU"], f"ID {r['ID_DZIALKI']} przy NUMER_OBREBU {r['NUMER_OBREBU']}")

    # 2b. Numer obrebu z ewidencji a polozenie w PRG
    pts = gpd.GeoDataFrame(gdf[["ID_DZIALKI", "NUMER_OBREBU"]],
                           geometry=gdf.geometry.representative_point(), crs=CRS)
    joined = gpd.sjoin(pts, prg[["nr", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    outside = joined[joined["nr"].isna()]
    for i, r in outside.iterrows():
        add("dzialka_poza_gmina", r["NUMER_OBREBU"], f"{r['ID_DZIALKI']}: punkt poza obrebami PRG",
            gdf.geometry.iloc[i])
    wrong = joined[joined["nr"].notna() & (joined["nr"] != joined["NUMER_OBREBU"])]
    for i, r in wrong.iterrows():
        add("dzialka_w_obcym_obrebie", r["nr"],
            f"{r['ID_DZIALKI']} (NUMER_OBREBU {r['NUMER_OBREBU']}) lezy w obrebie PRG {r['nr']}",
            gdf.geometry.iloc[i])
    unknown = sorted(set(gdf["NUMER_OBREBU"]) - set(prg["nr"]))
    for u in unknown:
        add("obreb_nieznany_w_prg", u, f"NUMER_OBREBU {u} nie istnieje w PRG")

    # 2c. Nakladanie dzialek (cale miasto, wektorowo)
    geoms = gdf.geometry.values
    a, b = gdf.sindex.query(geoms, predicate="intersects")
    keep = a < b
    a, b = a[keep], b[keep]
    inter = shapely.intersection(geoms[a], geoms[b])
    areas = shapely.area(inter)
    print(f"  par sasiednich dzialek: {len(a)} | nakladanie > 0: {int((areas > 0).sum())} | "
          f"najwieksze m2: {np.round(np.sort(areas)[-5:][::-1], 2).tolist() if len(areas) else []}")
    for k in np.where(areas > OVERLAP_TOL_M2)[0]:
        ia, ib = a[k], b[k]
        add("nakladanie_dzialek", gdf["NUMER_OBREBU"].iloc[ia],
            f"{gdf['ID_DZIALKI'].iloc[ia]} x {gdf['ID_DZIALKI'].iloc[ib]}: {areas[k]:.2f} m2", inter[k])

    # 2d. Nazwy i pokrycie, obreb po obrebie
    per = []
    for _, o in prg.sort_values("nr").iterrows():
        nr, og = o["nr"], o.geometry
        own = gdf[gdf["NUMER_OBREBU"] == nr]
        row = {"obreb": nr, "nazwa_prg": o["name"], "dzialek": len(own), "brak_danych": nr in no_data}
        names = sorted(set(own["NAZWA_OBREBU"]))
        row["nazwy_egib"] = names
        if nr in no_data:
            per.append(row)
            continue
        if names and names != [o["name"]]:
            add("nazwa_rozna", nr, f"PRG '{o['name']}' a EGiB {names}")
        if own.empty:
            row.update(max_bez_dzialki_m2=round(og.area, 1), max_poza_obrebem_m2=0.0)
        else:
            cover = shapely.union_all(own.geometry.values)
            unc, out = pieces(og.difference(cover)), pieces(cover.difference(og))
            row["max_bez_dzialki_m2"] = round(max((p.area for p in unc), default=0.0), 2)
            row["max_poza_obrebem_m2"] = round(max((p.area for p in out), default=0.0), 2)
            row["suma_pol_dzialek_m2"] = round(float(own.area.sum()), 1)
        row["pole_prg_m2"] = round(og.area, 1)
        if nr not in COVER_EXCEPTIONS:
            parts = [("bez_dzialki", p) for p in (pieces(og.difference(cover)) if not own.empty else [og])]
            if not own.empty:
                parts += [("poza_obrebem", p) for p in pieces(cover.difference(og))]
            big = [(k, p) for k, p in parts if p.area > COVER_TOL_M2]
            for k, p in big:
                add("pokrycie_" + k, nr, f"{p.area:,.1f} m2", p)
            row["kawalki_ponad_tol"] = len(big)
        per.append(row)

    # 3. Zestawienie z przewidywaniem
    rules = Counter(f["rule"] for f in findings)
    measured = {
        "obreby_bez_danych": len(no_data),
        "nazwy_rozne": rules["nazwa_rozna"],
        "dzialki_w_obcym_obrebie": rules["dzialka_w_obcym_obrebie"],
        "nakladania_ponad_tol": rules["nakladanie_dzialek"],
        "identyfikatory_powtorzone_lub_zle": rules["id_powtorzony"] + rules["id_zly_obreb"],
        "obreby_z_pokryciem_ponad_tol": sum(1 for r in per if r.get("kawalki_ponad_tol", 0) > 0),
    }
    compare = {}
    for k, (op, v) in EXPECTED.items():
        ok = measured[k] == v if op == "==" else measured[k] <= v
        compare[k] = {"zmierzone": measured[k], "oczekiwane": f"{op} {v}", "zgodne": ok}

    pole_puste = {c: int((gdf[c] == "").sum()) for c in ("POLE_EWIDENCYJNE", "KLASOUZYTKI_EGIB")}
    summary = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "teryt": args.teryt, "url": args.url,
        "regula": {"cover_tol_m2": COVER_TOL_M2, "overlap_tol_m2": OVERLAP_TOL_M2,
                   "cover_exceptions": sorted(COVER_EXCEPTIONS)},
        "pobranie": {"opis": note, "kafle_niezgodne": [list(t) for t, _, _ in bad]},
        "dzialek": len(gdf), "obrebow_prg": len(prg),
        "puste_pola": pole_puste,
        "daty": sorted(set(gdf["DATA"]))[:5],
        "inne_fakty": {"dzialki_poza_gmina": rules["dzialka_poza_gmina"],
                       "numery_obrebow_nieznane_w_prg": unknown},
        "znaleziska_wg_reguly": dict(rules),
        "zestawienie_z_przewidywaniem": compare,
        "obreby": per,
        "znaleziska": [{k: v for k, v in f.items() if k != "geometry"} for f in findings],
    }
    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jpath, gpath = OUT / f"c8_{stamp}.json", OUT / f"c8_{stamp}.gpkg"
    jpath.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    geo = [f for f in findings if f["geometry"] is not None]
    if geo:
        gpd.GeoDataFrame(geo, geometry="geometry", crs=CRS).to_file(gpath, layer="znaleziska", driver="GPKG")

    print(f"\nDzialek: {len(gdf)} | obrebow PRG: {len(prg)} | puste pola: {pole_puste}")
    print(f"Znaleziska wg reguly: {dict(rules)}")
    top = sorted((r for r in per if r.get("kawalki_ponad_tol")), key=lambda r: -max(
        r.get("max_bez_dzialki_m2", 0), r.get("max_poza_obrebem_m2", 0)))
    for r in top[:10]:
        print(f"  pokrycie {r['obreb']} {r['nazwa_prg']}: kawalkow > {COVER_TOL_M2:.0f} m2: "
              f"{r['kawalki_ponad_tol']} | max bez dzialki {r['max_bez_dzialki_m2']:,.1f} | "
              f"max poza obrebem {r['max_poza_obrebem_m2']:,.1f}")
    for f in findings:
        if f["rule"] in ("nazwa_rozna", "dzialka_w_obcym_obrebie", "nakladanie_dzialek",
                         "id_powtorzony", "id_zly_obreb", "obreb_nieznany_w_prg"):
            print(f"  {f['rule']} {f['obreb']}: {f['detail']}")
    print("\nZestawienie z przewidywaniem:")
    for k, c in compare.items():
        print(f"  {k}: zmierzone {c['zmierzone']} | oczekiwane {c['oczekiwane']} | "
              f"{'ZGODNE' if c['zgodne'] else 'NIEZGODNE'}")
    print(f"\nZapisano: {jpath}" + (f" i {gpath}" if geo else ""))


if __name__ == "__main__":
    main()
