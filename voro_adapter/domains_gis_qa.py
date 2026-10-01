"""
Pakiet domenowy: gis_qa (jakosc danych przestrzennych, gminy PRG + TERC).

Krok 3 planu 1.3d: hipotezy i TABELA RELACJI zapisane PRZED kodem, ktory ich uzywa.

Dlaczego trzy dowody, a nie szesc (po jednym na C1-C6):
ReasoningEngine liczy spojnosc jako 1 - SREDNIA sprzecznosci. Przy szesciu dowodach
jedno znalezisko C6 dawaloby PASS spojnosc 0,83 (> progu 0,80) -> falszywe PASS.
Wzoru Reasoning nie zmieniamy (regresja K6), wiec zmieniamy KSZTALT dowodow:
kazdy dowod odpowiada na pytanie rozstrzygajace miedzy hipotezami.
Podzial na C1-C6 i progi (params.json) wyliczaja te liczby i zostaja w metadanych.
"""

DOMAIN = "gis_qa"

# ---------------------------------------------------------------- Identity
LABEL_KEY = "dataset_id"
IDENTITY_KEYS = ("dataset_id", "n_features")

# ---------------------------------------------------------------- Knowledge
# musi byc zgodne z FACT_KEYS w gis_qa_provider.py
FACT_KEYS = (
    "n_features", "n_geom_empty", "n_geom_invalid", "n_teryt_duplicated",
    "n_parent_missing", "max_dist_to_parent_m", "n_terc_missing",
    "n_name_differs_from_terc", "n_overlaps_positive", "max_overlap_m2",
    "n_gaps", "max_gap_m2",
)

# ---------------------------------------------------------------- Hipotezy
HYPOTHESIS_IDS = ("PASS", "REVIEW", "REJECT")
HYPOTHESES = (
    "PASS: zbior jest wiarygodny i nadaje sie do uzycia.",
    "REVIEW: zbior ma problemy, ale zaden nie jest krytyczny.",
    "REJECT: zbior ma co najmniej jeden problem krytyczny.",
)

# Ktore sprawdzenia sa krytyczne (zgodne z SEVERITY w checks.py)
CRITICAL_CHECKS = ("C1", "C2", "C3", "C4")
NONCRITICAL_CHECKS = ("C5", "C6")

# ---------------------------------------------------------------- Dowody
EVIDENCE_SOURCES = ("findings_total", "findings_critical", "findings_noncritical")

# ---------------------------------------------------------------- Relacje
# SPRZECZNOSC dowodu z hipoteza: 0.0 = zgodne/neutralne, 1.0 = sprzeczne.
# Klucz wyniku: "zero" (brak znalezisk) albo "positive" (> 0).
RELATIONS = {
    "findings_total": {
        "zero":     {"PASS": 0.0, "REVIEW": 1.0, "REJECT": 1.0},
        "positive": {"PASS": 1.0, "REVIEW": 0.0, "REJECT": 0.0},
    },
    "findings_critical": {
        "zero":     {"PASS": 0.0, "REVIEW": 0.0, "REJECT": 1.0},
        "positive": {"PASS": 1.0, "REVIEW": 1.0, "REJECT": 0.0},
    },
    "findings_noncritical": {
        "zero":     {"PASS": 0.0, "REVIEW": 1.0, "REJECT": 0.0},
        "positive": {"PASS": 1.0, "REVIEW": 0.0, "REJECT": 0.0},
    },
}

# Remis: wybieramy ostrozniej
TIE_ORDER = ("REJECT", "REVIEW", "PASS")

# ---------------------------------------------------------------- Przewidywania (zapisane z gory)
PREDICTIONS = {
    "golden":  {"selected": "PASS",   "readiness": 1.0, "status": "ACCEPT"},
    "seed_42": {"selected": "REJECT", "readiness": 1.0, "status": "ACCEPT"},
}


def outcome(count: int) -> str:
    return "positive" if count > 0 else "zero"


def contradictions(counts: dict) -> dict:
    """counts: {"findings_total": n, "findings_critical": n, "findings_noncritical": n}
    -> {hipoteza: [sprzecznosc kazdego dowodu]}"""
    return {h: [RELATIONS[src][outcome(counts[src])][h] for src in EVIDENCE_SOURCES]
            for h in HYPOTHESIS_IDS}


if __name__ == "__main__":
    # Samosprawdzenie wzorem ReasoningEngine: certainty=1, completeness=0.6*1+0.4*min(3/3,1)=1,
    # relevance=3/3=1, consistency=1-mean(sprzecznosci), readiness=(c*cons*comp*rel)**0.25
    scen = {
        "czysty (golden)":           {"findings_total": 0, "findings_critical": 0, "findings_noncritical": 0},
        "tylko niekrytyczne":        {"findings_total": 5, "findings_critical": 0, "findings_noncritical": 5},
        "tylko krytyczne":           {"findings_total": 3, "findings_critical": 3, "findings_noncritical": 0},
        "krytyczne + niekr. (seed)": {"findings_total": 9, "findings_critical": 4, "findings_noncritical": 5},
    }
    for name, counts in scen.items():
        cons = {h: 1 - sum(v) / len(v) for h, v in contradictions(counts).items()}
        ready = {h: round(c ** 0.25, 4) for h, c in cons.items()}
        best = max(ready.values())
        winner = next(h for h in TIE_ORDER if ready[h] == best)
        ok = "ACCEPT" if cons[winner] >= 0.80 and ready[winner] >= 0.75 else "ABSTAIN"
        print(f"{name:<28} spojnosc {cons}  -> {winner} (gotowosc {ready[winner]}, {ok})")
