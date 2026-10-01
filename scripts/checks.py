"""
VORO gis_qa - sprawdzenia C1-C6 jako OCENA pomiarow.

Od kroku 1.3b sprawdzenia nie dotykaja geometrii. Dostaja fakty z measures.measure()
i porownuja je z wiedza: progami (params.json) i znanymi wyjatkami.
W VORO: pomiary = provider (Observation), ocena = organy.
Uczenie (etap 3) zmienia TYLKO progi - pomiary swiata sa stale.

Kazde znalezisko: {"check", "teryt", "severity", "detail"}; teryt=None = caly zbior.
"""
import csv
from collections import Counter
from pathlib import Path

import numpy as np
from pyproj import Transformer

from measures import measure

SEVERITY = {"C1": "krytyczna", "C2": "krytyczna", "C3": "krytyczna",
            "C4": "krytyczna", "C5": "wysoka", "C6": "srednia", "C7": "wysoka"}
PL_BBOX_LONLAT = (14.07, 49.00, 24.16, 54.84)


def finding(check, teryt, detail):
    return {"check": check, "teryt": teryt, "severity": SEVERITY[check], "detail": detail}


def c1_geometry(m, params):
    out = []
    for f in m["features"]:
        if f["geom_empty"]:
            out.append(finding("C1", f["teryt"], "pusta geometria"))
        elif not f["geom_valid"]:
            out.append(finding("C1", f["teryt"], f["geom_reason"]))
    return out


def c2_teryt(m, params):
    out = []
    teryt = [f["teryt"] for f in m["features"]]
    fmt_ok = [t for t in teryt if len(t) == 7 and t.isdigit()]
    for t in teryt:
        if not (len(t) == 7 and t.isdigit()):
            out.append(finding("C2", t, "zly format TERYT (oczekiwano 7 cyfr)"))
    counts = Counter(teryt)
    for t in sorted(k for k, v in counts.items() if v > 1):
        out.append(finding("C2", t, f"TERYT wystepuje {counts[t]} razy"))
    for t in fmt_ok:
        if t[-1] not in "123":
            out.append(finding("C2", t, f"rodzaj gminy '{t[-1]}' spoza 1/2/3"))
    return out


def c3_nesting(m, params):
    out = []
    tol = params["c3_buffer_m"]
    for f in m["features"]:
        if not f["parent_exists"]:
            out.append(finding("C3", f["teryt"], f"powiat {f['teryt'][:4]} nie istnieje"))
        elif f["dist_to_parent_m"] is not None and f["dist_to_parent_m"] > tol:
            out.append(finding("C3", f["teryt"], f"gmina lezy poza swoim powiatem {f['teryt'][:4]}"))
    return out


def crs_finding(m, params):
    expected = params["expected_crs"]
    if m["crs"] is None:
        return finding("C4", None, "brak deklaracji CRS")
    if m["crs"] != expected:
        return finding("C4", None, f"CRS {m['crs']} zamiast {expected}")
    return None


def c4_extent(m, params):
    out = []
    t = Transformer.from_crs("EPSG:4326", params["expected_crs"], always_xy=True)
    lon0, lat0, lon1, lat1 = PL_BBOX_LONLAT
    xs, ys = t.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
    mg = params["c4_margin_m"]
    minx, maxx, miny, maxy = min(xs) - mg, max(xs) + mg, min(ys) - mg, max(ys) + mg
    for f in m["features"]:
        if f["bounds"] is None:
            continue
        x0, y0, x1, y1 = f["bounds"]
        if x0 < minx or x1 > maxx or y0 < miny or y1 > maxy:
            out.append(finding("C4", f["teryt"], "geometria poza zasiegiem Polski"))
    return out


def c5_topology(m, params, diagnostics):
    out = []
    tol_o, tol_g = params["c5_overlap_tol_m2"], params["c5_gap_tol_m2"]
    for o in m["overlaps"]:
        if o["area_m2"] > tol_o:
            a = o["area_m2"]
            out.append(finding("C5", o["a"], f"nakladanie z {o['b']}: {a:.1f} m2"))
            out.append(finding("C5", o["b"], f"nakladanie z {o['a']}: {a:.1f} m2"))
    below = np.array([o["area_m2"] for o in m["overlaps"] if o["area_m2"] <= tol_o])
    diagnostics["c5_overlap_pairs_checked"] = m["n_pairs_checked"]
    diagnostics["c5_overlaps_below_tol"] = int(len(below))
    diagnostics["c5_overlap_max_below_tol_m2"] = float(below.max()) if len(below) else 0.0

    for g in m["gaps"]:
        if g["area_m2"] <= tol_g:
            continue
        touching = ", ".join(g["touching"]) if g["touching"] else "?"
        for t in g["touching"]:
            out.append(finding("C5", t, f"szczelina {g['area_m2']:.1f} m2 (graniczy z: {touching})"))
    small = np.array([g["area_m2"] for g in m["gaps"] if g["area_m2"] <= tol_g])
    diagnostics["c5_gaps_total"] = len(m["gaps"])
    diagnostics["c5_gaps_below_tol"] = int(len(small))
    diagnostics["c5_gap_max_below_tol_m2"] = float(small.max()) if len(small) else 0.0
    return out


