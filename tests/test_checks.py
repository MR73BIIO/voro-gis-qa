"""Testy C1-C6 na malym, sztucznym zbiorze: 2 powiaty x 4 gminy (kwadraty 1 km)."""
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely import affinity
from shapely.geometry import Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from checks import run_all  # noqa: E402

PARAMS = {"expected_crs": "EPSG:2180", "c3_buffer_m": 1.0, "c4_margin_m": 20000,
          "c5_overlap_tol_m2": 1.0, "c5_gap_tol_m2": 1.0}
X0, Y0 = 500000, 500000
NAMES = ["Łódź", "Kraków", "Gdańsk", "Żary", "Ełk", "Śrem", "Nysa", "Oława"]


@pytest.fixture
def clean():
    g, p, k = [], [], 0
    for pi, pc in enumerate(["0401", "0402"]):
        px = X0 + pi * 2000
        p.append((pc, box(px, Y0, px + 2000, Y0 + 2000)))
        for i in range(2):
            for j in range(2):
                g.append((f"{pc}{k + 1:02d}1", NAMES[k],
                          box(px + i * 1000, Y0 + j * 1000, px + (i + 1) * 1000, Y0 + (j + 1) * 1000)))
                k += 1
    gminy = gpd.GeoDataFrame(g, columns=["teryt", "name", "geometry"], crs="EPSG:2180")
    powiaty = gpd.GeoDataFrame(p, columns=["teryt", "geometry"], crs="EPSG:2180")
    terc = dict(zip(gminy["teryt"], gminy["name"]))
    return gminy, powiaty, terc


def checks_hit(findings, teryt):
    return {f["check"] for f in findings if f["teryt"] == teryt}


def test_clean_has_no_findings(clean):
    findings, _ = run_all(*clean, PARAMS)
    assert findings == []


def test_c1_bowtie(clean):
    g, p, t = clean
    g.loc[3, "geometry"] = Polygon([(0, 0), (1000, 1000), (1000, 0), (0, 1000)])
    g.loc[3, "geometry"] = affinity.translate(g.loc[3, "geometry"], X0 + 1000, Y0 + 1000)
    assert "C1" in checks_hit(run_all(g, p, t, PARAMS)[0], g.loc[3, "teryt"])


def test_c2_duplicate(clean):
    g, p, t = clean
    g.loc[0, "teryt"] = g.loc[1, "teryt"]
    assert "C2" in checks_hit(run_all(g, p, t, PARAMS)[0], g.loc[1, "teryt"])


def test_c3_wrong_parent(clean):
    g, p, t = clean
    g.loc[6, "teryt"] = "0409071"
    assert "C3" in checks_hit(run_all(g, p, t, PARAMS)[0], "0409071")


def test_c4_wrong_crs(clean):
    g, p, t = clean
    g = g.set_crs("EPSG:4326", allow_override=True)
    findings, diag = run_all(g, p, t, PARAMS)
    assert any(f["check"] == "C4" and f["teryt"] is None for f in findings)
    assert "skipped" in diag


def test_c5_shift_overlap(clean):
    g, p, t = clean
    g.loc[4, "geometry"] = affinity.translate(g.loc[4, "geometry"], 50, 0)
    assert "C5" in checks_hit(run_all(g, p, t, PARAMS)[0], g.loc[4, "teryt"])


def test_c5_interior_gap(clean):
    g, p, t = clean
    # szczelina wewnatrz pokrycia: wyciecie 10 x 200 m na wspolnej granicy dwoch gmin
    g.loc[0, "geometry"] = g.loc[0, "geometry"].difference(
        box(X0 + 990, Y0 + 400, X0 + 1000, Y0 + 600))
    hits = run_all(g, p, t, PARAMS)[0]
    assert any(f["check"] == "C5" and "szczelina" in f["detail"] for f in hits)


def test_c6_lost_diacritics(clean):
    g, p, t = clean
    g.loc[2, "name"] = "Gdansk"
    assert "C6" in checks_hit(run_all(g, p, t, PARAMS)[0], g.loc[2, "teryt"])


def test_c6_exception_exact_only(clean):
    g, p, t = clean
    teryt = g.loc[2, "teryt"]
    t[teryt] = "Gdańsk"
    g.loc[2, "name"] = "Gdańsk (Pomorski)"
    exc = [{"check": "C6", "teryt": teryt, "value": "Gdańsk (Pomorski)", "reference": "Gdańsk"}]
    findings, diag = run_all(g, p, t, PARAMS, exc)
    assert findings == [] and diag["c6_known_exceptions_applied"] == 1
    g.loc[2, "name"] = "Gdansk (Pomorski)"          # zepsuta nazwa -> wyjatek nie pasuje
    findings, _ = run_all(g, p, t, PARAMS, exc)
    assert "C6" in checks_hit(findings, teryt)
