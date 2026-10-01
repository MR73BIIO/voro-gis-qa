"""Raport: sumy sie zgadzaja, status widoczny, raport nie zalezy od truth.json."""
import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from checks import judge  # noqa: E402
from incidents import build_incidents  # noqa: E402
from inject import inject  # noqa: E402
from measures import measure  # noqa: E402
from report import collect, render_html, render_md  # noqa: E402

PARAMS = {"expected_crs": "EPSG:2180", "c3_buffer_m": 1.0, "c4_margin_m": 20000,
          "c5_overlap_tol_m2": 1.0, "c5_gap_tol_m2": 1.0}
MANIFEST = {"prg": {"url": "u", "zip_sha256": "a" * 64, "downloaded_at_utc": "2026-09-29"},
            "terc": {"path": "data/raw/terc.csv", "sha256": "b" * 64}}


def _grid():
    g, p, X0 = [], [], 500000
    for pi in range(2):
        pc = f"040{pi + 1}"
        p.append((pc, box(X0 + pi * 3000, X0, X0 + (pi + 1) * 3000, X0 + 3000)))
        k = 0
        for i in range(3):
            for j in range(3):
                k += 1
                x, y = X0 + pi * 3000 + i * 1000, X0 + j * 1000
                g.append((f"{pc}{k:02d}2", f"Łąka {pc}-{k}", box(x, y, x + 1000, y + 1000)))
    gm = gpd.GeoDataFrame(g, columns=["teryt", "name", "geometry"], crs="EPSG:2180")
    pw = gpd.GeoDataFrame(p, columns=["teryt", "geometry"], crs="EPSG:2180")
    return gm, pw, dict(zip(gm["teryt"], gm["name"]))


def _run(gm, pw, terc):
    m = measure(gm, pw, terc)
    findings, diag = judge(m, PARAMS)
    inc = build_incidents(m, findings, PARAMS)
    crit = {f["teryt"] for f in findings if f["severity"] == "krytyczna"}
    other = {f["teryt"] for f in findings} - crit
    st = ["REJECT" if t in crit else "REVIEW" if t in other else "PASS" for t in gm["teryt"]]
    return {"data": "x.gpkg", "run_at_utc": "now", "n_features": len(gm), "crs": m["crs"],
            "dataset_status": "REJECT" if crit else "REVIEW" if findings else "PASS",
            "status_counts": {k: st.count(k) for k in ("PASS", "REVIEW", "REJECT")},
            "findings_per_check": {c: sum(f["check"] == c for f in findings) for c in
                                   {f["check"] for f in findings}},
            "findings": findings, "incidents": inc, "diagnostics": diag,
            "params": PARAMS, "known_exceptions": []}


def test_report_golden_and_corrupted():
    gm, pw, terc = _grid()
    for data in (gm, inject(gm, pw, seed=3, n=1)[0]):
        d = collect(_run(data, pw, terc), MANIFEST)
        assert all(d["sums_ok"].values())
        md = render_md(d)
        assert f"Status: {d['status']}" in md
        assert "truth" not in md
        assert d["status"] in render_html(d, md)
