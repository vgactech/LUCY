"""
lucy_kernel.py — Noyau principal LuCY (cycle d'exécution complet)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : kernel / lucy_kernel
Auteur : LuCY Project

Implémente le cycle CDC §4.2 :
Input → PERCEIVE (SE+SI) → PERCEIVE-DEEP (NE+NI) → JUDGE (TE+TI+FE+FI) → ARBITRATE → LEARN → Output

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from ..coordination.arbitrator import Arbitrator, CycleOutputs
from ..functions.feeling_ex import CollectiveValueRegistry, SentimentExtraverti
from ..functions.feeling_in import InternalValueRegistry, SentimentIntroverti
from ..functions.intuition_ex import IntuitionExtravertie, KnowledgeGraph
from ..functions.intuition_in import IntuitionIntrovertie
from ..functions.sensation_ex import SensationExtravertie
from ..functions.sensation_in import SensationIntrovertie
from ..functions.thinking_ex import ExternalFactBase, PenseeExtravertie
from ..functions.thinking_in import InternalModelStore, PenseeIntrovertie
from ..functions.types import ActionDecision
from ..io.forensic_logger import ForensicLogger, get_logger
from ..memory.episodic_memory import EpisodicMemory
from ..memory.procedural_memory import ProceduralMemory
from ..memory.semantic_memory import SemanticMemory
from ..memory.working_memory import WorkingMemory
from .lucy_state import LuCYState


class LuCYKernel:
    """Noyau cognitif principal de LuCY.

    Orchestre les 8 opérateurs, les 4 couches mémoire, l'arbitrage et l'apprentissage.
    Chaque appel à `run_cycle()` exécute un cycle complet.
    Le log forensic est alimenté à chaque phase.
    """

    def __init__(
        self,
        data_dir: Path | str = Path("data"),
        debug: bool = True,
    ) -> None:
        data_path = Path(data_dir)

        # Logger forensic
        self.logger: ForensicLogger = get_logger("lucy-kernel")
        self.logger.log_init("0.1.0")

        # 4 couches mémoire
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(data_path / "episodic.jsonl")
        self.semantic = SemanticMemory(data_path / "semantic.json")
        self.procedural = ProceduralMemory(data_path / "procedural_weights.json")

        # 8 opérateurs
        self.SE = SensationExtravertie()
        self.SI = SensationIntrovertie()
        self.NE = IntuitionExtravertie(graph=self.semantic.get_graph_for_ne())
        self.NI = IntuitionIntrovertie()
        self.TE = PenseeExtravertie()
        self.TI = PenseeIntrovertie()
        self.FE = SentimentExtraverti()
        self.FI = SentimentIntroverti()

        # Arbitrateur
        self.arbitrator = Arbitrator(weights=self.procedural.all_weights())

        # État
        self.state = LuCYState()
        self._debug = debug

        # Charger la mémoire épisodique dans SI
        past_facts = self.episodic.load_facts()
        if past_facts:
            self.SI.load_episodic_facts(past_facts[-50:])

    # ------------------------------------------------------------------
    # Cycle principal
    # ------------------------------------------------------------------

    def run_cycle(self, stimulus: Any) -> ActionDecision:
        """Exécuter un cycle cognitif complet sur un stimulus.

        Args:
            stimulus: texte brut, dict JSON, ou None

        Returns:
            ActionDecision — décision finale + métadonnées
        """
        cycle_id = "lucy_c" + uuid.uuid4().hex[:8]
        t_cycle_start = time.time_ns()

        self.state.cycle_count += 1
        self.state.advance_phase("PERCEIVE")
        self.logger.log_cycle_start(cycle_id, type(stimulus).__name__)

        outputs = CycleOutputs()

        # ---------------------------------------------------------------
        # Phase 1 : PERCEIVE — SE + SI
        # ---------------------------------------------------------------
        t0 = time.time_ns()
        se_fact = self.SE.process(stimulus)
        outputs.se_fact = se_fact
        self.working.push("SE_FACT", se_fact.to_dict(), cycle_id)
        self.episodic.store_fact(se_fact, cycle_id)
        self.logger.log_perceive("SE", cycle_id, stimulus, se_fact.to_dict(), time.time_ns() - t0)

        t0 = time.time_ns()
        si_impression = self.SI.process(se_fact)
        outputs.si_impression = si_impression
        self.working.push("SI_IMPRESSION", si_impression.to_dict(), cycle_id)
        self.logger.log_perceive("SI", cycle_id, se_fact.to_dict(), si_impression.to_dict(), time.time_ns() - t0)

        self.state.perceptual_buffer.append(se_fact)
        self.state.subjective_impressions.append(si_impression)

        # ---------------------------------------------------------------
        # Phase 2 : PERCEIVE-DEEP — NE + NI
        # ---------------------------------------------------------------
        self.state.advance_phase("PERCEIVE-DEEP")

        # Synchroniser le graphe NE depuis la mémoire sémantique
        self.NE.graph = self.semantic.get_graph_for_ne()

        t0 = time.time_ns()
        ne_hypotheses = self.NE.process(se_fact)
        outputs.ne_hypotheses = ne_hypotheses
        self.working.push("NE_HYPOTHESES", ne_hypotheses.to_dict(), cycle_id)
        self.logger.log_perceive("NE", cycle_id, se_fact.to_dict(), ne_hypotheses.to_dict(), time.time_ns() - t0)

        t0 = time.time_ns()
        ni_pattern = self.NI.process(se_fact)
        outputs.ni_pattern = ni_pattern
        self.working.push("NI_PATTERN", ni_pattern.to_dict(), cycle_id)
        self.logger.log_perceive("NI", cycle_id, se_fact.to_dict(), ni_pattern.to_dict(), time.time_ns() - t0)

        self.state.hypothesis_set = ne_hypotheses
        self.state.abstract_patterns.append(ni_pattern)

        # ---------------------------------------------------------------
        # Phase 3 : JUDGE — TE + TI + FE + FI
        # ---------------------------------------------------------------
        self.state.advance_phase("JUDGE")

        t0 = time.time_ns()
        te_judgment = self.TE.process(ne_hypotheses)
        outputs.te_judgment = te_judgment
        self.working.push("TE_JUDGMENT", te_judgment.to_dict(), cycle_id)
        self.logger.log_judge("TE", cycle_id, ne_hypotheses.to_dict(), te_judgment.to_dict(), time.time_ns() - t0)

        t0 = time.time_ns()
        ti_model = self.TI.process(ne_hypotheses)
        outputs.ti_model = ti_model
        self.working.push("TI_MODEL", ti_model.to_dict(), cycle_id)
        self.logger.log_judge("TI", cycle_id, ne_hypotheses.to_dict(), ti_model.to_dict(), time.time_ns() - t0)

        t0 = time.time_ns()
        fe_value = self.FE.process(te_judgment)
        outputs.fe_value = fe_value
        self.working.push("FE_VALUE", fe_value.to_dict(), cycle_id)
        self.logger.log_judge("FE", cycle_id, te_judgment.to_dict(), fe_value.to_dict(), time.time_ns() - t0)

        t0 = time.time_ns()
        action_candidate = te_judgment.accepted[0] if te_judgment.accepted else ti_model.principle
        fi_value = self.FI.process(action_candidate, context={"prior_action": self.state.last_action})
        outputs.fi_value = fi_value
        self.working.push("FI_VALUE", fi_value.to_dict(), cycle_id)
        self.logger.log_judge("FI", cycle_id, action_candidate, fi_value.to_dict(), time.time_ns() - t0)

        self.state.external_judgment = te_judgment
        self.state.internal_model = ti_model
        self.state.relational_value = fe_value
        self.state.internal_value = fi_value

        # ---------------------------------------------------------------
        # Phase 4 : ARBITRATE
        # ---------------------------------------------------------------
        self.state.advance_phase("ARBITRATE")
        t0 = time.time_ns()

        # Mettre à jour les poids depuis la mémoire procédurale
        self.arbitrator._weights = self.procedural.all_weights()

        decision = self.arbitrator.arbitrate(outputs)
        t_arb = time.time_ns() - t0

        self.logger.log_arbitrate(
            cycle_id,
            decision.action,
            not decision.conflict_detected,
            t_arb,
        )

        self.state.last_decision = decision
        self.state.last_action = decision.action
        self.state.advance_phase("DONE")

        # Épisode complet
        self.episodic.store(
            "CYCLE_RESULT",
            {
                "decision": decision.to_dict(),
                "consensus": decision.consensus_score,
                "conflict": decision.conflict_detected,
            },
            cycle_id,
        )

        total_duration = time.time_ns() - t_cycle_start
        self.logger.log(
            event_type="CYCLE_END",
            phase="DONE",
            cycle_id=cycle_id,
            output_summary=decision.to_dict(),
            duration_ns=total_duration,
        )

        return decision

    # ------------------------------------------------------------------
    # Apprentissage
    # ------------------------------------------------------------------

    def learn(self, function_id: str, feedback: float) -> float:
        """Appliquer un feedback à un opérateur et mettre à jour la mémoire procédurale.

        Args:
            function_id: SE / SI / NE / NI / TE / TI / FE / FI
            feedback: [-1.0, +1.0]

        Returns:
            Nouveau poids.
        """
        t0 = time.time_ns()
        old_weight = self.procedural.get_weight(function_id)
        new_weight = self.procedural.update_weight(function_id, feedback)
        self.procedural.flush()
        delta = new_weight - old_weight
        cycle_id = "learn_" + uuid.uuid4().hex[:6]
        self.logger.log_learn(cycle_id, function_id, feedback, delta, time.time_ns() - t0)
        return new_weight

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    def flush_all(self) -> None:
        """Persister toutes les mémoires persistantes."""
        self.semantic.flush()
        self.procedural.flush()
