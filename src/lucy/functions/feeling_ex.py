"""
feeling_ex.py — FE : Sentiment Extraverti

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / feeling_ex
Auteur : LuCY Project

Question de départ : Quelle valeur cette décision prend-elle dans le contexte relationnel ?

Nature : Jugement
Orientation : Valeurs et relations du monde extérieur
Limite : peut sur-adapter aux conventions — garde-fou FE_NORM_STALENESS_MAX

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .contracts import CONTRACT_FE
from .types import ExternalJudgment, InternalModel, OperatorTrace, RelationalValue

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FE_NORM_STALENESS_MAX: int = 1000   # cycles après lesquels une norme est périmée
FE_DEFAULT_ACCEPTABILITY: float = 0.5


# ---------------------------------------------------------------------------
# Registre de valeurs collectives
# ---------------------------------------------------------------------------

@dataclass
class CollectiveNorm:
    """Une norme collective dans le registre FE."""
    norm_id: str
    description: str
    weight: float = 1.0         # importance de la norme [0.0 – 2.0]
    cycle_added: int = 0        # cycle lors de l'ajout


class CollectiveValueRegistry:
    """Registre des normes et valeurs collectives pour FE."""

    def __init__(self) -> None:
        self._norms: dict[str, CollectiveNorm] = {}
        self._affected_parties: list[str] = []
        self._cycle_counter: int = 0

        # Normes de base
        self.add_norm("n:coherence", "Actions must be coherent with stated reasoning", weight=1.2)
        self.add_norm("n:transparency", "Actions must be explainable to stakeholders", weight=1.0)
        self.add_norm("n:do_no_harm", "Actions must not harm known parties", weight=1.5)

    def add_norm(self, norm_id: str, description: str, weight: float = 1.0) -> None:
        self._norms[norm_id] = CollectiveNorm(
            norm_id=norm_id,
            description=description,
            weight=weight,
            cycle_added=self._cycle_counter,
        )

    def add_party(self, party: str) -> None:
        if party not in self._affected_parties:
            self._affected_parties.append(party)

    def tick(self) -> None:
        """Incrémenter le compteur de cycles."""
        self._cycle_counter += 1

    def active_norms(self) -> list[CollectiveNorm]:
        """Retourner les normes non périmées."""
        return [
            n for n in self._norms.values()
            if (self._cycle_counter - n.cycle_added) <= FE_NORM_STALENESS_MAX
        ]

    def stale_norms(self) -> list[str]:
        """Normes périmées (pour alerte)."""
        return [
            n.norm_id for n in self._norms.values()
            if (self._cycle_counter - n.cycle_added) > FE_NORM_STALENESS_MAX
        ]


# ---------------------------------------------------------------------------
# Opérateur FE principal
# ---------------------------------------------------------------------------

class SentimentExtraverti:
    """FE — Évaluation par les valeurs et normes du monde extérieur.

    Phase 2 : contrat opérationnel formel intégré (CONTRACT_FE).
    Transformations :
    1. Évaluation par les normes partagées (registre externe)
    2. Calcul de l'impact relationnel (qui est affecté ?)
    3. Score d'acceptabilité sociale de l'action candidate
    4. Vérification des limites du contrat + génération OperatorTrace
    """

    def __init__(self, registry: CollectiveValueRegistry | None = None) -> None:
        self.registry = registry or CollectiveValueRegistry()
        self.contract = CONTRACT_FE

    def process(self, judgment: ExternalJudgment | InternalModel, cycle_ref: str = "") -> RelationalValue:
        """Évaluer la valeur relationnelle d'un jugement.

        Args:
            judgment  : sortie de TE ou TI
            cycle_ref : identifiant du cycle appelant (traçabilité Phase 2).

        Returns:
            RelationalValue — acceptabilité sociale + parties affectées + normes.
            Le champ `trace` contient la traçabilité complète.
        """
        t_start = time.time_ns()
        self.registry.tick()

        input_hash = judgment.trace.input_hash if hasattr(judgment, "trace") and judgment.trace else ""
        trace = OperatorTrace(
            operator_id="FE",
            cycle_ref=cycle_ref,
            input_hash=input_hash,
        )

        # Extraire les éléments à évaluer
        if isinstance(judgment, ExternalJudgment):
            items = judgment.accepted
            base_confidence = judgment.confidence
            justification_prefix = "external_judgment"
        else:
            # InternalModel
            items = [judgment.principle]
            base_confidence = judgment.consistency_score
            justification_prefix = "internal_model"

        active_norms = self.registry.active_norms()
        stale = self.registry.stale_norms()
        norm_refs = [n.norm_id for n in active_norms]

        if stale:
            norm_refs.append(f"WARNING:stale_norms={stale}")

        trace.intermediate_steps.append(f"norms_used:{[n.norm_id for n in active_norms]}")
        if stale:
            trace.intermediate_steps.append(f"stale_norms_detected:{stale}")

        # --- Étape 1 : évaluation par les normes ---
        acceptability_scores: list[float] = []
        for norm in active_norms:
            score = self._evaluate_against_norm(items, norm, base_confidence)
            acceptability_scores.append(score * norm.weight)

        if acceptability_scores:
            total_weight = sum(n.weight for n in active_norms)
            acceptability = sum(acceptability_scores) / total_weight if total_weight > 0 else FE_DEFAULT_ACCEPTABILITY
        else:
            acceptability = FE_DEFAULT_ACCEPTABILITY

        # --- Étape 2 : parties affectées ---
        affected_parties = list(self.registry._affected_parties)
        if not affected_parties:
            affected_parties = ["system"]

        trace.intermediate_steps.append(f"affected_parties:{affected_parties}")
        trace.intermediate_steps.append(f"scoring_method:weighted_norm_registry")

        # --- Étape 3 : justification ---
        justification = (
            f"{justification_prefix}:accepted={len(items)} items, "
            f"norms_active={len(active_norms)}, "
            f"acceptability={round(acceptability, 3)}"
        )

        result = RelationalValue(
            acceptability=round(max(0.0, min(1.0, acceptability)), 4),
            affected_parties=affected_parties,
            norm_ref=norm_refs,
            justification=justification,
            ts_ns=t_start,
            trace=trace,
        )

        # --- Phase 3 (P0-A) : vérification du contrat via finalize_trace ---
        result, trace = self.contract.finalize_trace(result, trace, t_start)

        return result

    def _evaluate_against_norm(
        self,
        items: list[str],
        norm: CollectiveNorm,
        base_confidence: float,
    ) -> float:
        """Évaluer la conformité des items à une norme.

        Heuristique : confiance + pénalité si items vides.
        Dans une implémentation étendue, ceci intégrerait une base de règles sémantiques.
        """
        if not items:
            return 0.3  # actions vides = faible acceptabilité par défaut

        # do_no_harm : items suspects réduisent le score
        if norm.norm_id == "n:do_no_harm":
            harmful_hints = {"delete", "remove", "destroy", "harm", "block", "reject_all"}
            item_set = {i.lower() for i in items}
            if item_set & harmful_hints:
                return round(base_confidence * 0.3, 4)

        # coherence et transparency : confiance de base
        return round(base_confidence * 0.8 + 0.2, 4)
