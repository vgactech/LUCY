"""
arbitrator.py — Coordinateur et arbitrage des 8 opérateurs LuCY

Projet : LuCY (Language Unit for Cognitive Yield)
Module : coordination / arbitrator
Auteur : LuCY Project

Politique d'arbitrage définie dans le CDC §4.3 :
- Conflit TE vs TI → priorité TE si données externes disponibles, sinon TI
- Conflit FE vs FI → log du conflit + escalade CONFLICT_PENDING
- Perception faible → bloquer NE et TE jusqu'à confirmation
- Consensus 6/8 opérateurs → action validée

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..functions.types import (
    AbstractPattern,
    ActionDecision,
    ExternalJudgment,
    HypothesisSet,
    InternalModel,
    InternalValue,
    PerceptualFact,
    RelationalValue,
    SubjectiveImpression,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONSENSUS_MIN: float = 6 / 8   # 75 % = 6 opérateurs sur 8
SE_WEAK_THRESHOLD: float = 0.3
TE_ACCEPTANCE_MIN: float = 0.5
FE_FI_CONFLICT_THRESHOLD: float = 0.3  # différence FE/FI déclenchant escalade


# ---------------------------------------------------------------------------
# Saisie d'un cycle complet
# ---------------------------------------------------------------------------

@dataclass
class CycleOutputs:
    """Sorties complètes d'un cycle cognitif — une par opérateur."""
    se_fact: PerceptualFact | None = None
    si_impression: SubjectiveImpression | None = None
    ne_hypotheses: HypothesisSet | None = None
    ni_pattern: AbstractPattern | None = None
    te_judgment: ExternalJudgment | None = None
    ti_model: InternalModel | None = None
    fe_value: RelationalValue | None = None
    fi_value: InternalValue | None = None


# ---------------------------------------------------------------------------
# Arbitrateur
# ---------------------------------------------------------------------------

