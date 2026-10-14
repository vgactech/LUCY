"""
test_lucy_phase2_contracts.py — Tests Phase 2 : Contrats opérationnels formels

Projet : LuCY (Language Unit for Cognitive Yield)
Module : tests
Auteur : LuCY Project

Tests P2-T01 → P2-T32 couvrant :
  - Existence et structure des 8 contrats OperatorContract
  - Présence du champ `trace` dans toutes les sorties des opérateurs
  - Vérification des limites (HardLimit) à l'exécution
  - Critères de réussite (SuccessCriterion) mesurables
  - Traçabilité : intermediate_steps, input_hash, limits_checked
  - Violations détectées correctement (limites violées)

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import sys
from pathlib import Path

# Chemin d'import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from lucy.functions.contracts import all_contracts, get_contract
from lucy.functions.feeling_ex import SentimentExtraverti
from lucy.functions.feeling_in import SentimentIntroverti
from lucy.functions.intuition_ex import IntuitionExtravertie, KnowledgeGraph
from lucy.functions.intuition_in import IntuitionIntrovertie
from lucy.functions.sensation_ex import SensationExtravertie
from lucy.functions.sensation_in import SensationIntrovertie
from lucy.functions.thinking_ex import ExternalFactBase, PenseeExtravertie
from lucy.functions.thinking_in import PenseeIntrovertie
from lucy.functions.types import (
    HardLimit,
    HypothesisSet,
    OperatorContract,
    OperatorTrace,
    PerceptualFact,
    SuccessCriterion,
)


# ---------------------------------------------------------------------------
# P2-T01 → P2-T08 : Existence des 8 contrats
# ---------------------------------------------------------------------------

class TestContractExistence:
    """P2-T01 → P2-T08 : Chaque opérateur a un contrat OperatorContract."""

    def test_P2_T01_contract_se_exists(self):
        c = get_contract("SE")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "SE"

    def test_P2_T02_contract_si_exists(self):
        c = get_contract("SI")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "SI"

    def test_P2_T03_contract_ne_exists(self):
        c = get_contract("NE")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "NE"

    def test_P2_T04_contract_ni_exists(self):
        c = get_contract("NI")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "NI"

    def test_P2_T05_contract_te_exists(self):
        c = get_contract("TE")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "TE"

    def test_P2_T06_contract_ti_exists(self):
        c = get_contract("TI")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "TI"

    def test_P2_T07_contract_fe_exists(self):
        c = get_contract("FE")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "FE"

    def test_P2_T08_contract_fi_exists(self):
        c = get_contract("FI")
        assert isinstance(c, OperatorContract)
        assert c.operator_id == "FI"


# ---------------------------------------------------------------------------
# P2-T09 → P2-T12 : Structure des contrats (6 dimensions)
# ---------------------------------------------------------------------------

class TestContractStructure:
    """P2-T09 → P2-T12 : Chaque contrat contient les 6 dimensions formelles."""

    def test_P2_T09_all_contracts_have_6_dimensions(self):
        for op_id, contract in all_contracts().items():
            assert contract.operation, f"{op_id}: operation vide"
            assert contract.mechanism, f"{op_id}: mechanism vide"
            assert contract.output_type, f"{op_id}: output_type vide"
            assert contract.traceability, f"{op_id}: traceability vide"
            assert contract.hard_limits, f"{op_id}: hard_limits vide"
            assert contract.success_criteria, f"{op_id}: success_criteria vide"

    def test_P2_T10_hard_limits_have_check_fn(self):
        for op_id, contract in all_contracts().items():
            for lim in contract.hard_limits:
                assert isinstance(lim, HardLimit), f"{op_id}: limite non HardLimit"
                assert callable(lim.check_fn), f"{op_id}: check_fn non callable"

    def test_P2_T11_success_criteria_have_evaluate_fn(self):
        for op_id, contract in all_contracts().items():
            for criterion in contract.success_criteria:
                assert isinstance(criterion, SuccessCriterion)
                assert callable(criterion.evaluate_fn)

    def test_P2_T12_contract_to_dict_complete(self):
        c = get_contract("SE")
        d = c.to_dict()
        assert "operator_id" in d
        assert "operation" in d
        assert "mechanism" in d
        assert "output_type" in d
        assert "hard_limits" in d
        assert "traceability_keys" in d
        assert "success_criteria" in d


# ---------------------------------------------------------------------------
# P2-T13 → P2-T20 : Présence de OperatorTrace dans les sorties
# ---------------------------------------------------------------------------

class TestOperatorTracePresence:
    """P2-T13 → P2-T20 : Chaque opérateur produit une sortie avec un champ trace."""

    def test_P2_T13_se_produces_trace(self):
        se = SensationExtravertie()
        result = se.process("Hello world", cycle_ref="test_c01")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "SE"
        assert result.trace.cycle_ref == "test_c01"
        assert result.trace.limits_checked is True

    def test_P2_T14_si_produces_trace(self):
        se = SensationExtravertie()
        si = SensationIntrovertie()
        fact = se.process("Test data")
        result = si.process(fact, cycle_ref="test_c02")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "SI"
        assert result.trace.limits_checked is True

    def test_P2_T15_ne_produces_trace(self):
        se = SensationExtravertie()
        ne = IntuitionExtravertie()
        fact = se.process("Test")
        result = ne.process(fact, cycle_ref="test_c03")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "NE"
        assert result.trace.limits_checked is True

    def test_P2_T16_ni_produces_trace(self):
        se = SensationExtravertie()
        ni = IntuitionIntrovertie()
        fact = se.process("Abstract concept")
        result = ni.process(fact, cycle_ref="test_c04")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "NI"
        assert result.trace.limits_checked is True

    def test_P2_T17_te_produces_trace(self):
        se = SensationExtravertie()
        ne = IntuitionExtravertie()
        te = PenseeExtravertie()
        fact = se.process("Data")
        hypotheses = ne.process(fact)
        result = te.process(hypotheses, cycle_ref="test_c05")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "TE"
        assert result.trace.limits_checked is True

    def test_P2_T18_ti_produces_trace(self):
        se = SensationExtravertie()
        ne = IntuitionExtravertie()
        ti = PenseeIntrovertie()
        fact = se.process("Model")
        hypotheses = ne.process(fact)
        result = ti.process(hypotheses, cycle_ref="test_c06")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "TI"
        assert result.trace.limits_checked is True

    def test_P2_T19_fe_produces_trace(self):
        se = SensationExtravertie()
        ne = IntuitionExtravertie()
        te = PenseeExtravertie()
        fe = SentimentExtraverti()
        fact = se.process("Social context")
        hypotheses = ne.process(fact)
        judgment = te.process(hypotheses)
        result = fe.process(judgment, cycle_ref="test_c07")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "FE"
        assert result.trace.limits_checked is True

    def test_P2_T20_fi_produces_trace(self):
        fi = SentimentIntroverti()
        result = fi.process("store_fact", cycle_ref="test_c08")
        assert isinstance(result.trace, OperatorTrace)
        assert result.trace.operator_id == "FI"
        assert result.trace.limits_checked is True


# ---------------------------------------------------------------------------
# P2-T21 → P2-T24 : Contenu de la trace (intermediate_steps + input_hash)
# ---------------------------------------------------------------------------

class TestOperatorTraceContent:
    """P2-T21 → P2-T24 : La trace contient les informations de traçabilité requises."""

    def test_P2_T21_se_trace_has_steps(self):
        se = SensationExtravertie()
        result = se.process("Hello world")
        # La trace doit contenir source_type + detection_step + confidence_computation
        steps = result.trace.intermediate_steps
        assert any("source_type" in s for s in steps)
        assert any("detection_step" in s for s in steps)
        assert any("confidence_computation" in s for s in steps)

    def test_P2_T22_se_trace_has_input_hash(self):
        se = SensationExtravertie()
        result = se.process("Some text")
        assert result.trace.input_hash.startswith("sha256:")

    def test_P2_T23_si_trace_has_assimilation_step(self):
        se = SensationExtravertie()
        si = SensationIntrovertie()
        fact = se.process("Experience")
        result = si.process(fact)
        steps = result.trace.intermediate_steps
        assert any("assimilation_weight" in s for s in steps)

    def test_P2_T24_fi_trace_has_values_evaluated(self):
        fi = SentimentIntroverti()
        result = fi.process("do_something")
        steps = result.trace.intermediate_steps
        assert any("values_evaluated" in s for s in steps)
        assert any("congruence_score" in s for s in steps)


# ---------------------------------------------------------------------------
# P2-T25 → P2-T28 : Vérification des limites (HardLimit.check)
# ---------------------------------------------------------------------------

class TestHardLimits:
    """P2-T25 → P2-T28 : Les limites sont vérifiées et violations détectées."""

    def test_P2_T25_se_confidence_always_in_range(self):
        """Limite SE : confidence dans [0.0, 1.0]."""
        se = SensationExtravertie()
        for stim in [None, "", "short", "a" * 500, {"key": "value"}, 42]:
            result = se.process(stim)
            assert 0.0 <= result.confidence <= 1.0
            assert result.trace.limits_violated == [], f"Violation inattendue pour {stim!r}"

    def test_P2_T26_si_assimilation_weight_bounded(self):
        """Limite SI : assimilation_weight <= SI_BIAS_MAX=0.95."""
        se = SensationExtravertie()
        si = SensationIntrovertie()
        fact = se.process("Test")
        result = si.process(fact)
        assert result.assimilation_weight <= 0.95
        assert "assimilation_weight_bounded" not in result.trace.limits_violated

    def test_P2_T27_ne_hypothesis_count_bounded(self):
        """Limite NE : max 5 hypothèses."""
        g = KnowledgeGraph()
        # Graphe dense avec de nombreux voisins
        for i in range(10):
            g.add_edge("text", f"concept_{i}", weight=0.9)
        se = SensationExtravertie()
        ne = IntuitionExtravertie(graph=g)
        fact = se.process("text data here")
        result = ne.process(fact)
        assert len(result.candidates) <= 5
        assert "hypothesis_count_bounded" not in result.trace.limits_violated

    def test_P2_T28_fi_invariant_no_wipe(self):
        """Limite FI : action contenant 'wipe' → v:no_wipe retourne 0.0 (violation signalée)."""
        fi = SentimentIntroverti()
        result = fi.process("wipe the forensic log")
        # La valeur v:no_wipe doit être signalée dans les violation_notes
        # (score individuel = 0.0 pour v:no_wipe, même si la congruence globale > 0.3
        # car les autres valeurs compensent)
        assert "low_congruence" in result.notes or "v:no_wipe" in result.notes, (
            f"Attendu 'v:no_wipe' dans les notes, obtenu: {result.notes!r}"
        )
        # Le score v:no_wipe dans l'évaluation interne doit valoir 0.0
        # (violation documentée via violation_notes dans la trace)
        wipe_violations = [
            s for s in result.trace.intermediate_steps
            if "no_wipe" in s and "0.0" in s
        ]
        assert wipe_violations, (
            f"Attendu une étape de trace signalant v:no_wipe=0.0, trace: {result.trace.intermediate_steps}"
        )


# ---------------------------------------------------------------------------
# P2-T29 → P2-T32 : Critères de réussite (SuccessCriterion)
# ---------------------------------------------------------------------------

class TestSuccessCriteria:
    """P2-T29 → P2-T32 : Les critères de réussite produisent des scores dans [0.0, 1.0]."""

    def test_P2_T29_se_criteria_scores_in_range(self):
        se = SensationExtravertie()
        result = se.process("Hello world")
        for name, score in result.trace.criteria_scores.items():
            assert 0.0 <= score <= 1.0, f"Critère {name}: score {score} hors [0,1]"

    def test_P2_T30_te_criteria_judgment_produced(self):
        se = SensationExtravertie()
        ne = IntuitionExtravertie()
        te = PenseeExtravertie()
        fact = se.process("evaluate this")
        hypotheses = ne.process(fact)
        result = te.process(hypotheses)
        # Le critère 'judgment_produced' doit être > 0 si accepted ou rejected
        scores = result.trace.criteria_scores
        assert "judgment_produced" in scores
        # Score > 0 si au moins une décision
        if result.accepted or result.rejected:
            assert scores["judgment_produced"] == 1.0

    def test_P2_T31_fi_invariants_protected_score(self):
        fi = SentimentIntroverti()
        # Action normale : les invariants sont protégés
        result = fi.process("store_knowledge_graph")
        scores = result.trace.criteria_scores
        assert "invariants_protected" in scores
        assert 0.0 <= scores["invariants_protected"] <= 1.0

    def test_P2_T32_all_criteria_scores_populated_after_process(self):
        """Tous les opérateurs peuplent criteria_scores après process()."""
        se = SensationExtravertie()
        si = SensationIntrovertie()
        ne = IntuitionExtravertie()
        ni = IntuitionIntrovertie()
        te = PenseeExtravertie()
        ti = PenseeIntrovertie()
        fe = SentimentExtraverti()
        fi = SentimentIntroverti()

        fact = se.process("complete pipeline test")
        assert fact.trace.criteria_scores, "SE: criteria_scores vide"

        si_res = si.process(fact)
        assert si_res.trace.criteria_scores, "SI: criteria_scores vide"

        ne_res = ne.process(fact)
        assert ne_res.trace.criteria_scores, "NE: criteria_scores vide"

        ni_res = ni.process(fact)
        assert ni_res.trace.criteria_scores, "NI: criteria_scores vide"

        te_res = te.process(ne_res)
        assert te_res.trace.criteria_scores, "TE: criteria_scores vide"

        ti_res = ti.process(ne_res)
        assert ti_res.trace.criteria_scores, "TI: criteria_scores vide"

        fe_res = fe.process(te_res)
        assert fe_res.trace.criteria_scores, "FE: criteria_scores vide"

        fi_res = fi.process("apply_decision")
        assert fi_res.trace.criteria_scores, "FI: criteria_scores vide"
