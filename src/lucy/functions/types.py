"""
types.py — Structures de données partagées entre les 8 opérateurs LuCY

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / types
Auteur : LuCY Project

Phase 2 — Contrats opérationnels formels (OperatorContract + OperatorTrace)
Phase 3 (audit) — Corrections P0-A, P0-B, P1-A, P1-B :
  P0-A : HardLimit.check() lève LimitViolationError si la limite est violée.
         Le résultat n'est JAMAIS retourné si une limite est franchie.
  P0-B : v:no_wipe étendu aux synonymes dans feeling_in.py.
  P1-A : OperatorContract.check_traceability_keys() vérifie que chaque clé
         déclarée dans `traceability` est présente dans les intermediate_steps
         de l'OperatorTrace produit.
  P1-B : SuccessCriterion.evaluate() clamp [0.0, 1.0] sur le score retourné.
Chaque opérateur dispose d'un contrat formalisé décrivant :
  1. operation      : ce que l'opérateur fait à l'information
  2. mechanism      : comment il réalise cette opération
  3. output_type    : ce qu'il produit et transmet
  4. hard_limits    : ce qu'il NE DOIT PAS faire (vérifiable à l'exécution)
  5. traceability   : informations pour reconstruire le raisonnement
  6. success_criteria : tests vérifiables quantitatifs

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Phase 2 — Contrat opérationnel formel
# ---------------------------------------------------------------------------

class LimitViolationError(RuntimeError):
    """P0-A — Levée quand une HardLimit est violée.

    L'opérateur DOIT attraper cette exception, loguer la violation dans la
    trace, et NE PAS retourner de résultat (ou retourner une valeur de repli
    explicitement marquée `limit_violated=True`).
    """

    def __init__(self, limit_name: str, operator_id: str, description: str = "") -> None:
        self.limit_name = limit_name
        self.operator_id = operator_id
        self.description = description
        super().__init__(
            f"[LuCY/{operator_id}] HardLimit '{limit_name}' violée : {description}"
        )


@dataclass
class HardLimit:
    """Une limite inviolable pour un opérateur.

    Phase 3 (P0-A) : check() lève LimitViolationError si la limite est
    violée. L'opérateur ne doit JAMAIS retourner un résultat invalide.
    violated=True sert uniquement de cache post-vérification (logging).
    """
    name: str
    description: str
    check_fn: Callable[[Any], bool] = field(default=lambda _: True, repr=False)
    violated: bool = False

    def check(self, result: Any, operator_id: str = "UNKNOWN") -> bool:
        """Vérifie la limite. Lève LimitViolationError si violée (P0-A).

        Args:
            result      : sortie brute de l'opérateur à vérifier.
            operator_id : identifiant de l'opérateur appelant (pour l'erreur).

        Returns:
            True si la limite est respectée.

        Raises:
            LimitViolationError : si la limite est violée — l'appelant DOIT
            l'attraper et ne pas retourner le résultat tel quel.
        """
        ok = self.check_fn(result)
        self.violated = not ok
        if not ok:
            raise LimitViolationError(
                limit_name=self.name,
                operator_id=operator_id,
                description=self.description,
            )
        return True


@dataclass
class SuccessCriterion:
    """Un critère de réussite mesurable pour un opérateur.

    Phase 3 (P1-B) : evaluate() clamp le score dans [0.0, 1.0]. Une
    evaluate_fn retournant une valeur hors intervalle est silencieusement
    corrigée et la déviation est mémorisée dans `clamped`.
    """
    name: str
    description: str
    evaluate_fn: Callable[[Any], float] = field(default=lambda _: 1.0, repr=False)
    # score [0.0 – 1.0] mis à jour par evaluate()
    last_score: float = 0.0
    clamped: bool = False  # True si le score brut était hors [0.0, 1.0]

    def evaluate(self, result: Any) -> float:
        """Évalue et mémorise le score, clamped dans [0.0, 1.0] (P1-B)."""
        raw = float(self.evaluate_fn(result))
        clamped_score = max(0.0, min(1.0, raw))
        self.clamped = (raw != clamped_score)
        self.last_score = clamped_score
        return self.last_score


@dataclass
class OperatorContract:
    """Contrat opérationnel formel d'un opérateur LuCY (Phase 2).

    Contient les 6 dimensions spécifiées dans le CDC Phase 2 :
    1. operation        — opération fondamentale
    2. mechanism        — mécanisme de réalisation
    3. output_type      — type de sortie produit
    4. hard_limits      — limites vérifiables à l'exécution
    5. traceability     — clés de traçabilité obligatoires dans le trace dict
    6. success_criteria — critères de réussite mesurables
    """
    operator_id: str          # SE / SI / NE / NI / TE / TI / FE / FI
    operation: str
    mechanism: str
    output_type: str
    hard_limits: list[HardLimit] = field(default_factory=list)
    traceability: list[str] = field(default_factory=list)
    success_criteria: list[SuccessCriterion] = field(default_factory=list)

    def check_all_limits(
        self, result: Any, operator_id: str | None = None
    ) -> tuple[bool, list[str]]:
        """Vérifier toutes les limites (P0-A).

        Si une limite est violée, LimitViolationError est levée immédiatement —
        le résultat NE DOIT PAS être retourné à l'appelant.

        Les opérateurs doivent appeler check_all_limits() dans un bloc
        try/except LimitViolationError et retourner une valeur de repli.

        Args:
            result      : sortie brute à vérifier.
            operator_id : transmis à HardLimit.check() pour les messages d'erreur.

        Returns:
            (True, []) si toutes les limites sont respectées.

        Raises:
            LimitViolationError : dès la première limite violée.
        """
        op_id = operator_id or self.operator_id
        for lim in self.hard_limits:
            lim.check(result, operator_id=op_id)  # lève si violée
        return (True, [])

    def check_traceability_keys(self, trace: "OperatorTrace") -> tuple[bool, list[str]]:
        """P1-A — Vérifier que chaque clé déclarée dans `traceability` est présente
        dans les intermediate_steps de la trace produite.

        Une clé est considérée présente si au moins un élément de
        `trace.intermediate_steps` commence par `{key}:` ou contient `{key}`.

        Returns:
            (all_present, missing_keys)
        """
        missing: list[str] = []
        for key in self.traceability:
            found = any(key in step for step in trace.intermediate_steps)
            if not found:
                missing.append(key)
        return (len(missing) == 0, missing)

    def evaluate_all_criteria(self, result: Any) -> dict[str, float]:
        """Évaluer tous les critères. Retourne {name: score}."""
        return {c.name: c.evaluate(result) for c in self.success_criteria}

    def finalize_trace(
        self,
        result: Any,
        trace: "OperatorTrace",
        t_start: int,
        fallback_result: Any | None = None,
    ) -> tuple[Any, "OperatorTrace"]:
        """P0-A — Finaliser la trace après vérification des limites.

        Si une limite est violée :
        - L'exception LimitViolationError est attrapée.
        - trace.limits_checked = True, trace.limits_violated = [nom_limite].
        - Si `fallback_result` est fourni, il est retourné à la place du résultat invalide.
        - Sinon, l'exception est re-levée.

        Si toutes les limites sont respectées :
        - trace.limits_checked = True, trace.limits_violated = [].
        - trace.criteria_scores est peuplé.
        - (result, trace) est retourné.

        Usage dans les opérateurs :
            result, trace = contract.finalize_trace(result, trace, t_start, fallback_result)
            return result
        """
        trace.limits_checked = True
        try:
            self.check_all_limits(result, operator_id=self.operator_id)
            trace.limits_violated = []
        except LimitViolationError as exc:
            trace.limits_violated = [exc.limit_name]
            trace.intermediate_steps.append(f"LIMIT_VIOLATED:{exc.limit_name}:{exc.description}")
            trace.criteria_scores = {}
            trace.duration_ns = time.time_ns() - t_start
            if fallback_result is not None:
                return fallback_result, trace
            raise

        # Vérification des clés de traçabilité (P1-A — non bloquant, log seulement)
        all_present, missing = self.check_traceability_keys(trace)
        if not all_present:
            trace.intermediate_steps.append(f"TRACEABILITY_MISSING_KEYS:{missing}")

        trace.criteria_scores = self.evaluate_all_criteria(result)
        trace.duration_ns = time.time_ns() - t_start
        return result, trace

    def to_dict(self) -> dict:
        return {
            "operator_id": self.operator_id,
            "operation": self.operation,
            "mechanism": self.mechanism,
            "output_type": self.output_type,
            "hard_limits": [
                {"name": l.name, "description": l.description, "violated": l.violated}
                for l in self.hard_limits
            ],
            "traceability_keys": self.traceability,
            "success_criteria": [
                {"name": c.name, "description": c.description, "last_score": c.last_score}
                for c in self.success_criteria
            ],
        }


@dataclass
class OperatorTrace:
    """Trace de traçabilité produite par chaque appel d'opérateur.

    Permet de reconstruire le raisonnement après-coup sans ré-exécution.
    Toujours incluse dans les sorties des opérateurs Phase 2.
    """
    operator_id: str
    cycle_ref: str = ""           # identifiant du cycle appelant
    input_hash: str = ""          # SHA-256 tronqué de l'entrée
    intermediate_steps: list[str] = field(default_factory=list)
    limits_checked: bool = False
    limits_violated: list[str] = field(default_factory=list)
    criteria_scores: dict[str, float] = field(default_factory=dict)
    duration_ns: int = 0
    ts_ns: int = field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            "operator_id": self.operator_id,
            "cycle_ref": self.cycle_ref,
            "input_hash": self.input_hash,
            "intermediate_steps": self.intermediate_steps,
            "limits_checked": self.limits_checked,
            "limits_violated": self.limits_violated,
            "criteria_scores": self.criteria_scores,
            "duration_ns": self.duration_ns,
            "ts_ns": self.ts_ns,
        }


# ---------------------------------------------------------------------------
# Sorties opérateurs de PERCEPTION
# ---------------------------------------------------------------------------
# Phase 2 : chaque sortie inclut un champ `trace: OperatorTrace` permettant
# de reconstruire le raisonnement sans ré-exécution.
# ---------------------------------------------------------------------------

@dataclass
class PerceptualFact:
    """Sortie de SE — Sensation Extravertie.

    Constate qu'une chose existe avec ses propriétés observables.
    Ne juge pas la valeur ni la signification — constate l'existence.
    Phase 2 : champ `trace` ajouté pour traçabilité complète.
    """
    exists: bool
    properties: dict[str, Any]
    confidence: float           # [0.0 – 1.0]
    ts_ns: int = field(default_factory=time.time_ns)
    source: str = "se"
    raw_input_hash: str = ""    # sha256 de l'entrée brute
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="SE"))

    def to_dict(self) -> dict:
        return {
            "exists": self.exists,
            "properties": self.properties,
            "confidence": self.confidence,
            "ts_ns": self.ts_ns,
            "source": self.source,
            "raw_input_hash": self.raw_input_hash,
            "trace": self.trace.to_dict(),
        }


@dataclass
class SubjectiveImpression:
    """Sortie de SI — Sensation Introvertie.

    Comment l'expérience concrète est assimilée intérieurement.
    Peut sur-pondérer l'impression — garde-fou SI_BIAS_MAX à appliquer.
    Phase 2 : champ `trace` ajouté.
    """
    fact_ref: str               # hash de référence du PerceptualFact
    similarity: float           # [0.0 – 1.0] similarité avec mémoire épisodique
    assimilation_weight: float  # poids d'assimilation appris
    notes: list[str] = field(default_factory=list)
    ts_ns: int = field(default_factory=time.time_ns)
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="SI"))

    def to_dict(self) -> dict:
        return {
            "fact_ref": self.fact_ref,
            "similarity": self.similarity,
            "assimilation_weight": self.assimilation_weight,
            "notes": self.notes,
            "ts_ns": self.ts_ns,
            "trace": self.trace.to_dict(),
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
    Phase 2 : champ `trace` ajouté.
    """
    candidates: list[Hypothesis]
    plausibility_scores: dict[str, float]
    expansion_depth: int = 1
    ts_ns: int = field(default_factory=time.time_ns)
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="NE"))

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
            "trace": self.trace.to_dict(),
        }


