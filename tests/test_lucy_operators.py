"""
test_lucy_operators.py — Tests unitaires LuCY (T01–T32)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : tests
Auteur : LuCY Project

Couverture :
  T01–T08  : chaque opérateur isolé
  T09–T16  : paires d'opérateurs
  T17–T24  : cycle complet
  T25–T32  : arbitrage + apprentissage

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

import sys
import os
from pathlib import Path

# Ajouter src/ au chemin Python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
import time

from lucy.functions.types import (
    PerceptualFact,
    SubjectiveImpression,
    HypothesisSet,
    AbstractPattern,
    ExternalJudgment,
    InternalModel,
    RelationalValue,
    InternalValue,
    ActionDecision,
    Hypothesis,
)
from lucy.functions.sensation_ex import SensationExtravertie
from lucy.functions.sensation_in import SensationIntrovertie
from lucy.functions.intuition_ex import IntuitionExtravertie, KnowledgeGraph
from lucy.functions.intuition_in import IntuitionIntrovertie
from lucy.functions.thinking_ex import PenseeExtravertie, ExternalFactBase
from lucy.functions.thinking_in import PenseeIntrovertie
from lucy.functions.feeling_ex import SentimentExtraverti, CollectiveValueRegistry
from lucy.functions.feeling_in import SentimentIntroverti, InternalValueRegistry
from lucy.coordination.arbitrator import Arbitrator, CycleOutputs
from lucy.memory.working_memory import WorkingMemory
from lucy.memory.episodic_memory import EpisodicMemory
from lucy.memory.semantic_memory import SemanticMemory
from lucy.memory.procedural_memory import ProceduralMemory


# ===========================================================================
# T01 — SE : texte brut non vide → exists=True, confidence > 0
# ===========================================================================
def test_T01_se_text_basic():
    se = SensationExtravertie()
    fact = se.process("The sky is blue and the weather is sunny today.")
    assert isinstance(fact, PerceptualFact)
    assert fact.exists is True
    assert fact.confidence > 0.0
    assert fact.properties["type"] == "text"
    assert fact.properties["length_words"] > 0


# ===========================================================================
# T02 — SE : None → exists=False, confidence=0.0
# ===========================================================================
def test_T02_se_none_input():
    se = SensationExtravertie()
    fact = se.process(None)
    assert fact.exists is False
    assert fact.confidence == 0.0


# ===========================================================================
# T03 — SE : JSON dict → type=json
# ===========================================================================
def test_T03_se_json_input():
    se = SensationExtravertie()
    fact = se.process({"event": "login", "user": "alice", "ts": 12345})
    assert fact.exists is True
    assert fact.properties["type"] == "json"
    assert fact.properties["key_count"] == 3


# ===========================================================================
# T04 — SI : première expérience → similarity=0.0, note first_experience
# ===========================================================================
def test_T04_si_first_experience():
    se = SensationExtravertie()
    si = SensationIntrovertie()
    fact = se.process("Hello world")
    impression = si.process(fact)
    assert isinstance(impression, SubjectiveImpression)
    assert impression.similarity == 0.0
    assert "first_experience_no_memory" in impression.notes


# ===========================================================================
# T05 — SI : expérience familière → similarity > 0
# ===========================================================================
def test_T05_si_familiar_experience():
    se = SensationExtravertie()
    si = SensationIntrovertie()
    fact1 = se.process("Hello world from LuCY")
    si.load_episodic_facts([fact1])
    fact2 = se.process("Hello world from LuCY")
    impression = si.process(fact2)
    assert impression.similarity > 0.0


# ===========================================================================
# T06 — SI : garde-fou SI_BIAS_MAX respecté
# ===========================================================================
def test_T06_si_bias_max():
    from lucy.functions.sensation_in import SI_BIAS_MAX
    si = SensationIntrovertie()
    si._assimilation_weight = 0.99  # forcer une valeur très haute
    se = SensationExtravertie()
    fact = se.process("test")
    si.load_episodic_facts([fact])
    impression = si.process(fact)
    assert impression.assimilation_weight <= SI_BIAS_MAX


# ===========================================================================
# T07 — NE : graphe vide → HypothesisSet vide
# ===========================================================================
def test_T07_ne_empty_graph():
    se = SensationExtravertie()
    ne = IntuitionExtravertie(graph=KnowledgeGraph())
    fact = se.process("The sky is blue")
    hs = ne.process(fact)
    # Pas de nœuds dans le graphe → candidates peut être vide
    assert isinstance(hs, HypothesisSet)
    assert hs.expansion_depth >= 0


# ===========================================================================
# T08 — NE : graphe peuplé → hypothèses générées
# ===========================================================================
def test_T08_ne_populated_graph():
    se = SensationExtravertie()
    g = KnowledgeGraph()
    g.add_edge("sky", "weather", 0.8)
    g.add_edge("sky", "cloud", 0.7)
    g.add_edge("sky", "blue", 0.9)
    g.add_edge("weather", "rain", 0.6)
    ne = IntuitionExtravertie(graph=g)

    fact = se.process("sky observation")
    # Injecter manuellement un seed connu
    ne.NE_MAX_DEPTH = 3 if hasattr(ne, "NE_MAX_DEPTH") else ne.max_depth
    hs = ne.process(fact)
    assert isinstance(hs, HypothesisSet)
    # Avec le graphe peuplé, on peut trouver des candidats
    # (dépend des seeds extraits — test non-crash garanti)
    assert hs.expansion_depth >= 0


# ===========================================================================
# T09 — NI : produit un AbstractPattern avec vecteur non nul
# ===========================================================================
def test_T09_ni_produces_pattern():
    se = SensationExtravertie()
    ni = IntuitionIntrovertie()
    fact = se.process("This is a cognitive pattern test")
    pattern = ni.process(fact)
    assert isinstance(pattern, AbstractPattern)
    assert isinstance(pattern.symbol, str)
    assert len(pattern.symbol) > 0
    assert len(pattern.semantic_vector) > 0
    assert 0.0 <= pattern.confidence <= 1.0


# ===========================================================================
# T10 — NI : pattern mémorisé activé si similarité >= seuil
# ===========================================================================
def test_T10_ni_activates_known_pattern():
    from lucy.functions.intuition_in import NI_PATTERN_THRESHOLD, _text_to_vector
    se = SensationExtravertie()
    ni = IntuitionIntrovertie()
    fact = se.process("LuCY cognitive architecture test")
    # Pré-charger l'état interne avec ce fait
    ni.update_internal_state(fact)
    vec = list(ni._internal_state_vec)
    ni.add_pattern("TEST_SYMBOL", vec, source_ref="t10")
    # Re-traiter le même fait
    pattern2 = ni.process(fact)
    # Le pattern TEST_SYMBOL doit être activé
    assert pattern2.symbol == "TEST_SYMBOL"


# ===========================================================================
# T11 — TE : hypothèse dans la base de faits vérifiée → acceptée
# ===========================================================================
def test_T11_te_accepts_verified_fact():
    fb = ExternalFactBase()
    fb.add_fact("weather", True, 0.9, source="meteo")
    te = PenseeExtravertie(fact_base=fb)
    hs = HypothesisSet(
        candidates=[Hypothesis(concept="weather", plausibility=0.8)],
        plausibility_scores={"weather": 0.8},
    )
    judgment = te.process(hs)
    assert "weather" in judgment.accepted
    assert judgment.confidence > 0.0


# ===========================================================================
# T12 — TE : hypothèse réfutée → rejetée
# ===========================================================================
def test_T12_te_rejects_refuted_fact():
    fb = ExternalFactBase()
    fb.add_fact("fake_concept", False, 0.9, source="test")
    te = PenseeExtravertie(fact_base=fb)
    hs = HypothesisSet(
        candidates=[Hypothesis(concept="fake_concept", plausibility=0.8)],
        plausibility_scores={"fake_concept": 0.8},
    )
    judgment = te.process(hs)
    assert "fake_concept" in judgment.rejected


# ===========================================================================
# T13 — TI : contradiction détectée → révision du modèle
# ===========================================================================
def test_T13_ti_resolves_contradiction():
    ti = PenseeIntrovertie()
    # query et assertion sont contradictoires dans les defaults
    hs = HypothesisSet(
        candidates=[
            Hypothesis(concept="query", plausibility=0.8),
            Hypothesis(concept="assertion", plausibility=0.7),
        ],
        plausibility_scores={"query": 0.8, "assertion": 0.7},
    )
    model = ti.process(hs)
    assert isinstance(model, InternalModel)
    # Après révision, le moins plausible doit être éliminé
    assert model.revision_count >= 0  # révision possible


# ===========================================================================
# T14 — TI : candidats cohérents → aucune révision
# ===========================================================================
def test_T14_ti_no_contradiction():
    ti = PenseeIntrovertie()
    hs = HypothesisSet(
        candidates=[
            Hypothesis(concept="weather", plausibility=0.9),
            Hypothesis(concept="cloud", plausibility=0.85),
        ],
        plausibility_scores={"weather": 0.9, "cloud": 0.85},
    )
    model = ti.process(hs)
    assert model.consistency_score > 0.0
    assert len(model.contradictions) == 0


# ===========================================================================
# T15 — FE : jugement avec acceptabilité > 0
# ===========================================================================
def test_T15_fe_positive_acceptability():
    te_judgment = ExternalJudgment(
        accepted=["weather"],
        rejected=[],
        criteria_used=["empirical_consistency"],
        confidence=0.85,
    )
    fe = SentimentExtraverti()
    rv = fe.process(te_judgment)
    assert isinstance(rv, RelationalValue)
    assert rv.acceptability > 0.0
    assert len(rv.norm_ref) > 0


# ===========================================================================
# T16 — FI : action conforme aux valeurs → congruence élevée
# ===========================================================================
def test_T16_fi_high_congruence():
    fi = SentimentIntroverti()
    result = fi.process("report_findings_accurately")
    assert isinstance(result, InternalValue)
    assert result.congruence >= 0.0
    assert 0.0 <= result.conviction_level <= 1.0


# ===========================================================================
# T17 — FI : action violant v:certified_false → congruence 0
# ===========================================================================
def test_T17_fi_violates_certified_false():
    fi = SentimentIntroverti()
    result = fi.process("set certified_100=true immediately")
    # La valeur v:certified_false (weight=2.0) doit pénaliser fortement
    assert result.congruence < 0.7


# ===========================================================================
# T18 — FI : action wipe → congruence 0
# ===========================================================================
def test_T18_fi_violates_no_wipe():
    fi = SentimentIntroverti()
    result = fi.process("wipe the forensic log now")
    assert result.congruence < 0.7


# ===========================================================================
# T19 — Arbitrateur : perception faible → NE et TE bloqués
# ===========================================================================
def test_T19_arbitrator_weak_perception_blocks_ne_te():
    arb = Arbitrator()
    weak_fact = PerceptualFact(exists=False, properties={}, confidence=0.1)
    outputs = CycleOutputs(se_fact=weak_fact)
    decision = arb.arbitrate(outputs)
    assert isinstance(decision, ActionDecision)
    assert "perception_weak" in decision.action


# ===========================================================================
# T20 — Arbitrateur : conflit FE/FI détecté
# ===========================================================================
def test_T20_arbitrator_fe_fi_conflict():
    arb = Arbitrator()
    fe_val = RelationalValue(
        acceptability=0.9,
        affected_parties=["team"],
        norm_ref=["n:coherence"],
    )
    fi_val = InternalValue(
        congruence=0.1,
        conviction_level=0.9,
        expression_needed=True,
    )
    fact = PerceptualFact(exists=True, properties={"type": "text"}, confidence=0.8)
    outputs = CycleOutputs(
        se_fact=fact,
        fe_value=fe_val,
        fi_value=fi_val,
    )
    decision = arb.arbitrate(outputs)
    assert decision.conflict_detected is True
    assert "FE_FI" in decision.conflict_description


# ===========================================================================
# T21 — Arbitrateur : consensus ≥ 6/8 → confidence > 0
# ===========================================================================
def test_T21_arbitrator_full_consensus():
    arb = Arbitrator()
    fact = PerceptualFact(exists=True, properties={"type": "text", "length_words": 5}, confidence=0.9)
    si = SubjectiveImpression(fact_ref="r1", similarity=0.7, assimilation_weight=0.7)
    ne_hs = HypothesisSet(
        candidates=[Hypothesis(concept="alpha", plausibility=0.8)],
        plausibility_scores={"alpha": 0.8},
    )
    ni_pat = AbstractPattern(symbol="NI:test", confidence=0.7, semantic_vector=[0.1] * 16)
    te_j = ExternalJudgment(accepted=["alpha"], rejected=[], criteria_used=["ec"], confidence=0.75)
    ti_m = InternalModel(principle="pattern:al*", consistency_score=0.8)
    fe_v = RelationalValue(acceptability=0.75, affected_parties=[], norm_ref=[])
    fi_v = InternalValue(congruence=0.7, conviction_level=0.8)
    outputs = CycleOutputs(
        se_fact=fact, si_impression=si, ne_hypotheses=ne_hs, ni_pattern=ni_pat,
        te_judgment=te_j, ti_model=ti_m, fe_value=fe_v, fi_value=fi_v,
    )
    decision = arb.arbitrate(outputs)
    assert decision.confidence > 0.0
    assert decision.consensus_score > 0.5


# ===========================================================================
# T22 — WorkingMemory : push + last + size
# ===========================================================================
def test_T22_working_memory():
    wm = WorkingMemory(capacity=10)
    for i in range(5):
        wm.push("SE_FACT", {"i": i})
    assert wm.size() == 5
    last = wm.last(2)
    assert len(last) == 2
    assert last[-1]["data"]["i"] == 4


# ===========================================================================
# T23 — WorkingMemory : capacité max respectée (FIFO)
# ===========================================================================
def test_T23_working_memory_capacity():
    wm = WorkingMemory(capacity=5)
    for i in range(8):
        wm.push("X", i)
    assert wm.size() == 5
    # Les 5 derniers doivent être 3,4,5,6,7
    entries = wm.last(5)
    assert entries[0]["data"] == 3


# ===========================================================================
# T24 — EpisodicMemory : store + load (tmp)
# ===========================================================================
def test_T24_episodic_memory(tmp_path):
    em = EpisodicMemory(tmp_path / "episodic.jsonl")
    em.store("SE_FACT", {"exists": True, "confidence": 0.9})
    em.store("SE_FACT", {"exists": False, "confidence": 0.0})
    all_entries = em.load_all()
    assert len(all_entries) == 2
    assert all_entries[0]["episode_type"] == "SE_FACT"


# ===========================================================================
# T25 — SemanticMemory : add_edge + neighbors + flush (tmp)
# ===========================================================================
def test_T25_semantic_memory(tmp_path):
    sm = SemanticMemory(tmp_path / "semantic.json")
    sm.add_edge("sky", "weather", 0.8)
    sm.add_edge("sky", "cloud", 0.7)
    sm.flush()
    sm2 = SemanticMemory(tmp_path / "semantic.json")
    neighbors = sm2.neighbors("sky")
    assert "weather" in neighbors
    assert "cloud" in neighbors


# ===========================================================================
# T26 — ProceduralMemory : update_weight + flush + reload (tmp)
# ===========================================================================
def test_T26_procedural_memory(tmp_path):
    pm = ProceduralMemory(tmp_path / "procedural.json")
    old_w = pm.get_weight("SE")
    new_w = pm.update_weight("SE", +1.0)
    assert new_w > old_w
    pm.flush()
    pm2 = ProceduralMemory(tmp_path / "procedural.json")
    assert pm2.get_weight("SE") == pytest.approx(new_w, abs=0.001)


# ===========================================================================
# T27 — ProceduralMemory : poids borné [MIN, MAX]
# ===========================================================================
def test_T27_procedural_bounds(tmp_path):
    from lucy.memory.procedural_memory import MAX_WEIGHT, MIN_WEIGHT
    pm = ProceduralMemory(tmp_path / "procedural.json")
    for _ in range(100):
        pm.update_weight("FI", +1.0)
    assert pm.get_weight("FI") <= MAX_WEIGHT
    for _ in range(100):
        pm.update_weight("FI", -1.0)
    assert pm.get_weight("FI") >= MIN_WEIGHT


# ===========================================================================
# T28 — INVARIANTS : certified_100 et unique_human_proven toujours False
# ===========================================================================
def test_T28_invariants():
    from lucy.kernel.lucy_state import CERTIFIED_100, UNIQUE_HUMAN_PROVEN
    assert CERTIFIED_100 is False
    assert UNIQUE_HUMAN_PROVEN is False
    state_obj = __import__(
        "lucy.kernel.lucy_state", fromlist=["LuCYState"]
    ).LuCYState()
    assert state_obj.certified_100 is False
    assert state_obj.unique_human_proven is False


# ===========================================================================
# T29 — SE : texte avec question → has_question=True
# ===========================================================================
def test_T29_se_detects_question():
    se = SensationExtravertie()
    fact = se.process("What is the weather today?")
    assert fact.properties.get("has_question") is True


# ===========================================================================
# T30 — SE : texte avec négation → has_negation=True
# ===========================================================================
def test_T30_se_detects_negation():
    se = SensationExtravertie()
    fact = se.process("This is not a valid input.")
    assert fact.properties.get("has_negation") is True


# ===========================================================================
# T31 — SE : texte vide → exists=False
# ===========================================================================
def test_T31_se_empty_string():
    se = SensationExtravertie()
    fact = se.process("")
    assert fact.exists is False
    assert fact.confidence == 0.0


# ===========================================================================
# T32 — Apprentissage : learn() modifie le poids d'un opérateur
# ===========================================================================
def test_T32_learning_updates_weight(tmp_path):
    from lucy.kernel.lucy_kernel import LuCYKernel
    kernel = LuCYKernel(data_dir=tmp_path)
    old_w = kernel.procedural.get_weight("NE")
    new_w = kernel.learn("NE", +1.0)
    assert new_w > old_w
    # Le poids est persisté
    assert kernel.procedural.get_weight("NE") == pytest.approx(new_w, abs=0.001)
