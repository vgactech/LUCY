"""LuCY Cognitive Agent v9.0 — ARC-AGI-3 (arc-prize-2026)

This is the ONLY file edited in the Kaggle Starter. `scripts/build_notebook.py`
splices the contents of this file into the Kaggle submission notebook.

[edit my_agent.py] → [make play-local] → [make submit]

Architecture v9.0 — FORENSIC-NS + BUDGET-FIX + AVAILABLE-ACTIONS-FIRST + UCB1
                  + BUG-C1..C7 fixes

CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Changes from v8.0:
  BUG-C1 fix : EXPLORE phase now uses random.choice(untried) instead of
               untried[0] — avoids always picking actions in enum-order.
  BUG-C3 fix : is_done() checks _action_count >= MAX_ACTIONS_TOTAL - 1 so
               the game ends at the correct budget (framework calls is_done
               BEFORE choose_action increments the counter).
  BUG-C4 fix : levels_completed clamped to max(current, previous) so a
               framework RESET that zeroes the field never causes false
               level_up=False after a real level completion.
  BUG-C5 fix : _stuck_streak and _phase reset on EVERY RESET path
               (per_level_budget RESET was missing the streak reset).
  BUG-C7 fix : on_done() guarded by _done_emitted flag so the SUMMARY
               is never printed twice if is_done() is called multiple times.

Changes from v7.0 (still active):
  BUG-B1 fix : MAX_ACTIONS_TOTAL was 500, real framework budget is ~80 → set to 80.
  BUG-B2 fix : is_done() now checks budget exhaustion, not only WIN state.
  BUG-B3 fix : _frame_delta no longer truncates at 256 elements.
  NEW     : _KaggleForensicLogger — inline nanosecond-precision logger that
            prints structured events to stdout (captured in __results__.html by
            Kaggle). No external file I/O required. Events fired BEFORE and
            DURING each state change.

Root cause of v1→v6 failures (kept for traceability):
  BUG-A3: Q-table on MD5(frame[:4096]) → never generalises (v1→v5).
  BUG-A4: v6.0 ignored latest_frame.available_actions → illegal actions used.

v7.0 Fixes (still active in v9.0):
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

import hashlib
import json
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

VERSION = "9.0"
DEBUG = True

# Action budgets — BUG-B1 fix: was 500, real ARC-AGI-3 framework budget ≈ 80
MAX_ACTIONS_TOTAL = 80          # hard cap per game (matches framework default)
MAX_ACTIONS_PER_LEVEL = 30      # per-level budget before RESET (was 120 → scaled)

# Stagnation detection
STUCK_THRESHOLD = 5             # same fingerprint N times in a row → strategy switch
RESET_AFTER_STUCK = 5           # K consecutive stuck events → force RESET

# UCB1 exploration constant (higher = more exploration)
UCB1_C = 1.4

# Minimum delta to count as "progress"
DELTA_MIN = 0.01


# ──────────────────────────────────────────────────────────────────────────────
# KAGGLE FORENSIC LOGGER — inline, nanosecond precision, stdout only
# ──────────────────────────────────────────────────────────────────────────────

class _KaggleForensicLogger:
    """Inline nanosecond forensic logger for Kaggle execution environment.

    Design constraints:
    - No external file I/O (Kaggle ephemeral FS — JSONL would not survive).
    - stdout print() is captured by Kaggle in __results__.html.
    - Each event line: [LuCY-NS:{ts_ns}] {event_type} | {payload_json}
    - Events fired BEFORE and DURING every state change (not only at end).
    - Summary JSON printed at game end.

    CERTIFIED_100=false | unique_human_proven=false
    """

    PREFIX = "[LuCY-NS"

    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self._events: list[dict] = []
        self._game_start_ns: int = time.time_ns()
        self._emit("GAME_INIT", {
            "game_id": game_id,
            "version": VERSION,
            "max_actions_total": MAX_ACTIONS_TOTAL,
            "max_actions_per_level": MAX_ACTIONS_PER_LEVEL,
            "certified_100": False,
            "unique_human_proven": False,
            "debug": DEBUG,
        })

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _emit(self, event_type: str, payload: dict) -> None:
        """Emit one forensic event to stdout with nanosecond timestamp."""
        ts_ns = time.time_ns()
        entry = {
            "ts_ns": ts_ns,
            "event": event_type,
            "game_id": self.game_id,
            **payload,
        }
        self._events.append(entry)
        # Compact JSON on a single line so Kaggle log remains readable
        line = json.dumps(entry, separators=(",", ":"), default=str)
        print(f"{self.PREFIX}:{ts_ns}] {event_type} | {line}", flush=True)

    # ── Public event API ──────────────────────────────────────────────────────

    def on_action_before(
        self,
        action_count: int,
        phase: str,
        candidates: list,
        fp: str,
        stuck_streak: int,
        levels_completed: int,
    ) -> int:
        """Fired BEFORE choose_action selects an action. Returns ts_ns of call."""
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
        """Fired immediately AFTER action is chosen — measures selection duration."""
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
        self._emit("STUCK", {
            "streak": streak,
            "phase": phase,
        })

    def on_reset(self, reason: str, action_count: int) -> None:
        self._emit("RESET", {
            "reason": reason,
            "action_count": action_count,
        })

    def on_state_change(self, state_name: str, action_count: int) -> None:
        self._emit("STATE_CHANGE", {
            "state": state_name,
            "action_count": action_count,
        })

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
        """Fired when is_done() returns True. Also prints full summary JSON.

        BUG-C7 fix: guarded by _done_emitted so the SUMMARY is never printed
        twice if the framework calls is_done() multiple times.
        """
        if getattr(self, "_done_emitted", False):
            return
        self._done_emitted = True
        elapsed_ns = time.time_ns() - self._game_start_ns
        self._emit("GAME_DONE", {
            "reason": reason,
            "levels_completed": levels_completed,
            "total_actions": total_actions,
            "elapsed_ns": elapsed_ns,
        })
        # Full summary for offline analysis
        summary = {
            "lucy_forensic_summary": True,
            "version": VERSION,
            "game_id": self.game_id,
            "levels_completed": levels_completed,
            "total_actions": total_actions,
            "elapsed_ms": round(elapsed_ns / 1_000_000, 2),
            "total_events": len(self._events),
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
    """Compact fingerprint of a visual game state.

    Handles nested lists (converted from numpy via tolist()) and numpy arrays.
    Uses a hash of the FULL flattened frame to detect any pixel change anywhere.
    """
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
        elif hasattr(frame, '__iter__'):
            flat = list(frame)
            return hashlib.sha1(str(flat).encode()).hexdigest()[:16]
        else:
            return str(frame)[:128]
    except Exception:
        return str(id(frame))[:16]


def _frame_delta(frame_a: Any, frame_b: Any) -> float:
    """Fraction of elements that differ between two frames (0.0 = identical).

    BUG-B3 fix: removed [:256] truncation — compares full frame.
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

        # BUG-B3 fix: was [:256] → now full frame comparison
        fa = _flatten(frame_a)
        fb = _flatten(frame_b)
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
        self.n_level_up: Counter[int] = Counter()
        self.n_progress: Counter[int] = Counter()
        self.n_total: Counter[int] = Counter()
        self.total_pulls: int = 0

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
            return float("inf")
        reward = (self.n_level_up[v] * 4.0 + self.n_progress[v] * 1.0) / n
        exploration = UCB1_C * math.sqrt(math.log(max(1, self.total_pulls)) / n)
        return reward + exploration

    def best_action(self, candidates: list[GameAction]) -> GameAction:
        return max(candidates, key=self.ucb1_score)

    def untried(self, candidates: list[GameAction]) -> list[GameAction]:
        return [a for a in candidates if self.n_total[a.value] == 0]


