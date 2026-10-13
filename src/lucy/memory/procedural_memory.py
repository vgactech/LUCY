"""
procedural_memory.py — Mémoire procédurale (poids + règles appris)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : memory / procedural_memory
Auteur : LuCY Project

Couche 4 : poids appris + règles persistants (JSON).

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import json
import time
from pathlib import Path

PROCEDURAL_DEFAULT_PATH = Path("data/procedural_weights.json")

# Poids par défaut des 8 opérateurs (CDC §4.3)
DEFAULT_WEIGHTS: dict[str, float] = {
    "SE": 1.0,
    "SI": 0.8,
    "NE": 0.9,
    "NI": 0.7,
    "TE": 1.0,
    "TI": 0.9,
    "FE": 0.7,
    "FI": 0.7,
}

LEARNING_RATE: float = 0.05
MIN_WEIGHT: float = 0.1
MAX_WEIGHT: float = 2.0


class ProceduralMemory:
    """Mémoire procédurale — poids des opérateurs + règles appris.

    Persistance JSON. Mise à jour par gradient discret.
    """

    def __init__(self, path: Path | str = PROCEDURAL_DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._weights: dict[str, float] = {}
        self._update_log: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._weights = data.get("weights", {})
                self._update_log = data.get("update_log", [])[-200:]
            except (json.JSONDecodeError, OSError):
                pass
        # Compléter avec les poids par défaut manquants
        for fn, w in DEFAULT_WEIGHTS.items():
            if fn not in self._weights:
                self._weights[fn] = w

    def flush(self) -> None:
        """Persister les poids sur disque."""
        data = {
            "weights": self._weights,
            "update_log": self._update_log[-200:],
            "ts_ns": time.time_ns(),
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_weight(self, function_id: str) -> float:
        """Obtenir le poids d'un opérateur."""
        return self._weights.get(function_id, DEFAULT_WEIGHTS.get(function_id, 0.5))

    def update_weight(self, function_id: str, feedback: float) -> float:
        """Mettre à jour le poids d'un opérateur par gradient discret.

        Args:
            function_id: SE / SI / NE / NI / TE / TI / FE / FI
            feedback: [-1.0 = erreur complète, 0.0 = neutre, +1.0 = succès]

        Returns:
            Nouveau poids.
        """
        old_weight = self.get_weight(function_id)
        delta = LEARNING_RATE * feedback
        new_weight = round(max(MIN_WEIGHT, min(old_weight + delta, MAX_WEIGHT)), 4)
        self._weights[function_id] = new_weight

        self._update_log.append({
            "ts_ns": time.time_ns(),
            "function": function_id,
            "feedback": feedback,
            "delta": round(delta, 6),
            "old_weight": old_weight,
            "new_weight": new_weight,
        })
        return new_weight

    def all_weights(self) -> dict[str, float]:
        return dict(self._weights)

    def recent_updates(self, n: int = 10) -> list[dict]:
        return self._update_log[-n:]