def c6_attributes(m, params, exceptions=(), diagnostics=None):
    """Wyjatek dziala tylko przy DOKLADNEJ zgodnosci obu wartosci."""
    allowed = {(e["teryt"], e["value"], e["reference"]) for e in exceptions if e["check"] == "C6"}
    applied, out = 0, []
    for f in m["features"]:
        t, name, ref = f["teryt"], f["name"], f["terc_name"]
        if name in ("", "nan", "None"):
            out.append(finding("C6", t, "pusta nazwa"))
        elif ref is None:
            out.append(finding("C6", t, "kodu nie ma w TERC"))
        elif name != ref:
            if (t, name, ref) in allowed:
                applied += 1
                continue
            out.append(finding("C6", t, f"nazwa '{name}' != TERC '{ref}'"))
    if diagnostics is not None:
        diagnostics["c6_known_exceptions_applied"] = applied
    return out


def c7_border(m, params, exceptions=(), diagnostics=None):
    """Granica panstwa: kawalki ponad progiem. Wyjatek (np. morze) tylko przy zgodnym rodzaju
    i powierzchni z dokladnoscia do tolerance_m2."""
    out = []
    if m.get("border") is None:
        if diagnostics is not None:
            diagnostics["c7"] = "pominiete: brak warstwy granicy panstwa"
        return out
    tol = params["c7_border_tol_m2"]
    allowed = [e for e in exceptions if e["check"] == "C7"]
    applied, below = 0, []
    for p in m["border"]:
        if p.get("reference"):
            # znany obszar (morze): musi sie zgadzac z wyjatkiem; jesli nie, zmienil sie caly obszar
            if any(e["kind"] == p["kind"] and abs(e["area_m2"] - p["area_m2"]) <= e["tolerance_m2"]
                   for e in allowed):
                applied += 1
            else:
                out.append(finding("C7", None,
                                   f"znany obszar bez gmin ma inna powierzchnie: {p['area_m2']:.1f} m2"))
            continue
        if p["area_m2"] <= tol:
            below.append(p["area_m2"])
            continue
        if any(e["kind"] == p["kind"] and abs(e["area_m2"] - p["area_m2"]) <= e["tolerance_m2"]
               for e in allowed):
            applied += 1
            continue
        what = "kawalek Polski bez gminy" if p["kind"] == "uncovered" else "gmina poza granica panstwa"
        detail = f"{what}: {p['area_m2']:.1f} m2"
        if p["touching"]:
            for t in p["touching"]:
                out.append(finding("C7", t, detail))
        else:
            out.append(finding("C7", None, detail))
    if diagnostics is not None:
        diagnostics["c7_pieces_total"] = len(m["border"])
        diagnostics["c7_pieces_below_tol"] = len(below)
        diagnostics["c7_max_below_tol_m2"] = float(max(below)) if below else 0.0
        diagnostics["c7_known_exceptions_applied"] = applied
    return out


def judge(m: dict, params: dict, exceptions=()):
    """Ocena pomiarow -> (znaleziska, diagnostyka)."""
    diagnostics, findings = {}, []
    crs = crs_finding(m, params)
    if crs:
        findings.append(crs)
    else:
        findings += c4_extent(m, params)
    findings += c1_geometry(m, params)
    findings += c2_teryt(m, params)
    if crs is None:
        findings += c3_nesting(m, params)
        findings += c5_topology(m, params, diagnostics)
        findings += c7_border(m, params, exceptions, diagnostics)
    else:
        diagnostics["skipped"] = "C3, C5, C7 pominiete z powodu zlego CRS"
    findings += c6_attributes(m, params, exceptions, diagnostics)
    return findings, diagnostics


def run_all(gminy, powiaty, terc, params, exceptions=()):
    """Zgodnosc wstecz: pomiar + ocena w jednym wywolaniu."""
    return judge(measure(gminy, powiaty, terc), params, exceptions)


def load_terc_gminy(path: Path) -> dict:
    """Kod gminy (WOJ+POW+GMI+RODZ, rodzaj 1/2/3) -> nazwa z TERC."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        out = {}
        for r in csv.DictReader(f, dialect=dialect):
            gmi, rodz = (r.get("GMI") or "").strip(), (r.get("RODZ") or "").strip()
            if gmi and rodz in ("1", "2", "3"):
                out[r["WOJ"].strip() + r["POW"].strip() + gmi + rodz] = r["NAZWA"].strip()
    if not out:
        raise ValueError(f"Nie odczytano gmin z TERC: {path}")
    return out
