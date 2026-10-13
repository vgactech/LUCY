"""
working_memory.py — Mémoire de travail (buffer circulaire)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : memory / working_memory
Auteur : LuCY Project

Couche 1 : buffer circulaire cycle courant — capacité 1024 entrées max.

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any


WORKING_MEMORY_CAPACITY: int = 1024


class WorkingMemory:
    """Buffer circulaire en mémoire pour le cycle cognitif courant.

    Propriétés :
    - Capacité maximale configurable (défaut 1024)
    - Éviction FIFO quand la capacité est atteinte
    - Accès O(1) aux N dernières entrées
    - Ne persiste pas entre les sessions (volatil)
    """

    def __init__(self, capacity: int = WORKING_MEMORY_CAPACITY) -> None:
        self._capacity = capacity
        self._buffer: deque[dict] = deque(maxlen=capacity)

    def push(self, entry_type: str, data: Any, cycle_id: str = "") -> None:
        """Ajouter une entrée dans le buffer."""
        self._buffer.append({
            "ts_ns": time.time_ns(),
            "entry_type": entry_type,
            "cycle_id": cycle_id,
            "data": data,
        })

    def last(self, n: int = 1) -> list[dict]:
        """Récupérer les N dernières entrées."""
        items = list(self._buffer)
        return items[-n:] if n <= len(items) else items

    def find_by_type(self, entry_type: str) -> list[dict]:
        """Filtrer les entrées par type."""
        return [e for e in self._buffer if e["entry_type"] == entry_type]

    def size(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        """Vider le buffer (fin de cycle)."""
        self._buffer.clear()

    @property
    def capacity(self) -> int:
        return self._capacity
