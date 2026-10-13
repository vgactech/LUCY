"""
sensation_in.py — SI : Sensation Introvertie

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / sensation_in
Auteur : LuCY Project

Question de départ : Comment cette expérience concrète est-elle assimilée intérieurement ?

Nature : Perception
Orientation : Facteur subjectif — impression intérieure
Limite : peut sur-pondérer l'impression — garde-fou SI_BIAS_MAX

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any

from .types import PerceptualFact, SubjectiveImpression

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SI_BIAS_MAX: float = 0.95       # poids d'assimilation maximal autorisé
SIMILARITY_FLOOR: float = 0.0   # similarité minimale


# ---------------------------------------------------------------------------
# Fonctions d'aide
# ---------------------------------------------------------------------------

def _vectorize_fact(fact: PerceptualFact) -> list[float]:
    """Convertir un PerceptualFact en vecteur numérique simple.

    Vecteur à 8 dimensions :
    0 : exists (0/1)
    1 : confidence
    2 : log(1 + length_chars) normalisé
    3 : length_words / 100 (plafonné à 1.0)
    4 : sentence_count / 10 (plafonné à 1.0)
    5 : has_question (0/1)
    6 : has_negation (0/1)
    7 : type encodé (text=0.5, json=1.0, event=0.7, none=0.0)
    """
    p = fact.properties
    type_enc = {"text": 0.5, "json": 1.0, "event": 0.7, "none": 0.0, "empty": 0.0}

    v = [
        1.0 if fact.exists else 0.0,
        float(fact.confidence),
        min(math.log1p(p.get("length_chars", 0)) / 10.0, 1.0),
        min(p.get("length_words", 0) / 100.0, 1.0),
        min(p.get("sentence_count", 0) / 10.0, 1.0),
        1.0 if p.get("has_question") else 0.0,
        1.0 if p.get("has_negation") else 0.0,
        type_enc.get(p.get("type", "none"), 0.3),
    ]
    return v


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Similarité cosinus entre deux vecteurs de même dimension."""
    if len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


def _fact_ref(fact: PerceptualFact) -> str:
    """Référence courte d'un PerceptualFact."""
    return fact.raw_input_hash or ("sha256:" + hashlib.sha256(
        json.dumps(fact.to_dict(), sort_keys=True, default=str).encode()
    ).hexdigest()[:16])


# ---------------------------------------------------------------------------
# Opérateur SI principal
# ---------------------------------------------------------------------------

class SensationIntrovertie:
    """SI — Assimilation subjective d'une expérience concrète.

    Transformations :
    1. Comparaison vectorielle du PerceptualFact entrant avec les expériences mémorisées
    2. Calcul de similarité cosinus (embedding 8D)
    3. Pondération par poids d'assimilation appris (garde-fou SI_BIAS_MAX)
    """

    def __init__(self) -> None:
        # Banque d'expériences mémorisées (vecteurs) — alimentation externe via mémoire épisodique
        self._memory_vectors: list[tuple[str, list[float]]] = []
        self._assimilation_weight: float = 0.7  # poids appris, modifiable par learning

    def add_memory(self, ref: str, vector: list[float]) -> None:
        """Ajouter une expérience mémorisée (vecteur 8D)."""
        self._memory_vectors.append((ref, vector))

    def load_episodic_facts(self, facts: list[PerceptualFact]) -> None:
        """Charger des PerceptualFacts depuis la mémoire épisodique."""
        for fact in facts:
            vec = _vectorize_fact(fact)
            ref = _fact_ref(fact)
            self._memory_vectors.append((ref, vec))

    def process(self, fact: PerceptualFact) -> SubjectiveImpression:
        """Assimiler un PerceptualFact et produire une SubjectiveImpression.

        Args:
            fact: sortie de SE

        Returns:
            SubjectiveImpression — comment cette expérience est intériorisée
        """
        t_start = time.time_ns()
        fact_vec = _vectorize_fact(fact)
        ref = _fact_ref(fact)

        notes: list[str] = []

        # --- Étape 1 : comparaison avec mémoire épisodique ---
        if not self._memory_vectors:
            # Aucun souvenir — première expérience
            similarity = 0.0
            notes.append("first_experience_no_memory")
        else:
            similarities = [
                _cosine_similarity(fact_vec, mem_vec)
                for _, mem_vec in self._memory_vectors
            ]
            similarity = max(similarities)
            best_idx = similarities.index(similarity)
            best_ref = self._memory_vectors[best_idx][0]
            notes.append(f"closest_memory={best_ref}")

            if similarity > 0.9:
                notes.append("very_familiar_experience")
            elif similarity < 0.2:
                notes.append("novel_experience")

        # --- Étape 2 : pondération par poids d'assimilation ---
        # Garde-fou : le poids ne peut pas dépasser SI_BIAS_MAX
        weight = min(self._assimilation_weight, SI_BIAS_MAX)

        # Modulation : expériences très familières pèsent plus
        modulated_weight = weight * (0.8 + 0.2 * similarity)
        modulated_weight = min(modulated_weight, SI_BIAS_MAX)

        if modulated_weight > 0.85:
            notes.append("high_assimilation_weight_warning")

        return SubjectiveImpression(
            fact_ref=ref,
            similarity=round(similarity, 4),
            assimilation_weight=round(modulated_weight, 4),
            notes=notes,
            ts_ns=t_start,
        )

    def update_assimilation_weight(self, delta: float) -> None:
        """Mise à jour du poids d'assimilation par le mécanisme d'apprentissage."""
        new_weight = self._assimilation_weight + delta
        self._assimilation_weight = max(0.1, min(new_weight, SI_BIAS_MAX))
