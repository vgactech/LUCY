"""
feeling_in.py — FI : Sentiment Introverti

Projet : LuCY (Language Unit for Cognitive Yield)
Module : functions / feeling_in
Auteur : LuCY Project

Question de départ : Quelle valeur cette situation possède-t-elle selon mes critères profonds ?

Nature : Jugement
Orientation : Valeurs intérieures profondes
Limite : jugement peut rester silencieux — mécanisme d'explicitation requis

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from .contracts import CONTRACT_FI
from .types import InternalValue, OperatorTrace

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FI_EXPRESSION_THRESHOLD: float = 0.3  # en dessous → expression_needed=True (alerte)
FI_CONVICTION_MIN: float = 0.2


# ---------------------------------------------------------------------------
# Registre de valeurs internes
# ---------------------------------------------------------------------------

@dataclass
class InternalValueEntry:
    """Une valeur interne dans le registre FI."""
    value_id: str
    description: str
    weight: float = 1.0         # importance [0.0 – 2.0]
    stability: float = 0.9      # stabilité inter-sessions [0.0 – 1.0]


class InternalValueRegistry:
    """Registre des valeurs internes profondes pour FI.

    Ces valeurs sont apprises et mises à jour par le mécanisme d'apprentissage.
    Elles représentent les convictions profondes du système.
    """

    def __init__(self) -> None:
        self._values: dict[str, InternalValueEntry] = {}
        self._decision_history: list[dict] = []  # historique des décisions FI

        # Valeurs fondatrices par défaut
        self.add_value("v:truthfulness", "Statements must be accurate and verifiable", weight=1.5)
        self.add_value("v:consistency", "Behavior must be consistent across similar contexts", weight=1.2)
        self.add_value("v:certified_false", "certified_100 must remain False without proof", weight=2.0)
        self.add_value("v:no_wipe", "Forensic logs must never be deleted", weight=2.0)

    def add_value(self, value_id: str, description: str, weight: float = 1.0) -> None:
        self._values[value_id] = InternalValueEntry(
            value_id=value_id,
            description=description,
            weight=weight,
        )

    def all_values(self) -> list[InternalValueEntry]:
        return list(self._values.values())

    def record_decision(self, action: str, congruence: float) -> None:
        """Mémoriser une décision passée (historique FI)."""
        self._decision_history.append({
            "action": action,
            "congruence": congruence,
            "ts_ns": time.time_ns(),
        })
        # Garder les 100 dernières décisions
        if len(self._decision_history) > 100:
            self._decision_history = self._decision_history[-100:]

    def average_past_congruence(self) -> float:
        """Congruence moyenne sur les décisions passées."""
        if not self._decision_history:
            return 0.5
        return round(
            sum(d["congruence"] for d in self._decision_history) / len(self._decision_history),
            4,
        )


# ---------------------------------------------------------------------------
# Opérateur FI principal
# ---------------------------------------------------------------------------

class SentimentIntroverti:
    """FI — Évaluation par les valeurs internes profondes.

    Phase 2 : contrat opérationnel formel intégré (CONTRACT_FI).
    Transformations :
    1. Projection de l'action sur les valeurs internes (distance dans l'espace des valeurs)
    2. Évaluation de conformité aux convictions profondes
    3. Génération du signal d'acceptabilité intime (+ explicitation si nécessaire)
    4. Vérification des limites du contrat + génération OperatorTrace
    """

    def __init__(self, registry: InternalValueRegistry | None = None) -> None:
        self.registry = registry or InternalValueRegistry()
        self.contract = CONTRACT_FI

    def process(self, action_candidate: str, context: dict | None = None, cycle_ref: str = "") -> InternalValue:
        """Évaluer une action candidate par rapport aux valeurs internes.

        Args:
            action_candidate : description de l'action (str)
            context          : contexte optionnel (jugements précédents)
            cycle_ref        : identifiant du cycle appelant (traçabilité Phase 2).

        Returns:
            InternalValue — congruence, conviction, signal d'expression.
            Le champ `trace` contient la traçabilité complète.
        """
        t_start = time.time_ns()
        ctx = context or {}

        import hashlib
        import json
        input_hash = "sha256:" + hashlib.sha256(
            json.dumps(action_candidate, default=str).encode()
        ).hexdigest()[:16]

        trace = OperatorTrace(
            operator_id="FI",
            cycle_ref=cycle_ref,
            input_hash=input_hash,
        )

        values = self.registry.all_values()
        if not values:
            result = InternalValue(
                congruence=0.5,
                conviction_level=FI_CONVICTION_MIN,
                expression_needed=False,
                notes="no_internal_values_loaded",
                ts_ns=t_start,
                trace=trace,
            )
            trace.intermediate_steps.append("values_evaluated:none")
            # P0-A : finalize_trace gère limits + traceability + criteria
            result, trace = self.contract.finalize_trace(result, trace, t_start)
            return result

        # --- Étape 1 : évaluation par chaque valeur interne ---
        congruence_scores: list[float] = []
        violation_notes: list[str] = []

        for val in values:
            score = self._evaluate_against_value(action_candidate, val, ctx)
            congruence_scores.append(score * val.weight)
            if score < 0.4:
                violation_notes.append(f"low_congruence:{val.value_id}={round(score, 3)}")

        trace.intermediate_steps.append(f"values_evaluated:{[v.value_id for v in values]}")
        trace.intermediate_steps.append(f"violation_notes:{violation_notes}")

        # --- Étape 2 : calcul de la congruence globale ---
        total_weight = sum(v.weight for v in values)
        congruence = (
            sum(congruence_scores) / total_weight
            if total_weight > 0 else 0.5
        )
        congruence = round(max(0.0, min(1.0, congruence)), 4)

        # Conviction : stabilité par rapport à l'historique
        past_avg = self.registry.average_past_congruence()
        deviation = abs(congruence - past_avg)
        conviction_level = round(max(FI_CONVICTION_MIN, 1.0 - deviation), 4)

        trace.intermediate_steps.append(f"congruence_score:{congruence:.4f}")
        trace.intermediate_steps.append(f"conviction_level:{conviction_level:.4f}")

        # --- Étape 3 : signal d'expression ---
        expression_needed = congruence < FI_EXPRESSION_THRESHOLD

        notes = "; ".join(violation_notes) if violation_notes else "all_values_satisfied"
        if expression_needed:
            notes = f"EXPRESSION_NEEDED|{notes}"

        # Mémorisation
        self.registry.record_decision(action_candidate, congruence)

        result = InternalValue(
            congruence=congruence,
            conviction_level=conviction_level,
            expression_needed=expression_needed,
            notes=notes,
            ts_ns=t_start,
            trace=trace,
        )

        # --- Phase 3 (P0-A) : vérification du contrat via finalize_trace ---
        result, trace = self.contract.finalize_trace(result, trace, t_start)

        return result

    def _evaluate_against_value(
        self,
        action: str,
        val: InternalValueEntry,
        ctx: dict,
    ) -> float:
        """Évaluer la congruence d'une action avec une valeur interne.

        Règles basées sur des heuristiques lexicales et contextuelles.
        Sans LLM : heuristiques déterministes appliquées au texte.
        """
        action_lower = action.lower()

        # Invariants absolus ARTCB / LuCY
        if val.value_id == "v:certified_false":
            if "certified_100=true" in action_lower or "certify" in action_lower:
                return 0.0
            return 1.0

        if val.value_id == "v:no_wipe":
            # P0-B : liste étendue aux synonymes pour éviter les contournements lexicaux
            _no_wipe_keywords = (
                "wipe",
                "truncate",
                "delete_log",
                "clear_forensic",
                "remove_forensic",
                "destroy_log",
                "erase_log",
                "purge_log",
                "reset_forensic",
                "drop_forensic",
                "flush_forensic",
                "overwrite_log",
            )
            if any(w in action_lower for w in _no_wipe_keywords):
                return 0.0
            return 1.0

        if val.value_id == "v:truthfulness":
            # Pénalité si l'action contient des marqueurs d'invention
            if any(w in action_lower for w in ("invent", "fake", "fabricate", "mock")):
                return 0.1
            return 0.85

        if val.value_id == "v:consistency":
            # Cohérence : si le contexte contient un jugement précédent contradictoire
            prior = ctx.get("prior_action", "")
            if prior and prior.lower() == action_lower:
                return 1.0  # même action = cohérent
            return 0.75

        # Valeur générique
        return 0.7

    def update_value_weight(self, value_id: str, delta: float) -> None:
        """Mise à jour du poids d'une valeur interne par le learning."""
        val = self.registry._values.get(value_id)
        if val:
            val.weight = round(max(0.1, min(val.weight + delta, 2.0)), 4)
