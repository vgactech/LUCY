"""
__init__.py — Module functions LuCY

Phase 2 : exports des contrats opérationnels + OperatorContract/OperatorTrace
Phase 3 (audit) : export de LimitViolationError (P0-A)
Phase 4 (audit critique) : export CriticalTraceabilityError, LimitCheckResult,
                           CriterionResult (P0-A/P0-B/P1-A/P1-B)
"""
from .contracts import CONTRACT_FE, CONTRACT_FI, CONTRACT_NE, CONTRACT_NI
from .contracts import CONTRACT_SE, CONTRACT_SI, CONTRACT_TE, CONTRACT_TI
from .contracts import all_contracts, get_contract
from .types import (
    AbstractPattern,
    ActionDecision,
    CriticalTraceabilityError,
    CriterionResult,
    ExternalJudgment,
    HardLimit,
    Hypothesis,
    HypothesisSet,
    InternalModel,
    InternalValue,
    LimitCheckResult,
    LimitViolationError,
    OperatorContract,
    OperatorTrace,
    PerceptualFact,
    RelationalValue,
    SubjectiveImpression,
    SuccessCriterion,
)
