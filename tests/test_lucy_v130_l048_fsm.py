"""Tests L-048 — _SelectPlaceFSM + _validate_transposition

Tests couverts :
  T-FSM-01 … T-FSM-05  : _validate_transposition (5 assertions A1–A5)
  T-FSM-06 … T-FSM-10  : _SelectPlaceFSM._classify_frame (floor/piece/target)
  T-FSM-11 … T-FSM-15  : _SelectPlaceFSM._is_confirmed_selection
  T-FSM-16 … T-FSM-20  : _SelectPlaceFSM._is_confirmed_placement
  T-FSM-21 … T-FSM-25  : _SelectPlaceFSM.step() transitions OBSERVE→SELECT→PLACE→OBSERVE
  T-FSM-26 … T-FSM-30  : Robustesse (frame None, vide, ndarray, recovery)

CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif
"""

from __future__ import annotations

import sys
import os
import types
from typing import Any

# ── Stub arcengine (not available outside Kaggle) ─────────────────────────────
arcengine_stub = types.ModuleType("arcengine")


class _GameStateObj:
    WIN = "WIN"
    NOT_PLAYED = "NOT_PLAYED"
    GAME_OVER = "GAME_OVER"
    PLAYING = "PLAYING"


_ALL_ACTION_VALUES = [0, 1, 2, 3, 4, 5, 6, 7]


class _GameAction:
    _instances: dict = {}

    def __init__(self, value: int) -> None:
        self.value = value
        self.name = f"ACTION{value}"

    def is_complex(self) -> bool:
        return self.value == 6

    def is_simple(self) -> bool:
        return not self.is_complex()

    def set_data(self, d: dict) -> None:
        self._data = d

    @classmethod
    def from_id(cls, v: int) -> "_GameAction":
        if v not in cls._instances:
            cls._instances[v] = cls(v)
        return cls._instances[v]

    def __class_getitem__(cls, item: Any) -> Any:
        return cls

    def __iter__(self):
        return iter([_GameAction(v) for v in _ALL_ACTION_VALUES])

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, _GameAction):
            return item.value in _ALL_ACTION_VALUES
        return item in _ALL_ACTION_VALUES


# Singleton class-level iterator support via metaclass trick
class _GameActionMeta(type):
    def __iter__(cls):
        return iter([_GameAction(v) for v in _ALL_ACTION_VALUES])

    def __contains__(cls, item: Any) -> bool:
        if isinstance(item, _GameAction):
            return item.value in _ALL_ACTION_VALUES
        return False


class GameActionClass(_GameAction, metaclass=_GameActionMeta):
    RESET = _GameAction(0)  # treat value=0 as RESET for stub purposes

    @classmethod
    def from_id(cls, v: int) -> "_GameAction":
        return _GameAction(v)


_game_state_obj = _GameStateObj()


arcengine_stub.GameState = _game_state_obj
arcengine_stub.GameAction = GameActionClass
arcengine_stub.FrameData = object

# Also make GameState attributes work as identity comparison
_game_state_obj.WIN = _game_state_obj.WIN
_game_state_obj.NOT_PLAYED = _game_state_obj.NOT_PLAYED
_game_state_obj.GAME_OVER = _game_state_obj.GAME_OVER


class _AgentsAgent:
    pass


agents_stub = types.ModuleType("agents")
agent_stub = types.ModuleType("agents.agent")
agent_stub.Agent = _AgentsAgent
agents_stub.agent = agent_stub

sys.modules.setdefault("arcengine", arcengine_stub)
sys.modules.setdefault("agents", agents_stub)
sys.modules.setdefault("agents.agent", agent_stub)

# ── Import the module under test ───────────────────────────────────────────────
_agent_path = os.path.join(os.path.dirname(__file__), "..", "agent", "my_agent_v130.py")
import importlib.util

spec = importlib.util.spec_from_file_location("my_agent_v130", _agent_path)
mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(mod)  # type: ignore[union-attr]

_validate_transposition = mod._validate_transposition
_SelectPlaceFSM = mod._SelectPlaceFSM


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-01 … 05 — _validate_transposition (5 deterministic assertions)
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_01_validate_transposition_returns_dict():
    """T-FSM-01: _validate_transposition returns a dict with expected keys."""
    result = _validate_transposition([[[1, 2], [3, 4]]])
    assert isinstance(result, dict)
    assert "ok" in result
    assert "passed" in result
    assert "failed" in result
    assert "details" in result


