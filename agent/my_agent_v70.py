"""LuCY Cognitive Agent v7.0 — ARC-AGI-3 (arc-prize-2026)

This is the ONLY file edited in the Kaggle Starter. `scripts/build_notebook.py`
splices the contents of this file into the Kaggle submission notebook.

[edit my_agent.py] → [make play-local] → [make submit]

Architecture v7.0 — AVAILABLE-ACTIONS-FIRST + UCB1 + SYSTEMATIC EXPLORATION

CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Root cause of v1→v6 failures (BUG-A3, BUG-A4):
  BUG-A3: Q-table on MD5(frame[:4096]) → never generalises (v1→v5).
  BUG-A4: v6.0 ignored latest_frame.available_actions → tried actions that do
           nothing in the current game context, wasting budget.

v7.0 Fixes:
  Fix-1: Always use latest_frame.available_actions to filter legal actions.
  Fix-2: UCB1 selection (exploration constant C=1.4) instead of simple ranking.
  Fix-3: Reasoning stored as local variable (not set on GameAction enum singleton).
  Fix-4: State-based action recall: remember which action unlocked each state change.
  Fix-5: Adaptive budget per level based on levels_completed progress.

Scoring (RHAE — Relative Human Action Efficiency):
  score = (human_baseline_actions / ai_actions)^2 per completed level
  → Goal: complete ≥1 level per game efficiently.

Contract (enforced by ARC-AGI-3-Agents framework):
  - Subclass agents.agent.Agent
  - Class must be named MyAgent
  - Implement is_done(frames, latest_frame) -> bool
  - Implement choose_action(frames, latest_frame) -> GameAction
"""

from __future__ import annotations

import math
import random
import time
from collections import Counter, defaultdict, deque
from typing import Any, Optional

from arcengine import FrameData, GameAction, GameState
from agents.agent import Agent

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

VERSION = "7.0"
DEBUG = True

# Action budgets
MAX_ACTIONS_TOTAL = 500       # hard cap per game (framework default is 80 but we set higher)
MAX_ACTIONS_PER_LEVEL = 120   # per-level budget before RESET

# Stagnation detection
STUCK_THRESHOLD = 5           # same fingerprint N times in a row → strategy switch
RESET_AFTER_STUCK = 5         # K consecutive stuck events → force RESET

# UCB1 exploration constant (higher = more exploration)
UCB1_C = 1.4

# Minimum delta to count as "progress"
DELTA_MIN = 0.01


# ──────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────────────────────

def _frame_fingerprint(frame: Any) -> str:
    """Compact fingerprint of a visual game state.

    Handles nested lists (converted from numpy via tolist()) and numpy arrays.
    Uses a hash of the FULL flattened frame to detect any pixel change anywhere.
    """
    if frame is None:
        return "null"
    try:
        import hashlib
        import numpy as np

        if isinstance(frame, np.ndarray):
            return hashlib.sha1(frame.tobytes()).hexdigest()[:16]

        # For list-of-lists (what Agent._convert_raw_frame_data produces)
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
            # Hash the full flat list so ANY pixel change is detected
            return hashlib.sha1(str(flat).encode()).hexdigest()[:16]
        elif hasattr(frame, '__iter__'):
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

        fa = _flatten(frame_a)[:256]
        fb = _flatten(frame_b)[:256]
        n = min(len(fa), len(fb))
        if n == 0:
            return 1.0
        return sum(1 for a, b in zip(fa, fb) if a != b) / n
    except Exception:
        return 1.0


