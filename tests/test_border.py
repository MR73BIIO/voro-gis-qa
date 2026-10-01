"""C7: granica panstwa. Siatka 10 x 10 gmin + pas 'morza' na polnocy w warstwie panstwa."""
import sys
from pathlib import Path

import geopandas as gpd
import pytest
import shapely
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from checks import judge  # noqa: E402
from evaluate import evaluate  # noqa: E402
from incidents import build_incidents  # noqa: E402
from inject import inject  # noqa: E402
from measures import measure  # noqa: E402

PARAMS = {"expected_crs": "EPSG:2180", "c3_buffer_m": 1.0, "c4_margin_m": 20000,
          "c5_overlap_tol_m2": 1.0, "c5_gap_tol_m2": 1.0, "c7_border_tol_m2": 150.0}
X0 = Y0 = 500000


@pytest.fixture
def world():
    g, p = [], []
    for pi in range(2):
        for pj in range(2):
            pc = f"04{pi * 2 + pj + 1:02d}"
            p.append((pc, box(X0 + pi * 5000, Y0 + pj * 5000, X0 + (pi + 1) * 5000, Y0 + (pj + 1) * 5000)))
            k = 0
            for i in range(5):
                for j in range(5):
                    k += 1
                    x, y = X0 + pi * 5000 + i * 1000, Y0 + pj * 5000 + j * 1000
                    g.append((f"{pc}{k:02d}2", f"Łąka {pc}-{k}", box(x, y, x + 1000, y + 1000)))
    gm = gpd.GeoDataFrame(g, columns=["teryt", "name", "geometry"], crs="EPSG:2180")
    pw = gpd.GeoDataFrame(p, columns=["teryt", "geometry"], crs="EPSG:2180")
    sea = box(X0, Y0 + 10000, X0 + 10000, Y0 + 12000)
    state_geom = shapely.union_all(gm.geometry.values).union(sea)
    state = gpd.GeoDataFrame({"name": ["X"]}, geometry=[state_geom], crs="EPSG:2180")
    exc = [{"check": "C7", "kind": "uncovered", "area_m2": sea.area, "tolerance_m2": 1.0}]
    ref = gpd.GeoDataFrame({"name": ["sea"]}, geometry=[sea], crs="EPSG:2180")
    return gm, pw, dict(zip(gm["teryt"], gm["name"])), state, exc, ref


def test_golden_with_sea_is_clean(world):
    gm, pw, terc, state, exc, ref = world
    findings, diag = judge(measure(gm, pw, terc, state, ref), PARAMS, exc)
    assert findings == []
    assert diag["c7_known_exceptions_applied"] == 1


def test_sea_without_exception_is_reported(world):
    gm, pw, terc, state, _, ref = world
    findings, _ = judge(measure(gm, pw, terc, state, ref), PARAMS, [])
    assert any(f["check"] == "C7" for f in findings)


def test_no_state_layer_skips_c7(world):
    gm, pw, terc, _, exc, _ = world
    findings, diag = judge(measure(gm, pw, terc), PARAMS, exc)
    assert findings == [] and "c7" in diag


def test_e9_border_gaps_found(world):
    gm, pw, terc, state, exc, ref = world
    corrupted, truth = inject(gm, pw, seed=5, n=3, types=["E9"], state=state)
    assert len(truth) == 3
    m = measure(corrupted, pw, terc, state, ref)
    findings, _ = judge(m, PARAMS, exc)
    res = evaluate({"injected": truth}, findings)
    assert res["per_error"]["E9"]["detected"] == 3
    assert res["per_check"]["C7"]["fp"] == 0
    inc = build_incidents(m, findings, PARAMS)
    assert all(any(e["teryt"] in i["members"] for i in inc) for e in truth)


def test_coastal_gap_stays_local(world):
    """Dziura przy brzegu nie moze 'zarazic' wszystkich gmin nadmorskich."""
    gm, pw, terc, state, exc, ref = world
    g = gm.copy()
    coastal = [i for i, geom in enumerate(g.geometry) if geom.bounds[3] == Y0 + 10000]
    i = coastal[3]
    x0, _, x1, y1 = g.geometry.iloc[i].bounds
    g.loc[i, "geometry"] = g.geometry.iloc[i].difference(box((x0 + x1) / 2 - 50, y1 - 50, (x0 + x1) / 2 + 50, y1))
    findings, diag = judge(measure(g, pw, terc, state, ref), PARAMS, exc)
    c7 = {f["teryt"] for f in findings if f["check"] == "C7"}
    assert g.loc[i, "teryt"] in c7
    assert len(c7) <= 3
    assert diag["c7_known_exceptions_applied"] == 1
