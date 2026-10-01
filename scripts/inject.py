"""
VORO gis_qa - krok 1.2: wstrzykiwacz bledow.

Bierze ZLOTY ZBIOR, psuje go w kontrolowany sposob i zapisuje, CO zepsul.
Ten sam seed = zawsze ten sam zepsuty zbior (zloty zbior nigdy nie jest zmieniany).

Uzycie:
    python scripts/inject.py --seed 42 --n 20
Wynik:
    data/runs/seed_42/corrupted.gpkg
    data/runs/seed_42/truth.json

Typy bledow (jeden blad na gmine; sasiedzi celu nie sa kolejnymi celami):
    E1 samoprzeciecie geometrii        -> C1
    E2 skopiowany TERYT innej gminy     -> C2
    E3 zly kod powiatu w TERYT          -> C3
    E4 jedna gmina w zlym ukladzie wsp. -> C4
    E5 przesuniecie gminy o 5-200 m     -> C5
    E6 szczelina na granicy z sasiadem  -> C5
    E7 usuniete polskie znaki z nazwy   -> C6
    E8 pusta nazwa                      -> C6

"collateral" = gminy, ktore legalnie dostana znalezisko przez cudzy blad
(np. sasiad przesunietej gminy). Nie licza sie jako falszywe alarmy.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / "manifest.json"
GOLDEN = BASE / "data" / "golden" / "golden.gpkg"

# E1-E8 = domyslny zestaw (seed 42 z README). E9 tylko na zyczenie (--types ... E9).
ALL_TYPES = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]
EXTRA_TYPES = ["E9"]
EXPECTED = {"E1": ["C1"], "E2": ["C2"], "E3": ["C3"], "E4": ["C4"],
            "E5": ["C5"], "E6": ["C5"], "E7": ["C6"], "E8": ["C6"], "E9": ["C7"]}
PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
PL_CHARS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")


# ---------------------------------------------------------------- pomocnicze
def neighbours(gminy) -> dict:
    geoms = gminy.geometry.values
    teryt = gminy["teryt"].astype(str).values
    left, right = gminy.sindex.query(geoms, predicate="intersects")
    out = {t: set() for t in teryt}
    for i, j in zip(left, right):
        if i != j:
            out[teryt[i]].add(teryt[j])
    return out


def largest_part(geom):
    if isinstance(geom, MultiPolygon):
        parts = list(geom.geoms)
        k = max(range(len(parts)), key=lambda i: parts[i].area)
        return parts, k
    return [geom], 0


def rebuild(parts, k, new_part):
    parts = parts.copy()
    parts[k] = new_part
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


# ---------------------------------------------------------------- bledy
def e1_self_intersection(geom, rng):
    parts, k = largest_part(geom)
    poly = parts[k]
    coords = list(poly.exterior.coords)[:-1]
    for _ in range(100):
        i = int(rng.integers(0, len(coords) - 2))
        c = coords.copy()
        c[i], c[i + 1] = c[i + 1], c[i]
        cand = Polygon(c + [c[0]], [r.coords for r in poly.interiors])
        if not cand.is_valid:
            return rebuild(parts, k, cand), f"zamiana wierzcholkow {i}/{i + 1}"
    x0, y0, x1, y1 = poly.bounds  # awaryjnie: kokarda na prostokacie
    bow = Polygon([(x0, y0), (x1, y1), (x1, y0), (x0, y1), (x0, y0)])
    return rebuild(parts, k, bow), "kokarda (awaryjnie)"


def e5_shift(geom, rng):
    d = float(rng.uniform(5, 200))
    a = float(rng.uniform(0, 2 * np.pi))
    return affinity.translate(geom, d * np.cos(a), d * np.sin(a)), round(d, 1)


def e6_gap(geom, nb_geom, rng):
    shared = geom.boundary.intersection(nb_geom.boundary)
    lines = [g for g in getattr(shared, "geoms", [shared]) if g.length > 0]
    if not lines:
        return None, None
    line = max(lines, key=lambda g: g.length)
    r = float(rng.uniform(20, 100))
    cut = line.interpolate(0.5, normalized=True).buffer(r)
    return geom.difference(cut), round(r, 1)


def e9_border_gap(geom, state_boundary, rng):
    """Szczelina przy granicy panstwa: wyciecie polkola w miejscu, gdzie gmina styka sie z granica."""
    shared = geom.boundary.intersection(state_boundary)
    lines = [g for g in getattr(shared, "geoms", [shared]) if g.length > 0]
    if not lines:
        return None, None
    line = max(lines, key=lambda g: g.length)
    r = float(rng.uniform(20, 100))
    cut = line.interpolate(0.5, normalized=True).buffer(r)
    return geom.difference(cut), round(r, 1)


def e4_wrong_crs(geom, crs):
    return gpd.GeoSeries([geom], crs=crs).to_crs("EPSG:4326").iloc[0]


# ---------------------------------------------------------------- rdzen
def inject(gminy, powiaty, seed: int, n: int, types=None, state=None):
    """Zwraca (zepsuty GeoDataFrame, lista wpisow truth). Wejscie nie jest zmieniane."""
    types = types or ALL_TYPES
    rng = np.random.default_rng(seed)
    g = gminy.copy().reset_index(drop=True)
    g["teryt"] = g["teryt"].astype(str)
    nb = neighbours(g)
    existing = set(g["teryt"])
    pow_codes = sorted(powiaty["teryt"].astype(str))
    row_of = {t: i for i, t in enumerate(g["teryt"])}

    state_boundary = None
    if state is not None:
        state_boundary = shapely.union_all(state.geometry.values).boundary

    blocked, truth = set(), []
    order = [g["teryt"][i] for i in rng.permutation(len(g))]

    def pick(pred):
        for t in order:
            if t not in blocked and pred(t):
                blocked.add(t)
                blocked.update(nb[t])
                return t
        return None

    for etype in types:
        for _ in range(n):
            if etype == "E7":
                t = pick(lambda t: PL_CHARS & set(str(g.at[row_of[t], "name"])))
            elif etype == "E6":
                t = pick(lambda t: len(nb[t]) > 0)
            elif etype == "E9":
                if state_boundary is None:
                    print("UWAGA: E9 wymaga warstwy granicy panstwa - pominiete")
                    break
                t = pick(lambda t: g.at[row_of[t], "geometry"].boundary.intersection(
                    state_boundary).length > 0)
            elif etype == "E2":
                t = pick(lambda t: True)
            else:
                t = pick(lambda t: True)
            if t is None:
                print(f"UWAGA: zabraklo kandydatow dla {etype}")
                break
            i = row_of[t]
            entry = {"error": etype, "original_teryt": t, "teryt": t,
                     "expected_checks": EXPECTED[etype], "collateral": [], "detail": ""}

            if etype == "E1":
                g.at[i, "geometry"], entry["detail"] = e1_self_intersection(g.at[i, "geometry"], rng)
                entry["collateral"] = sorted(nb[t])
            elif etype == "E2":
                src = sorted(nb[t])[int(rng.integers(0, len(nb[t])))] if nb[t] else \
                    order[int(rng.integers(0, len(order)))]
                g.at[i, "teryt"] = src
                entry.update(teryt=src, detail=f"skopiowany TERYT gminy {src}", collateral=[src])
            elif etype == "E3":
                woj, gm = t[:2], t[4:]
                same_woj = [p for p in pow_codes if p.startswith(woj) and p != t[:4]]
                cands = [p + gm for p in same_woj if p + gm not in existing]
                new = cands[int(rng.integers(0, len(cands)))] if cands and rng.random() < 0.5 \
                    else woj + "99" + gm
                g.at[i, "teryt"] = new
                existing.add(new)
                entry.update(teryt=new, detail=f"powiat {t[:4]} -> {new[:4]}")
            elif etype == "E4":
                g.at[i, "geometry"] = e4_wrong_crs(g.at[i, "geometry"], g.crs)
                entry.update(detail="geometria w EPSG:4326 w warstwie EPSG:2180",
                             collateral=sorted(nb[t]))
            elif etype == "E5":
                g.at[i, "geometry"], d = e5_shift(g.at[i, "geometry"], rng)
                entry.update(detail=f"przesuniecie {d} m", collateral=sorted(nb[t]))
            elif etype == "E6":
                new_geom = None
                for other in [sorted(nb[t])[k] for k in rng.permutation(len(nb[t]))]:
                    # sasiad musi miec WSPOLNA KRAWEDZ, nie tylko naroznik
                    new_geom, r = e6_gap(g.at[i, "geometry"], g.at[row_of[other], "geometry"], rng)
                    if new_geom is not None:
                        break
                if new_geom is None:
                    print(f"UWAGA: {t} nie ma sasiada ze wspolna krawedzia - E6 pominiete")
                    continue
                g.at[i, "geometry"] = new_geom
                entry.update(detail=f"szczelina r={r} m przy granicy z {other}",
                             collateral=sorted(nb[t]))
            elif etype == "E9":
                new_geom, r = e9_border_gap(g.at[i, "geometry"], state_boundary, rng)
                if new_geom is None:
                    print(f"UWAGA: {t} nie styka sie z granica panstwa - E9 pominiete")
                    continue
                g.at[i, "geometry"] = new_geom
                entry.update(detail=f"szczelina przy granicy panstwa r={r} m",
                             collateral=sorted(nb[t]))
            elif etype == "E7":
                old = str(g.at[i, "name"])
                g.at[i, "name"] = old.translate(PL)
                entry["detail"] = f"'{old}' -> '{g.at[i, 'name']}'"
            elif etype == "E8":
                entry["detail"] = f"usunieto nazwe '{g.at[i, 'name']}'"
                g.at[i, "name"] = ""
            truth.append(entry)
    return g, truth


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n", type=int, default=20, help="liczba bledow kazdego typu")
    ap.add_argument("--types", nargs="*", default=ALL_TYPES,
                    help="domyslnie E1-E8; E9 (szczelina przy granicy panstwa) na zyczenie")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_golden import content_hash

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    gminy = gpd.read_file(GOLDEN, layer="gminy").sort_values("teryt").reset_index(drop=True)
    powiaty = gpd.read_file(GOLDEN, layer="powiaty").sort_values("teryt").reset_index(drop=True)
    golden_hash = content_hash(gminy)
    if golden_hash != manifest["golden"]["content_hash"]["gminy"]:
        sys.exit("BLAD: zloty zbior rozni sie od manifestu - przerwano.")

    try:
        state = gpd.read_file(GOLDEN, layer="panstwo")
    except Exception:
        state = None
    corrupted, truth = inject(gminy, powiaty, args.seed, args.n, args.types, state)

    out = BASE / "data" / "runs" / f"seed_{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    gpkg = out / "corrupted.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    corrupted.to_file(gpkg, layer="gminy", driver="GPKG")
    powiaty.to_file(gpkg, layer="powiaty", driver="GPKG")
    if state is not None:
        state.to_file(gpkg, layer="panstwo", driver="GPKG")
    try:
        gpd.read_file(GOLDEN, layer="known_uncovered").to_file(gpkg, layer="known_uncovered", driver="GPKG")
    except Exception:
        pass

    record = {
        "seed": args.seed, "n_per_type": args.n, "types": args.types,
        "golden_hash": golden_hash,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_injected": len(truth), "injected": truth,
    }
    (out / "truth.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = {}
    for e in truth:
        counts[e["error"]] = counts.get(e["error"], 0) + 1
    print(f"OK. Seed {args.seed}: wstrzyknieto {len(truth)} bledow {counts}")
    print(f"    {gpkg}")
    print(f"    {out / 'truth.json'}")


if __name__ == "__main__":
    main()