def test_fsm_02_validate_transposition_a1_asymmetric():
    """T-FSM-02: A1 — 2×2 asymmetric columnar frame transposed correctly."""
    result = _validate_transposition([[[1, 2], [3, 4]]])
    assert result["ok"] is True, f"details={result['details']}"
    assert result["passed"] == 5
    assert result["failed"] == 0


def test_fsm_03_validate_transposition_a3_single_cell():
    """T-FSM-03: A3 — single non-zero cell at col=1, row=2 → grid[2][1]=7."""
    result = _validate_transposition([[[0, 0, 0, 0], [0, 0, 7, 0], [0, 0, 0, 0]]])
    # We only check that A3 itself passed
    a3 = next((d for d in result["details"] if d["test"] == "A3_single_nonzero_cell"), None)
    assert a3 is not None, "A3 test not found in details"
    assert a3["passed"] is True, f"A3 detail: {a3}"


def test_fsm_04_validate_transposition_a4_no_crash():
    """T-FSM-04: A4 — empty / None frames must not raise exceptions."""
    result = _validate_transposition(None)
    # Validator itself should not raise — it returns a result
    assert isinstance(result, dict)
    # A4 should be PASS (None handled gracefully)
    a4 = next((d for d in result.get("details", []) if d["test"] == "A4_empty_no_crash"), None)
    if a4 is not None:
        assert a4["passed"] is True, f"A4 detail: {a4}"


