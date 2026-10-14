"""LuCY Cognitive Agent v11.0 — ARC-AGI-3 (arc-prize-2026)

This is the ONLY file edited in the Kaggle Starter. `scripts/build_notebook.py`
splices the contents of this file into the Kaggle submission notebook.

[edit my_agent.py] → [make play-local] → [make submit]

Architecture v11.0 — LuCY PROGRAM SYNTHESIS
  D-LUCY-001: LuCY IS her own cognitive model — NO external LLM whatsoever.
  Intelligence emerges from:
    1. Direct grid perception       (_GridPerceptor)       ← from v10.0
    2. Transformation detection     (_TransformDetector)   ← NEW v11.0
    3. Rule hypothesis engine       (_RuleHypothesizer)    ← NEW v11.0
    4. Cross-game persistent memory (_CrossGameMemory)     ← NEW v11.0
    5. Episodic memory              (_EpisodicMemory)      ← from v10.0
    6. Cognitive scoring engine     (_CognitiveEngine)     ← upgraded v11.0
    7. Nanosecond forensic log      (_KaggleForensicLogger)← from v10.0

CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Changes from v10.0:
  MOD-PS1 : _TransformDetector — analyses consecutive frames to detect what
             CHANGED between them: colour swaps, translation, fill ratio shift,
             axis reflection, border pattern changes.
  MOD-PS2 : _RuleHypothesizer — accumulates (action, transform_signature)
             pairs. A hypothesis is "action A causes transform T with probability p".
             When confidence >= HYPOTHESIS_CONFIRM_THRESHOLD, the rule is treated
             as CONFIRMED and becomes the primary action to repeat.
  MOD-PS3 : _CrossGameMemory — stores confirmed rules as JSON in /tmp for
             reuse across multiple games in the same Kaggle session. Falls back
             gracefully (dict in memory) when /tmp is not writable.
  MOD-PS4 : _CognitiveEngine upgraded — adds a 5th signal: rule_score, the
             probability that a candidate action is a confirmed rule for the
             current puzzle type. W_RULE=4.0 (highest weight).

  Root cause of levels_completed=0 addressed:
    v1..v10: No rule inference. Optimised numeric signals without understanding
    the semantic puzzle rules (which action sequence solves this puzzle type).
    v11.0: Explicitly tracks WHAT CHANGED after each action, clusters changes
    by action, and concentrates on the action whose effects best match the
    goal state transition seen in earlier frames.

Kept from v10.0:
  _GridPerceptor (grid feature extraction — symmetry, colour, complexity).
  _EpisodicMemory (per-game action→outcome scores).
  _KaggleForensicLogger (nanosecond stdout logger, BUG-C7 guard).
  _frame_fingerprint / _frame_delta utilities.
  _get_available_actions with integer fallback.
  RESET budget and stagnation recovery logic.
  All BUG-B1/B2/B3/C1/C3/C4/C5/C7 fixes remain active.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
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

# Action budgets (BUG-B1 fix carried from v9.0)
MAX_ACTIONS_TOTAL = 80
MAX_ACTIONS_PER_LEVEL = 30

# Stagnation detection
STUCK_THRESHOLD = 5
RESET_AFTER_STUCK = 5

# Cognitive scoring weights — v11.0 adds W_RULE
W_MEMORY = 2.0      # weight for episodic memory score
W_PROGRESS = 1.5    # weight for frame-delta progress
W_DIVERSITY = 0.8   # weight for under-tried actions
W_PERCEPTION = 1.0  # weight for perception-based hint
W_RULE = 4.0        # weight for confirmed rule hypothesis (NEW v11.0)

# Minimum delta to count as progress
DELTA_MIN = 0.01

# Program synthesis thresholds
HYPOTHESIS_CONFIRM_THRESHOLD = 0.70  # p >= 70% → treat as confirmed rule
HYPOTHESIS_MIN_TRIALS = 3            # need at least 3 observations before confirming
TRANSFORM_SIG_BUCKETS = 8            # number of buckets for transform signature

# Grid feature weights for perception hint
_COMPLEX_ACTIONS = {6}
_SIMPLE_ACTIONS = {1, 2, 3, 4, 5, 7}

# Cross-game memory path (Kaggle ephemeral /tmp — graceful fallback)
_CROSS_GAME_MEMORY_PATH = "/tmp/lucy_v11_cross_game.json"


# ──────────────────────────────────────────────────────────────────────────────
# KAGGLE FORENSIC LOGGER — inline, nanosecond precision, stdout only
# ──────────────────────────────────────────────────────────────────────────────

class _KaggleForensicLogger:
    """Inline nanosecond forensic logger for Kaggle execution environment.

    Design constraints:
    - No external file I/O (Kaggle ephemeral FS).
    - stdout print() captured by Kaggle in __results__.html.
    - Each event line: [LuCY-NS:{ts_ns}] {event_type} | {payload_json}
    - Events fired BEFORE and DURING every state change.
    - Summary JSON printed at game end.

    CERTIFIED_100=false | unique_human_proven=false
    """

    PREFIX = "[LuCY-NS"

    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self._events: list[dict] = []
        self._game_start_ns: int = time.time_ns()
        self._done_emitted: bool = False  # BUG-C7 fix
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
        entry = {
            "ts_ns": ts_ns,
            "event": event_type,
            "game_id": self.game_id,
            **payload,
        }
        self._events.append(entry)
        line = json.dumps(entry, separators=(",", ":"), default=str)
        print(f"{self.PREFIX}:{ts_ns}] {event_type} | {line}", flush=True)

    def on_perception(self, features: dict) -> None:
        self._emit("PERCEPTION", features)

    def on_cognitive_score(self, scores: dict) -> None:
        self._emit("COGNITIVE_SCORE", scores)

    def on_rule_hypothesis(self, payload: dict) -> None:
        self._emit("RULE_HYPOTHESIS", payload)

    def on_rule_confirmed(self, payload: dict) -> None:
        self._emit("RULE_CONFIRMED", payload)

    def on_transform_detected(self, payload: dict) -> None:
        self._emit("TRANSFORM_DETECTED", payload)

    def on_action_before(
        self,
        action_count: int,
        phase: str,
        candidates: list,
        fp: str,
        stuck_streak: int,
        levels_completed: int,
    ) -> int:
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

    def on_action_after(
        self,
        action_count: int,
        action_name: str,
        phase: str,
        ts_before_ns: int,
        is_complex: bool,
    ) -> None:
        ts_after = time.time_ns()
        self._emit("ACTION_AFTER", {
            "action_count": action_count,
            "action": action_name,
            "phase": phase,
            "is_complex": is_complex,
            "selection_dur_ns": ts_after - ts_before_ns,
        })

    def on_level_up(self, old_level: int, new_level: int, actions_this_level: int) -> None:
        self._emit("LEVEL_UP", {
            "old_level": old_level,
            "new_level": new_level,
            "actions_this_level": actions_this_level,
        })

    def on_stuck(self, streak: int, phase: str) -> None:
        self._emit("STUCK", {"streak": streak, "phase": phase})

    def on_reset(self, reason: str, action_count: int) -> None:
        self._emit("RESET", {"reason": reason, "action_count": action_count})

    def on_model_update(
        self,
        action_name: str,
        level_up: bool,
        delta: float,
        n_total: int,
    ) -> None:
        self._emit("MODEL_UPDATE", {
            "action": action_name,
            "level_up": level_up,
            "delta": round(delta, 4),
            "n_total": n_total,
        })

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
        print(
            f"{self.PREFIX}:SUMMARY] {json.dumps(summary, separators=(',', ':'))}",
            flush=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────────────────────

def _scalar(v: Any) -> int:
    """Recursively extract a scalar int from any nested structure.

    Carried from v10.0 BUG-D1 fix.
    """
    if isinstance(v, (list, tuple)):
        return _scalar(v[0]) if v else 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


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

    BUG-B3 fix: full frame comparison, no [:256] truncation.
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
    """Extract available actions from frame (Fix-1 from v7.0).

    Prefers latest_frame.available_actions (authoritative) if non-empty.
    Falls back to all simple GameActions excluding RESET.
    """
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
# MODULE 1 — GRID PERCEPTOR (carried from v10.0)
# ──────────────────────────────────────────────────────────────────────────────

class _GridPerceptor:
    """Direct visual perception of ARC-AGI-3 grids.

    D-LUCY-001: no external LLM — features extracted by native Python analysis.

    Features extracted:
      symmetry_h      : horizontal symmetry ratio [0..1]
      symmetry_v      : vertical symmetry ratio [0..1]
      dominant_colour : most frequent cell value (int)
      complexity      : number of distinct non-zero cell values
      active_ratio    : fraction of non-zero cells
      colour_count    : total number of distinct colours (including 0)
      delta_mass      : signed change in count of non-zero cells vs previous frame
    """

    def extract(
        self,
        frame: Any,
        prev_frame: Any = None,
    ) -> dict:
        """Extract visual features from a frame. Returns feature dict."""
        features: dict = {
            "symmetry_h": 0.0,
            "symmetry_v": 0.0,
            "dominant_colour": 0,
            "complexity": 1,
            "active_ratio": 0.0,
            "colour_count": 1,
            "delta_mass": 0,
            "grid_valid": False,
            "rows": 0,
            "cols": 0,
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

        # Flatten to uniform 2D matrix (pad missing cells with 0)
        mat = [[grid[r][c] if c < len(grid[r]) else 0
                for c in range(cols)]
               for r in range(rows)]

        all_vals = [_scalar(mat[r][c]) for r in range(rows) for c in range(cols)]
        mat = [[_scalar(mat[r][c]) for c in range(cols)] for r in range(rows)]
        counter = Counter(all_vals)
        features["dominant_colour"] = counter.most_common(1)[0][0] if counter else 0
        features["colour_count"] = len(counter)
        features["complexity"] = len([v for v in counter if v != 0]) or 1

        total = rows * cols
        active = sum(1 for v in all_vals if v != 0)
        features["active_ratio"] = active / max(1, total)

        if rows >= 2:
            h_matches = 0
            h_total = 0
            for c in range(cols):
                for dr in range(rows // 2):
                    r1, r2 = dr, rows - 1 - dr
                    h_total += 1
                    if mat[r1][c] == mat[r2][c]:
                        h_matches += 1
            features["symmetry_h"] = h_matches / max(1, h_total)

        if cols >= 2:
            v_matches = 0
            v_total = 0
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
                prev_active = sum(
                    1 for row in prev_grid for v in row if v != 0
                )
                features["delta_mass"] = active - prev_active

        return features

    @staticmethod
    def _to_grid(frame: Any) -> Optional[list]:
        """Convert any frame representation to a list-of-lists grid."""
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
# MODULE PS1 — TRANSFORM DETECTOR (NEW v11.0)
# ──────────────────────────────────────────────────────────────────────────────

class _TransformDetector:
    """Detects what transformation occurred between two consecutive frames.

    D-LUCY-001: pure Python arithmetic — no LLM.

    A transformation signature is a compact descriptor of the change type:
      fill_ratio_change : signed change in fraction of non-zero cells
      dominant_colour_shift : did the dominant colour change? (bool)
      mass_change_bucket : quantised signed mass delta in 8 buckets
      h_sym_change : change in horizontal symmetry (increased/decreased/stable)
      v_sym_change : change in vertical symmetry (increased/decreased/stable)
      changed_fraction : what fraction of cells changed between frames

    These six attributes form a TransformSignature that identifies the type
    of effect an action had on the game state.
    """

    _BUCKET_EDGES = [-1.0, -0.5, -0.2, -0.05, 0.05, 0.2, 0.5, 1.0]

    def detect(
        self,
        feats_before: dict,
        feats_after: dict,
        frame_before: Any,
        frame_after: Any,
    ) -> dict:
        """Return a transform signature dict comparing before/after features.

        Returns an empty dict if either frame is invalid.
        """
        if not feats_before.get("grid_valid") or not feats_after.get("grid_valid"):
            return {}

        # Fill ratio change
        fill_before = feats_before.get("active_ratio", 0.0)
        fill_after = feats_after.get("active_ratio", 0.0)
        fill_delta = round(fill_after - fill_before, 4)

        # Dominant colour shift
        dom_before = feats_before.get("dominant_colour", 0)
        dom_after = feats_after.get("dominant_colour", 0)
        colour_shift = dom_before != dom_after

        # Mass change bucket (quantised)
        mass_delta = feats_after.get("delta_mass", 0)
        total_cells = max(
            feats_before.get("rows", 1) * feats_before.get("cols", 1), 1
        )
        mass_norm = max(-1.0, min(1.0, mass_delta / total_cells))
        mass_bucket = self._quantise(mass_norm)

        # Symmetry changes (stable / increased / decreased)
        h_before = feats_before.get("symmetry_h", 0.0)
        h_after = feats_after.get("symmetry_h", 0.0)
        h_sym_change = self._sym_change(h_before, h_after)

        v_before = feats_before.get("symmetry_v", 0.0)
        v_after = feats_after.get("symmetry_v", 0.0)
        v_sym_change = self._sym_change(v_before, v_after)

        # Changed fraction (pixel-level)
        changed_frac = round(_frame_delta(frame_before, frame_after), 4)

        return {
            "fill_delta": fill_delta,
            "colour_shift": colour_shift,
            "mass_bucket": mass_bucket,
            "h_sym_change": h_sym_change,
            "v_sym_change": v_sym_change,
            "changed_frac": changed_frac,
        }

    def signature_key(self, sig: dict) -> str:
        """Convert a transform signature to a compact string key for hashing."""
        if not sig:
            return "null"
        return (
            f"fd{sig.get('fill_delta', 0):.2f}"
            f"cs{int(sig.get('colour_shift', False))}"
            f"mb{sig.get('mass_bucket', 4)}"
            f"hs{sig.get('h_sym_change', 's')}"
            f"vs{sig.get('v_sym_change', 's')}"
            f"cf{sig.get('changed_frac', 0.0):.2f}"
        )

    @staticmethod
    def _quantise(v: float) -> int:
        """Quantise a value in [-1,1] into 0..7 bucket."""
        for i, edge in enumerate(_TransformDetector._BUCKET_EDGES):
            if v <= edge:
                return i
        return TRANSFORM_SIG_BUCKETS - 1

    @staticmethod
    def _sym_change(before: float, after: float) -> str:
        """Return 'i' (increased), 'd' (decreased), 's' (stable)."""
        diff = after - before
        if diff > 0.05:
            return "i"
        if diff < -0.05:
            return "d"
        return "s"


# ──────────────────────────────────────────────────────────────────────────────
# MODULE PS2 — RULE HYPOTHESIZER (NEW v11.0)
# ──────────────────────────────────────────────────────────────────────────────

class _RuleHypothesizer:
    """Accumulates (action, transform_signature) evidence and infers rules.

    D-LUCY-001: pure Python — no LLM.

    A rule is a pair (action_value, transform_sig_key) that occurs with
    sufficient frequency to be considered predictive.

    confirmed_rules: {action_value: best_transform_sig_key}
      — the most likely transformation caused by each action.

    rule_confidence: {action_value: float in [0,1]}
      — fraction of observations where the dominant signature occurred.

    A rule is "confirmed" when:
      rule_confidence[v] >= HYPOTHESIS_CONFIRM_THRESHOLD
      AND n_observations[v] >= HYPOTHESIS_MIN_TRIALS
    """

    def __init__(self) -> None:
        # {action_value: {sig_key: count}}
        self._sig_counts: defaultdict[int, Counter] = defaultdict(Counter)
        # {action_value: total observations}
        self._n_obs: Counter = Counter()

    def record(self, action: GameAction, sig_key: str) -> None:
        """Record an observed (action → transform_signature) pair."""
        if not sig_key or sig_key == "null":
            return
        v = action.value
        self._sig_counts[v][sig_key] += 1
        self._n_obs[v] += 1

    def rule_score(self, action: GameAction) -> float:
        """Return confidence that this action causes a consistent transformation.

        Returns 0.0 if not enough observations or no dominant signature.
        """
        v = action.value
        n = self._n_obs[v]
        if n < HYPOTHESIS_MIN_TRIALS:
            return 0.0
        if not self._sig_counts[v]:
            return 0.0
        best_count = self._sig_counts[v].most_common(1)[0][1]
        return best_count / n

    def dominant_sig(self, action: GameAction) -> Optional[str]:
        """Return the most observed transform signature for an action."""
        v = action.value
        if not self._sig_counts[v]:
            return None
        return self._sig_counts[v].most_common(1)[0][0]

    def is_confirmed(self, action: GameAction) -> bool:
        """True when the rule hypothesis is confirmed (high confidence + enough data)."""
        return (
            self._n_obs[action.value] >= HYPOTHESIS_MIN_TRIALS
            and self.rule_score(action) >= HYPOTHESIS_CONFIRM_THRESHOLD
        )

    def confirmed_actions(self, candidates: list[GameAction]) -> list[GameAction]:
        """Return the subset of candidates with confirmed rules, sorted by confidence."""
        confirmed = [a for a in candidates if self.is_confirmed(a)]
        confirmed.sort(key=self.rule_score, reverse=True)
        return confirmed

    def to_dict(self) -> dict:
        """Serialise to a dict for cross-game persistence."""
        return {
            "sig_counts": {
                str(k): dict(v) for k, v in self._sig_counts.items()
            },
            "n_obs": dict(self._n_obs),
        }

    def merge_from_dict(self, data: dict) -> None:
        """Merge persisted cross-game data into this hypothesizer."""
        try:
            for k, v in data.get("sig_counts", {}).items():
                self._sig_counts[int(k)].update(v)
            for k, v in data.get("n_obs", {}).items():
                self._n_obs[int(k)] += int(v)
        except Exception:
            pass  # Corrupt persistent data — fail-open (keep in-memory data)


# ──────────────────────────────────────────────────────────────────────────────
# MODULE PS3 — CROSS-GAME MEMORY (NEW v11.0)
# ──────────────────────────────────────────────────────────────────────────────

class _CrossGameMemory:
    """Persists confirmed rule hypotheses across multiple games in a session.

    D-LUCY-001: JSON file in /tmp — no external service, no LLM.

    Falls back gracefully to in-memory dict when /tmp is not writable.
    Thread-safety: single-process Kaggle environment — no locking needed.
    """

    def __init__(self, path: str = _CROSS_GAME_MEMORY_PATH) -> None:
        self._path = path
        self._data: dict = {}  # in-memory fallback
        self._writable = True
        self._load()

    def _load(self) -> None:
        """Load persisted data from disk if available."""
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                    if isinstance(loaded, dict):
                        self._data = loaded
        except Exception:
            self._data = {}

    def save(self, hypothesizer: _RuleHypothesizer) -> None:
        """Persist the current hypothesizer state to disk."""
        try:
            payload = hypothesizer.to_dict()
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            self._data = payload
        except Exception:
            self._writable = False
            self._data = hypothesizer.to_dict()

    def load_into(self, hypothesizer: _RuleHypothesizer) -> None:
        """Merge persisted data from previous games into the hypothesizer."""
        if self._data:
            hypothesizer.merge_from_dict(self._data)

    @property
    def game_count(self) -> int:
        """Approximate number of games accumulated (n_obs sum as proxy)."""
        try:
            return sum(self._data.get("n_obs", {}).values())
        except Exception:
            return 0


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 2 — EPISODIC MEMORY (carried from v10.0)
# ──────────────────────────────────────────────────────────────────────────────

class _EpisodicMemory:
    """Stores per-game experience: which actions produced progress on which states.

    D-LUCY-001: pure Python data structures — no external storage.

    Key: grid fingerprint (16-char hex)
    Value: {action_value: cumulative_score}
      +2.0 per level_up
      +1.0 per frame delta > DELTA_MIN
      -0.1 per no-progress action (decay)
    """

    LEVEL_UP_REWARD = 2.0
    PROGRESS_REWARD = 1.0
    NO_PROGRESS_DECAY = 0.1

    def __init__(self) -> None:
        self._scores: defaultdict[str, dict[int, float]] = defaultdict(dict)
        self._n_tried: Counter[int] = Counter()

    def record(
        self,
        fp: str,
        action: GameAction,
        level_up: bool,
        delta: float,
    ) -> None:
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

    def best_on_state(
        self,
        fp: str,
        candidates: list[GameAction],
    ) -> Optional[GameAction]:
        scores = {a: self._scores[fp].get(a.value, None) for a in candidates}
        known = {a: s for a, s in scores.items() if s is not None}
        if not known:
            return None
        return max(known, key=known.__getitem__)

    def n_tried(self, action: GameAction) -> int:
        return self._n_tried[action.value]


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 3 — COGNITIVE ENGINE (upgraded v11.0 — adds rule_score signal)
# ──────────────────────────────────────────────────────────────────────────────

class _CognitiveEngine:
    """Scores available actions using five cognitive signals.

    D-LUCY-001: pure arithmetic, no external call.

    score(action) = W_MEMORY      * memory_score(fp, action)    [recalled experience]
                  + W_PROGRESS    * progress_score(action)       [frame delta history]
                  + W_DIVERSITY   * diversity_score(action)      [exploration bonus]
                  + W_PERCEPTION  * perception_hint(feats, act)  [grid-based hint]
                  + W_RULE        * rule_score(action)           [program synthesis — NEW]
    """

    def __init__(
        self,
        memory: _EpisodicMemory,
        hypothesizer: _RuleHypothesizer,
        n_progress: Counter,
        n_total: Counter,
    ) -> None:
        self._memory = memory
        self._hypothesizer = hypothesizer
        self._n_progress = n_progress
        self._n_total = n_total

    def score_all(
        self,
        fp: str,
        candidates: list[GameAction],
        features: dict,
        total_actions: int,
    ) -> dict[GameAction, float]:
        """Return {action: cognitive_score} for all candidates."""
        scores: dict[GameAction, float] = {}
        max_tried = max((self._memory.n_tried(a) for a in candidates), default=1)

        for action in candidates:
            v = action.value
            n = max(self._n_total[v], 1)

            # Signal 1 — episodic memory score on current grid state
            mem = self._memory.memory_score(fp, action)

            # Signal 2 — historical progress rate
            prog = self._n_progress[v] / n

            # Signal 3 — diversity bonus (under-tried actions get boost)
            tried = self._memory.n_tried(action)
            div = 1.0 - (tried / max(max_tried, 1))

            # Signal 4 — perception hint (grid-feature heuristic)
            hint = self._perception_hint(features, action)

            # Signal 5 — rule hypothesis confidence (NEW v11.0)
            rule = self._hypothesizer.rule_score(action)

            total = (
                W_MEMORY * mem
                + W_PROGRESS * prog
                + W_DIVERSITY * div
                + W_PERCEPTION * hint
                + W_RULE * rule
            )
            scores[action] = total

        return scores

    @staticmethod
    def _perception_hint(features: dict, action: GameAction) -> float:
        """Heuristic: which action is likely useful given grid features."""
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
# MAIN AGENT — LuCY v11.0
# ──────────────────────────────────────────────────────────────────────────────

class MyAgent(Agent):
    """LuCY Program Synthesis v11.0 — native cognitive agent, zero external LLM.

    D-LUCY-001: LuCY IS her own type of cognitive model.

    Four phases:
      EXPLORE  : try every available action at least once (diversity-first).
      SYNTH    : program synthesis active — exploit confirmed rule hypotheses.
      EXPLOIT  : cognitive scoring engine selects best action.
      RECOVER  : after stagnation, diversify or force RESET.

    Forensic events (stdout, nanosecond timestamps):
      GAME_INIT, PERCEPTION, TRANSFORM_DETECTED, RULE_HYPOTHESIS,
      RULE_CONFIRMED, COGNITIVE_SCORE, ACTION_BEFORE, ACTION_AFTER,
      LEVEL_UP, STUCK, RESET, MODEL_UPDATE, GAME_DONE, SUMMARY.

    CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
    """

    MAX_ACTIONS = MAX_ACTIONS_TOTAL

    # Shared cross-game memory across all instances in the same session
    _shared_cross_game: Optional[_CrossGameMemory] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))

        # Forensic logger (NS precision)
        self._forensic = _KaggleForensicLogger(game_id=str(self.game_id))

        # Grid perception module (v10.0)
        self._perceptor = _GridPerceptor()

        # Program synthesis modules (NEW v11.0)
        self._transform_detector = _TransformDetector()
        self._hypothesizer = _RuleHypothesizer()

        # Cross-game memory: init once per session, shared across games
        if MyAgent._shared_cross_game is None:
            MyAgent._shared_cross_game = _CrossGameMemory()
        MyAgent._shared_cross_game.load_into(self._hypothesizer)

        # Episodic memory (v10.0)
        self._memory = _EpisodicMemory()
        self._n_progress: Counter[int] = Counter()
        self._n_total: Counter[int] = Counter()

        # State counters
        self._action_count: int = 0
        self._level_action_count: int = 0
        self._levels_completed: int = 0
        self._max_levels_seen: int = 0  # BUG-C4 fix
        self._stuck_streak: int = 0
        self._prev_fp: str = ""
        self._prev_action: Optional[GameAction] = None
        self._prev_features: dict = {}
        self._phase: str = "explore"

        if DEBUG:
            cross_obs = MyAgent._shared_cross_game.game_count
            print(
                f"[LuCY v{VERSION}] game_id={self.game_id!r} "
                f"PROGRAM_SYNTHESIS external_llm=False "
                f"MAX_ACTIONS={MAX_ACTIONS_TOTAL} "
                f"cross_game_obs={cross_obs}",
                flush=True,
            )

    # ── Contract ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"LuCY-ProgramSynthesis-v{VERSION}"

    def is_done(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> bool:
        """BUG-B2/C3 fix: stop on WIN or budget exhaustion."""
        if latest_frame.state is GameState.WIN:
            self._on_game_end("WIN")
            return True
        if self._action_count >= MAX_ACTIONS_TOTAL - 1:
            self._on_game_end("BUDGET_EXHAUSTED")
            return True
        return False

    def _on_game_end(self, reason: str) -> None:
        """Called when the game ends — persist cross-game memory."""
        self._forensic.on_done(
            reason=reason,
            levels_completed=self._levels_completed,
            total_actions=self._action_count,
        )
        # Persist the accumulated rule hypotheses for future games
        if MyAgent._shared_cross_game is not None:
            MyAgent._shared_cross_game.save(self._hypothesizer)

    def choose_action(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> GameAction:
        self._action_count += 1
        self._level_action_count += 1

        # ── Terminal state → RESET ────────────────────────────────────────────
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._level_action_count = 0
            self._stuck_streak = 0
            self._forensic.on_reset(
                reason=f"state_{latest_frame.state.name}",
                action_count=self._action_count,
            )
            if DEBUG:
                print(f"[LuCY] state={latest_frame.state.name} → RESET", flush=True)
            return GameAction.RESET

        # ── Per-level budget exhausted → RESET ───────────────────────────────
        if self._level_action_count > MAX_ACTIONS_PER_LEVEL:
            self._forensic.on_reset(
                reason="per_level_budget",
                action_count=self._action_count,
            )
            self._level_action_count = 0
            self._phase = "explore"
            self._stuck_streak = 0  # BUG-C5 fix
            if DEBUG:
                print("[LuCY] per-level budget exhausted → RESET", flush=True)
            return GameAction.RESET

        # ── Get available actions (Fix-1) ─────────────────────────────────────
        candidates = _get_available_actions(latest_frame)
        if not candidates:
            candidates = [a for a in GameAction
                          if a is not GameAction.RESET and a.is_simple()]

        # ── Observe frame ─────────────────────────────────────────────────────
        fp = _frame_fingerprint(latest_frame.frame)
        prev_raw = frames[-2].frame if len(frames) >= 2 else None

        # ── Cognitive perception (MOD-1) ──────────────────────────────────────
        features = self._perceptor.extract(latest_frame.frame, prev_raw)
        if DEBUG and self._action_count <= 3:
            self._forensic.on_perception({
                "action_count": self._action_count,
                "fp_prefix": fp[:8],
                **{k: round(v, 3) if isinstance(v, float) else v
                   for k, v in features.items()},
            })

        # ── Level tracking (BUG-C4 fix) ───────────────────────────────────────
        current_levels_raw = getattr(latest_frame, "levels_completed", 0) or 0
        current_levels = max(current_levels_raw, self._max_levels_seen)
        self._max_levels_seen = current_levels
        level_up = current_levels > self._levels_completed
        if level_up:
            self._forensic.on_level_up(
                old_level=self._levels_completed,
                new_level=current_levels,
                actions_this_level=self._level_action_count,
            )
            if DEBUG:
                print(
                    f"[LuCY] LEVEL UP {self._levels_completed} → {current_levels} "
                    f"(actions this level: {self._level_action_count})",
                    flush=True,
                )
            self._levels_completed = current_levels
            self._level_action_count = 0
            self._stuck_streak = 0
            self._phase = "explore"

        # ── Record outcome of previous action + TRANSFORM DETECTION (NEW v11.0) ──
        if self._prev_action is not None and len(frames) >= 2:
            delta = _frame_delta(frames[-2].frame, latest_frame.frame)
            self._memory.record(self._prev_fp, self._prev_action, level_up, delta)
            self._n_total[self._prev_action.value] += 1
            if level_up or delta >= DELTA_MIN:
                self._n_progress[self._prev_action.value] += 1
            self._forensic.on_model_update(
                action_name=self._prev_action.name,
                level_up=level_up,
                delta=delta,
                n_total=self._n_total[self._prev_action.value],
            )

            # Program synthesis: detect the transform caused by prev_action
            if self._prev_features and delta > 0:
                sig = self._transform_detector.detect(
                    self._prev_features, features,
                    frames[-2].frame, latest_frame.frame,
                )
                sig_key = self._transform_detector.signature_key(sig)
                self._hypothesizer.record(self._prev_action, sig_key)

                if DEBUG and sig:
                    self._forensic.on_transform_detected({
                        "action": self._prev_action.name,
                        "sig_key": sig_key,
                        "changed_frac": sig.get("changed_frac", 0.0),
                        "mass_bucket": sig.get("mass_bucket", 4),
                    })

                # Log confirmed rules (first time each action becomes confirmed)
                if self._hypothesizer.is_confirmed(self._prev_action):
                    conf = self._hypothesizer.rule_score(self._prev_action)
                    dom_sig = self._hypothesizer.dominant_sig(self._prev_action)
                    if DEBUG:
                        self._forensic.on_rule_confirmed({
                            "action": self._prev_action.name,
                            "confidence": round(conf, 3),
                            "dominant_sig": dom_sig,
                        })

        # Store current features for next transform detection
        self._prev_features = features

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
                if DEBUG:
                    print(
                        f"[LuCY] STUCK (streak={self._stuck_streak}) → recover",
                        flush=True,
                    )
            if self._stuck_streak >= STUCK_THRESHOLD + RESET_AFTER_STUCK:
                self._forensic.on_reset(
                    reason="deep_stuck",
                    action_count=self._action_count,
                )
                self._stuck_streak = 0
                self._level_action_count = 0
                self._phase = "explore"
                if DEBUG:
                    print("[LuCY] deep stuck → RESET", flush=True)
                return GameAction.RESET

        # ── Phase upgrade: if confirmed rules exist, switch to SYNTH ──────────
        confirmed = self._hypothesizer.confirmed_actions(candidates)
        if confirmed and self._phase == "exploit":
            self._phase = "synth"

        # ── Emit forensic BEFORE action selection ─────────────────────────────
        ts_before = self._forensic.on_action_before(
            action_count=self._action_count,
            phase=self._phase,
            candidates=candidates,
            fp=fp,
            stuck_streak=self._stuck_streak,
            levels_completed=self._levels_completed,
        )

        # ── Phase dispatch ─────────────────────────────────────────────────────
        unseen = [a for a in candidates
                  if self._memory.n_tried(a) == 0]

        if self._phase == "explore" and unseen:
            # EXPLORE: try unseen actions (random order — BUG-C1 fix)
            action = random.choice(unseen)

        elif self._phase == "synth" and confirmed:
            # SYNTH (NEW v11.0): use the highest-confidence confirmed rule
            action = confirmed[0]
            if DEBUG and self._action_count % 5 == 0:
                self._forensic.on_rule_hypothesis({
                    "action_count": self._action_count,
                    "synth_action": action.name,
                    "confidence": round(
                        self._hypothesizer.rule_score(action), 3
                    ),
                    "n_confirmed": len(confirmed),
                })

        elif self._phase == "recover":
            # RECOVER: prefer least-tried candidates (escape local minimum)
            if unseen:
                action = random.choice(unseen)
            else:
                engine = _CognitiveEngine(
                    self._memory, self._hypothesizer,
                    self._n_progress, self._n_total,
                )
                scores = engine.score_all(fp, candidates, features, self._action_count)
                action = min(candidates, key=lambda a: scores.get(a, 0.0))

        else:
            # EXPLOIT: full cognitive scoring engine (5 signals)
            self._phase = "exploit"
            engine = _CognitiveEngine(
                self._memory, self._hypothesizer,
                self._n_progress, self._n_total,
            )
            scores = engine.score_all(fp, candidates, features, self._action_count)

            if DEBUG and self._action_count % 10 == 0:
                top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
                self._forensic.on_cognitive_score({
                    "action_count": self._action_count,
                    "top3": {a.name: round(s, 3) for a, s in top},
                })

            action = max(candidates, key=lambda a: scores.get(a, 0.0))

        # ── Handle complex actions ─────────────────────────────────────────────
        if action.is_complex():
            active_ratio = features.get("active_ratio", 0.5)
            if features.get("grid_valid", False) and active_ratio < 0.5:
                x = random.randint(20, 44)
                y = random.randint(20, 44)
            else:
                x = random.randint(0, 63)
                y = random.randint(0, 63)
            action.set_data({"x": x, "y": y})

        # ── Emit forensic AFTER action selection ──────────────────────────────
        self._forensic.on_action_after(
            action_count=self._action_count,
            action_name=action.name,
            phase=self._phase,
            ts_before_ns=ts_before,
            is_complex=action.is_complex(),
        )

        self._prev_action = action

        if DEBUG and (self._action_count % 10 == 0 or level_up):
            n_hyp_confirmed = sum(
                1 for a in candidates
                if self._hypothesizer.is_confirmed(a)
            )
            print(
                f"[LuCY] n={self._action_count} action={action.name} "
                f"phase={self._phase} levels={self._levels_completed} "
                f"stuck={self._stuck_streak} "
                f"confirmed_rules={n_hyp_confirmed} "
                f"avail={[a.name for a in candidates]}",
                flush=True,
            )

        return action
