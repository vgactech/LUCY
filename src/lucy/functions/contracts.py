"""
contracts.py — Contrats opérationnels formels des 8 opérateurs LuCY (Phase 2)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / contracts
Auteur : LuCY Project

Ce module instancie les 8 contrats OperatorContract conformément au CDC Phase 2 §3.
Chaque contrat définit les 6 dimensions formelles :
  1. operation       — opération fondamentale de l'opérateur
  2. mechanism       — mécanisme de réalisation (sans LLM externe)
  3. output_type     — type Python de sortie produit
  4. hard_limits     — limites inviolables vérifiables à l'exécution
  5. traceability    — clés obligatoires dans OperatorTrace
  6. success_criteria — critères mesurables [0.0 – 1.0]

Usage :
    from lucy.functions.contracts import CONTRACT_SE, get_contract
    contract = get_contract("SE")

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

from typing import Any

from .types import (
    AbstractPattern,
    ExternalJudgment,
    HardLimit,
    HypothesisSet,
    InternalModel,
    InternalValue,
    OperatorContract,
    PerceptualFact,
    RelationalValue,
    SubjectiveImpression,
    SuccessCriterion,
)


# ---------------------------------------------------------------------------
# Helpers de vérification (pur Python, sans LLM)
# ---------------------------------------------------------------------------

def _confidence_in_range(result: Any) -> bool:
    """La confiance doit être dans [0.0, 1.0]."""
    c = getattr(result, "confidence", None)
    if c is None:
        return True  # champ optionnel selon l'opérateur
    return 0.0 <= float(c) <= 1.0


def _no_judgment_in_perception(result: PerceptualFact) -> bool:
    """SE / SI ne doivent pas contenir de champ 'accepted', 'rejected', ou 'principle'."""
    d = result.to_dict()
    forbidden = {"accepted", "rejected", "principle", "consistency_score"}
    return not (forbidden & set(d.keys()))


def _assimilation_weight_bounded(result: SubjectiveImpression) -> bool:
    """Le poids d'assimilation SI ne doit pas dépasser SI_BIAS_MAX=0.95."""
    return result.assimilation_weight <= 0.95


def _hypothesis_count_bounded(result: HypothesisSet) -> bool:
    """NE ne doit pas produire plus de NE_TOP_K=5 hypothèses."""
    return len(result.candidates) <= 5


def _all_plausibilities_in_range(result: HypothesisSet) -> bool:
    """Toutes les plausibilités NE doivent être dans [0.0, 1.0]."""
    return all(0.0 <= h.plausibility <= 1.0 for h in result.candidates)


def _ni_confidence_reduced_without_anchor(result: AbstractPattern) -> bool:
    """Si NI n'a pas de pattern ancré, la confiance doit être < 0.5."""
    # Heuristique : si source_ref est vide, c'est une synthèse sans ancrage
    if not result.source_ref:
        return result.confidence < 0.5
    return True


def _te_criteria_not_empty(result: ExternalJudgment) -> bool:
    """TE doit toujours utiliser au moins un critère externe."""
    return len(result.criteria_used) > 0


def _ti_revision_count_bounded(result: InternalModel) -> bool:
    """TI ne doit pas dépasser TI_MAX_REVISIONS=5 révisions."""
    return result.revision_count <= 5


def _fe_acceptability_in_range(result: RelationalValue) -> bool:
    """FE doit produire une acceptabilité dans [0.0, 1.0]."""
    return 0.0 <= result.acceptability <= 1.0


def _fi_invariants_respected(result: InternalValue) -> bool:
    """FI doit signaler expression_needed si congruence < FI_EXPRESSION_THRESHOLD=0.3."""
    if result.congruence < 0.3:
        return result.expression_needed
    return True


# ---------------------------------------------------------------------------
# Définition des 8 contrats
# ---------------------------------------------------------------------------

CONTRACT_SE = OperatorContract(
    operator_id="SE",
    operation="Détecter les caractéristiques présentes et les changements observables dans le stimulus.",
    mechanism="Extraction heuristique de propriétés concrètes (texte/JSON/événement) + calcul de "
              "score de confiance par type de source. Aucun LLM externe.",
    output_type="PerceptualFact",
    hard_limits=[
        HardLimit(
            name="no_judgment",
            description="SE ne produit pas de jugement de valeur ni de signification.",
            check_fn=_no_judgment_in_perception,
        ),
        HardLimit(
            name="confidence_in_range",
            description="confidence doit être dans [0.0, 1.0].",
            check_fn=_confidence_in_range,
        ),
    ],
    traceability=["source_type", "detection_step", "confidence_computation"],
    success_criteria=[
        SuccessCriterion(
            name="detection_rate",
            description="Ratio stimuli non-None détectés comme exists=True.",
            evaluate_fn=lambda r: 1.0 if (r.exists and r.confidence > 0) else 0.0,
        ),
        SuccessCriterion(
            name="properties_non_empty",
            description="Les propriétés extraites doivent contenir au moins 1 clé.",
            evaluate_fn=lambda r: 1.0 if len(r.properties) > 0 else 0.0,
        ),
    ],
)

