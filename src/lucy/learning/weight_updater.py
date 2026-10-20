"""
weight_updater.py — Mise à jour des poids via gradient discret LuCY

Projet : LuCY (Language Unit for Cognitive Yield)
Module : learning / weight_updater
Auteur : LuCY Project

Applique les UpdateInstruction produites par FeedbackProcessor à la
ProceduralMemory. Mesure la variation avant/après et produit un rapport
de mise à jour pour le forensic.

Séquence complète :
  FeedbackProcessor.process() → [UpdateInstruction]
  WeightUpdater.apply(instructions, procedural_memory) → WeightUpdateReport

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..memory.procedural_memory import ProceduralMemory
    from .feedback_processor import UpdateInstruction


# ---------------------------------------------------------------------------
# Rapport de mise à jour
# ---------------------------------------------------------------------------

@dataclass
class WeightDelta:
    """Variation de poids pour un opérateur."""
    function_id: str
    weight_before: float
    weight_after: float
    delta: float
    feedback_applied: float

    def to_dict(self) -> dict:
        return {
            "function_id": self.function_id,
            "weight_before": self.weight_before,
            "weight_after": self.weight_after,
            "delta": round(self.delta, 6),
            "feedback_applied": self.feedback_applied,
        }


@dataclass
class WeightUpdateReport:
    """Rapport complet d'une session de mise à jour.

    Contient les variations avant/après de chaque opérateur modifié.
    Utilisé pour les métriques d'apprentissage et le forensic.
    """
    deltas: list[WeightDelta]
    instructions_count: int
    skipped_count: int          # instructions déjà appliquées ou nulles
    ts_ns: int = field(default_factory=time.time_ns)
    cycle_ref: str = ""

    @property
    def operators_modified(self) -> list[str]:
        return [d.function_id for d in self.deltas if abs(d.delta) > 1e-9]

    @property
    def mean_absolute_delta(self) -> float:
        if not self.deltas:
            return 0.0
        return round(
            sum(abs(d.delta) for d in self.deltas) / len(self.deltas), 6
        )

    def to_dict(self) -> dict:
        return {
            "ts_ns": self.ts_ns,
            "cycle_ref": self.cycle_ref,
            "instructions_count": self.instructions_count,
            "skipped_count": self.skipped_count,
            "operators_modified": self.operators_modified,
            "mean_absolute_delta": self.mean_absolute_delta,
            "deltas": [d.to_dict() for d in self.deltas],
        }


# ---------------------------------------------------------------------------
# WeightUpdater
# ---------------------------------------------------------------------------

class WeightUpdater:
    """Applique les instructions de mise à jour à la mémoire procédurale.

    Invariants :
    - Une instruction déjà marquée `applied=True` est ignorée (idempotence).
    - Un delta_feedback nul (== 0.0) est skippé (pas de flush inutile).
    - La persistance est déclenchée après chaque batch (un seul flush).

    Utilisation :
        updater = WeightUpdater()
        report = updater.apply(instructions, procedural_memory, flush=True)
    """

    def __init__(self) -> None:
        self._reports: list[WeightUpdateReport] = []

    def apply(
        self,
        instructions: list["UpdateInstruction"],
        procedural: "ProceduralMemory",
        flush: bool = True,
        cycle_ref: str = "",
    ) -> WeightUpdateReport:
        """Appliquer un batch d'instructions à la mémoire procédurale.

        Args:
            instructions : liste produite par FeedbackProcessor.process()
            procedural   : instance ProceduralMemory à mettre à jour
            flush        : si True, persiste sur disque après la mise à jour
            cycle_ref    : identifiant du cycle source (pour le rapport)

        Returns:
            WeightUpdateReport avec les variations avant/après.
        """
        deltas: list[WeightDelta] = []
        skipped = 0

        for instr in instructions:
            # Idempotence : instruction déjà appliquée → skip
            if instr.applied:
                skipped += 1
                continue

            # Feedback nul → skip (ne pas dériver les poids inutilement)
            if abs(instr.delta_feedback) < 1e-9:
                skipped += 1
                instr.applied = True
                continue

            w_before = procedural.get_weight(instr.function_id)
            w_after = procedural.update_weight(instr.function_id, instr.delta_feedback)
            instr.applied = True

            deltas.append(WeightDelta(
                function_id=instr.function_id,
                weight_before=w_before,
                weight_after=w_after,
                delta=w_after - w_before,
                feedback_applied=instr.delta_feedback,
            ))

        if flush and deltas:
            procedural.flush()

        report = WeightUpdateReport(
            deltas=deltas,
            instructions_count=len(instructions),
            skipped_count=skipped,
            cycle_ref=cycle_ref,
        )
        self._reports.append(report)
        return report

    def learning_curve(self, n: int = 50) -> list[dict]:
        """Retourner la courbe d'apprentissage : mean_absolute_delta par rapport.

        Args:
            n : nombre de rapports récents

        Returns:
            Liste de {ts_ns, mean_abs_delta, operators_modified_count}
        """
        return [
            {
                "ts_ns": r.ts_ns,
                "mean_abs_delta": r.mean_absolute_delta,
                "operators_modified_count": len(r.operators_modified),
                "cycle_ref": r.cycle_ref,
            }
            for r in self._reports[-n:]
        ]

    def cumulative_delta(self, function_id: str) -> float:
        """Variation cumulée d'un opérateur sur tous les rapports.

        Args:
            function_id : SE / SI / NE / NI / TE / TI / FE / FI

        Returns:
            Somme des deltas réels (poids_après - poids_avant).
        """
        total = 0.0
        for report in self._reports:
            for d in report.deltas:
                if d.function_id == function_id:
                    total += d.delta
        return round(total, 6)