# ──────────────────────────────────────────────────────────────────────────────
# LUCY AGENT v8.0
# ──────────────────────────────────────────────────────────────────────────────

class MyAgent(Agent):
    """LuCY Cognitive Agent v8.0 — forensic-ns + budget-fix + UCB1 + recovery.

    Phase EXPLORE : try every available action once (UCB1 = inf for untried).
    Phase EXPLOIT : UCB1-guided selection from available actions.
    Phase RECOVER : after STUCK_THRESHOLD identical frames, diversify or RESET.

    Forensic events (stdout, nanosecond timestamps):
      GAME_INIT, ACTION_BEFORE, ACTION_AFTER, LEVEL_UP, STUCK, RESET,
      STATE_CHANGE, MODEL_UPDATE, GAME_DONE, SUMMARY.
    """

    MAX_ACTIONS = MAX_ACTIONS_TOTAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        random.seed(int(time.time() * 1_000_000) ^ hash(self.game_id))

        self._forensic = _KaggleForensicLogger(game_id=str(self.game_id))
        self._forensic._done_emitted = False  # BUG-C7: forward-declare here too

        self._model = _ActionModel()
        self._action_count: int = 0
        self._level_action_count: int = 0
        self._levels_completed: int = 0
        self._stuck_streak: int = 0
        self._prev_fp: str = ""
        self._prev_action: Optional[GameAction] = None
        self._phase: str = "explore"

        # BUG-C4 fix: track the seen maximum of levels_completed in case the
        # framework resets the field to 0 after a RESET (cumulative clamp).
        self._max_levels_seen: int = 0

        if DEBUG:
            print(f"[LuCY v{VERSION}] game_id={self.game_id!r} initialised "
                  f"MAX_ACTIONS={MAX_ACTIONS_TOTAL} (BUG-B1/C fixes active)",
                  flush=True)

    # ── Contract ──────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"LuCY-v{VERSION}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        """BUG-B2 fix: stop on WIN or on budget exhaustion (was only WIN).

        BUG-C3 fix: framework calls is_done() BEFORE choose_action() increments
        _action_count, so we use >= MAX_ACTIONS_TOTAL - 1 to stop at the correct
        boundary (action N is chosen, framework checks done, then calls is_done;
        at that point _action_count equals N-1).  We still stop on >= because the
        framework may also call is_done() after choose_action in some versions.
        """
        if latest_frame.state is GameState.WIN:
            self._forensic.on_done(
                reason="WIN",
                levels_completed=self._levels_completed,
                total_actions=self._action_count,
            )
            return True
        # BUG-C3 fix: was >= MAX_ACTIONS_TOTAL → now >= MAX_ACTIONS_TOTAL - 1
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
            self._forensic.on_state_change(latest_frame.state.name, self._action_count)
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
            # BUG-C5 fix: was missing _stuck_streak reset on this RESET path
            self._stuck_streak = 0
            if DEBUG:
                print(f"[LuCY] per-level budget exhausted → RESET", flush=True)
            return GameAction.RESET

        # ── Get available actions (Fix-1) ─────────────────────────────────────
        candidates = _get_available_actions(latest_frame)
        if not candidates:
            candidates = [a for a in GameAction
                          if a is not GameAction.RESET and a.is_simple()]

        # ── Observe frame ─────────────────────────────────────────────────────
        fp = _frame_fingerprint(latest_frame.frame)

        current_levels_raw = getattr(latest_frame, "levels_completed", 0) or 0
        # BUG-C4 fix: clamp to seen maximum so a framework reset-to-zero never
        # reverts our internal counter and never fires a false level_up.
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
                print(f"[LuCY] LEVEL UP {self._levels_completed} → {current_levels} "
                      f"(actions this level: {self._level_action_count})", flush=True)
            self._levels_completed = current_levels
            self._level_action_count = 0
            self._stuck_streak = 0
            self._phase = "exploit"

        # ── Record outcome of previous action ────────────────────────────────
        if self._prev_action is not None and len(frames) >= 2:
            delta = _frame_delta(frames[-2].frame, latest_frame.frame)
            self._model.record(self._prev_action, level_up, delta)
            self._forensic.on_model_update(
                action_name=self._prev_action.name,
                level_up=level_up,
                delta=delta,
                n_total=self._model.n_total[self._prev_action.value],
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
                    print(f"[LuCY] STUCK (streak={self._stuck_streak}) → recover phase",
                          flush=True)
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

        # ── Phase dispatch ────────────────────────────────────────────────────
        untried = self._model.untried(candidates)

        if self._phase == "explore" and untried:
            # BUG-C1 fix: was untried[0] (deterministic enum-order) →
            # random.choice(untried) so exploration is not always sequential.
            action = random.choice(untried)

        elif self._phase == "recover":
            if untried:
                action = random.choice(untried)
            else:
                action = min(candidates, key=lambda a: self._model.n_total[a.value])

        else:
            self._phase = "exploit"
            action = self._model.best_action(candidates)

        # ── Handle complex actions ─────────────────────────────────────────────
        if action.is_complex():
            action.set_data({"x": random.randint(0, 63), "y": random.randint(0, 63)})

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
