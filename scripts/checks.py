"""
VORO gis_qa - krok 1.1: szesc sprawdzen jakosci danych (C1-C6).

Kazde sprawdzenie zwraca liste znalezisk:
    {"check": "C5", "teryt": "0401011", "severity": "wysoka", "detail": "..."}
teryt = None oznacza znalezisko dla calego zbioru (np. zly CRS).

Sprawdzenia niczego nie naprawiaja i nie zgaduja - tylko opisuja.
"""
import csv
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer

SEVERITY = {"C1": "krytyczna", "C2": "krytyczna", "C3": "krytyczna",
            "C4": "krytyczna", "C5": "wysoka", "C6": "srednia"}

# przyblizony prostokat Polski (lon/lat), przeliczany do CRS danych
PL_BBOX_LONLAT = (14.07, 49.00, 24.16, 54.84)


def finding(check, teryt, detail):
    return {"check": check, "teryt": teryt, "severity": SEVERITY[check], "detail": detail}


# ---------------------------------------------------------------- C1
def c1_geometry(gminy, params):
    out = []
    for teryt, geom in zip(gminy["teryt"], gminy.geometry):
        if geom is None or geom.is_empty:
            out.append(finding("C1", teryt, "pusta geometria"))
        elif not geom.is_valid:
            out.append(finding("C1", teryt, shapely.is_valid_reason(geom)))
    return out


# ---------------------------------------------------------------- C2
def c2_teryt(gminy, params):
    out = []
    teryt = gminy["teryt"].astype(str)
    for t in teryt[~teryt.str.fullmatch(r"\d{7}")]:
        out.append(finding("C2", t, "zly format TERYT (oczekiwano 7 cyfr)"))
    for t in sorted(set(teryt[teryt.duplicated(keep=False)])):
        out.append(finding("C2", t, f"TERYT wystepuje {int((teryt == t).sum())} razy"))
    ok_fmt = teryt[teryt.str.fullmatch(r"\d{7}")]
    for t in ok_fmt[~ok_fmt.str[-1].isin(list("123"))]:
        out.append(finding("C2", t, f"rodzaj gminy '{t[-1]}' spoza 1/2/3"))
    return out


# ---------------------------------------------------------------- C3
def c3_nesting(gminy, powiaty, params):
    out = []
    tol = params["c3_buffer_m"]
    pow_geom = dict(zip(powiaty["teryt"].astype(str), powiaty.geometry))
    pow_buf = {}
    for teryt, geom in zip(gminy["teryt"].astype(str), gminy.geometry):
        parent = teryt[:4]
        if parent not in pow_geom:
            out.append(finding("C3", teryt, f"powiat {parent} nie istnieje"))
            continue
        if geom is None or geom.is_empty or not geom.is_valid:
            continue  # to zglasza C1
        if parent not in pow_buf:
            pow_buf[parent] = pow_geom[parent].buffer(tol)
        if not pow_buf[parent].contains(geom.representative_point()):
            out.append(finding("C3", teryt, f"gmina lezy poza swoim powiatem {parent}"))
    return out


# ---------------------------------------------------------------- C4
def c4_crs_extent(gminy, params):
    out = []
    expected = params["expected_crs"]
    if gminy.crs is None:
        return [finding("C4", None, "brak deklaracji CRS")]
    if gminy.crs.to_string() != expected:
        return [finding("C4", None, f"CRS {gminy.crs.to_string()} zamiast {expected}")]

    t = Transformer.from_crs("EPSG:4326", expected, always_xy=True)
    lon0, lat0, lon1, lat1 = PL_BBOX_LONLAT
    xs, ys = t.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
    m = params["c4_margin_m"]
    minx, maxx, miny, maxy = min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m

    for teryt, geom in zip(gminy["teryt"], gminy.geometry):
        if geom is None or geom.is_empty:
            continue
        x0, y0, x1, y1 = geom.bounds
        if x0 < minx or x1 > maxx or y0 < miny or y1 > maxy:
            out.append(finding("C4", teryt, "geometria poza zasiegiem Polski"))
    return out


