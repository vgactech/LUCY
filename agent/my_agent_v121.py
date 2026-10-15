"""LuCY Cognitive Agent v12.1 — ARC-AGI-3 (arc-prize-2026)

This is the ONLY file edited in the Kaggle Starter. `scripts/build_notebook.py`
splices the contents of this file into the Kaggle submission notebook.

[edit my_agent.py] → [make play-local] → [make submit]

Architecture v12.1 — LuCY FORENSIC MAX + GOAL-DELTA ENGINE (FIXED)
  D-LUCY-001: LuCY IS her own cognitive model — NO external LLM whatsoever.
  Intelligence emerges from:
    1. Direct grid perception    (_GridPerceptor)       — from v10.0
    2. Episodic memory           (_EpisodicMemory)      — from v10.0
    3. Cognitive scoring engine  (_CognitiveEngine)     — from v10.0
    4. Program synthesis engine  (_RuleMemory)          — from v11.0
    5. Goal-delta minimiser      (_GoalDeltaTracker)    — v12.0 (goal_found=false)
    6. Forensic logger MAXIMAL   (_KaggleForensicLogger v2) — v12.0
    7. Levels-completed progress signal                 — NEW v12.1

Fixes from v12.0 (audit L-032):

  FIX P0-A — win_levels FALSE LEVEL_UP at init:
    BEFORE: level_up triggered if current_win > self._win_levels (0 initially),
            but win_levels in FrameData = total levels in the game (6–10),
            NOT levels completed by LuCY. This caused a false LEVEL_UP on the
            very first frame of every game.
    AFTER:  win_levels_at_game_start captured at first frame.
            level_up is triggered ONLY if levels_completed increases
            (current_levels > self._levels_completed). win_levels is retained
            as metadata only; never used as a win signal.

  FIX P0-B — _GoalDeltaTracker inactive (goal_found=false on all 25 games):
    BEFORE: W_GOAL_DELTA=5.0 was always in score formula but goal_delta_map()
            returned None when goal_found=False → poids wasted, no real signal.
    AFTER:  When goal_found=False, a levels_completed delta signal replaces it:
            if levels_completed just increased, the previous action gets a
            LEVELS_PROGRESS_BONUS=5.0 added to its score. This gives LuCY a
            real learning signal even without a goal frame.

  FIX P0-C — visual change ≠ progression:
    BEFORE: n_progress[v] was incremented if delta >= DELTA_MIN (visual change
            in the grid). This rewarded actions that changed the image without
            verifying any progression toward winning.
    AFTER:  n_progress_real[v] is incremented ONLY if levels_completed increases
            (true progression signal). Visual delta is tracked separately as
            n_visual_change[v] for debugging. The score formula uses
            n_progress_real, not the visual delta counter.

  FIX P1-D — unproductive loops on single-action games:
    BEFORE: 6 games had available_actions=[6] throughout; LuCY repeated
            ACTION6×79 with no alternative strategy.
    AFTER:  same_state_streak counter: if fp unchanged for SINGLE_ACTION_LOOP_THRESHOLD
            consecutive steps AND only 1 candidate action, force RESET to break
            the loop early and reallocate budget.

Kept from v12.0:
  _GridPerceptor, _EpisodicMemory, _CognitiveEngine, _RuleMemory, _TransformType.
  _frame_fingerprint / _frame_delta / _pixel_diff_detail utilities.
  _KaggleForensicLogger v2, _GoalDeltaTracker (kept for future goal detection).
  All BUG-B1/B2/B3/C1/C3/C4/C5/C7/D1 fixes remain active.
  ACTION_ID_AUDIT, FRAME_INVENTORY, pixel_diff_detail all preserved.

CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections import Counter, defaultdict
from typing import Any, Optional

from arcengine import FrameData, GameAction, GameState
from agents.agent import Agent

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

VERSION = "12.1"
DEBUG = True  # PROTOCOLE_ARTCB: always DEBUG until user disables explicitly

# Action budgets — C-003 curriculum phase (2026-10-15): extended for r11l diagnosis
# AVANT: MAX_ACTIONS_TOTAL=80, MAX_ACTIONS_PER_LEVEL=30
# APRÈS: MAX_ACTIONS_TOTAL=200, MAX_ACTIONS_PER_LEVEL=80
MAX_ACTIONS_TOTAL = 200
MAX_ACTIONS_PER_LEVEL = 80

# Stagnation detection
STUCK_THRESHOLD = 5
RESET_AFTER_STUCK = 5

# FIX P1-D: single-action loop detection threshold
SINGLE_ACTION_LOOP_THRESHOLD = 8  # consecutive same-fp with 1 candidate → RESET

# Cognitive scoring weights
W_MEMORY = 3.0
W_PROGRESS = 2.0
W_DIVERSITY = 1.0
W_PERCEPTION = 1.5
W_GOAL_DELTA = 5.0        # active only when goal_found=True
LEVELS_PROGRESS_BONUS = 5.0  # FIX P0-B: replaces W_GOAL_DELTA when goal_found=False

# Program synthesis constants (from v11.0)
PS_CONFIDENCE_THRESHOLD = 1.5
PS_VERIFY_REWARD = 1.0
PS_CONTRADICT_DECAY = 0.8
PS_MAX_HYPOTHESES = 32

# Minimum delta to count as visual change
DELTA_MIN = 0.01

# Grid feature weights for perception hint
_COMPLEX_ACTIONS = {6}
_SIMPLE_ACTIONS = {1, 2, 3, 4, 5, 7}

# GameAction valid IDs (0-7 only — engine constraint, documented P0)
_VALID_GAMEACTION_IDS = frozenset(a.value for a in GameAction)


# ──────────────────────────────────────────────────────────────────────────────
# KAGGLE FORENSIC LOGGER v2 — MAXIMAL GRANULARITY (unchanged from v12.0)
# ──────────────────────────────────────────────────────────────────────────────

class _KaggleForensicLogger:
    """Inline nanosecond forensic logger v2 — FORENSIC_MAX mode.

    All events emitted to stdout (Kaggle console) as JSON Lines.
    Prefix format: [LuCY-NS:<ts_ns>] <EVENT_TYPE> | <json>

    v12.1 additions:
      - LEVELS_PROGRESS: emitted when levels_completed increases
      - SINGLE_ACTION_LOOP: emitted when P1-D loop detected

    CERTIFIED_100=false | unique_human_proven=false
    """

    PREFIX = "[LuCY-NS"
    SCHEMA_VERSION = "2.1"

    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self._events: list[dict] = []
        self._game_start_ns: int = time.monotonic_ns()
        self._wall_start_ns: int = time.time_ns()
        self._done_emitted: bool = False
        self._frame_inventory_done: bool = False
        self._seq: int = 0

        # P0 action-space audit counters
        self._action_id_known: int = 0
        self._action_id_unknown: Counter[int] = Counter()
        self._action_id_fallback: int = 0

        self._emit("GAME_INIT", {
            "game_id": game_id,
            "version": VERSION,
            "schema_version": self.SCHEMA_VERSION,
            "max_actions_total": MAX_ACTIONS_TOTAL,
            "max_actions_per_level": MAX_ACTIONS_PER_LEVEL,
            "ps_confidence_threshold": PS_CONFIDENCE_THRESHOLD,
            "valid_gameaction_ids": sorted(_VALID_GAMEACTION_IDS),
            "program_synthesis": True,
            "goal_delta_engine": True,
            "cognitive_engine": True,
            "external_llm": False,
            "certified_100": False,
            "unique_human_proven": False,
            "debug": DEBUG,
            "fix_p0a_win_levels": True,
            "fix_p0b_levels_progress_signal": True,
            "fix_p0c_real_progress_counter": True,
            "fix_p1d_single_action_loop": True,
            "note_timing": (
                "ts_ns=time.time_ns() civil clock; "
                "elapsed_ns=time.monotonic_ns() monotone; "
                "resolution_claimed=nanosecond_unit_not_guaranteed_precision"
            ),
        })

    def _emit(self, event_type: str, payload: dict) -> None:
        ts_ns = time.time_ns()
        mono_ns = time.monotonic_ns()
        elapsed_ns = mono_ns - self._game_start_ns
        self._seq += 1
        entry = {
            "schema_version": self.SCHEMA_VERSION,
            "seq": self._seq,
            "ts_ns": ts_ns,
            "elapsed_ns": elapsed_ns,
            "event": event_type,
            "game_id": self.game_id,
            **payload,
        }
        self._events.append(entry)
        line = json.dumps(entry, separators=(",", ":"), default=str)
        print(f"{self.PREFIX}:{ts_ns}] {event_type} | {line}", flush=True)

    # ── Frame inventory (P0 audit — first frame only) ──────────────────────

    def on_frame_inventory(self, frame_data: FrameData) -> None:
        """Inspect ALL attributes of FrameData — emitted once per game."""
        if self._frame_inventory_done:
            return
        self._frame_inventory_done = True

        attrs: dict = {}
        for attr_name in dir(frame_data):
            if attr_name.startswith("_"):
                continue
            try:
                val = getattr(frame_data, attr_name)
            except Exception as e:
                attrs[attr_name] = {"error": str(e)}
                continue
            if callable(val):
                continue
            try:
                t = type(val).__name__
                if hasattr(val, "shape"):
                    attrs[attr_name] = {"type": t, "shape": list(val.shape), "dtype": str(val.dtype)}
                elif isinstance(val, (list, tuple)):
                    attrs[attr_name] = {
                        "type": t,
                        "len": len(val),
                        "sample": val[:3] if len(val) > 0 else [],
                    }
                elif isinstance(val, (int, float, bool, str)):
                    attrs[attr_name] = {"type": t, "value": val}
                else:
                    attrs[attr_name] = {"type": t, "repr": str(val)[:120]}
            except Exception as e:
                attrs[attr_name] = {"error": str(e)}

        goal_attrs = {k: v for k, v in attrs.items()
                      if any(kw in k.lower() for kw in ["goal", "target", "example", "puzzle", "answer", "output"])}

        self._emit("FRAME_INVENTORY", {
            "total_attrs": len(attrs),
            "all_attrs": attrs,
            "goal_related_attrs": goal_attrs,
            "available_actions_raw": getattr(frame_data, "available_actions", "NOT_FOUND"),
            "available_actions_type": type(getattr(frame_data, "available_actions", None)).__name__,
            "win_levels_present": hasattr(frame_data, "win_levels"),
            "levels_completed_present": hasattr(frame_data, "levels_completed"),
        })

    # ── Action ID audit (P0) ───────────────────────────────────────────────

    def on_action_id_unknown(self, raw_id: int, attempt_count: int) -> None:
        self._action_id_unknown[raw_id] += 1
        if attempt_count <= 3:
            self._emit("ACTION_ID_UNKNOWN", {
                "raw_id": raw_id,
                "attempt_count": attempt_count,
                "valid_range": "0-7",
                "note": "GameAction.from_id() raises ValueError for this ID",
                "implication": "This game uses action IDs outside the 0-7 range; LuCY cannot execute them",
            })

    def on_action_id_audit(self, raw_ids: list[int], known: list[int], unknown: list[int]) -> None:
        self._emit("ACTION_ID_AUDIT", {
            "raw_ids": raw_ids,
            "known_ids": known,
            "unknown_ids": unknown,
            "n_known": len(known),
            "n_unknown": len(unknown),
            "fallback_triggered": len(unknown) > 0 and len(known) == 0,
        })

    # ── Goal delta (P1) ───────────────────────────────────────────────────

    def on_goal_delta(self, goal_found: bool, goal_attr: str, goal_delta: float) -> None:
        self._emit("GOAL_DELTA", {
            "goal_found": goal_found,
            "goal_attr_used": goal_attr,
            "goal_delta": round(goal_delta, 5) if goal_delta >= 0 else None,
            "note": "goal_delta=fraction of pixels differing from goal frame; 0.0=perfect match",
        })

    # ── FIX P0-B: levels progress signal ──────────────────────────────────

    def on_levels_progress(self, action_name: str, old_levels: int, new_levels: int, bonus: float) -> None:
        """FIX P0-B: emitted when levels_completed increases — real progress signal."""
        self._emit("LEVELS_PROGRESS", {
            "action": action_name,
            "old_levels_completed": old_levels,
            "new_levels_completed": new_levels,
            "levels_progress_bonus": bonus,
            "note": "FIX-P0B: real progress signal based on levels_completed, not visual delta",
        })

    # ── FIX P1-D: single-action loop detection ────────────────────────────

    def on_single_action_loop(self, streak: int, candidate: str, budget_remaining: int) -> None:
        """FIX P1-D: emitted when same-state + 1-candidate loop detected."""
        self._emit("SINGLE_ACTION_LOOP", {
            "same_state_streak": streak,
            "only_candidate": candidate,
            "budget_remaining": budget_remaining,
            "action": "FORCE_RESET",
            "note": "FIX-P1D: breaking unproductive single-action loop",
        })

    # ── Per-action forensics ───────────────────────────────────────────────

    def on_perception(self, features: dict) -> None:
        self._emit("PERCEPTION", features)

    def on_cognitive_score(self, scores: dict) -> None:
        self._emit("COGNITIVE_SCORE", scores)

    def on_synthesis_hypothesis(self, payload: dict) -> None:
        self._emit("PS_HYPOTHESIS", payload)

    def on_synthesis_follow(self, action_name: str, confidence: float) -> None:
        self._emit("PS_FOLLOW", {"action": action_name, "confidence": round(confidence, 3)})

    def on_action_before(
        self,
        action_count: int,
        phase: str,
        candidates: list[GameAction],
        fp: str,
        stuck_streak: int,
        levels_completed: int,
        win_levels: int,
        win_levels_at_start: int,
        raw_available_ids: list[int],
        goal_delta: float,
        frame_shape: Any,
    ) -> int:
        """Full pre-action state snapshot — v12.1 adds win_levels_at_start."""
        ts_before = time.monotonic_ns()
        known_ids = [i for i in raw_available_ids if i in _VALID_GAMEACTION_IDS]
        unknown_ids = [i for i in raw_available_ids if i not in _VALID_GAMEACTION_IDS]
        self._action_id_known += len(known_ids)
        if unknown_ids:
            self._action_id_fallback += 1

        self._emit("ACTION_BEFORE", {
            "action_count": action_count,
            "phase": phase,
            "fp_prefix": fp[:8],
            "stuck_streak": stuck_streak,
            "levels_completed": levels_completed,
            "win_levels": win_levels,
            "win_levels_at_game_start": win_levels_at_start,
            "win_levels_is_game_total": True,
            "n_candidates": len(candidates),
            "candidates": [a.name for a in candidates],
            "raw_available_ids": raw_available_ids,
            "raw_known_ids": known_ids,
            "raw_unknown_ids": unknown_ids,
            "n_unknown_ids": len(unknown_ids),
            "goal_delta_before": round(goal_delta, 5) if goal_delta >= 0 else None,
            "frame_shape": _describe_shape(frame_shape),
            "ts_before_monotone_ns": ts_before,
            "note_fix_p0a": "win_levels = total game levels, NOT Lucy wins. level_up uses levels_completed only.",
        })
        return ts_before

    def on_action_after(
        self,
        action_count: int,
        action_name: str,
        phase: str,
        ts_before_ns: int,
        is_complex: bool,
        pixel_diff: dict,
        goal_delta_after: float,
        goal_delta_improvement: float,
        transform_type: str,
    ) -> None:
        ts_after = time.monotonic_ns()
        self._emit("ACTION_AFTER", {
            "action_count": action_count,
            "action": action_name,
            "phase": phase,
            "is_complex": is_complex,
            "selection_dur_ns": ts_after - ts_before_ns,
            "pixel_diff": pixel_diff,
            "goal_delta_after": round(goal_delta_after, 5) if goal_delta_after >= 0 else None,
            "goal_delta_improvement": round(goal_delta_improvement, 5),
            "transform_type": transform_type,
            "note_pixel_diff": (
                "changed_frac=fraction of grid cells that differ; "
                "added=cells that became nonzero; removed=cells that became zero"
            ),
        })

    def on_level_up(self, old_level: int, new_level: int, old_win: int, new_win: int, actions_this_level: int) -> None:
        self._emit("LEVEL_UP", {
            "old_levels_completed": old_level,
            "new_levels_completed": new_level,
            "old_win_levels": old_win,
            "new_win_levels": new_win,
            "actions_this_level": actions_this_level,
            "note_fix_p0a": "LEVEL_UP now triggered only on levels_completed increase, not win_levels change",
        })

    def on_stuck(self, streak: int, phase: str) -> None:
        self._emit("STUCK", {"streak": streak, "phase": phase})

    def on_reset(self, reason: str, action_count: int, budget_remaining: int, stuck_streak: int) -> None:
        self._emit("RESET", {
            "reason": reason,
            "action_count": action_count,
            "budget_remaining": budget_remaining,
            "stuck_streak_at_reset": stuck_streak,
        })

    def on_model_update(self, action_name: str, level_up: bool, visual_delta: float,
                        real_progress: bool, n_total: int) -> None:
        self._emit("MODEL_UPDATE", {
            "action": action_name,
            "level_up": level_up,
            "visual_delta": round(visual_delta, 4),
            "real_progress": real_progress,
            "note_fix_p0c": "real_progress=True only when levels_completed increased",
            "n_total": n_total,
        })

    def on_done(self, reason: str, levels_completed: int, win_levels: int,
                win_levels_at_start: int, total_actions: int,
                n_progress_real: dict, n_visual_change: dict) -> None:
        """BUG-C7 fix: guarded by _done_emitted."""
        if self._done_emitted:
            return
        self._done_emitted = True
        elapsed_ns = time.monotonic_ns() - self._game_start_ns

        action_id_audit = {
            "known_ids_total": self._action_id_known,
            "unknown_ids_by_value": dict(self._action_id_unknown),
            "fallback_triggered_count": self._action_id_fallback,
            "top_unknown": self._action_id_unknown.most_common(5),
        }

        self._emit("GAME_DONE", {
            "reason": reason,
            "levels_completed": levels_completed,
            "win_levels_at_end": win_levels,
            "win_levels_at_start": win_levels_at_start,
            "real_level_ups": levels_completed,
            "total_actions": total_actions,
            "elapsed_ns": elapsed_ns,
            "elapsed_ms": round(elapsed_ns / 1_000_000, 2),
            "total_events": len(self._events),
            "action_id_audit": action_id_audit,
            "n_progress_real": n_progress_real,
            "n_visual_change": n_visual_change,
            "note_fix_p0a": "win_levels_at_start captured at first frame; level_up=levels_completed only",
            "note_fix_p0b": "levels_progress_bonus applied to scoring when goal_found=False",
            "note_fix_p0c": "n_progress_real counts true level progressions only",
        })
        summary = {
            "lucy_forensic_summary": True,
            "version": VERSION,
            "game_id": self.game_id,
            "levels_completed": levels_completed,
            "win_levels_at_start": win_levels_at_start,
            "win_levels_at_end": win_levels,
            "total_actions": total_actions,
            "elapsed_ms": round(elapsed_ns / 1_000_000, 2),
            "total_events": len(self._events),
            "action_id_audit": action_id_audit,
            "program_synthesis": True,
            "goal_delta_engine": True,
            "cognitive_engine": True,
            "external_llm": False,
            "certified_100": False,
            "unique_human_proven": False,
        }
        print(f"{self.PREFIX}:SUMMARY] {json.dumps(summary, separators=(',', ':'))}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# UTILITIES (unchanged from v12.0)
# ──────────────────────────────────────────────────────────────────────────────

def _describe_shape(frame: Any) -> Any:
    """Return shape description for logging without serialising the full frame."""
    if frame is None:
        return None
    try:
        import numpy as np
        if isinstance(frame, np.ndarray):
            return {"type": "ndarray", "shape": list(frame.shape), "dtype": str(frame.dtype)}
    except ImportError:
        pass
    if isinstance(frame, list):
        if len(frame) == 0:
            return {"type": "list", "len": 0}
        if isinstance(frame[0], list):
            return {"type": "list2d", "rows": len(frame), "cols": len(frame[0]) if frame else 0}
        return {"type": "list", "len": len(frame)}
    return {"type": type(frame).__name__}


def _frame_fingerprint(frame: Any) -> str:
    """Compact SHA1-based fingerprint of the full visual game state."""
    if frame is None:
        return "null"
    try:
        import numpy as np
        if isinstance(frame, np.ndarray):
            return hashlib.sha1(frame.tobytes()).hexdigest()[:16]
        flat: list = []

        def _flatten(obj: Any) -> None:
            if isinstance(obj, np.ndarray):
                flat.extend(int(v) for v in obj.flatten())
            elif isinstance(obj, list):
                for item in obj:
                    _flatten(item)
            else:
                flat.append(obj)

        if isinstance(frame, list):
            _flatten(frame)
            return hashlib.sha1(str(flat).encode()).hexdigest()[:16]
        elif hasattr(frame, "__iter__"):
            flat = list(frame)
            return hashlib.sha1(str(flat).encode()).hexdigest()[:16]
        else:
            return str(frame)[:128]
    except Exception:
        return str(id(frame))[:16]


def _frame_delta(frame_a: Any, frame_b: Any) -> float:
    """Fraction of elements that differ between two frames (0.0 = identical)."""
    if frame_a is None or frame_b is None:
        return 1.0
    try:
        def _flatten(f: Any) -> list:
            out: list = []
            if isinstance(f, list):
                for item in f:
                    out.extend(_flatten(item))
            else:
                out.append(f)
            return out

        fa = _flatten(frame_a)
        fb = _flatten(frame_b)
        n = min(len(fa), len(fb))
        if n == 0:
            return 1.0
        return sum(1 for a, b in zip(fa, fb) if a != b) / n
    except Exception:
        return 1.0


def _pixel_diff_detail(frame_a: Any, frame_b: Any) -> dict:
    """Detailed pixel-level diff: changed, added, removed counts + fraction."""
    base = {
        "changed_pixels": 0, "changed_frac": 0.0,
        "added_pixels": 0, "removed_pixels": 0,
        "net_change": 0, "total_pixels": 0,
        "comparable": False,
    }
    if frame_a is None or frame_b is None:
        return base
    try:
        def _flatten(f: Any) -> list:
            out: list = []
            if isinstance(f, list):
                for item in f:
                    out.extend(_flatten(item))
            else:
                out.append(f)
            return out

        fa = _flatten(frame_a)
        fb = _flatten(frame_b)
        n = min(len(fa), len(fb))
        if n == 0:
            return base
        changed = sum(1 for a, b in zip(fa, fb) if a != b)
        added = sum(1 for a, b in zip(fa, fb) if a == 0 and b != 0)
        removed = sum(1 for a, b in zip(fa, fb) if a != 0 and b == 0)
        return {
            "changed_pixels": changed,
            "changed_frac": round(changed / n, 6),
            "added_pixels": added,
            "removed_pixels": removed,
            "net_change": added - removed,
            "total_pixels": n,
            "comparable": True,
        }
    except Exception:
        return base


def _get_available_actions(latest_frame: FrameData, logger: Optional[_KaggleForensicLogger] = None) -> tuple[list[GameAction], list[int]]:
    """Extract available actions from frame; return (actions, raw_int_ids).

    P0 audit: logs unknown IDs that cannot be mapped to GameAction.
    Returns (list_of_valid_GameActions, list_of_all_raw_int_ids).
    Fallback to simple actions if no valid actions found.
    """
    raw_ids: list[int] = []
    avail_raw = getattr(latest_frame, "available_actions", None)
    if avail_raw:
        for a in avail_raw:
            if isinstance(a, int):
                raw_ids.append(a)
            elif isinstance(a, GameAction):
                raw_ids.append(a.value)

    result: list[GameAction] = []
    for raw_id in raw_ids:
        if isinstance(raw_id, GameAction):
            if raw_id is not GameAction.RESET:
                result.append(raw_id)
        else:
            if raw_id in _VALID_GAMEACTION_IDS:
                try:
                    ga = GameAction.from_id(raw_id)
                    if ga is not GameAction.RESET:
                        result.append(ga)
                except ValueError:
                    if logger:
                        logger.on_action_id_unknown(raw_id, logger._action_id_unknown.get(raw_id, 0) + 1)
            else:
                if logger:
                    cnt = logger._action_id_unknown[raw_id]
                    logger.on_action_id_unknown(raw_id, cnt + 1)

    if result:
        return result, raw_ids
    return [a for a in GameAction if a is not GameAction.RESET and a.is_simple()], raw_ids


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 1 — GRID PERCEPTOR (from v10.0, unchanged)
# ──────────────────────────────────────────────────────────────────────────────

class _GridPerceptor:
    """Direct visual perception of ARC-AGI-3 grids. D-LUCY-001: no external LLM."""

    def extract(self, frame: Any, prev_frame: Any = None) -> dict:
        features: dict = {
            "symmetry_h": 0.0, "symmetry_v": 0.0, "dominant_colour": 0,
            "complexity": 1, "active_ratio": 0.0, "colour_count": 1,
            "delta_mass": 0, "grid_valid": False,
            "active_count": 0, "rows": 0, "cols": 0,
            "centre_of_mass_r": 0.0, "centre_of_mass_c": 0.0,
        }
        grid = self._to_grid(frame)
        if grid is None or len(grid) == 0:
            return features
        features["grid_valid"] = True
        rows = len(grid)
        cols = max(len(r) for r in grid) if grid else 0
        if cols == 0:
            return features
        features["rows"] = rows
        features["cols"] = cols

        def _scalar(v: Any) -> int:
            if isinstance(v, (list, tuple)):
                return _scalar(v[0]) if v else 0
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        mat = [[_scalar(grid[r][c] if c < len(grid[r]) else 0)
                for c in range(cols)] for r in range(rows)]
        all_vals = [mat[r][c] for r in range(rows) for c in range(cols)]
        counter = Counter(all_vals)
        features["dominant_colour"] = counter.most_common(1)[0][0] if counter else 0
        features["colour_count"] = len(counter)
        features["complexity"] = len([v for v in counter if v != 0]) or 1

        total = rows * cols
        active = sum(1 for v in all_vals if v != 0)
        features["active_ratio"] = active / max(1, total)
        features["active_count"] = active

        if active > 0:
            sum_r = sum(r for r in range(rows) for c in range(cols) if mat[r][c] != 0)
            sum_c = sum(c for r in range(rows) for c in range(cols) if mat[r][c] != 0)
            features["centre_of_mass_r"] = sum_r / active
            features["centre_of_mass_c"] = sum_c / active

        if rows >= 2:
            h_matches = h_total = 0
            for c in range(cols):
                for dr in range(rows // 2):
                    r1, r2 = dr, rows - 1 - dr
                    h_total += 1
                    if mat[r1][c] == mat[r2][c]:
                        h_matches += 1
            features["symmetry_h"] = h_matches / max(1, h_total)

        if cols >= 2:
            v_matches = v_total = 0
            for r in range(rows):
                for dc in range(cols // 2):
                    c1, c2 = dc, cols - 1 - dc
                    v_total += 1
                    if mat[r][c1] == mat[r][c2]:
                        v_matches += 1
            features["symmetry_v"] = v_matches / max(1, v_total)

        if prev_frame is not None:
            prev_grid = self._to_grid(prev_frame)
            if prev_grid is not None:
                prev_active = sum(1 for row in prev_grid for v in row if v != 0)
                features["delta_mass"] = active - prev_active

        return features

    @staticmethod
    def _to_grid(frame: Any) -> Optional[list]:
        if frame is None:
            return None
        try:
            import numpy as np
            if isinstance(frame, np.ndarray):
                if frame.ndim == 2:
                    return frame.tolist()
                if frame.ndim == 3:
                    return frame[:, :, 0].tolist()
                return None
        except ImportError:
            pass
        if isinstance(frame, list):
            if len(frame) > 0 and isinstance(frame[0], list):
                return frame
            return [frame]
        return None


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 2 — EPISODIC MEMORY (from v10.0, unchanged)
# ──────────────────────────────────────────────────────────────────────────────

class _EpisodicMemory:
    """Stores per-game experience: (fingerprint, action) → cumulative score."""

    LEVEL_UP_REWARD = 2.0
    PROGRESS_REWARD = 1.0
    NO_PROGRESS_DECAY = 0.1

    def __init__(self) -> None:
        self._scores: defaultdict[str, dict[int, float]] = defaultdict(dict)
        self._n_tried: Counter[int] = Counter()

    def record(self, fp: str, action: GameAction, level_up: bool, delta: float) -> None:
        v = action.value
        self._n_tried[v] += 1
        prev = self._scores[fp].get(v, 0.0)
        if level_up:
            self._scores[fp][v] = prev + self.LEVEL_UP_REWARD
        elif delta >= DELTA_MIN:
            self._scores[fp][v] = prev + self.PROGRESS_REWARD
        else:
            self._scores[fp][v] = prev - self.NO_PROGRESS_DECAY

    def memory_score(self, fp: str, action: GameAction) -> float:
        return self._scores[fp].get(action.value, 0.0)

    def best_on_state(self, fp: str, candidates: list[GameAction]) -> Optional[GameAction]:
        scores = {a: self._scores[fp].get(a.value, None) for a in candidates}
        known = {a: s for a, s in scores.items() if s is not None}
        if not known:
            return None
        return max(known, key=known.__getitem__)

    def n_tried(self, action: GameAction) -> int:
        return self._n_tried[action.value]


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 3 — COGNITIVE ENGINE (FIX P0-B + P0-C applied here)
# ──────────────────────────────────────────────────────────────────────────────

class _CognitiveEngine:
    """Scores available actions using cognitive signals + goal_delta OR levels_progress.

    FIX P0-B: When goal_found=False, uses levels_progress_map (action → bonus if
              that action previously triggered a levels_completed increase).
    FIX P0-C: Uses n_progress_real (levels-based) instead of n_progress (visual).
    """

    def __init__(self, memory: _EpisodicMemory, n_progress_real: Counter, n_total: Counter) -> None:
        self._memory = memory
        self._n_progress_real = n_progress_real
        self._n_total = n_total

    def score_all(
        self,
        fp: str,
        candidates: list[GameAction],
        features: dict,
        total_actions: int,
        goal_delta_map: Optional[dict[int, float]] = None,
        levels_progress_map: Optional[dict[int, float]] = None,
    ) -> dict[GameAction, float]:
        """Score all candidates.

        goal_delta_map: action.value → improvement (higher=better) — used when goal_found=True
        levels_progress_map: action.value → bonus — used when goal_found=False (FIX P0-B)
        FIX P0-C: prog based on n_progress_real (level-ups only), not visual delta.
        """
        scores: dict[GameAction, float] = {}
        max_tried = max((self._memory.n_tried(a) for a in candidates), default=1)
        for action in candidates:
            v = action.value
            n = max(self._n_total[v], 1)
            mem = self._memory.memory_score(fp, action)
            # FIX P0-C: use real progress (levels_completed) not visual delta
            prog = self._n_progress_real[v] / n
            tried = self._memory.n_tried(action)
            div = 1.0 - (tried / max(max_tried, 1))
            hint = self._perception_hint(features, action)
            base = W_MEMORY * mem + W_PROGRESS * prog + W_DIVERSITY * div + W_PERCEPTION * hint

            # FIX P0-B: goal_delta_map (goal_found=True) OR levels_progress_map (goal_found=False)
            if goal_delta_map is not None and v in goal_delta_map:
                base += W_GOAL_DELTA * goal_delta_map[v]
            elif levels_progress_map is not None and v in levels_progress_map:
                base += levels_progress_map[v]  # already scaled by LEVELS_PROGRESS_BONUS

            scores[action] = base
        return scores

    @staticmethod
    def _perception_hint(features: dict, action: GameAction) -> float:
        if not features.get("grid_valid", False):
            return 0.5
        sym = (features.get("symmetry_h", 0.0) + features.get("symmetry_v", 0.0)) / 2.0
        active = features.get("active_ratio", 0.5)
        complexity = features.get("complexity", 1)
        delta_mass = features.get("delta_mass", 0)
        v = action.value
        if v in _SIMPLE_ACTIONS:
            score = 0.5
            if sym > 0.7:
                score += 0.3
            if active < 0.2:
                score += 0.2
            if delta_mass > 0:
                score += 0.1
            return min(score, 1.0)
        if v in _COMPLEX_ACTIONS:
            score = 0.3
            if complexity >= 3:
                score += 0.3
            if active > 0.5:
                score += 0.2
            if sym < 0.5:
                score += 0.2
            return min(score, 1.0)
        return 0.5


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 4 — PROGRAM SYNTHESIS ENGINE (from v11.0, unchanged)
# ──────────────────────────────────────────────────────────────────────────────

class _TransformType:
    """Discrete transformation categories inferred from frame pairs."""
    IDENTITY = "IDENTITY"
    GROWING = "GROWING"
    SHRINKING = "SHRINKING"
    RECOLOR = "RECOLOR"
    SHIFT = "SHIFT"
    DELTA = "DELTA"
    UNKNOWN = "UNKNOWN"


class _RuleMemory:
    """Persists transformation hypotheses within one game (from v11.0)."""

    def __init__(self) -> None:
        self._rules: defaultdict[tuple, dict[str, float]] = defaultdict(dict)
        self._n_records: int = 0

    @staticmethod
    def state_signature(features: dict) -> str:
        dom = features.get("dominant_colour", 0)
        cplx = min(features.get("complexity", 1), 5)
        active_bucket = int(features.get("active_ratio", 0.5) * 4)
        return f"{dom}:{cplx}:{active_bucket}"

    def record(self, action: GameAction, pre_features: dict, post_features: dict, level_up: bool) -> str:
        sig = self.state_signature(pre_features)
        transform = self._classify(pre_features, post_features, level_up)
        key = (action.value, sig)
        prev = self._rules[key].get(transform, 0.0)
        if level_up:
            self._rules[key][transform] = prev + PS_VERIFY_REWARD * 2.0
        elif transform != _TransformType.IDENTITY:
            self._rules[key][transform] = prev + PS_VERIFY_REWARD
        else:
            for t in list(self._rules[key].keys()):
                if t != _TransformType.IDENTITY:
                    self._rules[key][t] = self._rules[key][t] * PS_CONTRADICT_DECAY
            self._rules[key][_TransformType.IDENTITY] = prev + 0.1
        if len(self._rules) > PS_MAX_HYPOTHESES:
            worst = min(self._rules.keys(), key=lambda k: sum(self._rules[k].values()))
            del self._rules[worst]
        self._n_records += 1
        return transform

    @staticmethod
    def _classify(pre: dict, post: dict, level_up: bool) -> str:
        if level_up:
            return _TransformType.GROWING
        pre_active = pre.get("active_count", 0)
        post_active = post.get("active_count", 0)
        pre_dom = pre.get("dominant_colour", 0)
        post_dom = post.get("dominant_colour", 0)
        pre_com_r = pre.get("centre_of_mass_r", 0.0)
        pre_com_c = pre.get("centre_of_mass_c", 0.0)
        post_com_r = post.get("centre_of_mass_r", 0.0)
        post_com_c = post.get("centre_of_mass_c", 0.0)
        if (pre_active == post_active and pre_dom == post_dom
                and abs(pre_com_r - post_com_r) < 0.5
                and abs(pre_com_c - post_com_c) < 0.5):
            return _TransformType.IDENTITY
        if pre_dom != post_dom:
            return _TransformType.RECOLOR
        shift = math.sqrt((pre_com_r - post_com_r) ** 2 + (pre_com_c - post_com_c) ** 2)
        if shift > 1.5:
            return _TransformType.SHIFT
        if post_active > pre_active:
            return _TransformType.GROWING
        if post_active < pre_active:
            return _TransformType.SHRINKING
        return _TransformType.DELTA

    def best_action(self, candidates: list[GameAction], pre_features: dict,
                    prefer_transform: str = _TransformType.GROWING) -> tuple[Optional[GameAction], float]:
        sig = self.state_signature(pre_features)
        best_action: Optional[GameAction] = None
        best_conf = 0.0
        for action in candidates:
            key = (action.value, sig)
            conf = self._rules[key].get(prefer_transform, 0.0)
            if conf > best_conf:
                best_conf = conf
                best_action = action
        return best_action, best_conf

    def n_records(self) -> int:
        return self._n_records


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 5 — GOAL-DELTA TRACKER (v12.0 — kept, goal_found still False in ARC3)
# ──────────────────────────────────────────────────────────────────────────────

class _GoalDeltaTracker:
    """Inspects FrameData for goal/target frame and tracks goal_delta per action.

    NOTE v12.1: goal_found=False on all 25 ARC-AGI-3 local games (confirmed L-032).
    Kept for future compatibility; FIX P0-B provides alternative signal via
    levels_progress_map when goal_found=False.
    """

    _GOAL_ATTRS = ["goal", "target", "answer", "output_grid", "expected_output",
                   "puzzle_output", "solution", "goal_frame", "target_frame"]

    def __init__(self) -> None:
        self._goal_frame: Any = None
        self._goal_attr: str = "NOT_FOUND"
        self._goal_found: bool = False
        self._prev_goal_delta: float = -1.0
        self._action_improvement: dict[int, float] = {}

    def inspect_frame(self, frame_data: FrameData) -> None:
        if self._goal_found:
            return
        for attr in self._GOAL_ATTRS:
            val = getattr(frame_data, attr, None)
            if val is not None:
                self._goal_frame = val
                self._goal_attr = attr
                self._goal_found = True
                return
        for attr in dir(frame_data):
            if attr.startswith("_") or attr in ("frame", "state", "game_id", "guid"):
                continue
            if any(kw in attr.lower() for kw in ["goal", "target", "answer", "output", "expect", "solution"]):
                val = getattr(frame_data, attr, None)
                if val is not None and not callable(val):
                    self._goal_frame = val
                    self._goal_attr = attr
                    self._goal_found = True
                    return

    def current_delta(self, current_frame: Any) -> float:
        if not self._goal_found or self._goal_frame is None:
            return -1.0
        return _frame_delta(current_frame, self._goal_frame)

    def record_action_result(self, action: GameAction, delta_after: float) -> float:
        if delta_after < 0:
            return 0.0
        prev = self._prev_goal_delta
        improvement = (prev - delta_after) if prev >= 0 else 0.0
        self._action_improvement[action.value] = improvement
        self._prev_goal_delta = delta_after
        return improvement

    def goal_delta_map(self, candidates: list[GameAction]) -> Optional[dict[int, float]]:
        if not self._goal_found:
            return None
        return {a.value: self._action_improvement.get(a.value, 0.0) for a in candidates}

    @property
    def goal_found(self) -> bool:
        return self._goal_found

    @property
    def goal_attr(self) -> str:
        return self._goal_attr

    @property
    def prev_goal_delta(self) -> float:
        return self._prev_goal_delta


# ──────────────────────────────────────────────────────────────────────────────
# MAIN AGENT — LuCY v12.1
# ──────────────────────────────────────────────────────────────────────────────

class MyAgent(Agent):
    """LuCY Noyau Cognitif v12.1 — 4 bugfixes (P0-A/B/C + P1-D).

    D-LUCY-001: LuCY IS her own type of cognitive model.

    Phases:
      EXPLORE  : try every available action at least once (diversity-first).
                 Feed (pre→action→post) pairs into _RuleMemory + _GoalDeltaTracker.
      EXPLOIT  : use synthesized rules if confidence > PS_CONFIDENCE_THRESHOLD,
                 or goal-delta minimisation if goal frame found,
                 else fall back to _CognitiveEngine scoring.
      RECOVER  : after stagnation, diversify or force RESET.

    Key fixes v12.1:
      P0-A: win_levels_at_game_start captured; LEVEL_UP on levels_completed only
      P0-B: levels_progress_map signal replaces W_GOAL_DELTA when goal_found=False
      P0-C: n_progress_real counts true level progressions only (not visual delta)
      P1-D: SINGLE_ACTION_LOOP_THRESHOLD → force RESET on 1-candidate loop

    CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
    """

    MAX_ACTIONS = MAX_ACTIONS_TOTAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))

        self._forensic = _KaggleForensicLogger(game_id=str(self.game_id))
        self._perceptor = _GridPerceptor()
        self._memory = _EpisodicMemory()
        self._rule_memory = _RuleMemory()
        self._goal_tracker = _GoalDeltaTracker()

        # FIX P0-C: separate real-progress counter (levels-based) from visual
        self._n_progress_real: Counter[int] = Counter()  # increments only on level_up
        self._n_visual_change: Counter[int] = Counter()  # increments on visual delta (kept for debug)
        self._n_total: Counter[int] = Counter()

        # FIX P0-B: levels_progress_map — action.value → bonus when that action caused level_up
        self._levels_progress_map: dict[int, float] = {}

        self._action_count: int = 0
        self._level_action_count: int = 0
        self._levels_completed: int = 0

        # FIX P0-A: capture win_levels at game start (= total game levels, NOT LuCY wins)
        self._win_levels_at_game_start: int = -1   # -1 = not yet captured
        self._win_levels_current: int = 0          # current observed value (metadata only)

        self._max_levels_seen: int = 0
        self._stuck_streak: int = 0
        self._same_state_streak: int = 0           # FIX P1-D
        self._prev_fp: str = ""
        self._prev_action: Optional[GameAction] = None
        self._prev_features: Optional[dict] = None
        self._prev_frame: Any = None

        self._phase: str = "explore"

        if DEBUG:
            print(
                f"[LuCY v{VERSION}] game_id={self.game_id!r} "
                f"FORENSIC_MAX+FIX_P0A_P0B_P0C_P1D external_llm=False "
                f"MAX_ACTIONS={MAX_ACTIONS_TOTAL}",
                flush=True,
            )

    @property
    def name(self) -> str:
        return f"LuCY-NoyauCognitif-v{VERSION}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        if latest_frame.state is GameState.WIN:
            self._forensic.on_done(
                "WIN", self._levels_completed, self._win_levels_current,
                self._win_levels_at_game_start, self._action_count,
                dict(self._n_progress_real), dict(self._n_visual_change),
            )
            return True
        if self._action_count >= MAX_ACTIONS_TOTAL - 1:
            self._forensic.on_done(
                "BUDGET_EXHAUSTED", self._levels_completed, self._win_levels_current,
                self._win_levels_at_game_start, self._action_count,
                dict(self._n_progress_real), dict(self._n_visual_change),
            )
            return True
        return False

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        self._action_count += 1
        self._level_action_count += 1

        # ── First frame: full inventory + capture win_levels_at_game_start ──
        if self._action_count == 1:
            self._forensic.on_frame_inventory(latest_frame)
            self._goal_tracker.inspect_frame(latest_frame)
            self._forensic.on_goal_delta(
                self._goal_tracker.goal_found,
                self._goal_tracker.goal_attr,
                self._goal_tracker.current_delta(latest_frame.frame),
            )
            # FIX P0-A: capture game total levels at first frame
            raw_win = getattr(latest_frame, "win_levels", 0) or 0
            self._win_levels_at_game_start = raw_win
            self._win_levels_current = raw_win
            if DEBUG:
                print(
                    f"[LuCY v{VERSION}] win_levels_at_game_start={self._win_levels_at_game_start} "
                    f"(= total game levels, NOT LuCY wins)",
                    flush=True,
                )

        # ── Terminal state → RESET ────────────────────────────────────────
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._level_action_count = 0
            self._stuck_streak = 0
            self._same_state_streak = 0
            self._prev_features = None
            self._prev_frame = None
            self._forensic.on_reset(
                f"state_{latest_frame.state.name}",
                self._action_count,
                MAX_ACTIONS_TOTAL - self._action_count,
                self._stuck_streak,
            )
            if DEBUG:
                print(f"[LuCY] state={latest_frame.state.name} → RESET", flush=True)
            return GameAction.RESET

        # ── Per-level budget exhausted → RESET ───────────────────────────
        if self._level_action_count > MAX_ACTIONS_PER_LEVEL:
            self._forensic.on_reset(
                "per_level_budget",
                self._action_count,
                MAX_ACTIONS_TOTAL - self._action_count,
                self._stuck_streak,
            )
            self._level_action_count = 0
            self._phase = "explore"
            self._stuck_streak = 0
            self._same_state_streak = 0
            self._prev_features = None
            self._prev_frame = None
            if DEBUG:
                print("[LuCY] per-level budget exhausted → RESET", flush=True)
            return GameAction.RESET

        # ── Available actions (P0 action-space audit) ─────────────────────
        candidates, raw_ids = _get_available_actions(latest_frame, self._forensic)
        if not candidates:
            candidates = [a for a in GameAction if a is not GameAction.RESET and a.is_simple()]

        # ── FIX P1-D: single-action loop detection ─────────────────────
        fp = _frame_fingerprint(latest_frame.frame)
        if fp == self._prev_fp:
            self._same_state_streak += 1
        else:
            self._same_state_streak = 0

        if (len(candidates) == 1
                and self._same_state_streak >= SINGLE_ACTION_LOOP_THRESHOLD):
            budget_remaining = MAX_ACTIONS_TOTAL - self._action_count
            self._forensic.on_single_action_loop(
                self._same_state_streak,
                candidates[0].name,
                budget_remaining,
            )
            self._forensic.on_reset(
                "single_action_loop",
                self._action_count,
                budget_remaining,
                self._stuck_streak,
            )
            self._same_state_streak = 0
            self._stuck_streak = 0
            self._level_action_count = 0
            self._phase = "explore"
            self._prev_features = None
            self._prev_frame = None
            if DEBUG:
                print(
                    f"[LuCY] FIX-P1D single_action_loop streak={self._same_state_streak} → RESET",
                    flush=True,
                )
            return GameAction.RESET

        # ── Goal delta — current state ─────────────────────────────────────
        goal_delta_current = self._goal_tracker.current_delta(latest_frame.frame)

        # ── Observe frame ─────────────────────────────────────────────────
        prev_raw = frames[-2].frame if len(frames) >= 2 else None
        features = self._perceptor.extract(latest_frame.frame, prev_raw)

        if DEBUG and self._action_count <= 3:
            self._forensic.on_perception({
                "action_count": self._action_count,
                "fp_prefix": fp[:8],
                **{k: round(v, 3) if isinstance(v, float) else v for k, v in features.items()},
            })

        # ── FIX P0-A: level_up only on levels_completed — NOT win_levels ──
        current_levels_raw = getattr(latest_frame, "levels_completed", 0) or 0
        current_win_raw = getattr(latest_frame, "win_levels", 0) or 0
        current_levels = max(current_levels_raw, self._max_levels_seen)
        self._max_levels_seen = current_levels
        self._win_levels_current = current_win_raw  # metadata only — never used for level_up

        # FIX P0-A: level_up = only when levels_completed increases
        level_up = current_levels > self._levels_completed
        if level_up:
            self._forensic.on_level_up(
                self._levels_completed, current_levels,
                self._win_levels_current, self._win_levels_current,
                self._level_action_count,
            )
            if DEBUG:
                print(
                    f"[LuCY v{VERSION}] LEVEL UP levels_completed={self._levels_completed}→{current_levels} "
                    f"(win_levels={self._win_levels_current} = game total, ignored for level_up)",
                    flush=True,
                )
            self._levels_completed = current_levels
            self._level_action_count = 0
            self._stuck_streak = 0
            self._same_state_streak = 0
            self._phase = "exploit"

        # ── Pixel diff + record outcome of previous action ────────────────
        pixel_diff: dict = {"comparable": False}
        goal_delta_after = -1.0
        goal_delta_improvement = 0.0
        transform_type = _TransformType.UNKNOWN

        if self._prev_action is not None and len(frames) >= 2:
            prev_frame_data = frames[-2]
            visual_delta = _frame_delta(prev_frame_data.frame, latest_frame.frame)

            pixel_diff = _pixel_diff_detail(prev_frame_data.frame, latest_frame.frame)

            goal_delta_after = self._goal_tracker.current_delta(latest_frame.frame)
            goal_delta_improvement = self._goal_tracker.record_action_result(
                self._prev_action, goal_delta_after
            )

            if self._prev_features is not None:
                transform_type = self._rule_memory.record(
                    self._prev_action, self._prev_features, features, level_up
                )
                if DEBUG and self._action_count % 15 == 0:
                    self._forensic.on_synthesis_hypothesis({
                        "action": self._prev_action.name,
                        "transform": transform_type,
                        "n_rules": self._rule_memory.n_records(),
                    })

            self._memory.record(self._prev_fp, self._prev_action, level_up, visual_delta)
            self._n_total[self._prev_action.value] += 1

            # FIX P0-C: n_progress_real = level_up ONLY; n_visual_change = visual
            if level_up:
                self._n_progress_real[self._prev_action.value] += 1
                # FIX P0-B: record which action caused the level_up for scoring bonus
                self._levels_progress_map[self._prev_action.value] = LEVELS_PROGRESS_BONUS
                self._forensic.on_levels_progress(
                    self._prev_action.name,
                    self._levels_completed - 1,
                    self._levels_completed,
                    LEVELS_PROGRESS_BONUS,
                )
            if visual_delta >= DELTA_MIN:
                self._n_visual_change[self._prev_action.value] += 1

            self._forensic.on_model_update(
                self._prev_action.name, level_up, visual_delta,
                level_up,  # real_progress
                self._n_total[self._prev_action.value],
            )

        # ── Stagnation detection (stuck_streak on fp) ─────────────────────
        if fp == self._prev_fp:
            self._stuck_streak += 1
        else:
            self._stuck_streak = 0
        self._prev_fp = fp

        if self._stuck_streak >= STUCK_THRESHOLD:
            self._phase = "recover"
            if self._stuck_streak == STUCK_THRESHOLD:
                self._forensic.on_stuck(self._stuck_streak, self._phase)
            if self._stuck_streak >= STUCK_THRESHOLD + RESET_AFTER_STUCK:
                self._forensic.on_reset(
                    "deep_stuck",
                    self._action_count,
                    MAX_ACTIONS_TOTAL - self._action_count,
                    self._stuck_streak,
                )
                self._stuck_streak = 0
                self._same_state_streak = 0
                self._level_action_count = 0
                self._phase = "explore"
                self._prev_features = None
                self._prev_frame = None
                if DEBUG:
                    print("[LuCY] deep stuck → RESET", flush=True)
                return GameAction.RESET

        # ── Forensic BEFORE action (full snapshot) ─────────────────────────
        ts_before = self._forensic.on_action_before(
            self._action_count, self._phase, candidates, fp,
            self._stuck_streak, self._levels_completed,
            self._win_levels_current, self._win_levels_at_game_start,
            raw_ids, goal_delta_current,
            latest_frame.frame,
        )

        # ── Phase dispatch ─────────────────────────────────────────────────
        unseen = [a for a in candidates if self._memory.n_tried(a) == 0]
        goal_map = self._goal_tracker.goal_delta_map(candidates)

        # FIX P0-B: build levels_progress_map only when goal_found=False
        lp_map: Optional[dict[int, float]] = None
        if not self._goal_tracker.goal_found and self._levels_progress_map:
            lp_map = {a.value: self._levels_progress_map.get(a.value, 0.0) for a in candidates}

        if self._phase == "explore" and unseen:
            action = random.choice(unseen)

        elif self._phase == "recover":
            if unseen:
                action = random.choice(unseen)
            else:
                engine = _CognitiveEngine(self._memory, self._n_progress_real, self._n_total)
                scores = engine.score_all(fp, candidates, features, self._action_count,
                                          goal_map, lp_map)
                action = min(candidates, key=lambda a: scores.get(a, 0.0))

        else:
            self._phase = "exploit"
            ps_action, ps_conf = self._rule_memory.best_action(
                candidates, features, prefer_transform=_TransformType.GROWING
            )

            if ps_action is not None and ps_conf >= PS_CONFIDENCE_THRESHOLD:
                action = ps_action
                self._forensic.on_synthesis_follow(action.name, ps_conf)
                if DEBUG and self._action_count % 10 == 0:
                    print(
                        f"[LuCY] PS_FOLLOW action={action.name} conf={ps_conf:.2f}",
                        flush=True,
                    )
            else:
                engine = _CognitiveEngine(self._memory, self._n_progress_real, self._n_total)
                scores = engine.score_all(fp, candidates, features, self._action_count,
                                          goal_map, lp_map)

                if DEBUG and self._action_count % 10 == 0:
                    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
                    self._forensic.on_cognitive_score({
                        "action_count": self._action_count,
                        "goal_delta_active": goal_map is not None,
                        "levels_progress_active": lp_map is not None,
                        "top3": {a.name: round(s, 3) for a, s in top},
                    })

                action = max(candidates, key=lambda a: scores.get(a, 0.0))

        # ── Complex action (ACTION6) coordinate selection ─────────────────
        if action.is_complex():
            active_ratio = features.get("active_ratio", 0.5)
            if features.get("grid_valid", False) and active_ratio < 0.5:
                x = random.randint(20, 44)
                y = random.randint(20, 44)
            else:
                x = random.randint(0, 63)
                y = random.randint(0, 63)
            action.set_data({"x": x, "y": y})

        # ── Forensic AFTER action ──────────────────────────────────────────
        self._forensic.on_action_after(
            self._action_count, action.name, self._phase, ts_before,
            action.is_complex(),
            pixel_diff,
            goal_delta_after,
            goal_delta_improvement,
            transform_type,
        )

        self._prev_action = action
        self._prev_features = features
        self._prev_frame = latest_frame.frame

        if DEBUG and (self._action_count % 10 == 0 or level_up):
            print(
                f"[LuCY v{VERSION}] n={self._action_count} action={action.name} "
                f"phase={self._phase} levels_completed={self._levels_completed} "
                f"win_levels={self._win_levels_current}(start={self._win_levels_at_game_start}) "
                f"stuck={self._stuck_streak} same_state={self._same_state_streak} "
                f"ps_rules={self._rule_memory.n_records()} "
                f"goal_found={self._goal_tracker.goal_found} "
                f"lp_map_active={lp_map is not None} "
                f"avail={[a.name for a in candidates]} "
                f"raw_ids={raw_ids}",
                flush=True,
            )

        return action