@dataclass
class AbstractPattern:
    """Sortie de NI — Intuition Introvertie.

    Configuration symbolique interne dégagée de l'expérience.
    Confrontation obligatoire avec SE pour éviter la déconnexion des faits.
    Phase 2 : champ `trace` ajouté.
    """
    symbol: str
    confidence: float           # [0.0 – 1.0]
    semantic_vector: list[float]
    source_ref: str = ""
    ts_ns: int = field(default_factory=time.time_ns)
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="NI"))

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "confidence": self.confidence,
            "semantic_vector": self.semantic_vector[:8],  # résumé pour log
            "source_ref": self.source_ref,
            "ts_ns": self.ts_ns,
            "trace": self.trace.to_dict(),
        }


# ---------------------------------------------------------------------------
# Sorties opérateurs de JUGEMENT
# ---------------------------------------------------------------------------

@dataclass
class ExternalJudgment:
    """Sortie de TE — Pensée Extravertie.

    Jugement fondé sur les données et critères objectifs extérieurs.
    Les critères peuvent être incomplets — nécessite rafraîchissement.
    Phase 2 : champ `trace` ajouté.
    """
    accepted: list[str]
    rejected: list[str]
    criteria_used: list[str]
    confidence: float           # [0.0 – 1.0]
    ts_ns: int = field(default_factory=time.time_ns)
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="TE"))

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "criteria_used": self.criteria_used,
            "confidence": self.confidence,
            "ts_ns": self.ts_ns,
            "trace": self.trace.to_dict(),
        }


