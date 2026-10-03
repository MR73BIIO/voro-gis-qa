"""
VORO - lata 2.1: prawda PO Decision, PRZED Verification.

Uruchom:  cd /root/VORO && python3 /root/gis_qa/voro_adapter/patch_2_1.py

Zasady (jak przy poprzednich latach):
- dziala tylko przy DOKLADNYM dopasowaniu kotwic (kazda dokladnie 1 raz),
- najpierw sprawdza WSZYSTKO, zapisuje dopiero gdy wszystko pasuje
  (albo zmienia wszystko, albo nic),
- drugie uruchomienie niczego nie zmienia (znacznik juz obecny -> SKIP).

LifeKernel NIE jest ruszany. Zmiany:
  contracts/outcome_record.py               (nowy, rdzen, bez domeny)
  contracts/life_context.py                 (+ pole outcome = None)
  contracts/verification_record.py          (+ pola opcjonalne na koncu)
  verification/verification_engine.py       (+ galaz: gdy context.outcome)
  organism/runtime.py                       (+ outcome_provider=None, hak przed VERIFICATION)
  observation/providers/gis_qa_outcome_provider.py  (kopia z voro_adapter)

Bez outcome_provider (Ekstraklasa) zadna nowa linia sie nie wykonuje:
context.outcome zostaje None, Verification idzie stara sciezka.
"""
import sys
from pathlib import Path

VORO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/root/VORO")
ADAPTER = Path(__file__).resolve().parent

OUTCOME_RECORD = '''"""
VORO - OutcomeRecord

Prawda o swiecie, ktora wchodzi do organizmu
DOPIERO po Decision, a przed Verification.

Nie jest Observation. Nie jest Evidence.
Nie trafia do Reasoning ani do Decision.
Sluzy wylacznie Verification.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OutcomeRecord:

    subject_id: str

    expected: str            # klucz hipotezy zgodnej z prawda, np. "REJECT"

    source: str = ""         # skad prawda (np. sciezka truth.json)

    details: dict = field(default_factory=dict)
'''