def test_fsm_05_validate_transposition_a5_dimensions():
    """T-FSM-05: A5 — 4 cols × 3 rows → grid is 3 rows × 4 cols."""
    result = _validate_transposition([[[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]])
    a5 = next((d for d in result["details"] if d["test"] == "A5_dimensions_4cols_3rows"), None)
    assert a5 is not None
    assert a5["passed"] is True, f"A5 detail: {a5}"


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-06 … 10 — _SelectPlaceFSM._classify_frame
# ──────────────────────────────────────────────────────────────────────────────

def _make_grid(rows: int, cols: int, fill: int = 0) -> list:
    return [[fill] * cols for _ in range(rows)]


def test_fsm_06_classify_floor_dominates():
    """T-FSM-06: dominant colour = floor."""
    fsm = _SelectPlaceFSM()
    # 4×4 grid, colour 5 dominant (12 cells), colour 2 (3 cells), colour 3 (1 cell)
    grid = [
        [5, 5, 5, 5],
        [5, 2, 2, 5],
        [5, 2, 3, 5],
        [5, 5, 5, 5],
    ]
    fsm._classify_frame(grid)
    assert fsm._floor_colour == 5


def test_fsm_07_classify_piece_colour():
    """T-FSM-07: piece colour = second most frequent non-floor."""
    fsm = _SelectPlaceFSM()
    grid = [
        [5, 5, 5, 5],
        [5, 2, 2, 5],
        [5, 2, 3, 5],
        [5, 5, 5, 5],
    ]
    fsm._classify_frame(grid)
    assert fsm._piece_colour == 2


def test_fsm_08_classify_target_colour():
    """T-FSM-08: target colour = third most frequent non-floor."""
    fsm = _SelectPlaceFSM()
    grid = [
        [5, 5, 5, 5],
        [5, 2, 2, 5],
        [5, 2, 3, 5],
        [5, 5, 5, 5],
    ]
    fsm._classify_frame(grid)
    assert fsm._target_colour == 3


def test_fsm_09_classify_piece_cells_coordinates():
    """T-FSM-09: piece_cells contains all cells with piece_colour."""
    fsm = _SelectPlaceFSM()
    # floor=0, piece=1, target=2
    grid = [
        [0, 0, 0],
        [0, 1, 0],
        [0, 0, 2],
    ]
    fsm._classify_frame(grid)
    # piece_colour should be 1 or 2 (second most frequent non-zero)
    # 1 appears 1 time, 2 appears 1 time → piece=first of the two
    assert len(fsm._piece_cells) + len(fsm._target_cells) >= 1


def test_fsm_10_classify_fallback_when_only_two_colours():
    """T-FSM-10: if only floor+piece (no target), target_colour == piece_colour
    and combined target+piece cells = all non-floor cells."""
    fsm = _SelectPlaceFSM()
    # floor=0, only piece=1 (no third colour)
    grid = [
        [0, 0, 0],
        [0, 1, 1],
        [0, 0, 0],
    ]
    fsm._classify_frame(grid)
    # When only 2 colours, target_colour == piece_colour
    assert fsm._target_colour == fsm._piece_colour
    # All non-floor cells should appear in target_cells (since piece_colour==target_colour)
    all_non_floor = [(r, c) for r in range(3) for c in range(3) if grid[r][c] != 0]
    all_detected = fsm._piece_cells + fsm._target_cells
    assert len(all_detected) == len(all_non_floor), (
        f"piece_cells={fsm._piece_cells} target_cells={fsm._target_cells} "
        f"all_non_floor={all_non_floor}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-11 … 15 — _is_confirmed_selection
# ──────────────────────────────────────────────────────────────────────────────

def _col_frame(grid: list) -> list:
    """Convert row-major grid to columnar ARC-AGI-3 frame format."""
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    return [[[grid[r][c] for r in range(rows)] for c in range(cols)]]


def test_fsm_11_confirmed_selection_colour_change_near_click():
    """T-FSM-11: selection confirmed when colour changed near click coordinates."""
    fsm = _SelectPlaceFSM()
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    prev_grid = [[0, 0, 0], [0, 2, 0], [0, 0, 0]]
    curr_grid = [[0, 0, 0], [0, 7, 0], [0, 0, 0]]  # colour changed at (1,1)
    prev_frame = _col_frame(prev_grid)
    curr_frame = _col_frame(curr_grid)
    assert fsm._is_confirmed_selection(prev_frame, curr_frame) is True


def test_fsm_12_selection_not_confirmed_identical_frames():
    """T-FSM-12: selection not confirmed when frames are identical."""
    fsm = _SelectPlaceFSM()
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    grid = [[0, 0, 0], [0, 5, 0], [0, 0, 0]]
    frame = _col_frame(grid)
    assert fsm._is_confirmed_selection(frame, frame) is False


def test_fsm_13_selection_not_confirmed_change_far_from_click():
    """T-FSM-13: selection not confirmed when change is far from click zone."""
    fsm = _SelectPlaceFSM()
    fsm._last_click_r = 0
    fsm._last_click_c = 0
    prev_grid = [[1, 0, 0], [0, 0, 0], [0, 0, 2]]
    curr_grid = [[1, 0, 0], [0, 0, 0], [0, 0, 9]]  # change at (2,2), far from (0,0)
    prev_frame = _col_frame(prev_grid)
    curr_frame = _col_frame(curr_grid)
    # (0,0) neighbourhood: rows 0–1, cols 0–1 — no change there
    assert fsm._is_confirmed_selection(prev_frame, curr_frame) is False


def test_fsm_14_selection_none_frames():
    """T-FSM-14: _is_confirmed_selection returns False when frames are None."""
    fsm = _SelectPlaceFSM()
    assert fsm._is_confirmed_selection(None, None) is False
    assert fsm._is_confirmed_selection(None, [[[0]]]) is False
    assert fsm._is_confirmed_selection([[[0]]], None) is False


def test_fsm_15_selection_confirmed_neighbour_cell():
    """T-FSM-15: selection confirmed when a neighbour of click (not exact) changes."""
    fsm = _SelectPlaceFSM()
    fsm._last_click_r = 2
    fsm._last_click_c = 2
    prev_grid = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 3, 0], [0, 0, 0, 0]]
    curr_grid = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 7, 3, 0], [0, 0, 0, 0]]  # (2,1) changed
    prev_frame = _col_frame(prev_grid)
    curr_frame = _col_frame(curr_grid)
    assert fsm._is_confirmed_selection(prev_frame, curr_frame) is True


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-16 … 20 — _is_confirmed_placement
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_16_placement_confirmed_active_count_decreased():
    """T-FSM-16: placement confirmed when active cell count decreased."""
    fsm = _SelectPlaceFSM()
    fsm._floor_colour = 0
    fsm._piece_colour = 3
    fsm._prev_active_count = 4  # was 4 active cells
    # Now only 2 active cells
    curr_grid = [[0, 0, 0], [0, 3, 0], [0, 0, 0]]
    curr_frame = _col_frame(curr_grid)
    assert fsm._is_confirmed_placement(curr_frame) is True