# ---------------------------------------------------------------- C5
def c5_topology(gminy, params, diagnostics):
    """Nakladania sasiadow i szczeliny w pokryciu. Liczone w CRS metrycznym."""
    out = []
    ok = gminy[gminy.geometry.notna() & ~gminy.geometry.is_empty & gminy.geometry.is_valid]
    geoms = ok.geometry.values
    teryt = ok["teryt"].astype(str).values

    # --- nakladania
    left, right = ok.sindex.query(geoms, predicate="intersects")
    mask = left < right
    left, right = left[mask], right[mask]
    areas = shapely.area(shapely.intersection(geoms[left], geoms[right]))
    tol_o = params["c5_overlap_tol_m2"]
    for i, j, a in zip(left, right, areas):
        if a > tol_o:
            out.append(finding("C5", teryt[i], f"nakladanie z {teryt[j]}: {a:.1f} m2"))
            out.append(finding("C5", teryt[j], f"nakladanie z {teryt[i]}: {a:.1f} m2"))
    below = areas[(areas > 0) & (areas <= tol_o)]
    diagnostics["c5_overlap_pairs_checked"] = int(len(areas))
    diagnostics["c5_overlaps_below_tol"] = int(len(below))
    diagnostics["c5_overlap_max_below_tol_m2"] = float(below.max()) if len(below) else 0.0

    # --- szczeliny = dziury w polaczonym pokryciu
    union = shapely.union_all(geoms)
    holes = []
    for poly in getattr(union, "geoms", [union]):
        holes.extend(shapely.Polygon(r) for r in poly.interiors)
    tol_g = params["c5_gap_tol_m2"]
    hole_areas = np.array([h.area for h in holes]) if holes else np.array([])
    for hole, a in zip(holes, hole_areas):
        if a <= tol_g:
            continue
        idx = ok.sindex.query(hole.buffer(1.0), predicate="intersects")
        touching = ", ".join(teryt[idx]) if len(idx) else "?"
        for k in idx:
            out.append(finding("C5", teryt[k], f"szczelina {a:.1f} m2 (graniczy z: {touching})"))
    small = hole_areas[hole_areas <= tol_g] if len(hole_areas) else hole_areas
    diagnostics["c5_gaps_total"] = int(len(hole_areas))
    diagnostics["c5_gaps_below_tol"] = int(len(small))
    diagnostics["c5_gap_max_below_tol_m2"] = float(small.max()) if len(small) else 0.0
    return out


# ---------------------------------------------------------------- C6
def load_terc_gminy(path: Path) -> dict:
    """Kod gminy (WOJ+POW+GMI+RODZ, rodzaj 1/2/3) -> nazwa z TERC."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        rows = csv.DictReader(f, dialect=dialect)
        out = {}
        for r in rows:
            gmi, rodz = (r.get("GMI") or "").strip(), (r.get("RODZ") or "").strip()
            if gmi and rodz in ("1", "2", "3"):
                code = r["WOJ"].strip() + r["POW"].strip() + gmi + rodz
                out[code] = r["NAZWA"].strip()
    if not out:
        raise ValueError(f"Nie odczytano gmin z TERC: {path}")
    return out


def c6_attributes(gminy, terc: dict, params, exceptions=(), diagnostics=None):
    """Wyjatek dziala tylko przy DOKLADNEJ zgodnosci obu wartosci."""
    allowed = {(e["teryt"], e["value"], e["reference"]) for e in exceptions if e["check"] == "C6"}
    applied = 0
    out = []
    for teryt, name in zip(gminy["teryt"].astype(str), gminy["name"]):
        name = "" if name is None else " ".join(str(name).split())
        if name in ("", "nan", "None"):
            out.append(finding("C6", teryt, "pusta nazwa"))
            continue
        if teryt not in terc:
            out.append(finding("C6", teryt, "kodu nie ma w TERC"))
        elif name != terc[teryt]:
            if (teryt, name, terc[teryt]) in allowed:
                applied += 1
                continue
            out.append(finding("C6", teryt, f"nazwa '{name}' != TERC '{terc[teryt]}'"))
    if diagnostics is not None:
        diagnostics["c6_known_exceptions_applied"] = applied
    return out


# ---------------------------------------------------------------- wszystko
def run_all(gminy, powiaty, terc, params, exceptions=()):
    diagnostics = {}
    findings = []
    findings += c4_crs_extent(gminy, params)
    crs_ok = not any(f["check"] == "C4" and f["teryt"] is None for f in findings)
    findings += c1_geometry(gminy, params)
    findings += c2_teryt(gminy, params)
    if crs_ok:  # przy zlym CRS geometria nie ma sensu metrycznego
        findings += c3_nesting(gminy, powiaty, params)
        findings += c5_topology(gminy, params, diagnostics)
    else:
        diagnostics["skipped"] = "C3, C5 pominiete z powodu zlego CRS"
    findings += c6_attributes(gminy, terc, params, exceptions, diagnostics)
    return findings, diagnostics
