"""
semantic_memory.py — Mémoire sémantique (graphe de connaissances JSON)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : memory / semantic_memory
Auteur : LuCY Project

Couche 3 : graphe de connaissances persistant (JSON).

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SEMANTIC_DEFAULT_PATH = Path("data/semantic.json")


class SemanticMemory:
    """Mémoire sémantique — graphe de connaissances persistant.

    Structure : {concept: {neighbor: weight, ...}, ...}
    Persistance via JSON (chargé en mémoire, flush à la demande).
    """

    def __init__(self, path: Path | str = SEMANTIC_DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._graph: dict[str, dict[str, float]] = {}
        self._dirty: bool = False
        self._load()

    def _load(self) -> None:
        """Charger le graphe depuis le fichier JSON."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._graph = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._graph = {}
        else:
            self._graph = {}

    def flush(self) -> None:
        """Persister le graphe sur disque."""
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._graph, f, ensure_ascii=False, indent=2)
        self._dirty = False

    def add_concept(self, concept: str) -> None:
        if concept not in self._graph:
            self._graph[concept] = {}
            self._dirty = True

    def add_edge(self, src: str, dst: str, weight: float = 0.5) -> None:
        """Ajouter ou renforcer une arête bidirectionnelle."""
        self.add_concept(src)
        self.add_concept(dst)
        old = self._graph[src].get(dst, 0.0)
        self._graph[src][dst] = round(0.7 * old + 0.3 * weight, 4)
        old_rev = self._graph[dst].get(src, 0.0)
        self._graph[dst][src] = round(0.7 * old_rev + 0.3 * weight, 4)
        self._dirty = True

    def neighbors(self, concept: str) -> dict[str, float]:
        return dict(self._graph.get(concept, {}))

    def node_count(self) -> int:
        return len(self._graph)

    def to_dict(self) -> dict:
        return dict(self._graph)

    def get_graph_for_ne(self):
        """Retourner un KnowledgeGraph NE synchronisé avec cette mémoire."""
        from ..functions.intuition_ex import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.load_dict(dict(self._graph))
        return kg
