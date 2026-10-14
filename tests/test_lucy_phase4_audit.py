"""
test_lucy_phase4_audit.py — Tests Phase 4 LuCY (audit critique résiduel)

Projet : LuCY (Language Unit for Cognitive Yield)
Module : tests
Auteur : LuCY Project

Corrections testées :
  P0-A : trace forensic persistée AVANT re-raise de LimitViolationError
  P0-B : math.isfinite() guard — NaN et ±inf → score 0.0, jamais 1.0
  P1-A : états mutables isolés — check_stateless() / evaluate_stateless()
         ne mutent pas les instances globales
  P1-B : critical_traceability_keys — clés critiques bloquantes vs warnings

Tests P4-T01 → P4-T20 (20 tests)

CERTIFIED_100=false | unique_human_proven=false
Mode DEBUG actif
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from lucy.functions.types import (
    CriticalTraceabilityError,
    CriterionResult,
    HardLimit,
    LimitCheckResult,
    LimitViolationError,
    OperatorContract,
    OperatorTrace,
    SuccessCriterion,
    _persist_trace_forensic,
    _write_emergency_trace,
)


# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------

def _make_simple_contract(
    operator_id: str = "TEST",
    limits: list[HardLimit] | None = None,
    traceability: list[str] | None = None,
    critical_keys: list[str] | None = None,
    criteria: list[SuccessCriterion] | None = None,
) -> OperatorContract:
    """Créer un contrat minimal pour les tests."""
    return OperatorContract(
        operator_id=operator_id,
        operation="test operation",
        mechanism="test mechanism",
        output_type="Any",
        hard_limits=limits or [],
        traceability=traceability or [],
        critical_traceability_keys=critical_keys or [],
        success_criteria=criteria or [],
    )


def _make_trace(steps: list[str] | None = None) -> OperatorTrace:
    """Créer une trace minimale avec des steps optionnels."""
    t = OperatorTrace(operator_id="TEST")
    if steps:
        t.intermediate_steps = list(steps)
    return t


# ---------------------------------------------------------------------------
# P0-A : trace persistée avant re-raise
# ---------------------------------------------------------------------------

class TestP0A:
    """P4-T01 → P4-T05 — Trace forensic persistée AVANT re-raise."""

    def test_p4_t01_forensic_marker_in_steps_when_no_logger(self):
        """P4-T01 : Sans logger, le marqueur FORENSIC_PERSISTED_BEFORE_RAISE
        doit apparaître dans intermediate_steps avant le raise."""
        limit = HardLimit(
            name="always_fail",
            description="Toujours violée pour le test.",
            check_fn=lambda _: False,
        )
        contract = _make_simple_contract(limits=[limit])
        trace = _make_trace()
        t_start = time.time_ns()

        with pytest.raises(LimitViolationError):
            contract.finalize_trace("anything", trace, t_start, _forensic_logger=None)

        # La trace doit contenir le marqueur de persistance
        assert any(
            "FORENSIC_PERSISTED_BEFORE_RAISE" in step
            for step in trace.intermediate_steps
        ), f"Marqueur absent de intermediate_steps : {trace.intermediate_steps}"

    def test_p4_t02_forensic_logger_called_before_raise(self):
        """P4-T02 : Avec un logger mock, il doit être appelé AVANT le raise."""
        calls: list[dict] = []

        class MockLogger:
            def log(self, event: str, **kwargs):
                calls.append({"event": event, **kwargs})

        limit = HardLimit(
            name="always_fail",
            description="Toujours violée.",
            check_fn=lambda _: False,
        )
        contract = _make_simple_contract(limits=[limit])
        trace = _make_trace()
        t_start = time.time_ns()

        with pytest.raises(LimitViolationError):
            contract.finalize_trace("x", trace, t_start, _forensic_logger=MockLogger())

        assert len(calls) == 1, f"Logger appelé {len(calls)} fois (attendu 1)"
        assert calls[0]["event"] == "limit_violation"
        assert "trace" in calls[0]

    def test_p4_t03_forensic_persisted_even_without_fallback(self):
        """P4-T03 : Sans fallback et avec violation, la trace est persistée
        même si l'exception se propage jusqu'au test."""
        limit = HardLimit(
            name="always_fail",
            description="Violation de test.",
            check_fn=lambda _: False,
        )
        contract = _make_simple_contract(limits=[limit])
        trace = _make_trace()
        t_start = time.time_ns()

        exception_raised = False
        try:
            contract.finalize_trace("x", trace, t_start)
        except LimitViolationError:
            exception_raised = True

        assert exception_raised, "LimitViolationError aurait dû être levée"
        # Vérification de P0-A : le marqueur est dans la trace
        assert any(
            "FORENSIC_PERSISTED_BEFORE_RAISE" in step or "LIMIT_VIOLATED" in step
            for step in trace.intermediate_steps
        )

    def test_p4_t04_fallback_no_raise_still_marks_trace(self):
        """P4-T04 : Avec fallback fourni, pas de raise — mais la trace
        doit quand même contenir LIMIT_VIOLATED."""
        limit = HardLimit(
            name="always_fail",
            description="Violation.",
            check_fn=lambda _: False,
        )
        contract = _make_simple_contract(limits=[limit])
        trace = _make_trace()
        t_start = time.time_ns()

        result, final_trace = contract.finalize_trace(
            "bad", trace, t_start, fallback_result="FALLBACK"
        )
        assert result == "FALLBACK"
        assert any("LIMIT_VIOLATED" in step for step in final_trace.intermediate_steps)

    def test_p4_t05_critical_traceability_also_persisted_before_raise(self):
        """P4-T05 : CriticalTraceabilityError aussi persistée avant raise (P0-A)."""
        contract = _make_simple_contract(
            critical_keys=["mandatory_key"],
        )
        # Trace sans la clé critique
        trace = _make_trace(steps=["other_key:present"])
        t_start = time.time_ns()

        with pytest.raises(CriticalTraceabilityError):
            contract.finalize_trace("x", trace, t_start)

        assert any(
            "CRITICAL_TRACEABILITY_MISSING" in step or "FORENSIC_PERSISTED_BEFORE_RAISE" in step
            for step in trace.intermediate_steps
        )


# ---------------------------------------------------------------------------
# P0-B : guard math.isfinite() — NaN et ±inf
# ---------------------------------------------------------------------------

class TestP0B:
    """P4-T06 → P4-T10 — Guard NaN/±inf dans SuccessCriterion.evaluate()."""

    def test_p4_t06_nan_returns_zero_not_one(self):
        """P4-T06 : NaN doit retourner 0.0, pas 1.0 (bug Python max/min)."""
        criterion = SuccessCriterion(
            name="nan_test",
            description="Retourne NaN",
            evaluate_fn=lambda _: float("nan"),
        )
        score = criterion.evaluate("anything")
        assert score == 0.0, f"NaN → score attendu 0.0, obtenu {score}"
        assert criterion.clamped is True

    def test_p4_t07_positive_inf_returns_zero(self):
        """P4-T07 : +inf doit retourner 0.0 (score invalide), pas 1.0."""
        criterion = SuccessCriterion(
            name="inf_test",
            description="Retourne +inf",
            evaluate_fn=lambda _: float("inf"),
        )
        score = criterion.evaluate("anything")
        assert score == 0.0, f"+inf → score attendu 0.0, obtenu {score}"
        assert criterion.clamped is True

    def test_p4_t08_negative_inf_returns_zero(self):
        """P4-T08 : -inf doit retourner 0.0 (score invalide)."""
        criterion = SuccessCriterion(
            name="neginf_test",
            description="Retourne -inf",
            evaluate_fn=lambda _: float("-inf"),
        )
        score = criterion.evaluate("anything")
        assert score == 0.0, f"-inf → score attendu 0.0, obtenu {score}"

    def test_p4_t09_evaluate_stateless_nan_score_invalid(self):
        """P4-T09 : evaluate_stateless() doit marquer score_invalid=True pour NaN."""
        criterion = SuccessCriterion(
            name="nan_stateless",
            description="Stateless NaN test",
            evaluate_fn=lambda _: float("nan"),
        )
        result = criterion.evaluate_stateless("x")
        assert isinstance(result, CriterionResult)
        assert result.score == 0.0
        assert result.score_invalid is True
        assert result.clamped is True

    def test_p4_t10_valid_score_not_affected_by_guard(self):
        """P4-T10 : Un score valide dans [0, 1] n'est pas modifié par le guard."""
        criterion = SuccessCriterion(
            name="valid",
            description="Score valide",
            evaluate_fn=lambda _: 0.75,
        )
        score = criterion.evaluate("x")
        assert score == 0.75
        assert criterion.clamped is False
        # evaluate_stateless aussi
        cr = criterion.evaluate_stateless("x")
        assert cr.score == 0.75
        assert cr.score_invalid is False
        assert cr.clamped is False


