"""
VORO - 1.3d krok 2: pakiety domenowe.

Uruchom w /root/VORO:  python3 /root/gis_qa/voro_adapter/patch_step2_domains.py

1. Tworzy domains/ (ekstraklasa = DOKLADNIE dzisiejsze wartosci z organow, gis_qa).
2. Identity i Knowledge czytaja pakiet zamiast wartosci wpisanych na sztywno.
Bez metadata["domain"] w Observation wybierana jest Ekstraklasa -> zachowanie bez zmian.
Jesli ktorykolwiek fragment nie pasuje DOKLADNIE raz, NIC nie jest zmieniane.
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "organism" / "runtime.py").exists():
    sys.exit("BLAD: uruchom w katalogu /root/VORO")

PACKS = {
    "domains/__init__.py": '''"""
VORO - rejestr pakietow domenowych.

Wiedza o domenie (klucze tozsamosci, fakty, hipotezy, relacje) zyje tutaj,
a nie w organach. Organ pyta pakiet; pakiet wybiera Observation.metadata["domain"].
Brak domeny = Ekstraklasa (zgodnosc wsteczna).
"""
from domains import ekstraklasa, gis_qa

PACKS = {
    "ekstraklasa": ekstraklasa,
    "gis_qa": gis_qa,
}

DEFAULT_DOMAIN = "ekstraklasa"


def get_pack(observation=None):
    metadata = getattr(observation, "metadata", None) or {}
    domain = metadata.get("domain", DEFAULT_DOMAIN)
    if domain not in PACKS:
        raise ValueError(f"Nieznana domena '{domain}'. Znane: {sorted(PACKS)}")
    return PACKS[domain]
''',
    "domains/ekstraklasa.py": '''"""
Pakiet domenowy: Ekstraklasa.

DOKLADNIE wartosci, ktore wczesniej byly wpisane na sztywno w organach
(Identity, Knowledge, Hypothesis). Zmiana tutaj = zmiana zachowania K6.
"""

DOMAIN = "ekstraklasa"

# Identity
LABEL_KEY = "match_id"
IDENTITY_KEYS = ("match_id", "home", "away")

# Knowledge
FACT_KEYS = (
    "referee_foul_avg",
    "referee_card_expectation_asof",
    "referee_card_bias",
    "home_form_5g",
    "away_form_5g",
)

# Hypothesis (uzywane od kroku 4)
HYPOTHESES = (
    "Wyższa od ligowej oczekiwana liczba kartek "
    "dla sędziego zwiększa prawdopodobieństwo "
    "wysokiej liczby kartek w meczu.",
)

# Brak jawnych relacji: Evidence zostaje "fact_only",
# relacja pochodzi z wywolania live() (interpretation_relation).
RELATIONS = None
''',
    "domains/gis_qa.py": '''"""
Pakiet domenowy: gis_qa (jakosc danych przestrzennych, gminy PRG + TERC).

Fakty = liczniki i maksima z GisQaObservationProvider (bez progow).
Hipotezy i relacje C1-C6 dochodza w krokach 3-5.
"""

DOMAIN = "gis_qa"

# Identity
LABEL_KEY = "dataset_id"
IDENTITY_KEYS = ("dataset_id", "n_features")

# Knowledge - musi byc zgodne z FACT_KEYS w gis_qa_provider.py
FACT_KEYS = (
    "n_features", "n_geom_empty", "n_geom_invalid", "n_teryt_duplicated",
    "n_parent_missing", "max_dist_to_parent_m", "n_terc_missing",
    "n_name_differs_from_terc", "n_overlaps_positive", "max_overlap_m2",
    "n_gaps", "max_gap_m2",
)

# Hypothesis (krok 4)
HYPOTHESES = None

# Relacje (krok 3)
RELATIONS = None
''',
}

ID_FILE = ROOT / "identity" / "identity_organ.py"
KN_FILE = ROOT / "knowledge" / "knowledge_organ.py"

ID_PATCHES = [
    (re.compile(r"(\nfrom identity\.identity_engine import next_id\n)"),
     lambda m: m.group(1) + "from domains import get_pack\n"),
    (re.compile(r"(\n([ \t]*)payload = observation\.payload\n)"),
     lambda m: m.group(1) + m.group(2) + "pack = get_pack(observation)\n"),
    (re.compile(r'"match_id":\s*payload\.get\("match_id"\),\s*'
                r'"home":\s*payload\.get\("home"\),\s*'
                r'"away":\s*payload\.get\("away"\),'),
     lambda m: "**{key: payload.get(key) for key in pack.IDENTITY_KEYS},"),
    (re.compile(r"f\"Generated identity for \{payload\.get\('match_id'\)\}\""),
     lambda m: 'f"Generated identity for {payload.get(pack.LABEL_KEY)}"'),
]

KN_PATCHES = [
    (re.compile(r"(\nfrom knowledge\.knowledge_engine import KnowledgeEngine\n)"),
     lambda m: m.group(1) + "from domains import get_pack\n"),
    (re.compile(r'\n([ \t]*)match_id = payload\.get\(\s*"match_id",\s*"unknown"\s*\)'),
     lambda m: ("\n{i}pack = get_pack(context.observation)\n"
                "{i}match_id = payload.get(pack.LABEL_KEY, \"unknown\")").format(i=m.group(1))),
    (re.compile(r'for feature in \(\s*"referee_foul_avg",\s*"referee_card_expectation_asof",\s*'
                r'"referee_card_bias",\s*"home_form_5g",\s*"away_form_5g",\s*\):'),
     lambda m: "for feature in pack.FACT_KEYS:"),
]


def apply(path: Path, patches) -> str:
    src = path.read_text(encoding="utf-8")
    for rx, _ in patches:
        n = len(rx.findall(src))
        if n != 1:
            sys.exit(f"BLAD: {path.relative_to(ROOT)}: wzorzec {rx.pattern[:60]!r} pasuje {n} razy. NIC nie zmieniono.")
    for rx, fn in patches:
        src = rx.sub(fn, src, count=1)
    compile(src, str(path), "exec")
    return src


if (ROOT / "domains").exists():
    sys.exit("BLAD: katalog domains/ juz istnieje - krok 2 byl juz zaaplikowany?")

new_id = apply(ID_FILE, ID_PATCHES)
new_kn = apply(KN_FILE, KN_PATCHES)

for rel, text in PACKS.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
ID_FILE.write_text(new_id, encoding="utf-8")
KN_FILE.write_text(new_kn, encoding="utf-8")
print("OK: domains/ utworzone, identity_organ.py i knowledge_organ.py czytaja pakiet.")
