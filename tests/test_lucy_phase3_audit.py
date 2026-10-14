"""
test_lucy_phase3_audit.py — Tests Phase 3 : Corrections de l'audit P0/P1

Projet : LuCY (Language Unit for Cognitive Yield)
Module : tests
Auteur : LuCY Project

Tests P3-T01 → P3-T16 couvrant les 4 corrections de l'audit Phase 2 :

  P0-A : HardLimit.check() lève LimitViolationError (P3-T01 → P3-T04)
    — Un opérateur ne retourne JAMAIS un résultat violant une limite.
    — Chaque test construit artificiellement une violation d'une limite connue
      et vérifie que LimitViolationError est levée.

  P0-B : v:no_wipe étendu aux synonymes (P3-T05 → P3-T08)
    — FI doit retourner une congruence réduite (et signaler la violation)
      pour "wipe", "remove_forensic", "destroy_log", "purge_log", "erase_log",
      "reset_forensic", "drop_forensic", "flush_forensic", "overwrite_log".

  P1-A : check_traceability_keys() détecte les clés manquantes (P3-T09 → P3-T12)
    — OperatorContract.check_traceability_keys() retourne (False, [missing])
      quand une clé déclarée n'est pas dans les intermediate_steps.
    — Les opérateurs réels passent cette vérification (clés présentes).

  P1-B : SuccessCriterion.evaluate() clamp dans [0.0, 1.0] (P3-T13 → P3-T16)
    — Une evaluate_fn retournant -0.5 ou 1.5 est silencieusement corrigée.
    — clamped=True est mémorisé.

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from lucy.functions.contracts import get_contract
from lucy.functions.feeling_in import SentimentIntroverti
from lucy.functions.intuition_ex import IntuitionExtravertie, KnowledgeGraph
from lucy.functions.sensation_ex import SensationExtravertie
from lucy.functions.sensation_in import SensationIntrovertie
from lucy.functions.types import (
    HardLimit,
    HypothesisSet,
    InternalValue,
    LimitViolationError,
    OperatorContract,
    OperatorTrace,
    PerceptualFact,
    SuccessCriterion,
)


# ---------------------------------------------------------------------------
# P3-T01 → P3-T04 : P0-A — LimitViolationError levée sur violation réelle
# ---------------------------------------------------------------------------

class TestP0A_LimitViolationError:
    """P3-T01 → P3-T04 : HardLimit.check() lève LimitViolationError.

    Chaque test crée une violation directe d'une limite connue et vérifie
    que l'exception est levée avant que le résultat soit retourné.
    """

    def test_P3_T01_hard_limit_raises_on_violation(self):
        """P0-A — HardLimit.check() lève LimitViolationError si check_fn retourne False."""
        lim = HardLimit(
            name="always_fail",
            description="Ce test doit toujours échouer.",
            check_fn=lambda _: False,  # violation forcée
        )
        with pytest.raises(LimitViolationError) as exc_info:
            lim.check("any_result", operator_id="TEST")
        assert exc_info.value.limit_name == "always_fail"
        assert exc_info.value.operator_id == "TEST"
        assert lim.violated is True

    def test_P3_T02_hard_limit_no_raise_on_pass(self):
        """P0-A — HardLimit.check() retourne True sans lever si check_fn retourne True."""
        lim = HardLimit(
            name="always_pass",
            description="Ce test doit toujours passer.",
            check_fn=lambda _: True,
        )
        result = lim.check("any_result", operator_id="TEST")
        assert result is True
        assert lim.violated is False

    def test_P3_T03_contract_check_all_limits_raises_on_first_violation(self):
        """P0-A — OperatorContract.check_all_limits() lève dès la première limite violée."""
        contract = OperatorContract(
            operator_id="TEST",
            operation="test",
            mechanism="test",
            output_type="Any",
            hard_limits=[
                HardLimit("limit_pass", "toujours OK", check_fn=lambda _: True),
                HardLimit("limit_fail", "toujours KO", check_fn=lambda _: False),
                HardLimit("limit_pass2", "jamais atteint", check_fn=lambda _: True),
            ],
        )
        with pytest.raises(LimitViolationError) as exc_info:
            contract.check_all_limits("result", operator_id="TEST")
        assert exc_info.value.limit_name == "limit_fail"

    def test_P3_T04_finalize_trace_captures_violation_with_fallback(self):
        """P0-A — finalize_trace() retourne le fallback et log la violation si fourni."""
        contract = OperatorContract(
            operator_id="FI",
            operation="test",
            mechanism="test",
            output_type="InternalValue",
            hard_limits=[
                HardLimit("fake_violation", "violation forcée", check_fn=lambda _: False),
            ],
        )
        trace = OperatorTrace(operator_id="FI")
        import time
        t_start = time.time_ns()

        # Créer un résultat normal et un fallback
        bad_result = InternalValue(congruence=0.5, conviction_level=0.5)
        fallback = InternalValue(
            congruence=0.0,
            conviction_level=0.0,
            expression_needed=True,
            notes="LIMIT_VIOLATED_FALLBACK",
        )

        returned, final_trace = contract.finalize_trace(
            bad_result, trace, t_start, fallback_result=fallback
        )
        # Le fallback doit être retourné, pas bad_result
        assert returned.notes == "LIMIT_VIOLATED_FALLBACK"
        # La violation doit être dans la trace
        assert "fake_violation" in final_trace.limits_violated
        assert any("LIMIT_VIOLATED" in s for s in final_trace.intermediate_steps)


# ---------------------------------------------------------------------------
# P3-T05 → P3-T08 : P0-B — v:no_wipe étendu aux synonymes
# ---------------------------------------------------------------------------

class TestP0B_NoWipeSynonyms:
    """P3-T05 → P3-T08 : FI signale une violation pour tous les synonymes de wipe.

    FI évalue la congruence de l'action. Pour les actions touchant au wipe
    des logs forensic, le score v:no_wipe doit être 0.0 (violation signalée)
    même pour des synonymes non présents dans la Phase 2.
    """

    def _assert_wipe_detected(self, fi: SentimentIntroverti, action: str) -> None:
        """Vérifier que FI signale une violation v:no_wipe pour l'action donnée."""
        result = fi.process(action)
        # La violation doit apparaître dans notes ou dans la trace
        violation_in_notes = "low_congruence" in result.notes or "v:no_wipe" in result.notes
        violation_in_trace = any(
            "no_wipe" in s and "0.0" in s
            for s in result.trace.intermediate_steps
        )
        assert violation_in_notes or violation_in_trace, (
            f"Action {action!r} n'a pas déclenché de violation v:no_wipe.\n"
            f"notes={result.notes!r}\ntrace={result.trace.intermediate_steps}"
        )

    def test_P3_T05_wipe_original_still_detected(self):
        """P0-B — Mot original 'wipe' toujours détecté (régression)."""
        fi = SentimentIntroverti()
        self._assert_wipe_detected(fi, "wipe the forensic log")

    def test_P3_T06_remove_forensic_detected(self):
        """P0-B — Synonyme 'remove_forensic' désormais détecté (ajout P3)."""
        fi = SentimentIntroverti()
        self._assert_wipe_detected(fi, "remove_forensic data")

    def test_P3_T07_destroy_log_detected(self):
        """P0-B — Synonyme 'destroy_log' désormais détecté (ajout P3)."""
        fi = SentimentIntroverti()
        self._assert_wipe_detected(fi, "destroy_log to free space")

    def test_P3_T08_purge_erase_synonyms_detected(self):
        """P0-B — Synonymes 'purge_log', 'erase_log', 'overwrite_log' détectés (ajout P3)."""
        fi = SentimentIntroverti()
        for action in ("purge_log", "erase_log file", "overwrite_log with zeros"):
            self._assert_wipe_detected(fi, action)