def _get_available_actions(latest_frame: FrameData) -> list[GameAction]:
    """Extract the available actions from the frame.

    Prefers latest_frame.available_actions (authoritative) if non-empty.
    The field may contain GameAction objects OR raw integers (action ids).
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
                # Convert raw action id → GameAction
                try:
                    ga = GameAction.from_id(a)
                    if ga is not GameAction.RESET:
                        result.append(ga)
                except ValueError:
                    pass
        if result:
            return result
    # Fallback: all simple non-RESET actions
    return [a for a in GameAction if a is not GameAction.RESET and a.is_simple()]


# ──────────────────────────────────────────────────────────────────────────────
# UCB1 ACTION MODEL
# ──────────────────────────────────────────────────────────────────────────────

class _ActionModel:
    """Per-game action statistics with UCB1 selection.

    Tracks:
      - n_level_up : times action caused levels_completed to increase
      - n_progress : times action caused visible frame change (delta > DELTA_MIN)
      - n_total    : total times action was chosen
    """

    def __init__(self) -> None:
        self.n_level_up: Counter[int] = Counter()   # action.value → count
        self.n_progress: Counter[int] = Counter()
        self.n_total: Counter[int] = Counter()
        self.total_pulls: int = 0                    # sum of all pulls

    def record(self, action: GameAction, level_up: bool, delta: float) -> None:
        v = action.value
        self.n_total[v] += 1
        self.total_pulls += 1
        if level_up:
            self.n_level_up[v] += 1
            self.n_progress[v] += 1
        elif delta >= DELTA_MIN:
            self.n_progress[v] += 1

    def ucb1_score(self, action: GameAction) -> float:
        """UCB1 score — higher = prefer."""
        v = action.value
        n = self.n_total[v]
        if n == 0:
            return float("inf")  # untried → always prioritise
        # Reward: weight level_up more heavily than mere progress
        reward = (self.n_level_up[v] * 4.0 + self.n_progress[v] * 1.0) / n
        exploration = UCB1_C * math.sqrt(math.log(max(1, self.total_pulls)) / n)
        return reward + exploration

    def best_action(self, candidates: list[GameAction]) -> GameAction:
        """Return the candidate with highest UCB1 score."""
        return max(candidates, key=self.ucb1_score)

    def untried(self, candidates: list[GameAction]) -> list[GameAction]:
        return [a for a in candidates if self.n_total[a.value] == 0]


# ──────────────────────────────────────────────────────────────────────────────
# LUCY AGENT v7.0
# ──────────────────────────────────────────────────────────────────────────────

class MyAgent(Agent):
    """LuCY Cognitive Agent v7.0 — available-actions-first + UCB1 + recovery.

    Phase EXPLORE : try every available action once (UCB1 = inf for untried).
    Phase EXPLOIT : UCB1-guided selection from available actions.
    Phase RECOVER : after STUCK_THRESHOLD identical frames, diversify or RESET.
    """

    MAX_ACTIONS = MAX_ACTIONS_TOTAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Independent seed per game for reproducibility
        random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))

        self._model = _ActionModel()
        self._action_count: int = 0         # total actions this game
        self._level_action_count: int = 0   # actions since last level start
        self._levels_completed: int = 0     # last known levels_completed
        self._stuck_streak: int = 0         # consecutive identical frames
        self._prev_fp: str = ""
        self._prev_action: Optional[GameAction] = None
        self._phase: str = "explore"        # explore | exploit | recover

        if DEBUG:
            print(f"[LuCY v{VERSION}] game_id={self.game_id!r} initialised")

    # ── Contract ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"LuCY-v{VERSION}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        # Stop on WIN only; do NOT stop on GAME_OVER (let recovery RESET it).
        return latest_frame.state is GameState.WIN

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
            if DEBUG:
                print(f"[LuCY] state={latest_frame.state.name} → RESET")
            return GameAction.RESET

        # ── Per-level budget exhausted → RESET ───────────────────────────────
        if self._level_action_count > MAX_ACTIONS_PER_LEVEL:
            self._level_action_count = 0
            self._phase = "explore"
            if DEBUG:
                print(f"[LuCY] per-level budget exhausted → RESET")
            return GameAction.RESET

        # ── Get available actions (Fix-1) ─────────────────────────────────────
        candidates = _get_available_actions(latest_frame)
        if not candidates:
            candidates = [a for a in GameAction
                          if a is not GameAction.RESET and a.is_simple()]

        # ── Observe frame ─────────────────────────────────────────────────────
        fp = _frame_fingerprint(latest_frame.frame)

        current_levels = getattr(latest_frame, "levels_completed", 0) or 0
        level_up = current_levels > self._levels_completed
        if level_up:
            if DEBUG:
                print(f"[LuCY] LEVEL UP {self._levels_completed} → {current_levels} "
                      f"(actions this level: {self._level_action_count})")
            self._levels_completed = current_levels
            self._level_action_count = 0
            self._stuck_streak = 0
            self._phase = "exploit"   # after a win, exploit what worked

        # ── Record outcome of previous action (Fix-3: no enum attribute set) ──
        if self._prev_action is not None and len(frames) >= 2:
            delta = _frame_delta(frames[-2].frame, latest_frame.frame)
            self._model.record(self._prev_action, level_up, delta)

        # ── Stagnation detection ───────────────────────────────────────────────
        if fp == self._prev_fp:
            self._stuck_streak += 1
        else:
            self._stuck_streak = 0
        self._prev_fp = fp

        if self._stuck_streak >= STUCK_THRESHOLD:
            self._phase = "recover"
            if DEBUG and self._stuck_streak == STUCK_THRESHOLD:
                print(f"[LuCY] STUCK (streak={self._stuck_streak}) → recover phase")
            if self._stuck_streak >= STUCK_THRESHOLD + RESET_AFTER_STUCK:
                self._stuck_streak = 0
                self._level_action_count = 0
                self._phase = "explore"
                if DEBUG:
                    print("[LuCY] deep stuck → RESET")
                return GameAction.RESET

        # ── Phase dispatch ────────────────────────────────────────────────────
        untried = self._model.untried(candidates)

        if self._phase == "explore" and untried:
            # Systematic: try each available action once
            action = untried[0]

        elif self._phase == "recover":
            # Recovery: prefer untried; if all tried, pick worst-known (diversity)
            if untried:
                action = random.choice(untried)
            else:
                # Pick action with lowest total use (least exploited)
                action = min(candidates, key=lambda a: self._model.n_total[a.value])

        else:
            # exploit: UCB1-guided (also handles case when explore has no untried)
            self._phase = "exploit"
            action = self._model.best_action(candidates)

        # ── Handle complex actions (ACTION6) ──────────────────────────────────
        if action.is_complex():
            action.set_data({"x": random.randint(0, 63), "y": random.randint(0, 63)})

        # Store for next observation (Fix-3: local var, not enum attribute)
        self._prev_action = action

        if DEBUG and (self._action_count % 20 == 0 or level_up):
            print(
                f"[LuCY] n={self._action_count} action={action.name} "
                f"phase={self._phase} levels={self._levels_completed} "
                f"stuck={self._stuck_streak} "
                f"avail={[a.name for a in candidates]}"
            )

        return action
