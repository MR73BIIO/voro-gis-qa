"""
VORO - GisQaObservationProvider (srodowisko gis_qa).

Instalacja:  cp /root/gis_qa/voro_adapter/gis_qa_provider.py /root/VORO/observation/providers/

Tlumaczy swiat danych przestrzennych na JEDNA kanoniczna Observation.
- mierzy (measures.measure), NIE ocenia - progi i ocena naleza do organow,
- NIGDY nie czyta truth.json: prawda o wstrzyknietych bledach nie moze
  przekroczyc granicy organizmu (to bylby wyciek, jak xG post-match),
- as_of_timestamp = stan zrodla (PRG) z manifestu, nie czas uruchomienia.

subject_id:
    "golden"   -> data/golden/golden.gpkg
    "seed_42"  -> data/runs/seed_42/corrupted.gpkg
"""
import json
import sys
from pathlib import Path

from observation.observation import Observation
from observation.observation_provider import ObservationProvider

GIS_QA_ROOT = Path("/root/gis_qa")

FACT_KEYS = [
    "n_features", "n_geom_empty", "n_geom_invalid", "n_teryt_duplicated",
    "n_parent_missing", "max_dist_to_parent_m", "n_terc_missing",
    "n_name_differs_from_terc", "n_overlaps_positive", "max_overlap_m2",
    "n_gaps", "max_gap_m2",
    "n_border_pieces", "max_border_piece_m2", "known_uncovered_m2",
]


def summarize(m: dict) -> dict:
    """Fakty zbiorcze BEZ progow (liczniki i maksima wprost z pomiarow)."""
    feats = m["features"]
    teryt = [f["teryt"] for f in feats]
    dists = [f["dist_to_parent_m"] for f in feats if f["dist_to_parent_m"] is not None]
    all_border = m.get("border") or []
    border = [p for p in all_border if not p.get("reference")]
    reference = [p for p in all_border if p.get("reference")]
    return {
        "n_features": m["n_features"],
        "n_geom_empty": sum(f["geom_empty"] for f in feats),
        "n_geom_invalid": sum((not f["geom_empty"]) and (not f["geom_valid"]) for f in feats),
        "n_teryt_duplicated": len(teryt) - len(set(teryt)),
        "n_parent_missing": sum(not f["parent_exists"] for f in feats),
        "max_dist_to_parent_m": max(dists) if dists else 0.0,
        "n_terc_missing": sum(f["terc_name"] is None for f in feats),
        "n_name_differs_from_terc": sum(
            f["terc_name"] is not None and f["name"] != f["terc_name"] for f in feats),
        "n_overlaps_positive": len(m["overlaps"]),
        "max_overlap_m2": max((o["area_m2"] for o in m["overlaps"]), default=0.0),
        "n_gaps": len(m["gaps"]),
        "max_gap_m2": max((g["area_m2"] for g in m["gaps"]), default=0.0),
        "n_border_pieces": len(border),
        "max_border_piece_m2": max((p["area_m2"] for p in border), default=0.0),
        "known_uncovered_m2": sum(p["area_m2"] for p in reference),
    }


class GisQaObservationProvider(ObservationProvider):

    def __init__(self, root: Path = GIS_QA_ROOT):
        self.root = Path(root)
        scripts = str(self.root / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)

    def _dataset_path(self, subject_id: str) -> Path:
        if subject_id == "golden":
            return self.root / "data" / "golden" / "golden.gpkg"
        if subject_id.startswith("seed_"):
            return self.root / "data" / "runs" / subject_id / "corrupted.gpkg"
        raise ValueError(f"Nieznany zbior '{subject_id}' (oczekiwano 'golden' albo 'seed_<n>').")

    @staticmethod
    def _optional_layer(path, layer):
        import geopandas as gpd
        try:
            return gpd.read_file(path, layer=layer)
        except Exception:
            return None

    def observe(self, subject_id: str) -> Observation:
        import geopandas as gpd
        from checks import load_terc_gminy
        from measures import measure

        path = self._dataset_path(subject_id)
        if not path.exists():
            raise ValueError(f"Brak pliku zbioru: {path}")
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))

        gminy = gpd.read_file(path, layer="gminy")
        powiaty = gpd.read_file(path, layer="powiaty")
        state = self._optional_layer(path, "panstwo")
        reference = self._optional_layer(path, "known_uncovered")
        terc = load_terc_gminy(self.root / manifest["terc"]["path"])
        m = measure(gminy, powiaty, terc, state, reference)
        facts = summarize(m)

        payload = {
            "entity": "dataset",
            "dataset_id": subject_id,
            **facts,
            "measurements": m,
        }
        metadata = {
            "provider": self.__class__.__name__,
            "domain": "gis_qa",
            "identity_keys": ["dataset_id", "n_features"],
            "fact_keys": FACT_KEYS,
            "temporal_status": "EXPLICIT_SOURCE_STATE",
            "sources": {
                "prg_zip_sha256": manifest["prg"]["zip_sha256"],
                "terc_sha256": manifest["terc"]["sha256"],
                "golden_content_hash": manifest["golden"]["content_hash"]["gminy"],
                "state_layer": "panstwo" if state is not None else None,
                "dataset_file": str(path.relative_to(self.root)),
            },
        }
        return Observation(
            source="PRG+TERC",
            subject="dataset",
            payload=payload,
            metadata=metadata,
            as_of_timestamp=manifest["prg"]["downloaded_at_utc"],
        )
