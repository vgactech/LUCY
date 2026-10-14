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
Phase 4 (audit critique) — Corrections résiduelles P0-A / P0-B / P1-A / P1-B :
  P0-A : finalize_trace() persiste la trace forensic AVANT re-raise.
         LimitViolationError sans fallback = trace persistée côté logger,
         puis exception re-levée. Diagnostic jamais perdu.
  P0-B : SuccessCriterion.evaluate() guard math.isfinite() avant le clamp.
         NaN/±inf → score 0.0 + clamped=True + score_invalid=True.
         Vérification : max(0.0, min(1.0, NaN)) == 1.0 en Python — bug réel.
  P1-A : HardLimit.violated / SuccessCriterion.last_score / .clamped /
         .score_invalid ne sont plus stockés sur les instances globales.
         Ces états sont retournés uniquement via LimitCheckResult /
         CriterionResult et inclus dans l'OperatorTrace.
  P1-B : OperatorContract.critical_traceability_keys : list[str] — si une clé
         critique est absente de la trace, finalize_trace() lève
         CriticalTraceabilityError (ou retourne le fallback si fourni).
         Les clés non-critiques restent des warnings dans intermediate_steps.
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
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


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


class CriticalTraceabilityError(RuntimeError):
    """P1-B Phase 4 — Levée quand une clé de traçabilité critique est absente.

    Distincte de LimitViolationError : concerne le manque de preuve
    reconstructible, pas le franchissement d'une limite opérationnelle.
    """

    def __init__(self, missing_keys: list[str], operator_id: str) -> None:
        self.missing_keys = missing_keys
        self.operator_id = operator_id
        super().__init__(
            f"[LuCY/{operator_id}] Clés de traçabilité critiques manquantes : {missing_keys}"
        )


@dataclass
class LimitCheckResult:
    """Phase 4 (P1-A) — Résultat d'une vérification de limite.

    N'est JAMAIS stocké dans l'instance globale HardLimit.
    Retourné uniquement par check_stateless() pour éviter toute mutation
    des instances globales (thread-safety inter-cycles).
    """
    limit_name: str
    violated: bool
    operator_id: str = "UNKNOWN"


@dataclass
class CriterionResult:
    """Phase 4 (P1-A) — Résultat d'une évaluation de critère.

    N'est JAMAIS stocké dans l'instance globale SuccessCriterion.
    Retourné uniquement par evaluate_stateless() pour isoler les états
    par cycle (thread-safety).
    """
    criterion_name: str
    score: float          # [0.0, 1.0] — toujours fini et borné
    clamped: bool         # True si le score brut était hors [0.0, 1.0]
    score_invalid: bool   # True si le score brut était NaN ou infini (P0-B)
    raw_score: float      # valeur brute avant guard + clamp (debug)


@dataclass
class HardLimit:
    """Une limite inviolable pour un opérateur.

    Phase 3 (P0-A) : check() lève LimitViolationError si la limite est
    violée. L'opérateur ne doit JAMAIS retourner un résultat invalide.

    Phase 4 (P1-A) : check_stateless() est la méthode recommandée pour les
    nouveaux appels. Elle retourne un LimitCheckResult sans muter l'instance
    (thread-safe). check() reste disponible pour compatibilité ascendante mais
    son effet de bord `self.violated = not ok` est déprécié.
    """
    name: str
    description: str
    check_fn: Callable[[Any], bool] = field(default=lambda _: True, repr=False)
    # DEPRECATED Phase 4 (P1-A) : violated ne doit plus être lu par les
    # consommateurs — utiliser LimitCheckResult.violated à la place.
    violated: bool = False

    def check(self, result: Any, operator_id: str = "UNKNOWN") -> bool:
        """Vérifie la limite. Lève LimitViolationError si violée (P0-A).

        Compatibilité ascendante — maintient self.violated pour les anciens
        consommateurs. Préférer check_stateless() dans les nouveaux appels.

        Args:
            result      : sortie brute de l'opérateur à vérifier.
            operator_id : identifiant de l'opérateur appelant (pour l'erreur).

        Returns:
            True si la limite est respectée.

        Raises:
            LimitViolationError : si la limite est violée.
        """
        ok = self.check_fn(result)
        self.violated = not ok  # DEPRECATED — effet de bord conservé compat
        if not ok:
            raise LimitViolationError(
                limit_name=self.name,
                operator_id=operator_id,
                description=self.description,
            )
        return True

    def check_stateless(
        self, result: Any, operator_id: str = "UNKNOWN"
    ) -> LimitCheckResult:
        """Phase 4 (P1-A) — Vérifier la limite sans muter l'instance globale.

        Thread-safe : aucun état n'est écrit sur self.
        Lève LimitViolationError si la limite est violée (même comportement
        que check() pour la propagation d'exception).

        Returns:
            LimitCheckResult avec violated=False si la limite est respectée.

        Raises:
            LimitViolationError : si la limite est violée.
        """
        ok = self.check_fn(result)
        if not ok:
            raise LimitViolationError(
                limit_name=self.name,
                operator_id=operator_id,
                description=self.description,
            )
        return LimitCheckResult(limit_name=self.name, violated=False, operator_id=operator_id)


