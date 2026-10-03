"""
VORO - GisQaOutcomeProvider (2.1): prawda o zbiorze gis_qa.

Instalacja: robi to patch_2_1.py (kopia do /root/VORO/observation/providers/).

Osobna klasa, osobny plik: GisQaObservationProvider dalej NIGDY nie czyta
truth.json. Prawde czyta tylko ten provider, a Runtime wola go dopiero
PO Decision, PRZED Verification.

Regula (z przewidywania 2.1, commit 1bee614):
    golden                         -> PASS
    jakikolwiek blad E1-E4         -> REJECT
    tylko bledy z E5-E9            -> REVIEW
Seed bez truth.json albo bez zadnego kodu E -> blad (nie zgadujemy PASS).
"""
import json
import re
from pathlib import Path

from contracts.outcome_record import OutcomeRecord

GIS_QA_ROOT = Path("/root/gis_qa")

CRITICAL = {"E1", "E2", "E3", "E4"}
NONCRITICAL = {"E5", "E6", "E7", "E8", "E9"}
_CODE = re.compile(r"^E[1-9]$")


def _error_codes(node) -> list:
    """Wszystkie wartosci tekstowe w truth.json, ktore sa dokladnie kodem E1..E9."""
    found = []
    if isinstance(node, dict):
        for v in node.values():
            found += _error_codes(v)
    elif isinstance(node, list):
        for v in node:
            found += _error_codes(v)
    elif isinstance(node, str) and _CODE.match(node):
        found.append(node)
    return found


def expected_from_codes(codes) -> str:
    codes = set(codes)
    if codes & CRITICAL:
        return "REJECT"
    if codes and codes <= NONCRITICAL:
        return "REVIEW"
    raise ValueError(f"Nie da sie ustalic prawdy z kodow: {sorted(codes)}")


class GisQaOutcomeProvider:

    def __init__(self, root: Path = GIS_QA_ROOT):
        self.root = Path(root)
        self.calls = []          # do testu szczelnosci: kiedy i o co pytano

    def observe_outcome(self, subject_id: str) -> OutcomeRecord:
        self.calls.append(subject_id)

        if subject_id == "golden":
            return OutcomeRecord(subject_id=subject_id, expected="PASS",
                                 source="golden (bez bledow z definicji)")

        if not subject_id.startswith("seed_"):
            raise ValueError(f"Nieznany zbior '{subject_id}'.")

        path = self.root / "data" / "runs" / subject_id / "truth.json"
        if not path.exists():
            raise ValueError(f"Brak prawdy: {path}")

        codes = _error_codes(json.loads(path.read_text(encoding="utf-8")))
        counts = {c: codes.count(c) for c in sorted(set(codes))}
        return OutcomeRecord(
            subject_id=subject_id,
            expected=expected_from_codes(codes),
            source=str(path.relative_to(self.root)),
            details={"codes": counts},
        )