# ---------------------------------------------------------------------------
# P3-T09 → P3-T12 : P1-A — check_traceability_keys() détecte les manques
# ---------------------------------------------------------------------------

class TestP1A_TraceabilityKeysCheck:
    """P3-T09 → P3-T12 : check_traceability_keys() vérifie la complétude de la trace.

    P1-A est non-bloquant à l'exécution (les opérateurs logguent la clé manquante
    via TRACEABILITY_MISSING_KEYS dans intermediate_steps) mais la méthode
    check_traceability_keys() doit retourner (False, [missing_key]) quand
    une clé déclarée est absente de la trace.
    """

    def test_P3_T09_traceability_keys_all_present(self):
        """P1-A — check_traceability_keys() retourne (True, []) si toutes les clés sont présentes."""
        contract = get_contract("SE")
        trace = OperatorTrace(
            operator_id="SE",
            intermediate_steps=[
                "source_type:text",
                "detection_step:properties_extracted",
                "confidence_computation:0.9_threshold:0.5",
            ],
        )
        ok, missing = contract.check_traceability_keys(trace)
        assert ok is True
        assert missing == []

    def test_P3_T10_traceability_keys_missing_one(self):
        """P1-A — check_traceability_keys() retourne (False, ['confidence_computation']) si manquant."""
        contract = get_contract("SE")
        trace = OperatorTrace(
            operator_id="SE",
            intermediate_steps=[
                "source_type:text",
                "detection_step:ok",
                # "confidence_computation" manquant volontairement
            ],
        )
        ok, missing = contract.check_traceability_keys(trace)
        assert ok is False
        assert "confidence_computation" in missing

    def test_P3_T11_se_operator_real_trace_has_all_keys(self):
        """P1-A — L'opérateur SE produit une trace avec toutes ses clés déclarées."""
        se = SensationExtravertie()
        result = se.process("Hello world", cycle_ref="p3_t11")
        contract = get_contract("SE")
        ok, missing = contract.check_traceability_keys(result.trace)
        assert ok is True, f"Clés manquantes dans la trace SE : {missing}"

    def test_P3_T12_finalize_trace_logs_missing_keys(self):
        """P1-A — finalize_trace() ajoute TRACEABILITY_MISSING_KEYS dans intermediate_steps si clé absente."""
        contract = OperatorContract(
            operator_id="SE",
            operation="test",
            mechanism="test",
            output_type="PerceptualFact",
            traceability=["key_present", "key_missing"],
            hard_limits=[],
        )
        trace = OperatorTrace(
            operator_id="SE",
            intermediate_steps=["key_present:ok"],  # "key_missing" absent
        )
        fact = PerceptualFact(exists=True, properties={"x": 1}, confidence=0.9)
        import time
        t_start = time.time_ns()

        returned, final_trace = contract.finalize_trace(fact, trace, t_start)
        # La clé manquante doit être signalée dans les steps
        missing_logged = any(
            "TRACEABILITY_MISSING_KEYS" in s and "key_missing" in s
            for s in final_trace.intermediate_steps
        )
        assert missing_logged, (
            f"Attendu TRACEABILITY_MISSING_KEYS dans les steps, obtenu : {final_trace.intermediate_steps}"
        )


