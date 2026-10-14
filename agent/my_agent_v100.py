"""LuCY Cognitive Agent v10.0 — ARC-AGI-3 (arc-prize-2026)

This is the ONLY file edited in the Kaggle Starter. `scripts/build_notebook.py`
splices the contents of this file into the Kaggle submission notebook.

[edit my_agent.py] → [make play-local] → [make submit]

Architecture v10.0 — LuCY NOYAU COGNITIF NATIF
  D-LUCY-001: LuCY IS her own cognitive model — NO external LLM whatsoever.
  Intelligence emerges from:
    1. Direct grid perception  (_GridPerceptor)
    2. Episodic memory          (_EpisodicMemory)
    3. Cognitive scoring engine (_CognitiveEngine)
    4. Nanosecond forensic log  (_KaggleForensicLogger)

CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Changes from v9.0:
  D-LUCY-001 : REMOVED UCB1 bandits (blind statistics optimizer).
               REPLACED with native cognitive modules that READ the grid.
  MOD-1 : _GridPerceptor — extracts visual features directly from latest_frame.frame
           (symmetry_h, symmetry_v, dominant_colour, complexity_score, delta_mass,
            active_cell_ratio, colour_count, change_region_centroid).
  MOD-2 : _EpisodicMemory — stores (grid_fingerprint → action → outcome) across
           the game. Recalls which actions were productive on similar grid states.
  MOD-3 : _CognitiveEngine — scores each available action using a weighted sum:
           score = w_mem*memory_score + w_prog*progress_score
                 + w_div*diversity_score + w_pct*perception_hint
           No external call. No LLM. Pure Python arithmetic.
  MOD-4 : _ForensicCognitive events — PERCEPTION, FEATURE, SCORE added to NS log.

Kept from v9.0:
  _KaggleForensicLogger (nanosecond stdout logger, SUMMARY guard BUG-C7).
  _frame_fingerprint / _frame_delta utilities.
  _get_available_actions with integer fallback.
  RESET budget and stagnation recovery logic (updated to cognitive context).
  All BUG-B1/B2/B3/C1/C3/C4/C5/C7 fixes remain active.
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

VERSION = "10.0"
DEBUG = True  # PROTOCOLE_ARTCB: always DEBUG until user disables explicitly

# Action budgets (BUG-B1 fix carried from v9.0)
MAX_ACTIONS_TOTAL = 80
MAX_ACTIONS_PER_LEVEL = 30

# Stagnation detection
STUCK_THRESHOLD = 5
RESET_AFTER_STUCK = 5

# Cognitive scoring weights
W_MEMORY = 3.0      # weight for episodic memory score
W_PROGRESS = 2.0    # weight for frame-delta progress
W_DIVERSITY = 1.0   # weight for under-tried actions
W_PERCEPTION = 1.5  # weight for perception-based hint

# Minimum delta to count as progress
DELTA_MIN = 0.01

# Grid feature weights for perception hint
_COMPLEX_ACTIONS = {6}   # ACTION6 — only complex action (x,y coordinates)
_SIMPLE_ACTIONS = {1, 2, 3, 4, 5, 7}   # ACTION1..5, ACTION7


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
# MODULE 1 — GRID PERCEPTOR
# ──────────────────────────────────────────────────────────────────────────────

class _GridPerceptor:
    """Direct visual perception of ARC-AGI-3 grids.

    D-LUCY-001: no external LLM — features extracted by native Python analysis.

    Features extracted:
      symmetry_h      : horizontal symmetry ratio [0..1]
      symmetry_v      : vertical symmetry ratio [0..1]
      dominant_colour : most frequent cell value (int)
      complexity      : number of distinct cell values
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
        }

        grid = self._to_grid(frame)
        if grid is None or len(grid) == 0:
            return features

        features["grid_valid"] = True
        rows = len(grid)
        cols = max(len(r) for r in grid) if grid else 0
        if cols == 0:
            return features

        # Flatten to uniform 2D matrix (pad missing cells with 0)
        mat = [[grid[r][c] if c < len(grid[r]) else 0
                for c in range(cols)]
               for r in range(rows)]

        # Dominant colour — flatten to scalar values only (cells may be nested lists)
        def _scalar(v: Any) -> int:
            """Recursively extract a scalar int from any nested structure."""
            if isinstance(v, (list, tuple)):
                return _scalar(v[0]) if v else 0
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        all_vals = [_scalar(mat[r][c]) for r in range(rows) for c in range(cols)]
        # Rebuild mat with scalars for symmetry checks
        mat = [[_scalar(mat[r][c]) for c in range(cols)] for r in range(rows)]
        counter = Counter(all_vals)
        features["dominant_colour"] = counter.most_common(1)[0][0] if counter else 0
        features["colour_count"] = len(counter)
        features["complexity"] = len([v for v in counter if v != 0]) or 1

        # Active ratio (non-zero cells)
        total = rows * cols
        active = sum(1 for v in all_vals if v != 0)
        features["active_ratio"] = active / max(1, total)

        # Horizontal symmetry (row by row)
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

        # Vertical symmetry (column by column)
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

        # Delta mass vs previous frame
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
            # Single-row frame
            return [frame]
        return None


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 2 — EPISODIC MEMORY
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
        # fp → {action_value: score}
        self._scores: defaultdict[str, dict[int, float]] = defaultdict(dict)
        # action_value → total times tried
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
        """Return cumulative score of action on this grid state. 0.0 if unseen."""
        return self._scores[fp].get(action.value, 0.0)

    def best_on_state(
        self,
        fp: str,
        candidates: list[GameAction],
    ) -> Optional[GameAction]:
        """Return the action with highest memory score on fp, or None if all unseen."""
        scores = {a: self._scores[fp].get(a.value, None) for a in candidates}
        known = {a: s for a, s in scores.items() if s is not None}
        if not known:
            return None
        return max(known, key=known.__getitem__)

    def n_tried(self, action: GameAction) -> int:
        return self._n_tried[action.value]


