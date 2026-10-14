"""
sensation_ex.py — SE : Sensation Extravertie

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / sensation_ex
Auteur : LuCY Project

Phase 2 — Contrat opérationnel formel :
  Opération  : Détecter les caractéristiques présentes et les changements observables.
  Mécanisme  : Extraction heuristique de propriétés concrètes (texte/JSON/événement) +
               score de confiance par type de source. Aucun LLM externe.
  Sortie     : PerceptualFact (exists, properties, confidence, trace)
  Limites    : ne juge pas la valeur ni la signification — constate l'existence.
               confidence TOUJOURS dans [0.0, 1.0].
  Traçabilité: source_type, detection_step, confidence_computation dans OperatorTrace.
  Critères   : detection_rate + properties_non_empty (voir CONTRACT_SE).

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from .contracts import CONTRACT_SE
from .types import OperatorTrace, PerceptualFact

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DETECTION_THRESHOLD: float = float(os.environ.get("LUCY_SE_THRESHOLD", "0.3"))
MAX_PROPERTIES: int = 32
SI_BIAS_MAX: float = 0.95  # garde-fou partagé

# Poids de confiance par type de source
_SOURCE_CONFIDENCE: dict[str, float] = {
    "text":  0.75,
    "json":  0.90,
    "event": 0.85,
    "empty": 0.0,
}


# ---------------------------------------------------------------------------
# Fonctions d'aide
# ---------------------------------------------------------------------------

def _hash_input(raw: Any) -> str:
    """Hash SHA-256 court de l'entrée."""
    serialized = json.dumps(raw, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(serialized).hexdigest()[:16]


def _extract_text_properties(text: str) -> dict[str, Any]:
    """Extraire les propriétés observables d'un texte brut."""
    words = re.findall(r"\b\w+\b", text)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    props: dict[str, Any] = {
        "type": "text",
        "length_chars": len(text),
        "length_words": len(words),
        "sentence_count": len(sentences),
        "has_question": "?" in text,
        "has_negation": bool(re.search(r"\b(no|not|never|aucun|jamais|non|pas)\b",
                                       text, re.IGNORECASE)),
        "language_hint": _detect_language_hint(text),
        "first_token": words[0].lower() if words else "",
        "dominant_pos": _dominant_pos_hint(words),
    }
    return props


def _extract_json_properties(data: dict) -> dict[str, Any]:
    """Extraire les propriétés observables d'un objet JSON."""
    props: dict[str, Any] = {
        "type": "json",
        "key_count": len(data),
        "keys": list(data.keys())[:MAX_PROPERTIES],
        "has_numeric": any(isinstance(v, (int, float)) for v in data.values()),
        "has_nested": any(isinstance(v, (dict, list)) for v in data.values()),
        "depth": _json_depth(data),
    }
    return props


def _detect_language_hint(text: str) -> str:
    """Détection légère de la langue (heuristique sans LLM)."""
    fr_markers = re.findall(
        r"\b(le|la|les|un|une|des|est|sont|dans|avec|pour|sur|par|que|qui)\b",
        text, re.IGNORECASE
    )
    en_markers = re.findall(
        r"\b(the|is|are|was|were|with|for|from|this|that|have|has)\b",
        text, re.IGNORECASE
    )
    if len(fr_markers) > len(en_markers):
        return "fr"
    if len(en_markers) > len(fr_markers):
        return "en"
    return "unknown"


def _dominant_pos_hint(words: list[str]) -> str:
    """Estimation très grossière de la catégorie grammaticale dominante."""
    if not words:
        return "empty"
    avg_len = sum(len(w) for w in words) / len(words)
    if avg_len < 4:
        return "function_words"
    if avg_len > 7:
        return "content_words"
    return "mixed"


def _json_depth(obj: Any, _d: int = 0) -> int:
    """Profondeur max d'un objet JSON."""
    if _d > 8:  # borne anti-récursion infinie
        return _d
    if isinstance(obj, dict):
        if not obj:
            return _d
        return max(_json_depth(v, _d + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return _d
        return max(_json_depth(item, _d + 1) for item in obj)
    return _d


def _compute_confidence(source_type: str, data: Any) -> float:
    """Calcul du score de confiance SE basé sur la source et la richesse."""
    base = _SOURCE_CONFIDENCE.get(source_type, 0.5)

    # Pénalité si données vides
    if data is None or (isinstance(data, (str, dict, list)) and len(data) == 0):
        return 0.0

    # Bonus si données riches
    if isinstance(data, dict) and len(data) > 5:
        base = min(base + 0.05, 1.0)
    if isinstance(data, str) and len(data) > 100:
        base = min(base + 0.03, 1.0)

    return round(base, 4)


# ---------------------------------------------------------------------------
# Opérateur SE principal
# ---------------------------------------------------------------------------

class SensationExtravertie:
    """SE — Perception de ce qui est effectivement présent.

    Phase 2 : contrat opérationnel formel intégré (CONTRACT_SE).
    Transformations :
    1. Détection de présence (seuil DETECTION_THRESHOLD)
    2. Encodage des caractéristiques concrètes
    3. Vérification des limites du contrat + génération OperatorTrace
    4. Mise en tampon fenêtre glissante (via working memory externe)

    Ne juge pas, ne suppose pas — constate l'existence.
    """

    def __init__(self, threshold: float = DETECTION_THRESHOLD) -> None:
        self.threshold = threshold
        self._call_count: int = 0
        self.contract = CONTRACT_SE

    def process(self, stimulus: Any, cycle_ref: str = "") -> PerceptualFact:
        """Traiter un stimulus et produire un PerceptualFact.

        Args:
            stimulus  : texte brut (str), objet JSON (dict), événement horodaté (dict
                        avec clé 'ts_ns'), ou None.
            cycle_ref : identifiant du cycle appelant (traçabilité Phase 2).

        Returns:
            PerceptualFact avec exists=False si la confiance est sous le seuil.
            Le champ `trace` contient la traçabilité complète.
        """
        t_start = time.time_ns()
        self._call_count += 1
        raw_hash = _hash_input(stimulus)

        trace = OperatorTrace(
            operator_id="SE",
            cycle_ref=cycle_ref,
            input_hash=raw_hash,
        )

        # --- Étape 1 : détection de présence ---
        if stimulus is None:
            trace.intermediate_steps.append("detection_step:none_stimulus")
            trace.duration_ns = time.time_ns() - t_start
            result = PerceptualFact(
                exists=False,
                properties={"type": "none"},
                confidence=0.0,
                ts_ns=t_start,
                source="se",
                raw_input_hash=raw_hash,
                trace=trace,
            )
            # Vérification contrat
            all_ok, violated = self.contract.check_all_limits(result)
            trace.limits_checked = True
            trace.limits_violated = violated
            trace.criteria_scores = self.contract.evaluate_all_criteria(result)
            return result

        # --- Étape 2 : encodage des caractéristiques concrètes ---
        if isinstance(stimulus, str):
            source_type = "text" if stimulus.strip() else "empty"
            props = _extract_text_properties(stimulus) if stimulus.strip() else {"type": "empty"}
        elif isinstance(stimulus, dict):
            source_type = "json"
            props = _extract_json_properties(stimulus)
        else:
            # Conversion générique pour les types non anticipés
            source_type = "event"
            props = {"type": type(stimulus).__name__, "repr": str(stimulus)[:128]}

        trace.intermediate_steps.append(f"source_type:{source_type}")
        trace.intermediate_steps.append(f"detection_step:properties_extracted")

        # --- Étape 3 : calcul de la confiance ---
        confidence = _compute_confidence(source_type, stimulus)
        exists = confidence >= self.threshold
        trace.intermediate_steps.append(f"confidence_computation:{confidence:.4f}_threshold:{self.threshold}")

        result = PerceptualFact(
            exists=exists,
            properties=props,
            confidence=confidence,
            ts_ns=t_start,
            source="se",
            raw_input_hash=raw_hash,
            trace=trace,
        )

        # --- Phase 2 : vérification du contrat ---
        all_ok, violated = self.contract.check_all_limits(result)
        trace.limits_checked = True
        trace.limits_violated = violated
        trace.criteria_scores = self.contract.evaluate_all_criteria(result)
        trace.duration_ns = time.time_ns() - t_start

        return result
