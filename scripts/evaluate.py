"""
VORO gis_qa - ocena: porownanie znalezisk z prawda (truth.json).

Uzycie:
    python scripts/evaluate.py --truth data/runs/seed_42/truth.json
    (domyslnie bierze najnowszy out/findings_*.json)

Liczy:
    - wykrywalnosc kazdego typu bledu (ile wstrzyknietych zlapano oczekiwanym sprawdzeniem),
    - falszywe alarmy: znaleziska na gminach czystych (nie cel i nie collateral),
    - precyzje / czulosc / F1 dla kazdego sprawdzenia.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CHECKS = ["C1", "C2", "C3", "C4", "C5", "C6"]


def evaluate(truth: dict, findings: list) -> dict:
    by_teryt = defaultdict(set)
    for f in findings:
        if f["teryt"] is not None:
            by_teryt[f["teryt"]].add(f["check"])

    targets = {e["teryt"] for e in truth["injected"]}
    collateral = {c for e in truth["injected"] for c in e["collateral"]}

    per_error = defaultdict(lambda: {"injected": 0, "detected": 0, "missed": []})
    tp, fn = defaultdict(int), defaultdict(int)
    for e in truth["injected"]:
        hit = bool(set(e["expected_checks"]) & by_teryt.get(e["teryt"], set()))
        pe = per_error[e["error"]]
        pe["injected"] += 1
        for c in e["expected_checks"]:
            (tp if hit else fn)[c] += 1
        if hit:
            pe["detected"] += 1
        else:
            pe["missed"].append({"teryt": e["teryt"], "detail": e["detail"]})

    fp = defaultdict(int)
    fp_examples = defaultdict(list)
    for f in findings:
        t = f["teryt"]
        if t is None or t in targets or t in collateral:
            continue
        fp[f["check"]] += 1
        if len(fp_examples[f["check"]]) < 5:
            fp_examples[f["check"]].append(f"{t}: {f['detail']}")

    metrics = {}
    for c in CHECKS:
        p_den, r_den = tp[c] + fp[c], tp[c] + fn[c]
        prec = tp[c] / p_den if p_den else None
        rec = tp[c] / r_den if r_den else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if r_den else None)
        metrics[c] = {"tp": tp[c], "fn": fn[c], "fp": fp[c],
                      "precision": prec, "recall": rec, "f1": f1}
    return {"per_error": dict(per_error), "per_check": metrics,
            "false_alarm_examples": dict(fp_examples)}


def fmt(x):
    return "  -  " if x is None else f"{x:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--findings", type=Path)
    args = ap.parse_args()
    fpath = args.findings or max((BASE / "out").glob("findings_*.json"))
    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    run = json.loads(fpath.read_text(encoding="utf-8"))
    res = evaluate(truth, run["findings"])

    print(f"Prawda: {args.truth}  (seed {truth['seed']}, {truth['n_injected']} bledow)")
    print(f"Znaleziska: {fpath.name}\n")
    print("Blad  wstrz.  wykryte")
    for e in sorted(res["per_error"]):
        pe = res["per_error"][e]
        print(f"{e:<5} {pe['injected']:>6}  {pe['detected']:>7}")
    print("\nSprawdz.  TP   FN   FP   precyzja  czulosc  F1")
    for c, m in res["per_check"].items():
        print(f"{c:<8} {m['tp']:>3}  {m['fn']:>3}  {m['fp']:>3}   {fmt(m['precision'])}    "
              f"{fmt(m['recall'])}   {fmt(m['f1'])}")
    for e, pe in res["per_error"].items():
        for m in pe["missed"][:5]:
            print(f"  PRZEOCZONE {e} {m['teryt']}: {m['detail']}")
    for c, ex in res["false_alarm_examples"].items():
        for x in ex:
            print(f"  FALSZYWY ALARM {c} {x}")

    out = fpath.with_name(fpath.stem.replace("findings", "eval") + ".json")
    out.write_text(json.dumps({"truth": str(args.truth), "findings": str(fpath), **res},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nZapisano: {out}")


if __name__ == "__main__":
    main()
