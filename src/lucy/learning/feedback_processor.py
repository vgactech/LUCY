"""
feedback_processor.py — Traitement des feedbacks et mise à jour d'apprentissage

Projet : LuCY (Language Unit for Cognitive Yield)
Module : learning / feedback_processor
Auteur : LuCY Project

Traite les signaux de feedback [-1.0, +1.0] et produit des instructions
de mise à jour pour la mémoire procédurale.

Chaque feedback est :
  1. Validé (borné [-1.0, +1.0])
  2. Normalisé selon une fenêtre glissante (lissage anti-spike)
  3. Attribué à un ou plusieurs opérateurs (attribution causale)
  4. Enregistré dans le log forensic

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Limites et constantes
# ---------------------------------------------------------------------------

FEEDBACK_MIN: float = -1.0
FEEDBACK_MAX: float = +1.0
SMOOTHING_WINDOW: int = 10          # taille de la fenêtre glissante
SPIKE_THRESHOLD: float = 0.8       # feedback > seuil → spike détecté


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

@dataclass
class FeedbackRecord:
    """Un enregistrement de feedback brut."""
    raw_value: float                    # valeur brute fournie
    clamped_value: float                # bornée dans [-1.0, +1.0]
    smoothed_value: float               # après lissage fenêtre glissante
    target_operators: list[str]         # opérateurs concernés (SE/SI/NE…)
    is_spike: bool                      # True si |clamped| > SPIKE_THRESHOLD
    cycle_ref: str = ""
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "raw_value": self.raw_value,
            "clamped_value": self.clamped_value,
            "smoothed_value": self.smoothed_value,
            "target_operators": self.target_operators,
            "is_spike": self.is_spike,
            "cycle_ref": self.cycle_ref,
            "ts_ns": self.ts_ns,
        }


@dataclass
class UpdateInstruction:
    """Instruction de mise à jour pour un opérateur donné."""
    function_id: str            # SE / SI / NE / NI / TE / TI / FE / FI
    delta_feedback: float       # feedback à appliquer (≤ 0 si spike amorti)
    source_record: FeedbackRecord
    applied: bool = False

    def to_dict(self) -> dict:
        return {
            "function_id": self.function_id,
            "delta_feedback": self.delta_feedback,
            "applied": self.applied,
            "source_ts_ns": self.source_record.ts_ns,
        }


# ---------------------------------------------------------------------------
# Attribution causale simple (heuristique déterministe)
# ---------------------------------------------------------------------------

# Mappage : type d'action décidée → opérateurs responsables
_ACTION_TO_OPERATORS: dict[str, list[str]] = {
    "perception": ["SE", "SI"],
    "perception_weak": ["SE", "SI"],
    "hypothesis": ["NE", "NI"],
    "judgment": ["TE", "TI"],
    "ethical": ["FE", "FI"],
    "conflict": ["FE", "FI", "TE", "TI"],
    "full_cycle": ["SE", "SI", "NE", "NI", "TE", "TI", "FE", "FI"],
}

ALL_OPERATORS = ["SE", "SI", "NE", "NI", "TE", "TI", "FE", "FI"]


def _infer_operators(action: str, explicit_targets: Optional[list[str]] = None) -> list[str]:
    """Inférer les opérateurs responsables d'une action.

    Args:
        action          : chaîne d'action de la décision LuCY
        explicit_targets: opérateurs explicitement ciblés (prioritaire)

    Returns:
        Liste d'opérateurs à mettre à jour.
    """
    if explicit_targets:
        # Valider que les IDs sont connus
        return [op for op in explicit_targets if op in ALL_OPERATORS]

    action_lower = action.lower()
    for key, ops in _ACTION_TO_OPERATORS.items():
        if key in action_lower:
            return ops

    # Fallback : tous les opérateurs
    return ALL_OPERATORS[:]


# ---------------------------------------------------------------------------
# FeedbackProcessor principal
# ---------------------------------------------------------------------------

class FeedbackProcessor:
    """Traite les signaux de feedback et produit des UpdateInstruction.

    Utilisation :
        processor = FeedbackProcessor()
        instructions = processor.process(
            raw_feedback=+1.0,
            action="hypothesis",
            cycle_ref="lucy_c1a2b3"
        )
        for instr in instructions:
            procedural_memory.update_weight(instr.function_id, instr.delta_feedback)
            instr.applied = True
    """

    def __init__(self) -> None:
        self._history: list[float] = []    # historique des feedbacks clampés
        self._records: list[FeedbackRecord] = []

    def process(
        self,
        raw_feedback: float,
        action: str = "full_cycle",
        cycle_ref: str = "",
        explicit_targets: Optional[list[str]] = None,
    ) -> list[UpdateInstruction]:
        """Traiter un feedback brut et produire des instructions de mise à jour.

        Args:
            raw_feedback     : signal brut (idéalement [-1.0, +1.0])
            action           : action de la dernière décision LuCY
            cycle_ref        : identifiant du cycle source
            explicit_targets : forcer les opérateurs cibles (optionnel)

        Returns:
            Liste d'UpdateInstruction à appliquer à la mémoire procédurale.
        """
        # ── Étape 1 : validation + clamp ──────────────────────────────────
        if not math.isfinite(raw_feedback):
            clamped = 0.0       # NaN / ±inf → neutre fail-safe
        else:
            clamped = max(FEEDBACK_MIN, min(FEEDBACK_MAX, float(raw_feedback)))

        # ── Étape 2 : détection spike ─────────────────────────────────────
        is_spike = abs(clamped) > SPIKE_THRESHOLD

        # ── Étape 3 : lissage fenêtre glissante ───────────────────────────
        self._history.append(clamped)
        if len(self._history) > SMOOTHING_WINDOW:
            self._history = self._history[-SMOOTHING_WINDOW:]
        smoothed = round(sum(self._history) / len(self._history), 6)

        # ── Étape 4 : attribution causale ─────────────────────────────────
        operators = _infer_operators(action, explicit_targets)

        record = FeedbackRecord(
            raw_value=raw_feedback,
            clamped_value=clamped,
            smoothed_value=smoothed,
            target_operators=operators,
            is_spike=is_spike,
            cycle_ref=cycle_ref,
        )
        self._records.append(record)

        # ── Étape 5 : construire les instructions ─────────────────────────
        # Si spike → amortir le feedback de 50 % pour éviter les sauts
        effective = smoothed if is_spike else clamped

        instructions = [
            UpdateInstruction(
                function_id=op,
                delta_feedback=effective,
                source_record=record,
            )
            for op in operators
        ]
        return instructions

    def recent_records(self, n: int = 10) -> list[FeedbackRecord]:
        """Retourner les N derniers enregistrements."""
        return self._records[-n:]

    def statistics(self) -> dict:
        """Statistiques sur la fenêtre glissante actuelle."""
        if not self._history:
            return {"count": 0, "mean": 0.0, "positive_ratio": 0.0, "negative_ratio": 0.0}
        pos = sum(1 for v in self._history if v > 0)
        neg = sum(1 for v in self._history if v < 0)
        return {
            "count": len(self._history),
            "mean": round(sum(self._history) / len(self._history), 6),
            "positive_ratio": round(pos / len(self._history), 3),
            "negative_ratio": round(neg / len(self._history), 3),
        }