# ---------------------------------------------------------------------------
# P3-T13 → P3-T16 : P1-B — SuccessCriterion.evaluate() clamp [0.0, 1.0]
# ---------------------------------------------------------------------------

class TestP1B_ScoreClamping:
    """P3-T13 → P3-T16 : SuccessCriterion.evaluate() clamp le score dans [0.0, 1.0].

    Une evaluate_fn retournant une valeur hors intervalle est corrigée
    silencieusement. clamped=True est mémorisé pour l'audit.
    """

    def test_P3_T13_score_above_1_clamped(self):
        """P1-B — Un score de 1.5 est clamped à 1.0."""
        criterion = SuccessCriterion(
            name="over_one",
            description="Retourne 1.5",
            evaluate_fn=lambda _: 1.5,
        )
        score = criterion.evaluate("dummy")
        assert score == 1.0
        assert criterion.clamped is True
        assert criterion.last_score == 1.0

    def test_P3_T14_score_below_0_clamped(self):
        """P1-B — Un score de -0.5 est clamped à 0.0."""
        criterion = SuccessCriterion(
            name="below_zero",
            description="Retourne -0.5",
            evaluate_fn=lambda _: -0.5,
        )
        score = criterion.evaluate("dummy")
        assert score == 0.0
        assert criterion.clamped is True

    def test_P3_T15_score_in_range_not_clamped(self):
        """P1-B — Un score de 0.75 n'est pas modifié et clamped=False."""
        criterion = SuccessCriterion(
            name="normal_score",
            description="Retourne 0.75",
            evaluate_fn=lambda _: 0.75,
        )
        score = criterion.evaluate("dummy")
        assert score == 0.75
        assert criterion.clamped is False

    def test_P3_T16_all_operator_criteria_scores_clamped_in_range(self):
        """P1-B — Tous les critères des 8 opérateurs retournent des scores dans [0.0, 1.0]."""
        from lucy.functions.contracts import all_contracts
        from lucy.functions.feeling_ex import SentimentExtraverti
        from lucy.functions.feeling_in import SentimentIntroverti
        from lucy.functions.intuition_ex import IntuitionExtravertie
        from lucy.functions.intuition_in import IntuitionIntrovertie
        from lucy.functions.thinking_ex import PenseeExtravertie
        from lucy.functions.thinking_in import PenseeIntrovertie

        se = SensationExtravertie()
        si = SensationIntrovertie()
        ne = IntuitionExtravertie()
        ni = IntuitionIntrovertie()
        te = PenseeExtravertie()
        ti = PenseeIntrovertie()
        fe = SentimentExtraverti()
        fi = SentimentIntroverti()

        fact = se.process("clamp test input")
        si_res = si.process(fact)
        ne_res = ne.process(fact)
        ni_res = ni.process(fact)
        te_res = te.process(ne_res)
        ti_res = ti.process(ne_res)
        fe_res = fe.process(te_res)
        fi_res = fi.process("store_and_learn")

        for label, result in [
            ("SE", fact), ("SI", si_res), ("NE", ne_res), ("NI", ni_res),
            ("TE", te_res), ("TI", ti_res), ("FE", fe_res), ("FI", fi_res),
        ]:
            for name, score in result.trace.criteria_scores.items():
                assert 0.0 <= score <= 1.0, (
                    f"{label}/{name}: score {score} hors [0.0, 1.0]"
                )