def test_fsm_17_placement_not_confirmed_same_count():
    """T-FSM-17: placement not confirmed when active count unchanged."""
    fsm = _SelectPlaceFSM()
    fsm._floor_colour = 0
    fsm._piece_colour = 3
    fsm._prev_active_count = 1
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    curr_grid = [[0, 0, 0], [0, 3, 0], [0, 0, 0]]  # still 1 active cell
    curr_frame = _col_frame(curr_grid)
    # piece_colour still present near click → not placed
    assert fsm._is_confirmed_placement(curr_frame) is False


def test_fsm_18_placement_confirmed_piece_colour_gone():
    """T-FSM-18: placement confirmed when piece_colour disappeared from click zone."""
    fsm = _SelectPlaceFSM()
    fsm._floor_colour = 0
    fsm._piece_colour = 5
    fsm._prev_active_count = 2
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    # piece_colour (5) gone from click zone; only floor cells nearby
    curr_grid = [[0, 0, 0], [0, 0, 0], [0, 0, 5]]  # 5 far from (1,1)
    curr_frame = _col_frame(curr_grid)
    # active count same (1), piece_colour (5) present far away but NOT near click
    # Since prev_active_count=2 > current active=1 → confirmed by heuristic 1
    assert fsm._is_confirmed_placement(curr_frame) is True


def test_fsm_19_placement_none_frame():
    """T-FSM-19: _is_confirmed_placement returns False on None frame."""
    fsm = _SelectPlaceFSM()
    fsm._prev_active_count = 5
    assert fsm._is_confirmed_placement(None) is False


def test_fsm_20_placement_not_confirmed_piece_still_present():
    """T-FSM-20: placement not confirmed when piece_colour still visible near click."""
    fsm = _SelectPlaceFSM()
    fsm._floor_colour = 0
    fsm._piece_colour = 4
    fsm._prev_active_count = 3   # was 3
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    # 3 active cells of colour 4 — active count didn't decrease (still 3)
    curr_grid = [[0, 4, 0], [4, 4, 0], [0, 0, 0]]
    curr_frame = _col_frame(curr_grid)
    assert fsm._is_confirmed_placement(curr_frame) is False


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-21 … 25 — _SelectPlaceFSM.step() transitions
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_21_initial_state_is_observe():
    """T-FSM-21: FSM starts in OBSERVE state."""
    fsm = _SelectPlaceFSM()
    assert fsm._state == _SelectPlaceFSM.OBSERVE


def test_fsm_22_first_step_transitions_to_select():
    """T-FSM-22: first step (no prev_frame) → state SELECT, returns valid coords."""
    fsm = _SelectPlaceFSM()
    grid = [[0, 0, 0], [0, 2, 0], [0, 0, 3]]
    frame = _col_frame(grid)
    x, y, state = fsm.step(frame, None)
    assert state in ("SELECT", "SELECT_fallback_random")
    assert 0 <= x <= 63
    assert 0 <= y <= 63


def test_fsm_23_transitions_to_place_after_confirmed_selection():
    """T-FSM-23: step transitions SELECT→PLACE when selection is confirmed."""
    fsm = _SelectPlaceFSM()
    # Grid with piece (2) and target (3)
    prev_grid = [[0, 0, 0], [0, 2, 0], [0, 0, 3]]
    curr_grid = [[0, 0, 0], [0, 7, 0], [0, 0, 3]]  # piece changed colour near click
    prev_frame = _col_frame(prev_grid)
    curr_frame = _col_frame(curr_grid)

    # First step: OBSERVE → SELECT, click at piece cell
    x, y, state = fsm.step(prev_frame, None)
    assert state in ("SELECT", "SELECT_fallback_random")
    # Set click position near (1,1) so confirmation succeeds
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    fsm._state = _SelectPlaceFSM.SELECT

    # Second step: confirm selection → PLACE
    x2, y2, state2 = fsm.step(curr_frame, prev_frame)
    assert state2 in ("PLACE", "PLACE_fallback_random"), \
        f"Expected PLACE, got {state2}, FSM state={fsm._state}"