@dataclass
class InternalModel:
    """Sortie de TI — Pensée Introvertie.

    Modèle causal interne cohérent. Peut être faux même si cohérent —
    doit être confronté à SE/NE pour ancrage dans les faits.
    Phase 2 : champ `trace` ajouté.
    """
    principle: str
    consistency_score: float    # [0.0 – 1.0]
    revision_count: int = 0
    contradictions: list[str] = field(default_factory=list)
    ts_ns: int = field(default_factory=time.time_ns)
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="TI"))

    def to_dict(self) -> dict:
        return {
            "principle": self.principle,
            "consistency_score": self.consistency_score,
            "revision_count": self.revision_count,
            "contradictions": self.contradictions,
            "ts_ns": self.ts_ns,
            "trace": self.trace.to_dict(),
        }


@dataclass
class RelationalValue:
    """Sortie de FE — Sentiment Extraverti.

    Valeur relationnelle de l'action dans le contexte social.
    Garde-fou FE_NORM_STALENESS_MAX contre sur-adaptation aux conventions.
    Phase 2 : champ `trace` ajouté.
    """
    acceptability: float        # [0.0 – 1.0]
    affected_parties: list[str]
    norm_ref: list[str]
    justification: str = ""
    ts_ns: int = field(default_factory=time.time_ns)
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="FE"))

    def to_dict(self) -> dict:
        return {
            "acceptability": self.acceptability,
            "affected_parties": self.affected_parties,
            "norm_ref": self.norm_ref,
            "justification": self.justification,
            "ts_ns": self.ts_ns,
            "trace": self.trace.to_dict(),
        }


@dataclass
class InternalValue:
    """Sortie de FI — Sentiment Introverti.

    Évaluation selon les valeurs internes profondes.
    Le jugement peut rester silencieux — mécanisme d'explicitation requis.
    Phase 2 : champ `trace` ajouté.
    """
    congruence: float           # [0.0 – 1.0] conformité aux valeurs internes
    conviction_level: float     # [0.0 – 1.0]
    expression_needed: bool = False
    notes: str = ""
    ts_ns: int = field(default_factory=time.time_ns)
    trace: OperatorTrace = field(default_factory=lambda: OperatorTrace(operator_id="FI"))

    def to_dict(self) -> dict:
        return {
            "congruence": self.congruence,
            "conviction_level": self.conviction_level,
            "expression_needed": self.expression_needed,
            "notes": self.notes,
            "ts_ns": self.ts_ns,
            "trace": self.trace.to_dict(),
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