CONTRACT_SI = OperatorContract(
    operator_id="SI",
    operation="Comparer l'expérience présente avec les représentations conservées d'expériences antérieures.",
    mechanism="Vectorisation 8D du PerceptualFact + similarité cosinus avec banque de mémoire épisodique "
              "in-memory. Poids d'assimilation borné par SI_BIAS_MAX=0.95.",
    output_type="SubjectiveImpression",
    hard_limits=[
        HardLimit(
            name="assimilation_weight_bounded",
            description="assimilation_weight ne doit pas dépasser SI_BIAS_MAX=0.95.",
            check_fn=_assimilation_weight_bounded,
        ),
    ],
    traceability=["fact_ref", "closest_memory_ref", "similarity_score", "assimilation_weight"],
    success_criteria=[
        SuccessCriterion(
            name="similarity_computed",
            description="similarity doit être dans [0.0, 1.0].",
            evaluate_fn=lambda r: 1.0 if 0.0 <= r.similarity <= 1.0 else 0.0,
        ),
    ],
)

CONTRACT_NE = OperatorContract(
    operator_id="NE",
    operation="Générer de nouvelles associations et plusieurs prolongements possibles depuis le stimulus.",
    mechanism="Expansion BFS bornée (max_depth=3, top_k=5) dans le graphe de connaissances. "
              "Scoring de plausibilité par co-occurrence apprise. Sans LLM externe.",
    output_type="HypothesisSet",
    hard_limits=[
        HardLimit(
            name="hypothesis_count_bounded",
            description="NE ne produit pas plus de NE_TOP_K=5 hypothèses.",
            check_fn=_hypothesis_count_bounded,
        ),
        HardLimit(
            name="plausibilities_in_range",
            description="Toutes les plausibilités doivent être dans [0.0, 1.0].",
            check_fn=_all_plausibilities_in_range,
        ),
    ],
    traceability=["seed_concepts", "bfs_depth", "candidates_before_filter", "top_k_selected"],
    success_criteria=[
        SuccessCriterion(
            name="expansion_attempted",
            description="expansion_depth > 0 si le PerceptualFact existe.",
            evaluate_fn=lambda r: 1.0 if r.expansion_depth > 0 else 0.5,
        ),
    ],
)

CONTRACT_NI = OperatorContract(
    operator_id="NI",
    operation="Construire une interprétation synthétique en recherchant les structures sous-jacentes.",
    mechanism="Activation des patterns latents par similarité cosinus (vecteur 16D déterministe "
              "par hachage SHA-256). Intégration exponentielle de l'état interne (alpha=0.3).",
    output_type="AbstractPattern",
    hard_limits=[
        HardLimit(
            name="confidence_reduced_without_anchor",
            description="Sans pattern ancré (source_ref vide), la confiance doit être < 0.5.",
            check_fn=_ni_confidence_reduced_without_anchor,
        ),
        HardLimit(
            name="confidence_in_range",
            description="confidence doit être dans [0.0, 1.0].",
            check_fn=_confidence_in_range,
        ),
    ],
    traceability=["best_pattern_ref", "best_similarity", "internal_state_updated", "symbol_generated"],
    success_criteria=[
        SuccessCriterion(
            name="symbol_non_empty",
            description="Le symbole produit doit être non vide.",
            evaluate_fn=lambda r: 1.0 if len(r.symbol) > 0 else 0.0,
        ),
    ],
)

CONTRACT_TE = OperatorContract(
    operator_id="TE",
    operation="Organiser les informations et actions à partir de critères explicites et résultats vérifiables.",
    mechanism="Filtrage des hypothèses NE par scoring de cohérence externe (base de faits vérifiés + "
              "critères objectifs). Seuil d'acceptation TE_ACCEPTANCE_THRESHOLD=0.6.",
    output_type="ExternalJudgment",
    hard_limits=[
        HardLimit(
            name="criteria_not_empty",
            description="TE doit utiliser au moins un critère externe.",
            check_fn=_te_criteria_not_empty,
        ),
        HardLimit(
            name="confidence_in_range",
            description="confidence doit être dans [0.0, 1.0].",
            check_fn=_confidence_in_range,
        ),
    ],
    traceability=["criteria_used", "accepted_concepts", "rejected_concepts", "scoring_method"],
    success_criteria=[
        SuccessCriterion(
            name="judgment_produced",
            description="Au moins une décision accepted ou rejected est produite.",
            evaluate_fn=lambda r: 1.0 if (r.accepted or r.rejected) else 0.0,
        ),
    ],
)