# ---------------------------------------------------------------------------
# P1-A : isolation des états mutables (check_stateless / evaluate_stateless)
# ---------------------------------------------------------------------------

class TestP1A:
    """P4-T11 → P4-T15 — Isolation états mutables inter-cycles."""

    def test_p4_t11_check_stateless_does_not_set_violated(self):
        """P4-T11 : check_stateless() ne doit pas écrire sur HardLimit.violated."""
        limit = HardLimit(
            name="pass",
            description="Toujours vraie",
            check_fn=lambda _: True,
        )
        assert limit.violated is False
        result = limit.check_stateless("anything")
        assert isinstance(result, LimitCheckResult)
        assert result.violated is False
        # L'instance globale ne doit PAS avoir été mutée
        assert limit.violated is False  # toujours False, inchangé

    def test_p4_t12_check_stateless_violation_raises_not_sets_flag(self):
        """P4-T12 : check_stateless() lève l'exception sans muter violated."""
        limit = HardLimit(
            name="always_fail",
            description="Toujours fausse",
            check_fn=lambda _: False,
            violated=False,  # état initial
        )
        with pytest.raises(LimitViolationError):
            limit.check_stateless("x")
        # L'état de l'instance globale ne doit PAS avoir changé
        assert limit.violated is False, (
            "check_stateless() ne doit pas muter violated sur l'instance globale"
        )

    def test_p4_t13_evaluate_stateless_does_not_mutate_last_score(self):
        """P4-T13 : evaluate_stateless() ne doit pas écrire sur last_score."""
        criterion = SuccessCriterion(
            name="immutable",
            description="Test immutabilité",
            evaluate_fn=lambda _: 0.9,
            last_score=0.0,
        )
        cr = criterion.evaluate_stateless("x")
        assert cr.score == 0.9
        # L'instance globale ne doit PAS avoir été mutée
        assert criterion.last_score == 0.0, (
            "evaluate_stateless() ne doit pas muter last_score sur l'instance globale"
        )
        assert criterion.clamped is False

    def test_p4_t14_two_cycles_isolated(self):
        """P4-T14 : Deux cycles consécutifs ne partagent pas d'état via evaluate_stateless()."""
        criterion = SuccessCriterion(
            name="cycle_isolation",
            description="Test isolation deux cycles",
            evaluate_fn=lambda r: float(r),
        )
        cr1 = criterion.evaluate_stateless(0.3)
        cr2 = criterion.evaluate_stateless(0.8)
        assert cr1.score == 0.3
        assert cr2.score == 0.8
        # L'instance globale n'a pas bougé
        assert criterion.last_score == 0.0

    def test_p4_t15_check_all_limits_uses_stateless_internally(self):
        """P4-T15 : check_all_limits() utilise check_stateless() — violated reste False."""
        limit = HardLimit(
            name="pass_stateless",
            description="Limite qui passe",
            check_fn=lambda _: True,
            violated=False,
        )
        contract = _make_simple_contract(limits=[limit])
        contract.check_all_limits("ok")
        # violated ne doit pas avoir bougé car check_stateless ne mute pas
        assert limit.violated is False


