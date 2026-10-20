"""
learning/__init__.py — Package apprentissage LuCY

CERTIFIED_100=false | unique_human_proven=false
"""

from .feedback_processor import (
    FeedbackProcessor,
    FeedbackRecord,
    UpdateInstruction,
    FEEDBACK_MIN,
    FEEDBACK_MAX,
    SMOOTHING_WINDOW,
)
from .weight_updater import (
    WeightUpdater,
    WeightUpdateReport,
    WeightDelta,
)

__all__ = [
    "FeedbackProcessor",
    "FeedbackRecord",
    "UpdateInstruction",
    "WeightUpdater",
    "WeightUpdateReport",
    "WeightDelta",
    "FEEDBACK_MIN",
    "FEEDBACK_MAX",
    "SMOOTHING_WINDOW",
]
