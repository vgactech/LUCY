"""
episodic_memory.py — Mémoire épisodique persistante (JSONL append-only)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : memory / episodic_memory
Auteur : LuCY Project

Couche 2 : liste horodatée persistante — append-only, illimitée.

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..functions.types import PerceptualFact

EPISODIC_DEFAULT_PATH = Path("data/episodic.jsonl")


class EpisodicMemory:
    """Mémoire épisodique persistante en JSONL.

    Règle absolue : append-only.
    Chaque épisode = une ligne JSON horodatée.
    """

    def __init__(self, path: Path | str = EPISODIC_DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def store(self, episode_type: str, data: Any, cycle_id: str = "") -> dict:
        """Stocker un épisode.

        Args:
            episode_type: SE_FACT | SI_IMPRESSION | CYCLE_RESULT | ...
            data: données sérialisables JSON
            cycle_id: identifiant du cycle cognitif

        Returns:
            L'entrée écrite.
        """
        entry = {
            "ts_ns": time.time_ns(),
            "episode_type": episode_type,
            "cycle_id": cycle_id,
            "data": data if isinstance(data, (dict, list, str, int, float, bool)) else str(data),
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return entry

    def store_fact(self, fact: PerceptualFact, cycle_id: str = "") -> dict:
        """Raccourci pour stocker un PerceptualFact."""
        return self.store("SE_FACT", fact.to_dict(), cycle_id)

    def load_all(self) -> list[dict]:
        """Charger tous les épisodes mémorisés."""
        if not self._path.exists():
            return []
        episodes = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        episodes.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return episodes

    def load_recent(self, n: int = 50) -> list[dict]:
        """Charger les N épisodes les plus récents."""
        return self.load_all()[-n:]

    def load_facts(self) -> list[PerceptualFact]:
        """Charger les PerceptualFacts depuis la mémoire épisodique."""
        facts = []
        for ep in self.load_all():
            if ep.get("episode_type") == "SE_FACT":
                d = ep.get("data", {})
                if isinstance(d, dict):
                    facts.append(PerceptualFact(
                        exists=d.get("exists", False),
                        properties=d.get("properties", {}),
                        confidence=d.get("confidence", 0.0),
                        ts_ns=d.get("ts_ns", 0),
                        source=d.get("source", "se"),
                        raw_input_hash=d.get("raw_input_hash", ""),
                    ))
        return facts

    def count(self) -> int:
        """Nombre d'épisodes mémorisés."""
        return len(self.load_all())
