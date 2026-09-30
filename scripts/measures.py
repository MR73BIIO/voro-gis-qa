"""
VORO gis_qa - krok 1.3b: POMIARY swiata (bez zadnych progow i ocen).

To jest czesc, ktora w VORO wykonuje provider: tlumaczy swiat na fakty.
Nic tu nie decyduje, czy cos jest bledem - to robia sprawdzenia (checks.judge).

Wynik jest w pelni serializowalny do JSON (trafia do Observation.payload).
"""
import shapely


def measure(gminy, powiaty, terc: dict) -> dict:
    """Fakty o zbiorze gmin. Kolejnosc 'features' = kolejnosc wierszy."""
    teryt = gminy["teryt"].astype(str).tolist()
    names = ["" if n is None else " ".join(str(n).split()) for n in gminy["name"]]
    pow_geom = dict(zip(powiaty["teryt"].astype(str), powiaty.geometry))

    features = []
    for i, (t, name, geom) in enumerate(zip(teryt, names, gminy.geometry)):
        empty = geom is None or geom.is_empty
        valid = (not empty) and geom.is_valid
        parent = t[:4]
        f = {
            "row": i,
            "teryt": t,
            "name": name,
            "geom_empty": bool(empty),
            "geom_valid": bool(valid),
            "geom_reason": None if valid or empty else shapely.is_valid_reason(geom),
            "bounds": None if empty else [float(b) for b in geom.bounds],
            "parent_exists": parent in pow_geom,
            # odleglosc punktu reprezentatywnego od powiatu-rodzica (0 = w srodku)
            "dist_to_parent_m": (float(pow_geom[parent].distance(geom.representative_point()))
                                 if valid and parent in pow_geom else None),
            "terc_name": terc.get(t),
        }
        features.append(f)

    ok_idx = [f["row"] for f in features if f["geom_valid"]]
    ok = gminy.iloc[ok_idx]
    geoms = ok.geometry.values
    t_ok = [teryt[i] for i in ok_idx]

    # nakladania: kazda para przecinajacych sie gmin z polem > 0
    left, right = ok.sindex.query(geoms, predicate="intersects")
    mask = left < right
    left, right = left[mask], right[mask]
    areas = shapely.area(shapely.intersection(geoms[left], geoms[right]))
    overlaps = [{"a": t_ok[i], "b": t_ok[j], "area_m2": float(a)}
                for i, j, a in zip(left, right, areas) if a > 0]

    # szczeliny: dziury w polaczonym pokryciu
    gaps = []
    if len(geoms):
        union = shapely.union_all(geoms)
        for poly in getattr(union, "geoms", [union]):
            for ring in poly.interiors:
                hole = shapely.Polygon(ring)
                idx = ok.sindex.query(hole.buffer(1.0), predicate="intersects")
                gaps.append({"area_m2": float(hole.area),
                             "touching": [t_ok[k] for k in idx]})

    return {
        "crs": gminy.crs.to_string() if gminy.crs is not None else None,
        "n_features": len(features),
        "features": features,
        "n_pairs_checked": int(len(areas)),
        "overlaps": overlaps,
        "gaps": gaps,
    }