EDITS = [
    # ---------------- LifeContext ----------------
    (
        "contracts/life_context.py",
        "    outcome: object = None",
        "    observation: object = None\n",
        "    observation: object = None\n"
        "\n"
        "    #\n"
        "    # Outcome (2.1)\n"
        "    #\n"
        "    # Prawda o swiecie. Ustawiana przez Runtime\n"
        "    # DOPIERO po Decision, przed Verification.\n"
        "    # None = brak prawdy (np. Ekstraklasa) -> stara sciezka.\n"
        "    #\n"
        "\n"
        "    outcome: object = None\n",
    ),
    # ---------------- VerificationRecord ----------------
    (
        "contracts/verification_record.py",
        "outcome_match",
        "    created_at: datetime",
        "    created_at: datetime\n"
        "\n"
        "    # 2.1: porownanie z prawda (None = brak prawdy, stara sciezka)\n"
        "    outcome_match: bool | None = None\n"
        "\n"
        "    expected_hypothesis: str | None = None\n"
        "\n"
        "    selected_key: str | None = None",
    ),
    # ---------------- VerificationEngine: funkcja ----------------
    (
        "verification/verification_engine.py",
        "def _apply_outcome(",
        "class VerificationEngine:\n",
        "def _selected_key(decision) -> str:\n"
        "    # selected_hypothesis = tresc hipotezy, np. \"REJECT: ...\"\n"
        "    return str(decision.selected_hypothesis).split(\":\")[0].strip()\n"
        "\n"
        "\n"
        "def _apply_outcome(\n"
        "    verification: VerificationRecord,\n"
        "    decision: DecisionRecord,\n"
        "    outcome,\n"
        ") -> VerificationRecord:\n"
        "    #\n"
        "    # 2.1: Decision porownana z prawda.\n"
        "    # verified nadal = spojnosc Decision z Reasoning,\n"
        "    # wiec OrganResult.success i Kernel dzialaja jak dotad.\n"
        "    #\n"
        "    if not verification.verified:\n"
        "        return verification  # INCONSISTENT wygrywa, prawda nic nie zmienia\n"
        "\n"
        "    selected = _selected_key(decision)\n"
        "    expected = str(outcome.expected)\n"
        "    match = selected == expected\n"
        "\n"
        "    return VerificationRecord(\n"
        "        verification_id=verification.verification_id,\n"
        "        life_id=verification.life_id,\n"
        "        reasoning_id=verification.reasoning_id,\n"
        "        decision_id=verification.decision_id,\n"
        "        verified=verification.verified,\n"
        "        verification_result=(\"CONFIRMED\" if match else \"REFUTED\"),\n"
        "        explanation=(\n"
        "            f\"Decision ({decision.status}) wybrala {selected}; \"\n"
        "            f\"prawda: {expected}.\"\n"
        "        ),\n"
        "        created_at=verification.created_at,\n"
        "        outcome_match=match,\n"
        "        expected_hypothesis=expected,\n"
        "        selected_key=selected,\n"
        "    )\n"
        "\n"
        "\n"
        "class VerificationEngine:\n",
    ),
    # ---------------- VerificationEngine: run() ----------------
    (
        "verification/verification_engine.py",
        'getattr(context, "outcome", None) is not None',
        "        verification = self.verify(\n"
        "            reasoning,\n"
        "            decision,\n"
        "        )\n"
        "\n"
        "        return verification",
        "        verification = self.verify(\n"
        "            reasoning,\n"
        "            decision,\n"
        "        )\n"
        "\n"
        "        if getattr(context, \"outcome\", None) is not None:\n"
        "\n"
        "            verification = _apply_outcome(\n"
        "                verification,\n"
        "                decision,\n"
        "                context.outcome,\n"
        "            )\n"
        "\n"
        "        return verification",
    ),
    # ---------------- Runtime: funkcje pomocnicze ----------------
    (
        "organism/runtime.py",
        "def _decision_fingerprint(",
        "@dataclass\nclass OrganismRuntime:\n",
        "# --------------------------------------------------\n"
        "# 2.1 OUTCOME (prawda po Decision, przed Verification)\n"
        "# --------------------------------------------------\n"
        "\n"
        "def _decision_fingerprint(context):\n"
        "\n"
        "    d = context.outputs.get(\"decision\")\n"
        "\n"
        "    if d is None:\n"
        "        return None\n"
        "\n"
        "    return (\n"
        "        id(d), d.decision_id, d.status,\n"
        "        d.selected_hypothesis, d.confidence,\n"
        "    )\n"
        "\n"
        "\n"
        "def _observe_outcome_after_decision(\n"
        "    context, trace, outcome_provider, subject_id,\n"
        "):\n"
        "\n"
        "    #\n"
        "    # Brak decyzji = prawda w ogole nie jest wczytywana.\n"
        "    #\n"
        "\n"
        "    if \"decision\" not in context.outputs:\n"
        "        return None\n"
        "\n"
        "    fingerprint = _decision_fingerprint(context)\n"
        "\n"
        "    context.outcome = outcome_provider.observe_outcome(\n"
        "        subject_id\n"
        "    )\n"
        "\n"
        "    trace.events.append(\n"
        "        \"Outcome observed after \"\n"
        "        f\"{context.outputs['decision'].decision_id}\"\n"
        "    )\n"
        "\n"
        "    return fingerprint\n"
        "\n"
        "\n"
        "@dataclass\nclass OrganismRuntime:\n",
    ),
    # ---------------- Runtime: sygnatura live() ----------------
    (
        "organism/runtime.py",
        "outcome_provider=None",
        "        provider=None,  # ObservationProvider; None = Ekstraklasa\n    ):",
        "        provider=None,  # ObservationProvider; None = Ekstraklasa\n"
        "        outcome_provider=None,  # 2.1: prawda po Decision; None = brak\n"
        "    ):",
    ),
    # ---------------- Runtime: hak w petli ----------------
    (
        "organism/runtime.py",
        "decision_fingerprint = None",
        "        for organ in self.organs:\n\n",
        "        decision_fingerprint = None\n"
        "\n"
        "        for organ in self.organs:\n"
        "\n"
        "            if (\n"
        "                outcome_provider is not None\n"
        "                and organ.stage == \"VERIFICATION\"\n"
        "            ):\n"
        "\n"
        "                decision_fingerprint = (\n"
        "                    _observe_outcome_after_decision(\n"
        "                        context, trace,\n"
        "                        outcome_provider, subject_id,\n"
        "                    )\n"
        "                )\n"
        "\n",
    ),
    # ---------------- Runtime: kontrola szczelnosci ----------------
    (
        "organism/runtime.py",
        "SZCZELNOSC",
        "        # --------------------------------------------------\n"
        "        # PCT COMPLETION\n",
        "        if (\n"
        "            decision_fingerprint is not None\n"
        "            and _decision_fingerprint(context)\n"
        "            != decision_fingerprint\n"
        "        ):\n"
        "\n"
        "            raise RuntimeError(\n"
        "                \"SZCZELNOSC: Decision zmienila sie \"\n"
        "                \"po wczytaniu prawdy.\"\n"
        "            )\n"
        "\n"
        "        # --------------------------------------------------\n"
        "        # PCT COMPLETION\n",
    ),
]

NEW_FILES = [
    ("contracts/outcome_record.py", OUTCOME_RECORD),
    ("observation/providers/gis_qa_outcome_provider.py",
     (ADAPTER / "gis_qa_outcome_provider.py").read_text(encoding="utf-8")),
]


def main() -> int:
    texts, errors, log = {}, [], []

    for rel, marker, anchor, new in EDITS:
        path = VORO / rel
        if rel not in texts:
            if not path.exists():
                errors.append(f"BRAK PLIKU  {rel}")
                continue
            texts[rel] = path.read_text(encoding="utf-8")
        text = texts[rel]
        if marker in text:
            log.append(f"SKIP (juz jest)  {rel}  [{marker}]")
            continue
        n = text.count(anchor)
        if n != 1:
            errors.append(f"KOTWICA x{n} (ma byc 1)  {rel}  [{anchor.splitlines()[0].strip()}]")
            continue
        texts[rel] = text.replace(anchor, new, 1)
        log.append(f"ZMIANA  {rel}  [{marker}]")

    writes = []
    for rel, content in NEW_FILES:
        path = VORO / rel
        if path.exists():
            if path.read_text(encoding="utf-8") == content:
                log.append(f"SKIP (identyczny)  {rel}")
            else:
                errors.append(f"PLIK ISTNIEJE I SIE ROZNI  {rel}")
        else:
            writes.append((path, content))
            log.append(f"NOWY  {rel}")

    if errors:
        print("PRZERWANO - nic nie zapisano:")
        for e in errors:
            print("  ", e)
        return 1

    for rel, text in texts.items():
        path = VORO / rel
        if path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    for path, content in writes:
        path.write_text(content, encoding="utf-8")

    for line in log:
        print("  ", line)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
