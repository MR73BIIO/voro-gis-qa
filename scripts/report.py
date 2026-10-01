"""
VORO gis_qa - krok 1.5: raport QA (Markdown + HTML) z wyniku run_checks.py.

Uzycie:
    python scripts/report.py                       # najnowszy out/findings_*.json
    python scripts/report.py --findings out/findings_XXXX.json

Raport niczego nie liczy od nowa i NIE czyta truth.json. Pokazuje to, co widzialby klient.
Wynik: out/report_<czas>.md i out/report_<czas>.html
"""
import argparse
import hashlib
import html
import json
import subprocess
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / "manifest.json"

CHECKS = [
    ("C1", "Geometry valid and not empty", "critical"),
    ("C2", "TERYT code: 7 digits, unique, type 1/2/3", "critical"),
    ("C3", "Municipality inside its county", "critical"),
    ("C4", "Coordinate system and extent of Poland", "critical"),
    ("C5", "Overlaps and gaps between neighbours", "high"),
    ("C6", "Name present and equal to TERC", "medium"),
    ("C7", "Coverage of the state border", "high"),
]
SEV_EN = {"krytyczna": "critical", "wysoka": "high", "srednia": "medium"}


def short_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def git_version() -> str:
    try:
        return subprocess.check_output(["git", "-C", str(BASE), "rev-parse", "--short", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def collect(run: dict, manifest: dict) -> dict:
    counts = run["status_counts"]
    per_check = run.get("findings_per_check", {})
    incidents = run.get("incidents", [])
    sev = Counter(SEV_EN[i["severity"]] for i in incidents)
    total_findings = sum(per_check.values())
    checks_ok = {
        "statuses add up to the number of municipalities":
            sum(counts.values()) == run["n_features"],
        "findings per check add up to all findings":
            total_findings == len(run["findings"]),
        "findings in incidents add up to all findings":
            sum(i["n_findings"] for i in incidents) == len(run["findings"]),
    }
    return {
        "dataset": Path(run["data"]).name,
        "run_at": run["run_at_utc"],
        "status": run["dataset_status"],
        "counts": counts,
        "n_features": run["n_features"],
        "crs": run.get("crs"),
        "per_check": per_check,
        "n_findings": total_findings,
        "incidents": incidents,
        "incidents_by_severity": {k: sev.get(k, 0) for k in ("critical", "high", "medium")},
        "exceptions": run.get("known_exceptions", []),
        "exceptions_applied": (run.get("diagnostics", {}).get("c6_known_exceptions_applied", 0)
                               + run.get("diagnostics", {}).get("c7_known_exceptions_applied", 0)),
        "params": run["params"],
        "params_hash": short_hash(run["params"]),
        "exceptions_hash": short_hash(run.get("known_exceptions", [])),
        "code_version": git_version(),
        "source": {
            "prg_url": manifest["prg"]["url"],
            "prg_downloaded": manifest["prg"].get("downloaded_at_utc") or "unknown",
            "prg_sha": manifest["prg"]["zip_sha256"][:16],
            "terc_file": Path(manifest["terc"]["path"]).name if "terc" in manifest else "-",
            "terc_sha": manifest["terc"]["sha256"][:16] if "terc" in manifest else "-",
        },
        "sums_ok": checks_ok,
    }


def render_md(d: dict) -> str:
    L = []
    L += [f"# GIS data QA report: {d['dataset']}", ""]
    L += [f"**Status: {d['status']}**", ""]
    c = d["counts"]
    L += [f"{d['n_features']} municipalities checked. PASS {c['PASS']}, REVIEW {c['REVIEW']}, "
          f"REJECT {c['REJECT']}. {d['n_findings']} findings in {len(d['incidents'])} incidents.", ""]
    L += ["## Source and time", "",
          "| | |", "|---|---|",
          f"| Boundaries | PRG, {d['source']['prg_url']} |",
          f"| Downloaded | {d['source']['prg_downloaded']} |",
          f"| Package hash | `{d['source']['prg_sha']}…` |",
          f"| Names | TERC, {d['source']['terc_file']} (`{d['source']['terc_sha']}…`) |",
          f"| Report run | {d['run_at']} |", ""]
    L += ["## Coordinate system", "", f"Declared CRS: `{d['crs']}`. Expected: `{d['params']['expected_crs']}`.", ""]
    L += ["## Checks", "", "| Check | What it looks at | Severity | Findings |", "|---|---|---|---|"]
    for cid, what, sev in CHECKS:
        L.append(f"| {cid} | {what} | {sev} | {d['per_check'].get(cid, 0)} |")
    L += ["", "One critical finding gives REJECT. Only high or medium findings give REVIEW. No findings gives PASS.", ""]
    L += ["## Incidents", ""]
    if not d["incidents"]:
        L += ["No incidents.", ""]
    else:
        s = d["incidents_by_severity"]
        L += [f"{len(d['incidents'])} incidents: {s['critical']} critical, {s['high']} high, {s['medium']} medium. "
              "Findings with a common cause (overlap, shared gap, broken geometry at the same place) are grouped "
              "into one incident.", "",
              "| Incident | Severity | Probable cause | Municipalities | Findings | Checks |",
              "|---|---|---|---|---|---|"]
        for i in d["incidents"]:
            cause = f"{i['probable_cause']} {i.get('probable_cause_name') or ''}".strip() if i["probable_cause"] else "whole dataset"
            checks = ", ".join(f"{k}×{v}" for k, v in i["checks"].items())
            L.append(f"| {i['id']} | {SEV_EN[i['severity']]} | {cause} | {len(i['members'])} | {i['n_findings']} | {checks} |")
        L.append("")
    L += ["## Known exceptions", ""]
    if d["exceptions"]:
        L += [f"Applied in this run: {d['exceptions_applied']}.", "",
              "| Check | What | Expected | Reason |", "|---|---|---|---|"]
        for e in d["exceptions"]:
            if e["check"] == "C7":
                what = f"{e['kind']} piece"
                expected = f"{e['area_m2']:,.0f} m2 (± {e['tolerance_m2']} m2)"
            else:
                what = f"{e['teryt']} {e['value']}"
                expected = e["reference"]
            L.append(f"| {e['check']} | {what} | {expected} | {e['reason']} |")
    else:
        L.append("None.")
    L += ["", "## Who decided", "",
          f"Rules and thresholds from `params.json` (hash `{d['params_hash']}`), known exceptions (hash "
          f"`{d['exceptions_hash']}`), code version `{d['code_version']}`.", "",
          "| Parameter | Value |", "|---|---|"]
    for k, v in d["params"].items():
        L.append(f"| {k} | {v} |")
    L += ["", "## Consistency", ""]
    for name, ok in d["sums_ok"].items():
        L.append(f"- {'OK' if ok else 'FAILED'}: {name}")
    L += ["", "---", "Marcin Ruszczak · MR73BIIO · GIS · Data validation · Python · PL · DE · RU · EN", ""]
    return "\n".join(L)


def render_html(d: dict, md: str) -> str:
    """Prosty HTML z tych samych danych (bez zewnetrznych bibliotek)."""
    rows = []
    for line in md.splitlines():
        e = html.escape(line).replace("**", "")
        if line.startswith("# "):
            rows.append(f"<h1>{e[2:]}</h1>")
        elif line.startswith("## "):
            rows.append(f"<h2>{e[3:]}</h2>")
        elif line.startswith("|---"):
            continue
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append("<tr>" + "".join(f"<td>{html.escape(c).replace('`', '')}</td>" for c in cells) + "</tr>")
        elif line.startswith("- "):
            rows.append(f"<p class='chk'>{e[2:]}</p>")
        elif line.strip() in ("", "---"):
            rows.append("")
        else:
            rows.append(f"<p>{e.replace('`', '')}</p>")
    body, out, in_table = [], [], False
    for r in rows:
        if r.startswith("<tr>") and not in_table:
            out.append("<table>"); in_table = True
        if not r.startswith("<tr>") and in_table:
            out.append("</table>"); in_table = False
        out.append(r)
    if in_table:
        out.append("</table>")
    color = {"PASS": "#1f7a3a", "REVIEW": "#b07a00", "REJECT": "#a32020"}[d["status"]]
    css = ("body{font-family:Arial,sans-serif;max-width:980px;margin:24px auto;padding:0 16px;color:#222}"
           "h1{font-size:22px}h2{font-size:17px;margin-top:28px;border-bottom:1px solid #ddd}"
           "table{border-collapse:collapse;width:100%;font-size:13px}td{border:1px solid #ddd;padding:4px 6px}"
           "tr:first-child td{background:#f3f3f3;font-weight:bold}"
           f".status{{display:inline-block;padding:6px 14px;color:#fff;background:{color};font-weight:bold}}")
    out.insert(1, f"<p><span class='status'>{d['status']}</span></p>")
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>QA report {html.escape(d['dataset'])}</title>" \
           f"<style>{css}</style></head><body>{''.join(out)}</body></html>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", type=Path)
    args = ap.parse_args()
    fpath = args.findings or max((BASE / "out").glob("findings_*.json"))
    run = json.loads(fpath.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    d = collect(run, manifest)
    md = render_md(d)
    stem = fpath.stem.replace("findings", "report")
    (fpath.with_name(stem + ".md")).write_text(md, encoding="utf-8")
    (fpath.with_name(stem + ".html")).write_text(render_html(d, md), encoding="utf-8")
    print(f"Raport: {d['status']} | incydenty: {len(d['incidents'])} | sumy: "
          f"{'OK' if all(d['sums_ok'].values()) else 'BLAD'}")
    print(f"  {fpath.with_name(stem + '.md')}")
    print(f"  {fpath.with_name(stem + '.html')}")


if __name__ == "__main__":
    main()