@dataclass
class SuccessCriterion:
    """Un critère de réussite mesurable pour un opérateur.

    Phase 3 (P1-B) : evaluate() clamp le score dans [0.0, 1.0].
    Phase 4 (P0-B) : evaluate() guard math.isfinite() — NaN/±inf → 0.0 +
                     score_invalid=True (bug Python confirmé :
                     max(0.0, min(1.0, NaN)) == 1.0).
    Phase 4 (P1-A) : evaluate_stateless() est la méthode recommandée. Elle
                     retourne un CriterionResult sans muter last_score/clamped
                     sur l'instance globale (thread-safe).
    """
    name: str
    description: str
    evaluate_fn: Callable[[Any], float] = field(default=lambda _: 1.0, repr=False)
    # DEPRECATED Phase 4 (P1-A) : last_score / clamped ne doivent plus être
    # lus par les consommateurs — utiliser CriterionResult à la place.
    last_score: float = 0.0
    clamped: bool = False

    def evaluate(self, result: Any) -> float:
        """Évalue le score, clamped dans [0.0, 1.0].

        Phase 4 (P0-B) : guard isfinite() avant clamp.
        Compatibilité ascendante — maintient last_score/clamped pour les
        anciens consommateurs. Préférer evaluate_stateless().
        """
        raw = float(self.evaluate_fn(result))
        if not math.isfinite(raw):
            # P0-B : NaN ou ±inf → score invalide = 0.0, pas 1.0
            self.clamped = True
            self.last_score = 0.0
            return 0.0
        clamped_score = max(0.0, min(1.0, raw))
        self.clamped = (raw != clamped_score)
        self.last_score = clamped_score
        return self.last_score

    def evaluate_stateless(self, result: Any) -> "CriterionResult":
        """Phase 4 (P1-A) — Évaluer sans muter l'instance globale.

        Thread-safe : aucun état n'est écrit sur self.
        Inclut le guard math.isfinite() (P0-B).

        Returns:
            CriterionResult avec score dans [0.0, 1.0].
        """
        raw = float(self.evaluate_fn(result))
        if not math.isfinite(raw):
            return CriterionResult(
                criterion_name=self.name,
                score=0.0,
                clamped=True,
                score_invalid=True,
                raw_score=raw,
            )
        clamped_score = max(0.0, min(1.0, raw))
        return CriterionResult(
            criterion_name=self.name,
            score=clamped_score,
            clamped=(raw != clamped_score),
            score_invalid=False,
            raw_score=raw,
        )



# ---------------------------------------------------------------------------
# Phase 4 (P0-A) — Helper : persistance forensic avant re-raise
# ---------------------------------------------------------------------------

def _persist_trace_forensic(
    trace: "OperatorTrace",
    forensic_logger: Any,
    event: str = "limit_violation",
) -> None:
    """Persister la trace dans le log forensic AVANT de re-lever l'exception.

    P0-A Phase 4 : garantit que le diagnostic n'est jamais perdu même si
    l'exception traverse toute la pile d'appel sans être attrapée.

    Si `forensic_logger` est None (pas de logger injecté), la trace est
    enregistrée dans un fichier de secours basé sur le timestamp pour ne
    jamais perdre d'information (fallback sans dépendance externe).

    Args:
        trace           : trace à persister (OperatorTrace déjà partiellement renseignée).
        forensic_logger : instance avec méthode log(event, **kwargs), ou None.
        event           : type d'événement pour le log ('limit_violation' ou
                          'critical_traceability_missing').
    """
    import json as _json
    import os as _os

    trace_dict = trace.to_dict()
    trace_dict["forensic_event"] = event
    trace_dict["persisted_before_raise"] = True

    if forensic_logger is not None:
        try:
            forensic_logger.log(event, trace=trace_dict)
        except Exception:
            # Fail-safe : si le logger lui-même échoue, écrire en fichier brut
            _write_emergency_trace(trace_dict, event)
    else:
        # Pas de logger injecté → écriture d'urgence dans les intermediate_steps
        # (toujours visible dans la trace sans dépendance externe)
        trace.intermediate_steps.append(
            f"FORENSIC_PERSISTED_BEFORE_RAISE:{event}:ts_ns={trace.ts_ns}"
        )
        # Tentative d'écriture dans le fichier forensic par défaut
        _write_emergency_trace(trace_dict, event)


