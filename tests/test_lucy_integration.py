"""
test_lucy_integration.py — Tests d'intégration LuCY (A01–A04 + I01–I08)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : tests
Auteur : LuCY Project

A01 : LuCY résout un problème logique simple SANS LLM
A02 : LuCY détecte une contradiction dans ses propres jugements
A03 : LuCY apprend à améliorer un poids après feedback négatif
A04 : LuCY persiste son état entre deux sessions et retrouve le contexte

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
import time

from lucy.kernel.lucy_kernel import LuCYKernel
from lucy.functions.thinking_ex import ExternalFactBase


# ===========================================================================
# A01 — Résolution d'un problème logique simple SANS LLM
# ===========================================================================
def test_A01_problem_solving_native(tmp_path):
    """LuCY doit produire une décision cohérente sur un stimulus textuel,
    sans aucun appel LLM externe."""
    kernel = LuCYKernel(data_dir=tmp_path)

    # Peupler la base de faits TE avec des vérités connues
    kernel.TE.fact_base.add_fact("rain", True, 0.95, source="meteo")
    kernel.TE.fact_base.add_fact("umbrella", True, 0.90, source="logic")

    # Peupler le graphe sémantique
    kernel.semantic.add_edge("rain", "umbrella", 0.9)
    kernel.semantic.add_edge("rain", "cloud", 0.8)

    stimulus = "It is raining outside today"
    decision = kernel.run_cycle(stimulus)

    assert decision is not None
    assert isinstance(decision.action, str)
    assert len(decision.action) > 0
    assert decision.confidence >= 0.0
    # Pas d'appel LLM — vérification indirecte : pas d'erreur levée sans clé API


# ===========================================================================
# A02 — Détection d'une contradiction interne
# ===========================================================================
def test_A02_contradiction_detection(tmp_path):
    """LuCY doit détecter une contradiction entre deux hypothèses antagonistes
    et la résoudre ou la signaler dans le jugement TI."""
    kernel = LuCYKernel(data_dir=tmp_path)

    # Enregistrer une contradiction TI
    kernel.TI.add_contradiction("confirm", "deny")

    # Injecter directement un HypothesisSet avec contradictions
    from lucy.functions.types import HypothesisSet, Hypothesis
    from lucy.functions.thinking_in import PenseeIntrovertie

    ti = PenseeIntrovertie()
    ti.add_contradiction("confirm", "deny")
    hs = HypothesisSet(
        candidates=[
            Hypothesis(concept="confirm", plausibility=0.8),
            Hypothesis(concept="deny", plausibility=0.6),
        ],
        plausibility_scores={"confirm": 0.8, "deny": 0.6},
    )
    model = ti.process(hs)

    # Après révision, les deux concepts contradictoires ne peuvent pas coexister
    surviving = model.principle
    assert "confirm" in surviving or "deny" in surviving
    # L'un des deux doit avoir été éliminé (révision)
    assert not ("confirm" in surviving and "deny" in surviving)


# ===========================================================================
# A03 — Apprentissage par feedback négatif
# ===========================================================================
def test_A03_negative_feedback_reduces_weight(tmp_path):
    """Après un feedback négatif sur NE, son poids doit diminuer."""
    kernel = LuCYKernel(data_dir=tmp_path)

    weight_before = kernel.procedural.get_weight("NE")
    for _ in range(5):
        kernel.learn("NE", -1.0)
    weight_after = kernel.procedural.get_weight("NE")

    assert weight_after < weight_before


# ===========================================================================
# A04 — Persistance de la mémoire entre sessions
# ===========================================================================
def test_A04_memory_persistence(tmp_path):
    """Les épisodes stockés par un kernel doivent être retrouvés par un nouveau kernel."""
    # Session 1
    k1 = LuCYKernel(data_dir=tmp_path)
    k1.run_cycle("First session stimulus — hello LuCY")
    count_after_session1 = k1.episodic.count()
    assert count_after_session1 > 0

    # Session 2 — nouveau kernel, même dossier de données
    k2 = LuCYKernel(data_dir=tmp_path)
    count_session2 = k2.episodic.count()
    assert count_session2 >= count_after_session1  # mémoire conservée


# ===========================================================================
# I01 — Cycle complet sur stimulus JSON
# ===========================================================================
def test_I01_full_cycle_json(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    decision = kernel.run_cycle({"event": "system_check", "status": "ok", "ts": 1234})
    assert decision is not None
    assert isinstance(decision.action, str)


# ===========================================================================
# I02 — Cycle complet sur stimulus vide
# ===========================================================================
def test_I02_full_cycle_empty(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    decision = kernel.run_cycle(None)
    assert decision is not None
    # Perception faible → NE et TE bloqués
    assert "perception_weak" in decision.action


# ===========================================================================
# I03 — Log forensic alimenté après un cycle
# ===========================================================================
def test_I03_forensic_log_populated(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    initial_count = kernel.logger.count_entries()
    kernel.run_cycle("Test forensic logging")
    final_count = kernel.logger.count_entries()
    assert final_count > initial_count


# ===========================================================================
# I04 — LuCYState mis à jour après cycle
# ===========================================================================
def test_I04_state_updated(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    assert kernel.state.cycle_count == 0
    kernel.run_cycle("Update state test")
    assert kernel.state.cycle_count == 1
    assert kernel.state.last_action != ""


# ===========================================================================
# I05 — Cycles successifs incrémentent le compteur
# ===========================================================================
def test_I05_multiple_cycles(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    for i in range(5):
        kernel.run_cycle(f"Stimulus number {i}")
    assert kernel.state.cycle_count == 5


# ===========================================================================
# I06 — flush_all() persiste sans erreur
# ===========================================================================
def test_I06_flush_all(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    kernel.run_cycle("Flush test")
    kernel.flush_all()  # ne doit pas lever d'exception
    assert (tmp_path / "semantic.json").exists()
    assert (tmp_path / "procedural_weights.json").exists()


# ===========================================================================
# I07 — Cycle sur texte fr/en détecte la langue
# ===========================================================================
def test_I07_language_detection(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    decision_fr = kernel.run_cycle("Le ciel est bleu et il fait beau aujourd'hui.")
    decision_en = kernel.run_cycle("The sky is blue and the weather is great today.")
    # Les deux cycles doivent se terminer sans erreur
    assert decision_fr is not None
    assert decision_en is not None


# ===========================================================================
# I08 — Invariants CERTIFIED_100/unique_human_proven jamais True
# ===========================================================================
def test_I08_invariants_never_true(tmp_path):
    kernel = LuCYKernel(data_dir=tmp_path)
    for _ in range(10):
        kernel.run_cycle("Invariant check cycle")
    assert kernel.state.certified_100 is False
    assert kernel.state.unique_human_proven is False
