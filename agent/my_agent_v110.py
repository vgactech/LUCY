"""LuCY Cognitive Agent v11.0 — ARC-AGI-3 (arc-prize-2026)

This is the ONLY file edited in the Kaggle Starter. `scripts/build_notebook.py`
splices the contents of this file into the Kaggle submission notebook.

[edit my_agent.py] → [make play-local] → [make submit]

Architecture v11.0 — LuCY PROGRAM SYNTHESIS ENGINE
  D-LUCY-001: LuCY IS her own cognitive model — NO external LLM whatsoever.
  Intelligence emerges from:
    1. Direct grid perception    (_GridPerceptor)       — from v10.0
    2. Episodic memory           (_EpisodicMemory)      — from v10.0
    3. Cognitive scoring engine  (_CognitiveEngine)     — from v10.0
    4. Program synthesis engine  (_ProgramSynthesis)    — NEW v11.0
    5. Cross-episode rule memory (_RuleMemory)          — NEW v11.0
    6. Nanosecond forensic log   (_KaggleForensicLogger)

Changes from v10.0:
  ROOT CAUSE FIX: levels_completed=0/25 because v10.0 had no rule inference.
  PS-1 : _ProgramSynthesis — observes pairs of consecutive frames, detects
         which action caused which transformation (delta), builds hypotheses:
           - IDENTITY  : frame unchanged (action had no effect)
           - GROWING   : active cell count increased
           - SHRINKING : active cell count decreased
           - RECOLOR   : dominant colour changed
           - SHIFT     : centre-of-mass moved
  PS-2 : _RuleMemory — persists verified hypotheses across episodes within
         the same game. key=(action_value, pre_state_signature) → confidence.
         Confidence grows each verification, decays on contradiction.
  PS-3 : Synthesis loop in choose_action() — before picking, ask PS for the
         best-verified rule. If confidence > PS_CONFIDENCE_THRESHOLD, follow it.
         Otherwise fall back to cognitive scoring (v10.0 path).
  PS-4 : Hypothesis search — in EXPLORE phase, tries all candidates once to
         build a local transformation map before exploiting.

Kept from v10.0:
  _KaggleForensicLogger, _GridPerceptor, _EpisodicMemory, _CognitiveEngine.
  _frame_fingerprint / _frame_delta utilities.
  _get_available_actions with integer fallback.
  RESET budget, stagnation, phase dispatch logic.
  All BUG-B1/B2/B3/C1/C3/C4/C5/C7/D1 fixes remain active.

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

VERSION = "11.0"
DEBUG = True  # PROTOCOLE_ARTCB: always DEBUG until user disables explicitly

# Action budgets
MAX_ACTIONS_TOTAL = 80
MAX_ACTIONS_PER_LEVEL = 30

# Stagnation detection
STUCK_THRESHOLD = 5
RESET_AFTER_STUCK = 5

# Cognitive scoring weights (v10.0 — kept)
W_MEMORY = 3.0
W_PROGRESS = 2.0
W_DIVERSITY = 1.0
W_PERCEPTION = 1.5

# Program synthesis constants (NEW v11.0)
PS_CONFIDENCE_THRESHOLD = 1.5   # min confidence to follow a rule
PS_VERIFY_REWARD = 1.0          # confidence gain when rule verified
PS_CONTRADICT_DECAY = 0.8       # confidence decay on contradiction
PS_MAX_HYPOTHESES = 32          # cap per action to avoid memory explosion

# Minimum delta to count as progress
DELTA_MIN = 0.01

# Grid feature weights for perception hint
_COMPLEX_ACTIONS = {6}
_SIMPLE_ACTIONS = {1, 2, 3, 4, 5, 7}


# ──────────────────────────────────────────────────────────────────────────────
# KAGGLE FORENSIC LOGGER — inline, nanosecond precision, stdout only
# ──────────────────────────────────────────────────────────────────────────────

class _KaggleForensicLogger:
    """Inline nanosecond forensic logger for Kaggle execution environment.

    CERTIFIED_100=false | unique_human_proven=false
    """

    PREFIX = "[LuCY-NS"

    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self._events: list[dict] = []
        self._game_start_ns: int = time.time_ns()
        self._done_emitted: bool = False
        self._emit("GAME_INIT", {
            "game_id": game_id,
            "version": VERSION,
            "max_actions_total": MAX_ACTIONS_TOTAL,
            "max_actions_per_level": MAX_ACTIONS_PER_LEVEL,
            "program_synthesis": True,
            "cognitive_engine": True,
            "external_llm": False,
            "certified_100": False,
            "unique_human_proven": False,
            "debug": DEBUG,
        })

    def _emit(self, event_type: str, payload: dict) -> None:
        ts_ns = time.time_ns()
        entry = {"ts_ns": ts_ns, "event": event_type, "game_id": self.game_id, **payload}
        self._events.append(entry)
        line = json.dumps(entry, separators=(",", ":"), default=str)
        print(f"{self.PREFIX}:{ts_ns}] {event_type} | {line}", flush=True)

    def on_perception(self, features: dict) -> None:
        self._emit("PERCEPTION", features)

    def on_cognitive_score(self, scores: dict) -> None:
        self._emit("COGNITIVE_SCORE", scores)

    def on_synthesis_hypothesis(self, payload: dict) -> None:
        self._emit("PS_HYPOTHESIS", payload)

    def on_synthesis_follow(self, action_name: str, confidence: float) -> None:
        self._emit("PS_FOLLOW", {"action": action_name, "confidence": round(confidence, 3)})

    def on_action_before(self, action_count, phase, candidates, fp, stuck_streak, levels_completed) -> int:
        ts_before = time.time_ns()
        self._emit("ACTION_BEFORE", {
            "action_count": action_count,
            "phase": phase,
            "fp_prefix": fp[:8],
            "stuck_streak": stuck_streak,
            "levels_completed": levels_completed,
            "n_candidates": len(candidates),
            "candidates": [a.name for a in candidates],
            "ts_before_ns": ts_before,
        })
        return ts_before

    def on_action_after(self, action_count, action_name, phase, ts_before_ns, is_complex) -> None:
        ts_after = time.time_ns()
        self._emit("ACTION_AFTER", {
            "action_count": action_count,
            "action": action_name,
            "phase": phase,
            "is_complex": is_complex,
            "selection_dur_ns": ts_after - ts_before_ns,
        })

    def on_level_up(self, old_level, new_level, actions_this_level) -> None:
        self._emit("LEVEL_UP", {"old_level": old_level, "new_level": new_level,
                                "actions_this_level": actions_this_level})

    def on_stuck(self, streak, phase) -> None:
        self._emit("STUCK", {"streak": streak, "phase": phase})

    def on_reset(self, reason, action_count) -> None:
        self._emit("RESET", {"reason": reason, "action_count": action_count})

    def on_model_update(self, action_name, level_up, delta, n_total) -> None:
        self._emit("MODEL_UPDATE", {"action": action_name, "level_up": level_up,
                                    "delta": round(delta, 4), "n_total": n_total})

    def on_done(self, reason: str, levels_completed: int, total_actions: int) -> None:
        """BUG-C7 fix: guarded by _done_emitted."""
        if self._done_emitted:
            return
        self._done_emitted = True
        elapsed_ns = time.time_ns() - self._game_start_ns
        self._emit("GAME_DONE", {
            "reason": reason,
            "levels_completed": levels_completed,
            "total_actions": total_actions,
            "elapsed_ns": elapsed_ns,
        })
        summary = {
            "lucy_forensic_summary": True,
            "version": VERSION,
            "game_id": self.game_id,
            "levels_completed": levels_completed,
            "total_actions": total_actions,
            "elapsed_ms": round(elapsed_ns / 1_000_000, 2),
            "total_events": len(self._events),
            "program_synthesis": True,
            "cognitive_engine": True,
            "external_llm": False,
            "certified_100": False,
            "unique_human_proven": False,
        }
        print(f"{self.PREFIX}:SUMMARY] {json.dumps(summary, separators=(',', ':'))}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────────────────────

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
    """Fraction of elements that differ between two frames (0.0 = identical).

    BUG-B3 fix: full frame comparison.
    """
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


def _get_available_actions(latest_frame: FrameData) -> list[GameAction]:
    """Extract available actions from frame (Fix-1 from v7.0)."""
    avail = getattr(latest_frame, "available_actions", None)
    if avail:
        result = []
        for a in avail:
            if isinstance(a, GameAction):
                if a is not GameAction.RESET:
                    result.append(a)
            elif isinstance(a, int):
                try:
                    ga = GameAction.from_id(a)
                    if ga is not GameAction.RESET:
                        result.append(ga)
                except ValueError:
                    pass
        if result:
            return result
    return [a for a in GameAction if a is not GameAction.RESET and a.is_simple()]


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

        # Centre of mass of active cells
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
# MODULE 3 — COGNITIVE ENGINE (from v10.0, unchanged)
# ──────────────────────────────────────────────────────────────────────────────

class _CognitiveEngine:
    """Scores available actions using the four cognitive signals. D-LUCY-001."""

    def __init__(self, memory: _EpisodicMemory, n_progress: Counter, n_total: Counter) -> None:
        self._memory = memory
        self._n_progress = n_progress
        self._n_total = n_total

    def score_all(self, fp, candidates, features, total_actions) -> dict[GameAction, float]:
        scores: dict[GameAction, float] = {}
        max_tried = max((self._memory.n_tried(a) for a in candidates), default=1)
        for action in candidates:
            v = action.value
            n = max(self._n_total[v], 1)
            mem = self._memory.memory_score(fp, action)
            prog = self._n_progress[v] / n
            tried = self._memory.n_tried(action)
            div = 1.0 - (tried / max(max_tried, 1))
            hint = self._perception_hint(features, action)
            scores[action] = W_MEMORY * mem + W_PROGRESS * prog + W_DIVERSITY * div + W_PERCEPTION * hint
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
# MODULE 4 — PROGRAM SYNTHESIS ENGINE (NEW v11.0)
# ──────────────────────────────────────────────────────────────────────────────

class _TransformType:
    """Discrete transformation categories inferred from frame pairs."""
    IDENTITY = "IDENTITY"     # frame unchanged
    GROWING = "GROWING"       # active cell count increased
    SHRINKING = "SHRINKING"   # active cell count decreased
    RECOLOR = "RECOLOR"       # dominant colour changed
    SHIFT = "SHIFT"           # centre-of-mass moved significantly
    DELTA = "DELTA"           # generic change (< 5% but > 0)
    UNKNOWN = "UNKNOWN"


class _RuleMemory:
    """Persists transformation hypotheses within one game.

    Key  : (action_value, pre_state_signature)
    Value: {transform_type: confidence}

    pre_state_signature = coarse hash of (dominant_colour, complexity, active_ratio bucket).
    This is deliberately lossy so similar states share hypotheses.
    """

    def __init__(self) -> None:
        # (action_val, state_sig) → {transform_type: confidence}
        self._rules: defaultdict[tuple, dict[str, float]] = defaultdict(dict)
        self._n_records: int = 0

    @staticmethod
    def state_signature(features: dict) -> str:
        """Coarse fingerprint of the grid state for hypothesis matching."""
        dom = features.get("dominant_colour", 0)
        cplx = min(features.get("complexity", 1), 5)  # bucket to [1..5]
        active_bucket = int(features.get("active_ratio", 0.5) * 4)  # 0..4
        return f"{dom}:{cplx}:{active_bucket}"

    def record(
        self,
        action: GameAction,
        pre_features: dict,
        post_features: dict,
        level_up: bool,
    ) -> str:
        """Observe a (pre→action→post) transition and update rule memory."""
        sig = self.state_signature(pre_features)
        transform = self._classify(pre_features, post_features, level_up)

        key = (action.value, sig)
        prev = self._rules[key].get(transform, 0.0)

        if level_up:
            # Level up: strong confirmation regardless of transform type
            self._rules[key][transform] = prev + PS_VERIFY_REWARD * 2.0
        elif transform != _TransformType.IDENTITY:
            self._rules[key][transform] = prev + PS_VERIFY_REWARD
        else:
            # Identity: decay all non-IDENTITY rules for this (action, state)
            for t in list(self._rules[key].keys()):
                if t != _TransformType.IDENTITY:
                    self._rules[key][t] = self._rules[key][t] * PS_CONTRADICT_DECAY
            self._rules[key][_TransformType.IDENTITY] = prev + 0.1

        # Cap memory
        if len(self._rules) > PS_MAX_HYPOTHESES:
            # Remove entry with lowest total confidence
            worst = min(self._rules.keys(),
                        key=lambda k: sum(self._rules[k].values()))
            del self._rules[worst]

        self._n_records += 1
        return transform

    @staticmethod
    def _classify(pre: dict, post: dict, level_up: bool) -> str:
        """Classify the transformation between pre and post feature dicts."""
        if level_up:
            return _TransformType.GROWING  # level up = success = progress

        pre_active = pre.get("active_count", 0)
        post_active = post.get("active_count", 0)
        pre_dom = pre.get("dominant_colour", 0)
        post_dom = post.get("dominant_colour", 0)
        pre_com_r = pre.get("centre_of_mass_r", 0.0)
        pre_com_c = pre.get("centre_of_mass_c", 0.0)
        post_com_r = post.get("centre_of_mass_r", 0.0)
        post_com_c = post.get("centre_of_mass_c", 0.0)

        # No change at all
        if (pre_active == post_active and pre_dom == post_dom
                and abs(pre_com_r - post_com_r) < 0.5
                and abs(pre_com_c - post_com_c) < 0.5):
            return _TransformType.IDENTITY

        # Colour change
        if pre_dom != post_dom:
            return _TransformType.RECOLOR

        # Spatial shift
        shift = math.sqrt((pre_com_r - post_com_r) ** 2 + (pre_com_c - post_com_c) ** 2)
        if shift > 1.5:
            return _TransformType.SHIFT

        # Mass change
        if post_active > pre_active:
            return _TransformType.GROWING
        if post_active < pre_active:
            return _TransformType.SHRINKING

        return _TransformType.DELTA

    def best_action(
        self,
        candidates: list[GameAction],
        pre_features: dict,
        prefer_transform: str = _TransformType.GROWING,
    ) -> tuple[Optional[GameAction], float]:
        """Return (best_action, confidence) for the desired transform, or (None, 0.0)."""
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
# MAIN AGENT — LuCY v11.0
# ──────────────────────────────────────────────────────────────────────────────

class MyAgent(Agent):
    """LuCY Noyau Cognitif v11.0 — program synthesis + native cognitive engine.

    D-LUCY-001: LuCY IS her own type of cognitive model.

    Phases:
      EXPLORE  : try every available action at least once (diversity-first).
                 While exploring, feed (pre→action→post) pairs into _RuleMemory.
      EXPLOIT  : use synthesized rules if confidence > PS_CONFIDENCE_THRESHOLD,
                 else fall back to _CognitiveEngine scoring.
      RECOVER  : after stagnation, diversify or force RESET.

    CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
    """

    MAX_ACTIONS = MAX_ACTIONS_TOTAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))

        self._forensic = _KaggleForensicLogger(game_id=str(self.game_id))
        self._perceptor = _GridPerceptor()
        self._memory = _EpisodicMemory()
        self._rule_memory = _RuleMemory()        # NEW v11.0
        self._n_progress: Counter[int] = Counter()
        self._n_total: Counter[int] = Counter()

        self._action_count: int = 0
        self._level_action_count: int = 0
        self._levels_completed: int = 0
        self._max_levels_seen: int = 0
        self._stuck_streak: int = 0
        self._prev_fp: str = ""
        self._prev_action: Optional[GameAction] = None
        self._prev_features: Optional[dict] = None   # NEW v11.0
        self._phase: str = "explore"

        if DEBUG:
            print(
                f"[LuCY v{VERSION}] game_id={self.game_id!r} "
                f"NOYAU_COGNITIF_NATIF+PROGRAM_SYNTHESIS external_llm=False "
                f"MAX_ACTIONS={MAX_ACTIONS_TOTAL}",
                flush=True,
            )

    @property
    def name(self) -> str:
        return f"LuCY-NoyauCognitif-v{VERSION}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        if latest_frame.state is GameState.WIN:
            self._forensic.on_done("WIN", self._levels_completed, self._action_count)
            return True
        if self._action_count >= MAX_ACTIONS_TOTAL - 1:
            self._forensic.on_done("BUDGET_EXHAUSTED", self._levels_completed, self._action_count)
            return True
        return False

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        self._action_count += 1
        self._level_action_count += 1

        # ── Terminal state → RESET ────────────────────────────────────────────
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._level_action_count = 0
            self._stuck_streak = 0
            self._prev_features = None
            self._forensic.on_reset(f"state_{latest_frame.state.name}", self._action_count)
            if DEBUG:
                print(f"[LuCY] state={latest_frame.state.name} → RESET", flush=True)
            return GameAction.RESET

        # ── Per-level budget exhausted → RESET ───────────────────────────────
        if self._level_action_count > MAX_ACTIONS_PER_LEVEL:
            self._forensic.on_reset("per_level_budget", self._action_count)
            self._level_action_count = 0
            self._phase = "explore"
            self._stuck_streak = 0
            self._prev_features = None
            if DEBUG:
                print("[LuCY] per-level budget exhausted → RESET", flush=True)
            return GameAction.RESET

        # ── Available actions ─────────────────────────────────────────────────
        candidates = _get_available_actions(latest_frame)
        if not candidates:
            candidates = [a for a in GameAction if a is not GameAction.RESET and a.is_simple()]

        # ── Observe frame ─────────────────────────────────────────────────────
        fp = _frame_fingerprint(latest_frame.frame)
        prev_raw = frames[-2].frame if len(frames) >= 2 else None
        features = self._perceptor.extract(latest_frame.frame, prev_raw)

        if DEBUG and self._action_count <= 3:
            self._forensic.on_perception({
                "action_count": self._action_count,
                "fp_prefix": fp[:8],
                **{k: round(v, 3) if isinstance(v, float) else v for k, v in features.items()},
            })

        # ── Level tracking (BUG-C4) ───────────────────────────────────────────
        current_levels_raw = getattr(latest_frame, "levels_completed", 0) or 0
        current_levels = max(current_levels_raw, self._max_levels_seen)
        self._max_levels_seen = current_levels
        level_up = current_levels > self._levels_completed
        if level_up:
            self._forensic.on_level_up(self._levels_completed, current_levels,
                                       self._level_action_count)
            if DEBUG:
                print(f"[LuCY] LEVEL UP {self._levels_completed} → {current_levels}", flush=True)
            self._levels_completed = current_levels
            self._level_action_count = 0
            self._stuck_streak = 0
            self._phase = "exploit"

        # ── Record outcome of previous action (episodic memory + PS) ─────────
        if self._prev_action is not None and len(frames) >= 2:
            delta = _frame_delta(frames[-2].frame, latest_frame.frame)
            self._memory.record(self._prev_fp, self._prev_action, level_up, delta)
            self._n_total[self._prev_action.value] += 1
            if level_up or delta >= DELTA_MIN:
                self._n_progress[self._prev_action.value] += 1
            self._forensic.on_model_update(
                self._prev_action.name, level_up, delta,
                self._n_total[self._prev_action.value]
            )
            # NEW v11.0 — feed program synthesis rule memory
            if self._prev_features is not None:
                transform = self._rule_memory.record(
                    self._prev_action, self._prev_features, features, level_up
                )
                if DEBUG and self._action_count % 15 == 0:
                    self._forensic.on_synthesis_hypothesis({
                        "action": self._prev_action.name,
                        "transform": transform,
                        "n_rules": self._rule_memory.n_records(),
                    })

        # ── Stagnation detection ───────────────────────────────────────────────
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
                self._forensic.on_reset("deep_stuck", self._action_count)
                self._stuck_streak = 0
                self._level_action_count = 0
                self._phase = "explore"
                self._prev_features = None
                if DEBUG:
                    print("[LuCY] deep stuck → RESET", flush=True)
                return GameAction.RESET

        # ── Forensic BEFORE action ─────────────────────────────────────────────
        ts_before = self._forensic.on_action_before(
            self._action_count, self._phase, candidates, fp,
            self._stuck_streak, self._levels_completed,
        )

        # ── Phase dispatch with program synthesis (NEW v11.0) ─────────────────
        unseen = [a for a in candidates if self._memory.n_tried(a) == 0]

        if self._phase == "explore" and unseen:
            action = random.choice(unseen)

        elif self._phase == "recover":
            if unseen:
                action = random.choice(unseen)
            else:
                engine = _CognitiveEngine(self._memory, self._n_progress, self._n_total)
                scores = engine.score_all(fp, candidates, features, self._action_count)
                action = min(candidates, key=lambda a: scores.get(a, 0.0))

        else:
            # EXPLOIT: try program synthesis first
            self._phase = "exploit"
            ps_action, ps_conf = self._rule_memory.best_action(
                candidates, features, prefer_transform=_TransformType.GROWING
            )

            if ps_action is not None and ps_conf >= PS_CONFIDENCE_THRESHOLD:
                # Follow synthesized rule
                action = ps_action
                self._forensic.on_synthesis_follow(action.name, ps_conf)
                if DEBUG and self._action_count % 10 == 0:
                    print(
                        f"[LuCY] PS_FOLLOW action={action.name} conf={ps_conf:.2f}",
                        flush=True,
                    )
            else:
                # Fall back to cognitive scoring engine
                engine = _CognitiveEngine(self._memory, self._n_progress, self._n_total)
                scores = engine.score_all(fp, candidates, features, self._action_count)

                if DEBUG and self._action_count % 10 == 0:
                    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
                    self._forensic.on_cognitive_score({
                        "action_count": self._action_count,
                        "top3": {a.name: round(s, 3) for a, s in top},
                    })

                action = max(candidates, key=lambda a: scores.get(a, 0.0))

        # ── Complex action (ACTION6) coordinate selection ─────────────────────
        if action.is_complex():
            active_ratio = features.get("active_ratio", 0.5)
            if features.get("grid_valid", False) and active_ratio < 0.5:
                x = random.randint(20, 44)
                y = random.randint(20, 44)
            else:
                x = random.randint(0, 63)
                y = random.randint(0, 63)
            action.set_data({"x": x, "y": y})

        # ── Forensic AFTER action ──────────────────────────────────────────────
        self._forensic.on_action_after(
            self._action_count, action.name, self._phase, ts_before, action.is_complex()
        )

        self._prev_action = action
        self._prev_features = features   # NEW v11.0 — save for PS update next step

        if DEBUG and (self._action_count % 10 == 0 or level_up):
            print(
                f"[LuCY] n={self._action_count} action={action.name} "
                f"phase={self._phase} levels={self._levels_completed} "
                f"stuck={self._stuck_streak} ps_rules={self._rule_memory.n_records()} "
                f"avail={[a.name for a in candidates]}",
                flush=True,
            )

        return action
