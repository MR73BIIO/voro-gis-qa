"""
VORO - lata 2.2b: poprawka przyrzadu audytu (pamiec mierzona przy narodzinach).

Uruchom:  cd /root/VORO && python3 /root/gis_qa/voro_adapter/patch_2_2b.py

Dlaczego: LifeFlow.publish publikuje wynik organu Memory do context.memory
(setattr), wiec na koncu zycia context.memory = wspomnienia BIEZACEGO zycia (3),
a nie pamiec wczytana przy narodzinach. Proba 2.2 pokazala 3 zamiast 74/77/80/83.
To blad przyrzadu (audyt czytal w zlym momencie), nie organizmu.

Poprawka tylko w organism/runtime.py: Runtime zapamietuje liczbe wspomnien
zaraz po PersistentMemoryLoader().load(), audyt bierze te liczbe.
Dodatkowo memory_stored_this_life = len(context.memory) na koncu (to, co bylo 3).
LifeKernel i LifeFlow bez zmian. Wymaga laty 2.2.
"""
import sys
from pathlib import Path

VORO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/root/VORO")
REL = "organism/runtime.py"

EDITS = [
    (
        "memory_loaded_at_birth = len(",
        "        context.memory = (\n"
        "            PersistentMemoryLoader().load()\n"
        "        )\n",
        "        context.memory = (\n"
        "            PersistentMemoryLoader().load()\n"
        "        )\n"
        "\n"
        "        # 2.2b: pamiec przy narodzinach (LifeFlow pozniej\n"
        "        # publikuje tu wspomnienia biezacego zycia).\n"
        "        memory_loaded_at_birth = len(context.memory)\n",
    ),
    (
        "def _life_audit(context, memory_loaded_at_birth",
        "def _life_audit(context):\n",
        "def _life_audit(context, memory_loaded_at_birth=None):\n",
    ),
    (
        "\"memory_stored_this_life\"",
        "        \"memory_loaded\": len(context.memory or []),\n",
        "        \"memory_loaded\": memory_loaded_at_birth,\n"
        "        \"memory_stored_this_life\": len(context.memory or []),\n",
    ),
    (
        "_life_audit(context, memory_loaded_at_birth)\n",
        "                _life_audit(context)\n",
        "                _life_audit(context, memory_loaded_at_birth)\n",
    ),
]


def main() -> int:
    path = VORO / REL
    if not path.exists():
        print("PRZERWANO - brak", REL)
        return 1
    text = path.read_text(encoding="utf-8")
    if "def _life_audit(" not in text:
        print("PRZERWANO - brak laty 2.2 (najpierw patch_2_2.py)")
        return 1
    errors, log = [], []
    for marker, anchor, new in EDITS:
        if marker in text:
            log.append(f"SKIP (juz jest)  [{marker}]")
            continue
        n = text.count(anchor)
        if n != 1:
            errors.append(f"KOTWICA x{n} (ma byc 1)  [{anchor.splitlines()[0].strip()}]")
            continue
        text = text.replace(anchor, new, 1)
        log.append(f"ZMIANA  [{marker}]")
    if errors:
        print("PRZERWANO - nic nie zapisano:")
        for e in errors:
            print("  ", e)
        return 1
    if path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    for line in log:
        print("  ", line)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
