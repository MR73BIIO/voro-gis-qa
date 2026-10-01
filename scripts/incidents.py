"""
VORO gis_qa - krok 1.4: incydenty zamiast alarmow.

Laczy znaleziska w grupy wedlug tego, co je fizycznie wiaze:
  - nakladanie dwoch gmin (C5 powyzej tolerancji),
  - wspolna szczelina (C5 powyzej tolerancji),
  - gmina z C1/C4, ktorej obrys (bbox) lezy tam, gdzie szczelina.
Kazda spojna grupa = jeden incydent. Znaleziska calego zbioru = osobny incydent.
Niczego nie ocenia od nowa: bierze znaleziska z checks.judge i pomiary z measures.measure.
"""
from collections import Counter, defaultdict

RANK = {"krytyczna": 3, "wysoka": 2, "srednia": 1}


class _Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _bbox_hit(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def build_incidents(m: dict, findings: list, params: dict) -> list:
    flagged = {f["teryt"] for f in findings if f["teryt"] is not None}
    uf = _Union()
    for t in flagged:
        uf.find(t)

    for o in m["overlaps"]:
        if o["area_m2"] > params["c5_overlap_tol_m2"]:
            uf.union(o["a"], o["b"])

    broken = {}
    for f in findings:
        if f["check"] in ("C1", "C4") and f["teryt"] is not None:
            broken[f["teryt"]] = None
    bounds = {feat["teryt"]: feat["bounds"] for feat in m["features"]}
    for t in broken:
        broken[t] = bounds.get(t)

    for g in m["gaps"]:
        if g["area_m2"] <= params["c5_gap_tol_m2"] or not g["touching"]:
            continue
        first = g["touching"][0]
        for t in g["touching"][1:]:
            uf.union(first, t)
        gb = g.get("bounds")
        if gb:
            for t, b in broken.items():
                if b is not None and _bbox_hit(gb, b):
                    uf.union(first, t)

    groups = defaultdict(list)
    for f in findings:
        if f["teryt"] is None:
            groups["__dataset__"].append(f)
        else:
            groups[uf.find(f["teryt"])].append(f)

    incidents = []
    for key, fs in groups.items():
        members = sorted({f["teryt"] for f in fs if f["teryt"] is not None})
        checks = Counter(f["check"] for f in fs)
        severity = max(fs, key=lambda f: RANK[f["severity"]])["severity"]
        per_member = Counter(f["teryt"] for f in fs if f["teryt"] is not None)
        critical = [t for t in members
                    if any(f["teryt"] == t and f["severity"] == "krytyczna" for f in fs)]
        pool = critical or members
        cause = max(pool, key=lambda t: per_member[t]) if pool else None
        incidents.append({
            "members": members,
            "probable_cause": cause,
            "severity": severity,
            "checks": dict(sorted(checks.items())),
            "n_findings": len(fs),
            "scope": "dataset" if key == "__dataset__" else "features",
        })
    incidents.sort(key=lambda i: (-RANK[i["severity"]], -i["n_findings"]))
    for n, inc in enumerate(incidents, 1):
        inc["id"] = f"INC-{n:04d}"
    return incidents
