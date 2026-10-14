"""
__init__.py — Module functions LuCY

Phase 2 : exports des contrats opérationnels + OperatorContract/OperatorTrace
Phase 3 (audit) : export de LimitViolationError (P0-A)
"""
from .contracts import CONTRACT_FE, CONTRACT_FI, CONTRACT_NE, CONTRACT_NI
from .contracts import CONTRACT_SE, CONTRACT_SI, CONTRACT_TE, CONTRACT_TI
from .contracts import all_contracts, get_contract
from .types import (
    AbstractPattern,
    ActionDecision,
    ExternalJudgment,
    HardLimit,
    Hypothesis,
    HypothesisSet,
    InternalModel,
    InternalValue,
    LimitViolationError,
    OperatorContract,
    OperatorTrace,
    PerceptualFact,
    RelationalValue,
    SubjectiveImpression,
    SuccessCriterion,
)
