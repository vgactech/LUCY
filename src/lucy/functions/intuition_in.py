"""
intuition_in.py — NI : Intuition Introvertie

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / intuition_in
Auteur : LuCY Project

Question de départ : Quelle signification ou configuration se dessine derrière l'expérience ?

Nature : Perception
Orientation : Images et significations intérieures
Limite : peut se déconnecter des faits — confrontation obligatoire avec SE

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any

from .contracts import CONTRACT_NI
from .types import AbstractPattern, OperatorTrace, PerceptualFact

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NI_VECTOR_DIM: int = 16         # dimensions du vecteur sémantique interne
NI_PATTERN_THRESHOLD: float = 0.6  # seuil pour activer un pattern latent


# ---------------------------------------------------------------------------
# Fonctions d'aide
# ---------------------------------------------------------------------------

def _text_to_vector(text: str, dim: int = NI_VECTOR_DIM) -> list[float]:
    """Convertir un texte en vecteur sémantique via hash déterministe.

    Méthode sans LLM : hashage en blocs puis normalisation L2.
    Propriété garantie : même texte → même vecteur.
    """
    if not text:
        return [0.0] * dim

    # Hachage par fenêtres glissantes de 4 caractères
    raw = text.encode("utf-8")
    vec = [0.0] * dim
    for i in range(len(raw) - 3):
        chunk = raw[i:i + 4]
        digest = hashlib.sha256(chunk).digest()
        for j in range(dim):
            byte_val = digest[j % 32]
            vec[j] += (byte_val / 255.0 - 0.5) * 2.0  # centré en 0

    # Normalisation L2
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]

    return [round(x, 6) for x in vec]


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Similarité cosinus."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (n1 * n2)))


def _symbol_from_vector(vec: list[float]) -> str:
    """Générer un symbole court depuis un vecteur (déterministe)."""
    raw = json.dumps([round(x, 3) for x in vec[:4]]).encode()
    return "NI:" + hashlib.sha256(raw).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Pattern latent
# ---------------------------------------------------------------------------

class LatentPattern:
    """Un pattern mémorisé en mémoire longue durée de NI."""

    def __init__(self, symbol: str, vector: list[float], source_ref: str = "") -> None:
        self.symbol = symbol
        self.vector = vector
        self.source_ref = source_ref
        self.activation_count: int = 0
        self.confirmed_count: int = 0  # fois confirmé par des faits SE


# ---------------------------------------------------------------------------
# Opérateur NI principal
# ---------------------------------------------------------------------------

class IntuitionIntrovertie:
    """NI — Synthèse des configurations et significations intérieures.

    Phase 2 : contrat opérationnel formel intégré (CONTRACT_NI).
    Transformations :
    1. Activation des patterns latents par similarité vectorielle
    2. Synthèse d'une représentation compressée (encodeur symbolique)
    3. Propagation à travers le graphe de sens interne
    4. Vérification des limites du contrat + génération OperatorTrace

    Confrontation avec SE obligatoire avant conclusion (garde-fou cognitif).
    """

    def __init__(self) -> None:
        self._patterns: list[LatentPattern] = []
        self._internal_state_vec: list[float] = [0.0] * NI_VECTOR_DIM
        self.contract = CONTRACT_NI

    def add_pattern(self, symbol: str, vector: list[float], source_ref: str = "") -> None:
        """Ajouter un pattern latent en mémoire longue durée."""
        self._patterns.append(LatentPattern(symbol, vector, source_ref))

    def update_internal_state(self, fact: PerceptualFact) -> None:
        """Mettre à jour l'état interne avec un nouveau fait perceptuel."""
        fact_text = json.dumps(fact.properties, sort_keys=True, default=str)
        fact_vec = _text_to_vector(fact_text)
        # Intégration exponentielle (mémoire courte vs longue)
        alpha = 0.3
        self._internal_state_vec = [
            round(alpha * fv + (1 - alpha) * sv, 6)
            for fv, sv in zip(fact_vec, self._internal_state_vec)
        ]

    def process(self, fact: PerceptualFact, cycle_ref: str = "") -> AbstractPattern:
        """Synthétiser un AbstractPattern depuis l'état interne et les patterns latents.

        Args:
            fact      : sortie de SE pour ancrage dans les faits
            cycle_ref : identifiant du cycle appelant (traçabilité Phase 2).

        Returns:
            AbstractPattern — configuration symbolique interne.
            Le champ `trace` contient la traçabilité complète.
        """
        t_start = time.time_ns()
        input_hash = fact.raw_input_hash or ""

        trace = OperatorTrace(
            operator_id="NI",
            cycle_ref=cycle_ref,
            input_hash=input_hash,
        )

        # Mise à jour de l'état interne avec le fait courant
        self.update_internal_state(fact)
        trace.intermediate_steps.append("internal_state_updated:yes")

        # --- Étape 1 : activation des patterns latents ---
        best_pattern: LatentPattern | None = None
        best_sim: float = 0.0

        for pattern in self._patterns:
            sim = _cosine_similarity(self._internal_state_vec, pattern.vector)
            if sim > best_sim:
                best_sim = sim
                best_pattern = pattern

        trace.intermediate_steps.append(f"best_similarity:{best_sim:.4f}")

        # --- Étape 2 : synthèse symbolique ---
        if best_pattern is not None and best_sim >= NI_PATTERN_THRESHOLD:
            symbol = best_pattern.symbol
            source_ref = best_pattern.source_ref
            confidence = round(best_sim * fact.confidence, 4)
            best_pattern.activation_count += 1
            trace.intermediate_steps.append(f"best_pattern_ref:{best_pattern.source_ref}")
        else:
            # Pas de pattern connu — synthèse nouvelle
            symbol = _symbol_from_vector(self._internal_state_vec)
            source_ref = fact.raw_input_hash or ""
            confidence = round(0.4 * fact.confidence, 4)  # confiance réduite sans ancrage
            trace.intermediate_steps.append("best_pattern_ref:none_new_synthesis")

        trace.intermediate_steps.append(f"symbol_generated:{symbol}")

        # --- Étape 3 : vecteur sémantique de sortie ---
        semantic_vector = list(self._internal_state_vec)

        result = AbstractPattern(
            symbol=symbol,
            confidence=confidence,
            semantic_vector=semantic_vector,
            source_ref=source_ref,
            ts_ns=t_start,
            trace=trace,
        )

        # --- Phase 3 (P0-A) : vérification du contrat via finalize_trace ---
        result, trace = self.contract.finalize_trace(result, trace, t_start)

        return result

    def confirm_pattern(self, symbol: str) -> None:
        """Incrémenter le compteur de confirmation d'un pattern (feedback SE)."""
        for p in self._patterns:
            if p.symbol == symbol:
                p.confirmed_count += 1
                break