class Arbitrator:
    """Arbitrage des sorties des 8 opérateurs cognitifs.

    Politique CDC §4.3 appliquée strictement.
    Jamais de wipe des conflits — toujours journalisés.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        from ..memory.procedural_memory import DEFAULT_WEIGHTS
        self._weights = weights or dict(DEFAULT_WEIGHTS)
        self._conflict_log: list[dict] = []

    def arbitrate(self, outputs: CycleOutputs) -> ActionDecision:
        """Arbitrer les sorties et produire une ActionDecision.

        Args:
            outputs: sorties complètes des 8 opérateurs

        Returns:
            ActionDecision — action finale + métadonnées de décision
        """
        t_start = time.time_ns()
        scores: dict[str, float] = {}
        conflict_detected = False
        conflict_description = ""
        action_parts: list[str] = []

        # --- Règle 1 : perception faible → bloquer NE et TE ---
        se_ok = (
            outputs.se_fact is not None
            and outputs.se_fact.exists
            and outputs.se_fact.confidence >= SE_WEAK_THRESHOLD
        )
        if not se_ok:
            scores["SE"] = 0.0
            scores["NE"] = 0.0  # bloqué
            scores["TE"] = 0.0  # bloqué
            action_parts.append("perception_weak:NE_TE_blocked")
        else:
            scores["SE"] = outputs.se_fact.confidence * self._weights.get("SE", 1.0)

        # --- SI ---
        if outputs.si_impression is not None:
            scores["SI"] = outputs.si_impression.similarity * self._weights.get("SI", 0.8)
        else:
            scores["SI"] = 0.0

        # --- NE (bloqué si perception faible) ---
        if "NE" not in scores:
            if outputs.ne_hypotheses is not None and outputs.ne_hypotheses.candidates:
                top_score = max(
                    (h.plausibility for h in outputs.ne_hypotheses.candidates), default=0.0
                )
                scores["NE"] = top_score * self._weights.get("NE", 0.9)
            else:
                scores["NE"] = 0.0

        # --- NI ---
        if outputs.ni_pattern is not None:
            scores["NI"] = outputs.ni_pattern.confidence * self._weights.get("NI", 0.7)
        else:
            scores["NI"] = 0.0

        # --- TE (bloqué si perception faible) ---
        if "TE" not in scores:
            if outputs.te_judgment is not None:
                scores["TE"] = outputs.te_judgment.confidence * self._weights.get("TE", 1.0)
            else:
                scores["TE"] = 0.0

        # --- TI ---
        if outputs.ti_model is not None:
            scores["TI"] = outputs.ti_model.consistency_score * self._weights.get("TI", 0.9)
        else:
            scores["TI"] = 0.0

        # --- Règle 2 : conflit TE vs TI ---
        te_score = scores.get("TE", 0.0)
        ti_score = scores.get("TI", 0.0)
        if abs(te_score - ti_score) > 0.3:
            if te_score > ti_score and outputs.te_judgment and outputs.te_judgment.accepted:
                # Priorité TE : données externes disponibles
                action_parts.append(f"TE_priority:accepted={outputs.te_judgment.accepted[:2]}")
                dominant = "TE"
            else:
                # Priorité TI : modèle interne
                action_parts.append(
                    f"TI_priority:principle={outputs.ti_model.principle if outputs.ti_model else 'none'}"
                )
                dominant = "TI"
        else:
            dominant = "TE" if te_score >= ti_score else "TI"

        # --- FE ---
        if outputs.fe_value is not None:
            scores["FE"] = outputs.fe_value.acceptability * self._weights.get("FE", 0.7)
        else:
            scores["FE"] = 0.0

        # --- FI ---
        if outputs.fi_value is not None:
            scores["FI"] = outputs.fi_value.congruence * self._weights.get("FI", 0.7)
        else:
            scores["FI"] = 0.0

        # --- Règle 3 : conflit FE vs FI ---
        fe_score = scores.get("FE", 0.0)
        fi_score = scores.get("FI", 0.0)
        if (outputs.fe_value is not None and outputs.fi_value is not None
                and abs(fe_score - fi_score) > FE_FI_CONFLICT_THRESHOLD * max(fe_score, fi_score, 0.01)):
            conflict_detected = True
            conflict_description = (
                f"FE_FI_CONFLICT: FE={round(fe_score, 3)} FI={round(fi_score, 3)}"
            )
            self._conflict_log.append({
                "ts_ns": t_start,
                "type": "FE_FI_CONFLICT",
                "fe_score": fe_score,
                "fi_score": fi_score,
            })
            action_parts.append("CONFLICT_PENDING:FE_FI")

        # --- Calcul du consensus ---
        active_scores = {k: v for k, v in scores.items() if v > 0}
        consensus_score = len(active_scores) / 8.0

        # Score de confiance global (moyenne pondérée des scores non nuls)
        if active_scores:
            total_w = sum(self._weights.get(k, 1.0) for k in active_scores)
            weighted_sum = sum(v for v in active_scores.values())
            confidence = round(
                weighted_sum / total_w if total_w > 0 else 0.0, 4
            )
        else:
            confidence = 0.0

        # --- Action finale ---
        if not action_parts:
            if outputs.te_judgment and outputs.te_judgment.accepted:
                action_parts.append(f"accept:{outputs.te_judgment.accepted[0]}")
            elif outputs.ti_model:
                action_parts.append(f"model:{outputs.ti_model.principle}")
            elif outputs.ne_hypotheses and outputs.ne_hypotheses.candidates:
                action_parts.append(f"hypothesis:{outputs.ne_hypotheses.candidates[0].concept}")
            else:
                action_parts.append("no_action:insufficient_data")

        action = "|".join(action_parts)

        return ActionDecision(
            action=action,
            confidence=confidence,
            consensus_score=round(consensus_score, 4),
            conflict_detected=conflict_detected,
            conflict_description=conflict_description,
            dominant_function=dominant,
            ts_ns=t_start,
        )

    def conflict_log(self) -> list[dict]:
        return list(self._conflict_log)