def _write_emergency_trace(trace_dict: dict, event: str) -> None:
    """Écriture d'urgence de la trace dans un fichier JSON minimal.

    Utilisée quand le forensic_logger n'est pas disponible. Garantit P0-A
    sans créer de dépendance sur ForensicLogger.
    """
    import json as _json
    import os as _os
    import time as _time

    # Chercher le dossier logs/forensic à partir du dossier courant
    candidate_paths = [
        "LuCY/logs/forensic/lucy_forensic_emergency.jsonl",
        "logs/forensic/lucy_forensic_emergency.jsonl",
        "/tmp/lucy_forensic_emergency.jsonl",
    ]
    for path in candidate_paths:
        try:
            dir_path = _os.path.dirname(path)
            if dir_path:
                _os.makedirs(dir_path, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(_json.dumps(trace_dict, default=str) + "\n")
            return  # Succès
        except Exception:
            continue  # Essayer le chemin suivant



@dataclass
class OperatorContract:
    """Contrat opérationnel formel d'un opérateur LuCY (Phase 2).

    Contient les 6 dimensions spécifiées dans le CDC Phase 2 :
    1. operation        — opération fondamentale
    2. mechanism        — mécanisme de réalisation
    3. output_type      — type de sortie produit
    4. hard_limits      — limites vérifiables à l'exécution
    5. traceability     — clés de traçabilité (warnings si manquantes)
    6. success_criteria — critères de réussite mesurables

    Phase 4 (P1-B) : critical_traceability_keys — sous-ensemble bloquant de
    `traceability`. Si une de ces clés est absente de la trace,
    finalize_trace() lève CriticalTraceabilityError (ou retourne le fallback).
    """
    operator_id: str          # SE / SI / NE / NI / TE / TI / FE / FI
    operation: str
    mechanism: str
    output_type: str
    hard_limits: list[HardLimit] = field(default_factory=list)
    traceability: list[str] = field(default_factory=list)
    success_criteria: list[SuccessCriterion] = field(default_factory=list)
    # Phase 4 (P1-B) : clés critiques bloquantes (sous-ensemble de traceability)
    critical_traceability_keys: list[str] = field(default_factory=list)

    def check_all_limits(
        self, result: Any, operator_id: Optional[str] = None
    ) -> tuple[bool, list[str]]:
        """Vérifier toutes les limites (P0-A).

        Phase 4 (P1-A) : utilise check_stateless() en interne pour éviter de
        muter les instances globales. L'exception LimitViolationError est
        toujours levée dès la première violation.

        Args:
            result      : sortie brute à vérifier.
            operator_id : transmis aux limites pour les messages d'erreur.

        Returns:
            (True, []) si toutes les limites sont respectées.

        Raises:
            LimitViolationError : dès la première limite violée.
        """
        op_id = operator_id or self.operator_id
        for lim in self.hard_limits:
            lim.check_stateless(result, operator_id=op_id)  # P1-A : sans mutation
        return (True, [])

    def check_traceability_keys(
        self, trace: "OperatorTrace"
    ) -> tuple[bool, list[str]]:
        """Vérifier que chaque clé déclarée dans `traceability` est présente.

        Une clé est considérée présente si au moins un élément de
        `trace.intermediate_steps` contient `{key}`.

        Returns:
            (all_present, missing_keys)
        """
        missing: list[str] = []
        for key in self.traceability:
            found = any(key in step for step in trace.intermediate_steps)
            if not found:
                missing.append(key)
        return (len(missing) == 0, missing)

    def check_critical_traceability_keys(
        self, trace: "OperatorTrace"
    ) -> tuple[bool, list[str]]:
        """Phase 4 (P1-B) — Vérifier les clés de traçabilité CRITIQUES.

        Si une clé listée dans `critical_traceability_keys` est absente de la
        trace, le diagnostic est irreconstituable → erreur bloquante.

        Returns:
            (all_present, missing_critical_keys)
        """
        missing_critical: list[str] = []
        for key in self.critical_traceability_keys:
            found = any(key in step for step in trace.intermediate_steps)
            if not found:
                missing_critical.append(key)
        return (len(missing_critical) == 0, missing_critical)

    def evaluate_all_criteria_stateless(self, result: Any) -> dict[str, "CriterionResult"]:
        """Phase 4 (P1-A) — Évaluer tous les critères sans muter les instances.

        Returns:
            {criterion_name: CriterionResult} — états isolés par cycle.
        """
        return {c.name: c.evaluate_stateless(result) for c in self.success_criteria}

    def evaluate_all_criteria(self, result: Any) -> dict[str, float]:
        """Évaluer tous les critères. Retourne {name: score}.

        Compatibilité ascendante — utilise evaluate_stateless() en interne
        (P1-A) mais retourne le format dict[str, float] attendu par finalize_trace.
        """
        results = self.evaluate_all_criteria_stateless(result)
        return {name: cr.score for name, cr in results.items()}

    def finalize_trace(
        self,
        result: Any,
        trace: "OperatorTrace",
        t_start: int,
        fallback_result: Any | None = None,
        _forensic_logger: Any | None = None,
    ) -> tuple[Any, "OperatorTrace"]:
        """Phase 4 — Finaliser la trace après vérification complète des limites.

        Séquence :
        1. Vérification des HardLimits (check_all_limits — stateless P1-A).
           - Violation → trace persistée forensic AVANT re-raise (P0-A).
           - fallback_result fourni → retour du fallback sans raise.
        2. Vérification des clés critiques (P1-B).
           - Clé critique manquante → CriticalTraceabilityError (ou fallback).
        3. Vérification des clés non-critiques (warning dans intermediate_steps).
        4. Évaluation des critères de réussite (stateless P1-A, guard NaN P0-B).
        5. Finalisation de la durée.

        Args:
            result           : sortie brute à vérifier.
            trace            : trace en cours de construction.
            t_start          : timestamp ns de début.
            fallback_result  : valeur de repli si violation. None = re-raise.
            _forensic_logger : optionnel — instance ForensicLogger pour P0-A.
                               Si None, la trace est encodée JSON dans
                               intermediate_steps (fallback sans dépendance).

        Returns:
            (result_final, trace) — result_final peut être le fallback.

        Raises:
            LimitViolationError        : si limite violée et pas de fallback.
            CriticalTraceabilityError  : si clé critique manquante et pas de fallback.
        """
        trace.limits_checked = True

        # ── Étape 1 : vérification des HardLimits ──────────────────────────
        try:
            self.check_all_limits(result, operator_id=self.operator_id)
            trace.limits_violated = []
        except LimitViolationError as exc:
            trace.limits_violated = [exc.limit_name]
            trace.intermediate_steps.append(
                f"LIMIT_VIOLATED:{exc.limit_name}:{exc.description}"
            )
            trace.criteria_scores = {}
            trace.duration_ns = time.time_ns() - t_start

            # P0-A : persister la trace forensic AVANT re-raise
            _persist_trace_forensic(trace, _forensic_logger, event="limit_violation")

            if fallback_result is not None:
                return fallback_result, trace
            raise

        # ── Étape 2 : vérification des clés critiques (P1-B) ───────────────
        all_critical_ok, missing_critical = self.check_critical_traceability_keys(trace)
        if not all_critical_ok:
            trace.intermediate_steps.append(
                f"CRITICAL_TRACEABILITY_MISSING:{missing_critical}"
            )
            trace.duration_ns = time.time_ns() - t_start

            # P0-A appliqué aussi aux erreurs de traçabilité critique
            _persist_trace_forensic(trace, _forensic_logger, event="critical_traceability_missing")

            if fallback_result is not None:
                return fallback_result, trace
            raise CriticalTraceabilityError(
                missing_keys=missing_critical,
                operator_id=self.operator_id,
            )

        # ── Étape 3 : clés non-critiques (warnings) ────────────────────────
        all_present, missing = self.check_traceability_keys(trace)
        if not all_present:
            # Filtrer les clés critiques déjà traitées (pour éviter doublons)
            non_critical_missing = [k for k in missing if k not in self.critical_traceability_keys]
            if non_critical_missing:
                trace.intermediate_steps.append(
                    f"TRACEABILITY_MISSING_KEYS:{non_critical_missing}"
                )

        # ── Étape 4 : évaluation des critères (stateless + guard NaN) ──────
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
                {"name": lim.name, "description": lim.description, "violated": lim.violated}
                for lim in self.hard_limits
            ],
            "traceability_keys": self.traceability,
            "critical_traceability_keys": self.critical_traceability_keys,
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
