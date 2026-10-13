"""
lucy_state.py — État interne LuCY (LuCYState dataclass)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : kernel / lucy_state
Auteur : LuCY Project

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..functions.types import (
    AbstractPattern,
    ActionDecision,
    ExternalJudgment,
    HypothesisSet,
    InternalModel,
    InternalValue,
    PerceptualFact,
    RelationalValue,
    SubjectiveImpression,
)

CERTIFIED_100: bool = False           # INVARIANT — jamais True sans preuve
UNIQUE_HUMAN_PROVEN: bool = False     # INVARIANT — jamais True sans preuve


@dataclass
class LuCYState:
    """État interne complet d'un cycle cognitif LuCY.

    Conforme au CDC §4.1.
    Les invariants certified_100 et unique_human_proven ne peuvent jamais être True.
    """

    # --- Sorties de perception ---
    perceptual_buffer: list[PerceptualFact] = field(default_factory=list)
    subjective_impressions: list[SubjectiveImpression] = field(default_factory=list)

    # --- Hypothèses actives ---
    hypothesis_set: HypothesisSet | None = None
    abstract_patterns: list[AbstractPattern] = field(default_factory=list)

    # --- Jugements actifs ---
    external_judgment: ExternalJudgment | None = None
    internal_model: InternalModel | None = None
    relational_value: RelationalValue | None = None
    internal_value: InternalValue | None = None

    # --- Décision finale ---
    last_decision: ActionDecision | None = None

    # --- Méta ---
    active_phase: str = "IDLE"
    cycle_count: int = 0
    ts_ns: int = field(default_factory=time.time_ns)
    last_action: str = ""
    certified_100: bool = CERTIFIED_100
    unique_human_proven: bool = UNIQUE_HUMAN_PROVEN

    def advance_phase(self, phase: str) -> None:
        """Mettre à jour la phase active."""
        self.active_phase = phase
        self.ts_ns = time.time_ns()

    def to_summary(self) -> dict:
        """Résumé léger de l'état pour le log forensic."""
        return {
            "active_phase": self.active_phase,
            "cycle_count": self.cycle_count,
            "ts_ns": self.ts_ns,
            "perceptual_buffer_size": len(self.perceptual_buffer),
            "hypothesis_count": (
                len(self.hypothesis_set.candidates) if self.hypothesis_set else 0
            ),
            "last_action": self.last_action,
            "certified_100": self.certified_100,
            "unique_human_proven": self.unique_human_proven,
        }