def test_fsm_24_recovery_after_max_consecutive_misses():
    """T-FSM-24: FSM resets to OBSERVE and reclassifies after MAX_CONSECUTIVE_MISSES."""
    fsm = _SelectPlaceFSM()
    grid = [[0, 2, 0], [0, 0, 0], [0, 0, 0]]
    frame = _col_frame(grid)

    # Force the FSM into SELECT with MAX_CONSECUTIVE_MISSES already reached
    fsm._state = _SelectPlaceFSM.SELECT
    fsm._consecutive_misses = _SelectPlaceFSM.MAX_CONSECUTIVE_MISSES

    # Next step must trigger recovery (reset to OBSERVE, then re-enter SELECT)
    x, y, state = fsm.step(frame, None)  # prev=None → no confirmation check
    # After recovery and re-classification, state should be SELECT
    assert state in ("SELECT", "SELECT_fallback_random"), \
        f"Expected SELECT after recovery, got {state}"
    # consecutive_misses was reset during recovery, but may be incremented
    # if the classification produced no piece_cells. Check it's < MAX.
    assert fsm._consecutive_misses < _SelectPlaceFSM.MAX_CONSECUTIVE_MISSES


def test_fsm_25_step_returns_valid_coords_always():
    """T-FSM-25: step() always returns (x, y) in [0, 63] regardless of frame content."""
    fsm = _SelectPlaceFSM()
    for frame_input in [None, [], [[[]]],
                        _col_frame([[1, 2], [3, 4]]),
                        _col_frame([[0] * 10 for _ in range(10)])]:
        x, y, _ = fsm.step(frame_input, None)
        assert 0 <= x <= 63, f"x={x} out of range for frame={frame_input}"
        assert 0 <= y <= 63, f"y={y} out of range for frame={frame_input}"


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-26 … 30 — Robustesse (edge cases)
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_26_step_with_none_frame():
    """T-FSM-26: step() with None frame returns fallback coords, no crash."""
    fsm = _SelectPlaceFSM()
    x, y, state = fsm.step(None, None)
    assert isinstance(x, int) and isinstance(y, int)
    assert 0 <= x <= 63 and 0 <= y <= 63


def test_fsm_27_step_with_empty_frame():
    """T-FSM-27: step() with empty list frame returns fallback, no crash."""
    fsm = _SelectPlaceFSM()
    x, y, state = fsm.step([], None)
    assert 0 <= x <= 63 and 0 <= y <= 63


def test_fsm_28_stats_property():
    """T-FSM-28: stats property returns expected keys."""
    fsm = _SelectPlaceFSM()
    s = fsm.stats
    assert "state" in s
    assert "confirmed_selections" in s
    assert "confirmed_placements" in s
    assert "consecutive_misses" in s
    assert "total_transitions" in s


def test_fsm_29_multiple_cycles_no_exception():
    """T-FSM-29: 20 consecutive step() calls without exception."""
    fsm = _SelectPlaceFSM()
    grid_a = [[0, 2, 0], [0, 0, 3], [0, 0, 0]]
    grid_b = [[0, 7, 0], [0, 0, 3], [0, 0, 0]]
    frames = [_col_frame(grid_a), _col_frame(grid_b)]
    prev = None
    for i in range(20):
        frame = frames[i % 2]
        x, y, state = fsm.step(frame, prev)
        assert 0 <= x <= 63
        assert 0 <= y <= 63
        prev = frame


def test_fsm_30_classify_uniform_grid():
    """T-FSM-30: uniform grid (all same colour) — floor only, no pieces/targets."""
    fsm = _SelectPlaceFSM()
    grid = [[5] * 4 for _ in range(4)]
    fsm._classify_frame(grid)
    assert fsm._floor_colour == 5
    assert fsm._piece_colour == -1   # no non-floor colour
    # piece_cells should be empty (or target_cells fallback to piece_cells = [])
    assert len(fsm._piece_cells) == 0