CONTRACT_TI = OperatorContract(
    operator_id="TI",
    operation="Analyser la structure interne d'un problème pour vérifier la cohérence logique.",
    mechanism="Construction du principe unificateur par détection des contradictions + révision "
              "itérative (max 5 révisions). Calcul de score de cohérence interne.",
    output_type="InternalModel",
    hard_limits=[
        HardLimit(
            name="revision_count_bounded",
            description="revision_count ne doit pas dépasser TI_MAX_REVISIONS=5.",
            check_fn=_ti_revision_count_bounded,
        ),
        HardLimit(
            name="consistency_in_range",
            description="consistency_score doit être dans [0.0, 1.0].",
            check_fn=lambda r: 0.0 <= r.consistency_score <= 1.0,
        ),
    ],
    traceability=["contradictions_detected", "revision_count", "principle_built", "candidates_after_revision"],
    success_criteria=[
        SuccessCriterion(
            name="principle_non_trivial",
            description="Le principe ne doit pas être 'no_hypothesis' si des candidats existent.",
            evaluate_fn=lambda r: 0.0 if r.principle == "no_hypothesis" else 1.0,
        ),
    ],
)

CONTRACT_FE = OperatorContract(
    operator_id="FE",
    operation="Évaluer en fonction des valeurs interpersonnelles et des conséquences sur les relations.",
    mechanism="Scoring par normes collectives pondérées (registre CollectiveValueRegistry). "
              "Détection des normes périmées (staleness > 1000 cycles). Parties affectées listées.",
    output_type="RelationalValue",
    hard_limits=[
        HardLimit(
            name="acceptability_in_range",
            description="acceptability doit être dans [0.0, 1.0].",
            check_fn=_fe_acceptability_in_range,
        ),
    ],
    traceability=["norms_used", "stale_norms_detected", "affected_parties", "scoring_method"],
    success_criteria=[
        SuccessCriterion(
            name="parties_identified",
            description="Au moins une partie affectée est identifiée.",
            evaluate_fn=lambda r: 1.0 if len(r.affected_parties) > 0 else 0.0,
        ),
    ],
)

CONTRACT_FI = OperatorContract(
    operator_id="FI",
    operation="Évaluer au regard des valeurs personnelles et internes configurées explicitement.",
    mechanism="Projection de l'action sur le registre de valeurs internes (InternalValueRegistry). "
              "Calcul de congruence pondérée. Signal expression_needed si congruence < 0.3.",
    output_type="InternalValue",
    hard_limits=[
        HardLimit(
            name="fi_invariants",
            description="expression_needed=True si congruence < FI_EXPRESSION_THRESHOLD=0.3.",
            check_fn=_fi_invariants_respected,
        ),
    ],
    traceability=["values_evaluated", "violation_notes", "congruence_score", "conviction_level"],
    success_criteria=[
        SuccessCriterion(
            name="invariants_protected",
            description="Les invariants v:certified_false et v:no_wipe doivent retourner 0.0 si violés.",
            evaluate_fn=lambda r: 1.0 if not ("EXPRESSION_NEEDED" in r.notes and "v:certified_false" not in r.notes) else 0.8,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Registre global
# ---------------------------------------------------------------------------

_ALL_CONTRACTS: dict[str, OperatorContract] = {
    "SE": CONTRACT_SE,
    "SI": CONTRACT_SI,
    "NE": CONTRACT_NE,
    "NI": CONTRACT_NI,
    "TE": CONTRACT_TE,
    "TI": CONTRACT_TI,
    "FE": CONTRACT_FE,
    "FI": CONTRACT_FI,
}


def get_contract(operator_id: str) -> OperatorContract:
    """Retourner le contrat d'un opérateur par son identifiant."""
    contract = _ALL_CONTRACTS.get(operator_id.upper())
    if contract is None:
        raise ValueError(f"Contrat inconnu pour l'opérateur : {operator_id!r}")
    return contract


def all_contracts() -> dict[str, OperatorContract]:
    """Retourner tous les contrats des 8 opérateurs."""
    return dict(_ALL_CONTRACTS)
