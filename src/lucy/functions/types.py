"""
types.py — Structures de données partagées entre les 8 opérateurs LuCY

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / types
Auteur : LuCY Project

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Sorties opérateurs de PERCEPTION
# ---------------------------------------------------------------------------

@dataclass
class PerceptualFact:
    """Sortie de SE — Sensation Extravertie.

    Constate qu'une chose existe avec ses propriétés observables.
    Ne juge pas la valeur ni la signification — constate l'existence.
    """
    exists: bool
    properties: dict[str, Any]
    confidence: float           # [0.0 – 1.0]
    ts_ns: int = field(default_factory=time.time_ns)
    source: str = "se"
    raw_input_hash: str = ""    # sha256 de l'entrée brute

    def to_dict(self) -> dict:
        return {
            "exists": self.exists,
            "properties": self.properties,
            "confidence": self.confidence,
            "ts_ns": self.ts_ns,
            "source": self.source,
            "raw_input_hash": self.raw_input_hash,
        }


@dataclass
class SubjectiveImpression:
    """Sortie de SI — Sensation Introvertie.

    Comment l'expérience concrète est assimilée intérieurement.
    Peut sur-pondérer l'impression — garde-fou SI_BIAS_MAX à appliquer.
    """
    fact_ref: str               # hash de référence du PerceptualFact
    similarity: float           # [0.0 – 1.0] similarité avec mémoire épisodique
    assimilation_weight: float  # poids d'assimilation appris
    notes: list[str] = field(default_factory=list)
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "fact_ref": self.fact_ref,
            "similarity": self.similarity,
            "assimilation_weight": self.assimilation_weight,
            "notes": self.notes,
            "ts_ns": self.ts_ns,
        }


@dataclass
class Hypothesis:
    """Une hypothèse candidate produite par NE."""
    concept: str
    plausibility: float         # [0.0 – 1.0]
    supporting_facts: list[str] = field(default_factory=list)
    depth: int = 1              # profondeur d'expansion dans le graphe


@dataclass
class HypothesisSet:
    """Sortie de NE — Intuition Extravertie.

    Possibilités ouvertes par l'environnement extérieur.
    Doit passer par TE ou TI pour validation.
    """
    candidates: list[Hypothesis]
    plausibility_scores: dict[str, float]
    expansion_depth: int = 1
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "candidates": [
                {
                    "concept": h.concept,
                    "plausibility": h.plausibility,
                    "supporting_facts": h.supporting_facts,
                    "depth": h.depth,
                }
                for h in self.candidates
            ],
            "plausibility_scores": self.plausibility_scores,
            "expansion_depth": self.expansion_depth,
            "ts_ns": self.ts_ns,
        }


@dataclass
class AbstractPattern:
    """Sortie de NI — Intuition Introvertie.

    Configuration symbolique interne dégagée de l'expérience.
    Confrontation obligatoire avec SE pour éviter la déconnexion des faits.
    """
    symbol: str
    confidence: float           # [0.0 – 1.0]
    semantic_vector: list[float]
    source_ref: str = ""
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "confidence": self.confidence,
            "semantic_vector": self.semantic_vector[:8],  # résumé pour log
            "source_ref": self.source_ref,
            "ts_ns": self.ts_ns,
        }


# ---------------------------------------------------------------------------
# Sorties opérateurs de JUGEMENT
# ---------------------------------------------------------------------------

@dataclass
class ExternalJudgment:
    """Sortie de TE — Pensée Extravertie.

    Jugement fondé sur les données et critères objectifs extérieurs.
    Les critères peuvent être incomplets — nécessite rafraîchissement.
    """
    accepted: list[str]
    rejected: list[str]
    criteria_used: list[str]
    confidence: float           # [0.0 – 1.0]
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "criteria_used": self.criteria_used,
            "confidence": self.confidence,
            "ts_ns": self.ts_ns,
        }


@dataclass
class InternalModel:
    """Sortie de TI — Pensée Introvertie.

    Modèle causal interne cohérent. Peut être faux même si cohérent —
    doit être confronté à SE/NE pour ancrage dans les faits.
    """
    principle: str
    consistency_score: float    # [0.0 – 1.0]
    revision_count: int = 0
    contradictions: list[str] = field(default_factory=list)
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "principle": self.principle,
            "consistency_score": self.consistency_score,
            "revision_count": self.revision_count,
            "contradictions": self.contradictions,
            "ts_ns": self.ts_ns,
        }


@dataclass
class RelationalValue:
    """Sortie de FE — Sentiment Extraverti.

    Valeur relationnelle de l'action dans le contexte social.
    Garde-fou FE_NORM_STALENESS_MAX contre sur-adaptation aux conventions.
    """
    acceptability: float        # [0.0 – 1.0]
    affected_parties: list[str]
    norm_ref: list[str]
    justification: str = ""
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "acceptability": self.acceptability,
            "affected_parties": self.affected_parties,
            "norm_ref": self.norm_ref,
            "justification": self.justification,
            "ts_ns": self.ts_ns,
        }


@dataclass
class InternalValue:
    """Sortie de FI — Sentiment Introverti.

    Évaluation selon les valeurs internes profondes.
    Le jugement peut rester silencieux — mécanisme d'explicitation requis.
    """
    congruence: float           # [0.0 – 1.0] conformité aux valeurs internes
    conviction_level: float     # [0.0 – 1.0]
    expression_needed: bool = False
    notes: str = ""
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "congruence": self.congruence,
            "conviction_level": self.conviction_level,
            "expression_needed": self.expression_needed,
            "notes": self.notes,
            "ts_ns": self.ts_ns,
        }


# ---------------------------------------------------------------------------
# Décision finale du coordinateur
# ---------------------------------------------------------------------------

@dataclass
class ActionDecision:
    """Décision finale après arbitrage des 8 opérateurs."""
    action: str
    confidence: float           # [0.0 – 1.0]
    consensus_score: float      # fraction des opérateurs convergents
    conflict_detected: bool = False
    conflict_description: str = ""
    dominant_function: str = ""
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "consensus_score": self.consensus_score,
            "conflict_detected": self.conflict_detected,
            "conflict_description": self.conflict_description,
            "dominant_function": self.dominant_function,
            "ts_ns": self.ts_ns,
        }
