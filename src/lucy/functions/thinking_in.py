"""
thinking_in.py — TI : Pensée Introvertie

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / thinking_in
Auteur : LuCY Project

Question de départ : Quel modèle ou principe explique la situation ?

Nature : Jugement
Orientation : Cohérence intellectuelle interne, modèle subjectif
Limite : modèle cohérent en interne peut être faux — confronter à SE/NE

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from typing import Any

from .contracts import CONTRACT_TI
from .types import HypothesisSet, InternalModel, OperatorTrace

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TI_CONSISTENCY_THRESHOLD: float = 0.5   # seuil pour considérer un modèle cohérent
TI_MAX_REVISIONS: int = 5               # nombre maximal de révisions par cycle


# ---------------------------------------------------------------------------
# Moteur de cohérence interne
# ---------------------------------------------------------------------------

class InternalModelStore:
    """Stockage des modèles causaux internes de TI."""

    def __init__(self) -> None:
        self._models: dict[str, InternalModel] = {}

    def get(self, key: str) -> InternalModel | None:
        return self._models.get(key)

    def store(self, key: str, model: InternalModel) -> None:
        self._models[key] = model

    def all_models(self) -> list[InternalModel]:
        return list(self._models.values())


def _detect_contradictions(candidates: list[str], known_contradictions: dict[str, list[str]]) -> list[str]:
    """Détecter les contradictions entre concepts candidats.

    known_contradictions: {concept_a: [concept_b, ...]} — paires incompatibles
    """
    found: list[str] = []
    candidate_set = set(candidates)
    for concept in candidates:
        opposites = known_contradictions.get(concept, [])
        for opp in opposites:
            if opp in candidate_set:
                pair = f"{concept}⊥{opp}"
                rev_pair = f"{opp}⊥{concept}"
                if pair not in found and rev_pair not in found:
                    found.append(pair)
    return found


def _build_principle(candidates: list[str], consistency: float) -> str:
    """Construire une formulation du principe unificateur."""
    if not candidates:
        return "no_candidates"
    if len(candidates) == 1:
        return f"singular:{candidates[0]}"
    # Recherche d'un thème commun basique (préfixe partagé)
    common_prefix = _longest_common_prefix(candidates)
    if len(common_prefix) >= 3:
        return f"pattern:{common_prefix}*"
    return f"group:{'+'.join(sorted(candidates)[:3])}"


def _longest_common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def _compute_consistency(
    candidates: list[str],
    contradictions: list[str],
    base_plausibilities: dict[str, float],
) -> float:
    """Calculer un score de cohérence interne [0.0 – 1.0]."""
    if not candidates:
        return 0.0

    # Pénalité par contradiction détectée
    contradiction_penalty = len(contradictions) * 0.2

    # Score moyen de plausibilité des candidats
    avg_plausibility = (
        sum(base_plausibilities.get(c, 0.5) for c in candidates) / len(candidates)
    )

    consistency = avg_plausibility - contradiction_penalty
    return round(max(0.0, min(1.0, consistency)), 4)


# ---------------------------------------------------------------------------
# Opérateur TI principal
# ---------------------------------------------------------------------------

class PenseeIntrovertie:
    """TI — Construction d'un modèle causal minimal cohérent en interne.

    Phase 2 : contrat opérationnel formel intégré (CONTRACT_TI).
    Transformations :
    1. Construction du modèle causal minimal (principe unificateur)
    2. Test de cohérence interne (contradiction ? circularité ?)
    3. Révision du modèle si contradiction détectée
    4. Vérification des limites du contrat + génération OperatorTrace
    """

    def __init__(self, model_store: InternalModelStore | None = None) -> None:
        self.model_store = model_store or InternalModelStore()
        # Paires de concepts connus comme contradictoires
        self._known_contradictions: dict[str, list[str]] = {
            "query": ["assertion"],
            "negation": ["affirmation"],
            "known": ["unknown"],
            "true": ["false"],
        }
        self.contract = CONTRACT_TI

    def add_contradiction(self, concept_a: str, concept_b: str) -> None:
        """Enregistrer une paire contradictoire (apprissage)."""
        self._known_contradictions.setdefault(concept_a, []).append(concept_b)
        self._known_contradictions.setdefault(concept_b, []).append(concept_a)

    def process(self, hypothesis_set: HypothesisSet, cycle_ref: str = "") -> InternalModel:
        """Construire un modèle causal interne à partir des hypothèses.

        Args:
            hypothesis_set : sortie de NE
            cycle_ref      : identifiant du cycle appelant (traçabilité Phase 2).

        Returns:
            InternalModel — principe + score de cohérence + contradictions.
            Le champ `trace` contient la traçabilité complète.
        """
        t_start = time.time_ns()
        input_hash = hypothesis_set.trace.input_hash if hypothesis_set.trace else ""

        trace = OperatorTrace(
            operator_id="TI",
            cycle_ref=cycle_ref,
            input_hash=input_hash,
        )

        if not hypothesis_set.candidates:
            trace.intermediate_steps.append("model:no_candidates")
            result = InternalModel(
                principle="no_hypothesis",
                consistency_score=0.0,
                revision_count=0,
                contradictions=[],
                ts_ns=t_start,
                trace=trace,
            )
            result, trace = self.contract.finalize_trace(result, trace, t_start)
            return result

        candidates = [h.concept for h in hypothesis_set.candidates]
        plausibilities = {h.concept: h.plausibility for h in hypothesis_set.candidates}

        # --- Étape 1 : détection des contradictions ---
        contradictions = _detect_contradictions(candidates, self._known_contradictions)
        trace.intermediate_steps.append(f"contradictions_detected:{contradictions}")

        revision_count = 0

        # --- Étape 2 : révision itérative pour résoudre les contradictions ---
        while contradictions and revision_count < TI_MAX_REVISIONS:
            # Supprimer le concept le moins plausible dans chaque paire contradictoire
            to_remove: set[str] = set()
            for pair in contradictions:
                parts = pair.split("⊥")
                if len(parts) == 2:
                    a, b = parts
                    worse = a if plausibilities.get(a, 0) < plausibilities.get(b, 0) else b
                    to_remove.add(worse)

            candidates = [c for c in candidates if c not in to_remove]
            plausibilities = {k: v for k, v in plausibilities.items() if k not in to_remove}
            contradictions = _detect_contradictions(candidates, self._known_contradictions)
            revision_count += 1

        trace.intermediate_steps.append(f"revision_count:{revision_count}")

        # --- Étape 3 : construction du principe unificateur ---
        consistency = _compute_consistency(candidates, contradictions, plausibilities)
        principle = _build_principle(candidates, consistency)
        trace.intermediate_steps.append(f"principle_built:{principle}")
        trace.intermediate_steps.append(f"candidates_after_revision:{candidates}")

        model = InternalModel(
            principle=principle,
            consistency_score=consistency,
            revision_count=revision_count,
            contradictions=contradictions,
            ts_ns=t_start,
            trace=trace,
        )

        # --- Phase 3 (P0-A) : vérification du contrat via finalize_trace ---
        model, trace = self.contract.finalize_trace(model, trace, t_start)

        # Mémoriser le modèle
        self.model_store.store(principle, model)
        return model
