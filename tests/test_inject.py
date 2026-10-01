"""Testy wstrzykiwacza: powtarzalnosc, nietkniety zloty zbior, pelna wykrywalnosc."""
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from checks import run_all  # noqa: E402
from evaluate import evaluate  # noqa: E402
from inject import ALL_TYPES, inject  # noqa: E402

PARAMS = {"expected_crs": "EPSG:2180", "c3_buffer_m": 1.0, "c4_margin_m": 20000,
          "c5_overlap_tol_m2": 1.0, "c5_gap_tol_m2": 1.0}
X0, Y0 = 500000, 500000


@pytest.fixture
def grid():
    """10 x 10 gmin (1 km), 4 powiaty po 5 x 5, wszystkie nazwy z polskimi znakami."""
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
                    g.append((f"{pc}{k:02d}2", f"Łąka Żółta {pc}-{k}", box(x, y, x + 1000, y + 1000)))
    gminy = gpd.GeoDataFrame(g, columns=["teryt", "name", "geometry"], crs="EPSG:2180")
    powiaty = gpd.GeoDataFrame(p, columns=["teryt", "geometry"], crs="EPSG:2180")
    return gminy, powiaty, dict(zip(gminy["teryt"], gminy["name"]))


def test_deterministic(grid):
    g, p, _ = grid
    a, ta = inject(g, p, seed=7, n=1)
    b, tb = inject(g, p, seed=7, n=1)
    assert ta == tb
    assert a.geometry.equals(b.geometry) and a["teryt"].equals(b["teryt"])


def test_golden_untouched(grid):
    g, p, _ = grid
    before = g.copy()
    inject(g, p, seed=1, n=1)
    assert g.equals(before)


def test_all_errors_detected_no_false_alarms(grid):
    g, p, terc = grid
    corrupted, truth = inject(g, p, seed=3, n=1)
    assert {e["error"] for e in truth} == set(ALL_TYPES)
    findings, _ = run_all(corrupted, p, terc, PARAMS)
    res = evaluate({"injected": truth}, findings)
    for etype, pe in res["per_error"].items():
        assert pe["detected"] == pe["injected"], (etype, pe["missed"])
    assert all(m["fp"] == 0 for m in res["per_check"].values())


def test_incidents_cover_every_error(grid):
    from checks import judge
    from evaluate import evaluate_incidents
    from incidents import build_incidents
    from measures import measure
    g, p, terc = grid
    m0 = measure(g, p, terc)
    assert build_incidents(m0, judge(m0, PARAMS)[0], PARAMS) == []
    for seed in (3, 7, 42):
        corrupted, truth = inject(g, p, seed=seed, n=1)
        m = measure(corrupted, p, terc)
        findings, _ = judge(m, PARAMS)
        res = evaluate_incidents({"injected": truth}, build_incidents(m, findings, PARAMS))
        assert res["errors_covered"] == res["n_errors"]
        assert res["incidents_unrelated"] == 0
        assert res["n_incidents"] < len(findings)
