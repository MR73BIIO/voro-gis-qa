"""
VORO - lata 2.2: audyt zycia w sladzie (fundament pod zasade nauki).

Uruchom:  cd /root/VORO && python3 /root/gis_qa/voro_adapter/patch_2_2.py

Wymaga laty 2.1. Zasady jak zawsze: dokladne dopasowanie kotwic,
albo wszystko albo nic, drugie uruchomienie = SKIP.

LifeKernel NIE jest ruszany. Zmienia sie tylko organism/runtime.py:
gdy jest outcome_provider, Runtime dopisuje do trace.trace_metadata
klucz "life_audit" (przed zapisem sladu). Bez outcome_provider
(Ekstraklasa, K6) nie wykonuje sie zadna nowa linia.

eligible_for_learning = true TYLKO gdy prawda przyszla ze swiata
i weryfikacja dala CONFIRMED (outcome_match True). Zasada nauki: prediction_2_2.md.
"""
import sys
from pathlib import Path

VORO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/root/VORO")

EDITS = [
    (
        "organism/runtime.py",
        "def _life_audit(",
        "@dataclass\nclass OrganismRuntime:\n",
        "def _life_audit(context):\n"
        "\n"
        "    #\n"
        "    # 2.2: audyt zycia. Tylko odczyt kontekstu.\n"
        "    #\n"
        "\n"
        "    import hashlib\n"
        "    import json\n"
        "\n"
        "    outputs = context.outputs\n"
        "\n"
        "    knowledge = outputs.get(\"knowledge\")\n"
        "    facts = getattr(knowledge, \"facts\", {}) or {}\n"
        "    knowledge_hash = hashlib.sha256(\n"
        "        json.dumps(\n"
        "            facts, sort_keys=True, ensure_ascii=False\n"
        "        ).encode(\"utf-8\")\n"
        "    ).hexdigest()\n"
        "\n"
        "    reasoning = outputs.get(\"reasoning\")\n"
        "    verification = outputs.get(\"verification\")\n"
        "    outcome = getattr(context, \"outcome\", None)\n"
        "\n"
        "    result = getattr(\n"
        "        verification, \"verification_result\", None\n"
        "    )\n"
        "    match = getattr(verification, \"outcome_match\", None)\n"
        "\n"
        "    return {\n"
        "        \"reasoning_readiness\": getattr(\n"
        "            reasoning, \"readiness\", None\n"
        "        ),\n"
        "        \"knowledge_hash\": knowledge_hash,\n"
        "        \"memory_loaded\": len(context.memory or []),\n"
        "        \"historical_relevant\": len(\n"
        "            context.relevant_historical_evidence or []\n"
        "        ),\n"
        "        \"outcome_expected\": getattr(outcome, \"expected\", None),\n"
        "        \"outcome_source\": getattr(outcome, \"source\", None),\n"
        "        \"verification_result\": result,\n"
        "        \"outcome_match\": match,\n"
        "        \"eligible_for_learning\": bool(\n"
        "            outcome is not None\n"
        "            and result == \"CONFIRMED\"\n"
        "            and match is True\n"
        "        ),\n"
        "    }\n"
        "\n"
        "\n"
        "@dataclass\nclass OrganismRuntime:\n",
    ),
    (
        "organism/runtime.py",
        "trace.trace_metadata[\"life_audit\"]",
        "                \"po wczytaniu prawdy.\"\n"
        "            )\n"
        "\n",
        "                \"po wczytaniu prawdy.\"\n"
        "            )\n"
        "\n"
        "        if outcome_provider is not None:\n"
        "\n"
        "            trace.trace_metadata[\"life_audit\"] = (\n"
        "                _life_audit(context)\n"
        "            )\n"
        "\n",
    ),
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

    if "outcome_provider=None" not in texts.get("organism/runtime.py", ""):
        errors.append("Brak laty 2.1 w organism/runtime.py - najpierw patch_2_1.py")

    if errors:
        print("PRZERWANO - nic nie zapisano:")
        for e in errors:
            print("  ", e)
        return 1
    for rel, text in texts.items():
        path = VORO / rel
        if path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    for line in log:
        print("  ", line)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
