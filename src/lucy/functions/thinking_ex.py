"""
thinking_ex.py — TE : Pensée Extravertie

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / thinking_ex
Auteur : LuCY Project

Question de départ : Quel jugement est justifié par les données et les références objectives ?

Nature : Jugement
Orientation : Critères intellectuels extérieurs, données objectives
Limite : critères extérieurs peuvent être incomplets — nécessite rafraîchissement

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .types import ExternalJudgment, HypothesisSet

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TE_ACCEPTANCE_THRESHOLD: float = 0.6  # score minimum pour accepter une hypothèse


# ---------------------------------------------------------------------------
# Base de faits vérifiés et critères externes
# ---------------------------------------------------------------------------

@dataclass
class ExternalFact:
    """Un fait vérifié dans la base de connaissances externe."""
    concept: str
    verified: bool
    confidence: float           # [0.0 – 1.0]
    source: str = ""
    context: dict = field(default_factory=dict)


class ExternalFactBase:
    """Base de faits vérifiés et critères objectifs pour TE."""

    def __init__(self) -> None:
        self._facts: dict[str, ExternalFact] = {}
        self._criteria: list[str] = []

    def add_fact(self, concept: str, verified: bool, confidence: float,
                 source: str = "", context: dict | None = None) -> None:
        self._facts[concept] = ExternalFact(
            concept=concept,
            verified=verified,
            confidence=confidence,
            source=source,
            context=context or {},
        )

    def add_criterion(self, criterion: str) -> None:
        if criterion not in self._criteria:
            self._criteria.append(criterion)

    def get_fact(self, concept: str) -> ExternalFact | None:
        return self._facts.get(concept)

    def all_criteria(self) -> list[str]:
        return list(self._criteria)

    def fact_count(self) -> int:
        return len(self._facts)


# ---------------------------------------------------------------------------
# Opérateur TE principal
# ---------------------------------------------------------------------------

class PenseeExtravertie:
    """TE — Jugement par les critères et données objectifs extérieurs.

    Transformations :
    1. Filtrage des hypothèses selon les règles formelles et normes
    2. Scoring de cohérence externe (données connues vs hypothèse)
    3. Classement par pertinence objective → accepted / rejected
    """

    def __init__(self, fact_base: ExternalFactBase | None = None) -> None:
        self.fact_base = fact_base or ExternalFactBase()
        # Critères par défaut (peuvent être enrichis par la mémoire sémantique)
        self.fact_base.add_criterion("empirical_consistency")
        self.fact_base.add_criterion("logical_coherence")
        self.fact_base.add_criterion("source_reliability")

    def process(self, hypothesis_set: HypothesisSet) -> ExternalJudgment:
        """Juger les hypothèses selon les faits et critères objectifs.

        Args:
            hypothesis_set: sortie de NE

        Returns:
            ExternalJudgment — hypothèses acceptées / rejetées + critères utilisés
        """
        t_start = time.time_ns()

        if not hypothesis_set.candidates:
            return ExternalJudgment(
                accepted=[],
                rejected=[],
                criteria_used=self.fact_base.all_criteria(),
                confidence=0.0,
                ts_ns=t_start,
            )

        accepted: list[str] = []
        rejected: list[str] = []
        criteria_used: list[str] = list(self.fact_base.all_criteria())
        scores: list[float] = []

        for hypothesis in hypothesis_set.candidates:
            score = self._score_hypothesis(hypothesis.concept, hypothesis.plausibility)
            scores.append(score)

            if score >= TE_ACCEPTANCE_THRESHOLD:
                accepted.append(hypothesis.concept)
            else:
                rejected.append(hypothesis.concept)

        # Confiance globale = moyenne des scores des hypothèses acceptées
        if accepted and scores:
            accepted_scores = [
                s for h, s in zip(hypothesis_set.candidates, scores)
                if h.concept in accepted
            ]
            confidence = round(sum(accepted_scores) / len(accepted_scores), 4)
        else:
            confidence = 0.0

        return ExternalJudgment(
            accepted=accepted,
            rejected=rejected,
            criteria_used=criteria_used,
            confidence=confidence,
            ts_ns=t_start,
        )

    def _score_hypothesis(self, concept: str, base_plausibility: float) -> float:
        """Calculer le score de cohérence externe d'une hypothèse.

        Règles :
        - Si le concept est dans la base de faits et vérifié → bonus confiance
        - Si le concept est dans la base de faits et non vérifié → pénalité
        - Si le concept est inconnu → score basé sur plausibilité seule
        """
        fact = self.fact_base.get_fact(concept)

        if fact is None:
            # Concept inconnu : score réduit à 60 % de la plausibilité NE
            return round(base_plausibility * 0.6, 4)

        if fact.verified:
            # Fait confirmé : amplification par la confiance du fait
            combined = base_plausibility * 0.5 + fact.confidence * 0.5
            return round(min(combined, 1.0), 4)
        else:
            # Fait réfuté : pénalité
            return round(base_plausibility * 0.2, 4)