# ---------------------------------------------------------------------------
# P1-B : critical_traceability_keys bloquantes
# ---------------------------------------------------------------------------

class TestP1B:
    """P4-T16 → P4-T20 — Clés critiques de traçabilité bloquantes."""

    def test_p4_t16_critical_key_present_no_error(self):
        """P4-T16 : Clé critique présente dans la trace → pas d'erreur."""
        contract = _make_simple_contract(
            critical_keys=["operator_id", "cycle_ref"],
        )
        trace = _make_trace(steps=["operator_id:SE", "cycle_ref:cycle_001"])
        t_start = time.time_ns()

        result, final_trace = contract.finalize_trace("output", trace, t_start)
        assert result == "output"
        assert final_trace.limits_violated == []

    def test_p4_t17_critical_key_missing_raises(self):
        """P4-T17 : Clé critique absente → CriticalTraceabilityError levée."""
        contract = _make_simple_contract(
            critical_keys=["mandatory_key"],
        )
        trace = _make_trace(steps=["other_stuff:present"])
        t_start = time.time_ns()

        with pytest.raises(CriticalTraceabilityError) as exc_info:
            contract.finalize_trace("output", trace, t_start)

        assert "mandatory_key" in exc_info.value.missing_keys

    def test_p4_t18_critical_key_missing_with_fallback(self):
        """P4-T18 : Clé critique absente avec fallback → pas de raise, fallback retourné."""
        contract = _make_simple_contract(
            critical_keys=["required_key"],
        )
        trace = _make_trace(steps=["unrelated:step"])
        t_start = time.time_ns()

        result, final_trace = contract.finalize_trace(
            "output", trace, t_start, fallback_result="SAFE_DEFAULT"
        )
        assert result == "SAFE_DEFAULT"
        assert any(
            "CRITICAL_TRACEABILITY_MISSING" in step
            for step in final_trace.intermediate_steps
        )

    def test_p4_t19_non_critical_key_missing_is_warning_only(self):
        """P4-T19 : Clé non-critique manquante → warning dans steps, pas d'exception."""
        contract = _make_simple_contract(
            traceability=["optional_key"],
            critical_keys=[],  # aucune clé critique
        )
        trace = _make_trace(steps=["unrelated:step"])
        t_start = time.time_ns()

        # Ne doit PAS lever d'exception
        result, final_trace = contract.finalize_trace("output", trace, t_start)
        assert result == "output"
        assert any(
            "TRACEABILITY_MISSING_KEYS" in step
            for step in final_trace.intermediate_steps
        )

    def test_p4_t20_critical_subset_of_traceability(self):
        """P4-T20 : critical_keys est un sous-ensemble de traceability.
        Si la clé critique est présente mais les non-critiques manquent,
        seuls les warnings sont produits (pas d'exception)."""
        contract = _make_simple_contract(
            traceability=["critical_key", "optional_key"],
            critical_keys=["critical_key"],  # seulement critical_key est bloquante
        )
        # Trace avec la clé critique mais sans l'optionnelle
        trace = _make_trace(steps=["critical_key:value_present"])
        t_start = time.time_ns()

        # Doit réussir malgré l'absence de optional_key
        result, final_trace = contract.finalize_trace("output", trace, t_start)
        assert result == "output"
        # Le warning sur optional_key doit être dans les steps
        assert any(
            "TRACEABILITY_MISSING_KEYS" in step
            for step in final_trace.intermediate_steps
        )
        # Mais pas d'erreur critique
        assert not any(
            "CRITICAL_TRACEABILITY_MISSING" in step
            for step in final_trace.intermediate_steps
        )