# ──────────────────────────────────────────────────────────────────────────────
# MODULE 3 — COGNITIVE ENGINE
# ──────────────────────────────────────────────────────────────────────────────

class _CognitiveEngine:
    """Scores available actions using the four cognitive signals.

    D-LUCY-001: pure arithmetic, no external call.

    score(action) = W_MEMORY      * memory_score(fp, action)   [recalled experience]
                  + W_PROGRESS    * progress_score(action)      [frame delta history]
                  + W_DIVERSITY   * diversity_score(action)     [exploration bonus]
                  + W_PERCEPTION  * perception_hint(feats, action) [grid-based hint]
    """

    def __init__(
        self,
        memory: _EpisodicMemory,
        n_progress: Counter,
        n_total: Counter,
    ) -> None:
        self._memory = memory
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

            # Signal 2 — historical progress rate (actions that moved the frame)
            prog = self._n_progress[v] / n

            # Signal 3 — diversity bonus (under-tried actions get boost)
            tried = self._memory.n_tried(action)
            div = 1.0 - (tried / max(max_tried, 1))

            # Signal 4 — perception hint (grid-feature based heuristic)
            hint = self._perception_hint(features, action)

            total = (
                W_MEMORY * mem
                + W_PROGRESS * prog
                + W_DIVERSITY * div
                + W_PERCEPTION * hint
            )
            scores[action] = total

        return scores

    @staticmethod
    def _perception_hint(features: dict, action: GameAction) -> float:
        """Heuristic: which action is likely useful given grid features.

        Rules (no external oracle — pure pattern heuristics):
        - High symmetry → prefer simple navigation actions (ACTION1..5)
        - Low active_ratio + non-zero complexity → try ACTION6 (complex, spatial)
        - High delta_mass (frame is growing) → continue same class of actions
        - High complexity (many colours) → prefer ACTION6 (can target a colour)
        """
        if not features.get("grid_valid", False):
            return 0.5  # neutral if no grid data

        sym = (features.get("symmetry_h", 0.0) + features.get("symmetry_v", 0.0)) / 2.0
        active = features.get("active_ratio", 0.5)
        complexity = features.get("complexity", 1)
        delta_mass = features.get("delta_mass", 0)

        v = action.value

        if v in _SIMPLE_ACTIONS:
            # Simple actions: preferred when grid has high symmetry or is nearly empty
            score = 0.5
            if sym > 0.7:
                score += 0.3
            if active < 0.2:
                score += 0.2
            if delta_mass > 0:
                score += 0.1
            return min(score, 1.0)

        if v in _COMPLEX_ACTIONS:
            # ACTION6 (x,y): preferred when grid has many distinct colours / complex patterns
            score = 0.3
            if complexity >= 3:
                score += 0.3
            if active > 0.5:
                score += 0.2
            if sym < 0.5:
                score += 0.2
            return min(score, 1.0)

        return 0.5  # neutral for unknown action types


# ──────────────────────────────────────────────────────────────────────────────
# MAIN AGENT — LuCY v10.0
# ──────────────────────────────────────────────────────────────────────────────

class MyAgent(Agent):
    """LuCY Noyau Cognitif v10.0 — native cognitive agent, zero external LLM.

    D-LUCY-001: LuCY IS her own type of cognitive model.

    Three phases:
      EXPLORE  : try every available action at least once (diversity-first).
      EXPLOIT  : cognitive scoring engine selects best action.
      RECOVER  : after stagnation, diversify or force RESET.

    Forensic events (stdout, nanosecond timestamps):
      GAME_INIT, PERCEPTION, COGNITIVE_SCORE, ACTION_BEFORE, ACTION_AFTER,
      LEVEL_UP, STUCK, RESET, MODEL_UPDATE, GAME_DONE, SUMMARY.

    CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
    """

    MAX_ACTIONS = MAX_ACTIONS_TOTAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))

        # Forensic logger (NS precision)
        self._forensic = _KaggleForensicLogger(game_id=str(self.game_id))

        # Cognitive modules (D-LUCY-001: native, no LLM)
        self._perceptor = _GridPerceptor()
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
        self._phase: str = "explore"

        if DEBUG:
            print(
                f"[LuCY v{VERSION}] game_id={self.game_id!r} "
                f"NOYAU_COGNITIF_NATIF external_llm=False "
                f"MAX_ACTIONS={MAX_ACTIONS_TOTAL}",
                flush=True,
            )

    # ── Contract ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"LuCY-NoyauCognitif-v{VERSION}"

    def is_done(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> bool:
        """BUG-B2/C3 fix: stop on WIN or budget exhaustion."""
        if latest_frame.state is GameState.WIN:
            self._forensic.on_done(
                reason="WIN",
                levels_completed=self._levels_completed,
                total_actions=self._action_count,
            )
            return True
        if self._action_count >= MAX_ACTIONS_TOTAL - 1:
            self._forensic.on_done(
                reason="BUDGET_EXHAUSTED",
                levels_completed=self._levels_completed,
                total_actions=self._action_count,
            )
            return True
        return False

    def choose_action(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> GameAction:
        self._action_count += 1
        self._level_action_count += 1

        # ── Terminal state → RESET ────────────────────────────────────────────
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._forensic.on_state_change = getattr(
                self._forensic, "on_state_change",
                lambda *a, **kw: None
            )
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

        # ── Cognitive perception (MOD-1) ──────────────────────────────────────
        prev_raw = frames[-2].frame if len(frames) >= 2 else None
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
            self._phase = "exploit"

        # ── Record outcome of previous action ────────────────────────────────
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

        # ── Emit forensic BEFORE action selection ─────────────────────────────
        ts_before = self._forensic.on_action_before(
            action_count=self._action_count,
            phase=self._phase,
            candidates=candidates,
            fp=fp,
            stuck_streak=self._stuck_streak,
            levels_completed=self._levels_completed,
        )

        # ── Phase dispatch — cognitive engine ─────────────────────────────────
        unseen = [a for a in candidates
                  if self._memory.n_tried(a) == 0]

        if self._phase == "explore" and unseen:
            # EXPLORE: try unseen actions first (random order — BUG-C1 fix)
            action = random.choice(unseen)

        elif self._phase == "recover":
            # RECOVER: prefer least-tried candidates
            if unseen:
                action = random.choice(unseen)
            else:
                engine = _CognitiveEngine(
                    self._memory, self._n_progress, self._n_total
                )
                scores = engine.score_all(fp, candidates, features, self._action_count)
                # In recover: pick action with LOWEST score (escape local minimum)
                action = min(candidates, key=lambda a: scores.get(a, 0.0))

        else:
            # EXPLOIT: cognitive scoring engine (MOD-3)
            self._phase = "exploit"
            engine = _CognitiveEngine(
                self._memory, self._n_progress, self._n_total
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
            # ACTION6: use perception features to choose target region
            active_ratio = features.get("active_ratio", 0.5)
            # Target region: if grid is sparse, target the active area (~centre);
            # if dense, target a random location for exploration
            if features.get("grid_valid", False) and active_ratio < 0.5:
                # Sparse grid → aim near centre
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
            print(
                f"[LuCY] n={self._action_count} action={action.name} "
                f"phase={self._phase} levels={self._levels_completed} "
                f"stuck={self._stuck_streak} "
                f"avail={[a.name for a in candidates]}",
                flush=True,
            )

        return action
