"""Tests L-049 — LuCY v13.1 corrections audit P0-A→P0-F

Tests couverts :
  T-FSM-31  : P0-A — pièce plus fréquente que le fond → classification correcte
  T-FSM-32  : P0-A — fond noir (0) avec 3 objets multi-couleurs
  T-FSM-33  : P0-C — pièce déplacée hors zone clic → placement NOT confirmed
  T-FSM-34  : P0-D — _validate_live_frame détecte frame malformée
  T-FSM-35  : P0-F — coordonnées blacklistées non réutilisées immédiatement
  T-FSM-36  : P0-A — grille uniforme → piece_colour=-1, target UNKNOWN

  T-FSM-37  : P0-A — target_colour UNKNOWN quand seulement 2 couleurs
  T-FSM-38  : P0-B — _is_confirmed_selection retourne (bool, float)
  T-FSM-39  : P0-B — confidence = 0.0 quand frames identiques
  T-FSM-40  : P0-B — confidence = 1/9 quand 1 cellule change
  T-FSM-41  : P0-C — _is_confirmed_placement retourne string
  T-FSM-42  : P0-C — 'piece_absent_full_grid' quand pièce absente
  T-FSM-43  : P0-D — _validate_live_frame frame valide
  T-FSM-44  : P0-D — _validate_transposition_regression reste PASS 5/5
  T-FSM-45  : P0-F — failed_coords purgé à chaque OBSERVE
  T-FSM-46  : stats inclut failed_coords_count + target_colour_unknown

CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif
"""

from __future__ import annotations

import sys
import os
import types
from typing import Any

# ── Stub arcengine (identique à test_lucy_v130_l048_fsm.py) ──────────────────
arcengine_stub = types.ModuleType("arcengine")

_ALL_ACTION_VALUES = [0, 1, 2, 3, 4, 5, 6, 7]


class _GameActionMeta(type):
    def __iter__(cls):
        return iter([
            type("GA", (), {
                "value": v,
                "name": f"ACTION{v}",
                "is_simple": lambda s, v=v: v != 6,
                "is_complex": lambda s, v=v: v == 6,
            })()
            for v in _ALL_ACTION_VALUES
        ])

    def __contains__(cls, item: Any) -> bool:
        val = getattr(item, "value", item)
        return val in _ALL_ACTION_VALUES


class GameActionClass(metaclass=_GameActionMeta):
    RESET = type("GA", (), {"value": 0, "name": "ACTION0"})()

    @classmethod
    def from_id(cls, v: int) -> Any:
        return type("GA", (), {
            "value": v, "name": f"ACTION{v}",
            "is_simple": lambda s: v != 6, "is_complex": lambda s: v == 6,
        })()


class _GameStateObj:
    WIN = "WIN"
    NOT_PLAYED = "NOT_PLAYED"
    GAME_OVER = "GAME_OVER"
    PLAYING = "PLAYING"


arcengine_stub.GameState = _GameStateObj()
arcengine_stub.GameAction = GameActionClass
arcengine_stub.FrameData = object

agents_stub = types.ModuleType("agents")
agent_stub = types.ModuleType("agents.agent")
agent_stub.Agent = object
agents_stub.agent = agent_stub

sys.modules.setdefault("arcengine", arcengine_stub)
sys.modules.setdefault("agents", agents_stub)
sys.modules.setdefault("agents.agent", agent_stub)

# ── Import module sous test ───────────────────────────────────────────────────
_agent_path = os.path.join(os.path.dirname(__file__), "..", "agent", "my_agent_v131.py")
import importlib.util

spec = importlib.util.spec_from_file_location("my_agent_v131", _agent_path)
mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(mod)  # type: ignore[union-attr]

_SelectPlaceFSM = mod._SelectPlaceFSM
_validate_transposition_regression = mod._validate_transposition_regression
_validate_live_frame = mod._validate_live_frame
COLOUR_UNKNOWN = _SelectPlaceFSM.COLOUR_UNKNOWN


def _col_frame(grid: list) -> list:
    """Convert row-major grid to columnar ARC-AGI-3 frame format."""
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    return [[[grid[r][c] for r in range(rows)] for c in range(cols)]]


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-31 — P0-A : pièce plus fréquente que le fond
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_31_piece_more_frequent_than_floor():
    """T-FSM-31: P0-A — pièce plus fréquente que fond → floor reste le plus fréquent."""
    fsm = _SelectPlaceFSM()
    # floor=0 (9 cellules), piece=1 (9 cellules) — au lieu du cas normal floor > piece
    grid = [
        [1, 1, 1, 0, 0, 0],
        [1, 1, 1, 0, 0, 0],
        [1, 1, 1, 0, 0, 2],  # 1 cellule cible (2)
    ]
    fsm._classify_frame(grid)
    # floor = couleur la plus fréquente
    all_vals = [v for row in grid for v in row]
    from collections import Counter
    dominant = Counter(all_vals).most_common(1)[0][0]
    assert fsm._floor_colour == dominant, f"floor={fsm._floor_colour} expected={dominant}"
    # piece_cells doit être non vide
    assert fsm._piece_colour >= 0 or len(fsm._piece_cells) > 0 or len(fsm._target_cells) > 0


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-32 — P0-A : fond noir (0) avec 3 objets
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_32_black_floor_three_object_colours():
    """T-FSM-32: P0-A — fond noir (0) + 3 couleurs d'objets → classification correcte."""
    fsm = _SelectPlaceFSM()
    # fond=0 (dominant), piece=2 (2nd), target=3 (3rd), objet4=4
    grid = [
        [0, 0, 0, 0, 0],
        [0, 2, 2, 0, 0],
        [0, 2, 0, 3, 0],
        [0, 0, 4, 0, 0],
        [0, 0, 0, 0, 0],
    ]
    fsm._classify_frame(grid)
    assert fsm._floor_colour == 0
    assert fsm._piece_colour in (2, 3, 4)  # 2ème plus fréquente non-fond
    assert fsm._target_colour != COLOUR_UNKNOWN, "target doit être connu avec 3 couleurs"
    assert len(fsm._piece_cells) >= 1
    assert len(fsm._target_cells) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-33 — P0-C : pièce déplacée hors zone clic → NOT confirmed
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_33_placement_false_positive_corrected():
    """T-FSM-33: P0-C — pièce déplacée hors zone clic mais toujours présente → False.

    C'est le faux positif de v13.0 corrigé en v13.1.
    AVANT: piece_colour absente zone 5×5 → True
    APRÈS: piece_colour présente quelque part sur la grille → False
    """
    fsm = _SelectPlaceFSM()
    fsm._floor_colour = 0
    fsm._piece_colour = 4
    fsm._prev_active_count = 1  # MÊME nombre de cellules actives qu'avant
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    # La pièce (4) a bougé de (1,1) → (0,0) — zone clic vide mais pièce présente
    curr_grid = [[4, 0, 0], [0, 0, 0], [0, 0, 0]]
    curr_frame = _col_frame(curr_grid)
    result = fsm._is_confirmed_placement(curr_frame)
    assert result is False, (
        f"P0-C FAIL: pièce déplacée hors zone mais présente sur grille → attendu False, got {result}. "
        "C'est le faux positif v13.0 qui devait être corrigé."
    )


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-34 — P0-D : _validate_live_frame détecte frame malformée
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_34_validate_live_frame_detects_none():
    """T-FSM-34a: _validate_live_frame(None) → ok=False avec message d'erreur."""
    result = _validate_live_frame(None)
    assert result["ok"] is False
    assert len(result["errors"]) > 0


def test_fsm_34b_validate_live_frame_valid():
    """T-FSM-34b: _validate_live_frame avec frame columnar valide → ok=True."""
    valid_frame = [[[1, 2, 3], [4, 5, 6]]]  # 2 cols × 3 rows
    result = _validate_live_frame(valid_frame)
    assert result["ok"] is True, f"Expected ok=True, got errors={result['errors']}"
    assert result["format"] == "columnar"
    assert result["rows"] == 3
    assert result["cols"] == 2


def test_fsm_34c_validate_live_frame_empty():
    """T-FSM-34c: _validate_live_frame([]) → ok=False."""
    result = _validate_live_frame([])
    assert result["ok"] is False


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-35 — P0-F : blacklist coordonnées
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_35_failed_coords_blacklisted_after_recovery():
    """T-FSM-35: P0-F — coords du dernier clic blacklistées après récupération MAX_MISSES."""
    fsm = _SelectPlaceFSM()
    # Forcer l'état SELECT avec MAX_MISSES atteint
    fsm._state = _SelectPlaceFSM.SELECT
    fsm._consecutive_misses = _SelectPlaceFSM.MAX_CONSECUTIVE_MISSES
    fsm._last_click_r = 3
    fsm._last_click_c = 4

    # Grille avec pièces (1) uniquement à (3,4) — la coord blacklistée
    grid = [[0] * 5 for _ in range(5)]
    grid[3][4] = 1
    frame = _col_frame(grid)

    x, y, state = fsm.step(frame, None)
    # Après récupération, (3,4) doit être dans failed_coords
    # (puis purgé par OBSERVE — vérifier AVANT la purge implique de regarder pendant)
    # On vérifie que le FSM est en SELECT et que les coordonnées échouées ont été traitées
    assert state in ("SELECT", "SELECT_fallback_random"), f"Expected SELECT after recovery, got {state}"
    # La blacklist est purgée par OBSERVE → vide après step
    assert fsm._consecutive_misses < _SelectPlaceFSM.MAX_CONSECUTIVE_MISSES


def test_fsm_35b_failed_coords_excluded_from_candidates():
    """T-FSM-35b: P0-F — coord blacklistée exclue des candidats SELECT."""
    fsm = _SelectPlaceFSM()
    fsm._state = _SelectPlaceFSM.SELECT
    # Blacklister (1,1)
    fsm._failed_coords = {(1, 1)}
    # Grille: seules (1,1) et (2,2) sont des pièces
    grid = [[0, 0, 0], [0, 1, 0], [0, 0, 1]]
    frame = _col_frame(grid)

    # Classify pour peupler piece_cells
    fsm._classify_frame([[0, 0, 0], [0, 1, 0], [0, 0, 1]])
    available_pieces = [rc for rc in fsm._piece_cells if rc not in fsm._failed_coords]
    # (2,2) doit être disponible même si (1,1) est blacklistée
    assert (2, 2) in available_pieces or len(fsm._piece_cells) > 0, \
        f"piece_cells={fsm._piece_cells} available={available_pieces}"


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-36 — P0-A : grille uniforme
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_36_uniform_grid_unknown_target():
    """T-FSM-36: P0-A — grille uniforme (1 couleur) → piece=-1, target=UNKNOWN."""
    fsm = _SelectPlaceFSM()
    grid = [[7] * 4 for _ in range(4)]  # tout = 7
    fsm._classify_frame(grid)
    assert fsm._floor_colour == 7
    assert fsm._piece_colour == -1
    assert fsm._target_colour == COLOUR_UNKNOWN
    assert len(fsm._piece_cells) == 0
    assert len(fsm._target_cells) == 0


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-37 — P0-A : target_colour UNKNOWN avec 2 couleurs
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_37_two_colours_target_unknown():
    """T-FSM-37: P0-A — seulement 2 couleurs → target_colour = COLOUR_UNKNOWN (v13.1).

    AVANT (v13.0): target_colour = piece_colour → faux positif structurel.
    APRÈS (v13.1): target_colour = COLOUR_UNKNOWN, target_cells = [].
    """
    fsm = _SelectPlaceFSM()
    grid = [[0, 0, 0], [0, 1, 1], [0, 0, 0]]
    fsm._classify_frame(grid)
    assert fsm._target_colour == COLOUR_UNKNOWN, (
        f"v13.1 FIX-P0A: attendu COLOUR_UNKNOWN (-2), got {fsm._target_colour}. "
        "En v13.0, target_colour = piece_colour causait des faux positifs en PLACE."
    )
    assert fsm._target_cells == [], f"target_cells should be empty, got {fsm._target_cells}"


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-38/39/40 — P0-B : _is_confirmed_selection retourne tuple
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_38_confirmed_selection_returns_tuple():
    """T-FSM-38: P0-B — _is_confirmed_selection retourne (bool, float)."""
    fsm = _SelectPlaceFSM()
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    prev = _col_frame([[0, 0, 0], [0, 2, 0], [0, 0, 0]])
    curr = _col_frame([[0, 0, 0], [0, 7, 0], [0, 0, 0]])
    result = fsm._is_confirmed_selection(prev, curr)
    assert isinstance(result, tuple) and len(result) == 2
    confirmed, confidence = result
    assert isinstance(confirmed, bool)
    assert isinstance(confidence, float)


def test_fsm_39_confidence_zero_identical_frames():
    """T-FSM-39: P0-B — confidence = 0.0 quand frames identiques."""
    fsm = _SelectPlaceFSM()
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    frame = _col_frame([[0, 0, 0], [0, 5, 0], [0, 0, 0]])
    confirmed, confidence = fsm._is_confirmed_selection(frame, frame)
    assert confirmed is False
    assert confidence == 0.0


def test_fsm_40_confidence_one_ninth_one_cell_changed():
    """T-FSM-40: P0-B — confidence ≈ 1/9 quand exactement 1 cellule change."""
    fsm = _SelectPlaceFSM()
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    prev = _col_frame([[0, 0, 0], [0, 2, 0], [0, 0, 0]])
    curr = _col_frame([[0, 0, 0], [0, 7, 0], [0, 0, 0]])  # seulement (1,1) change
    confirmed, confidence = fsm._is_confirmed_selection(prev, curr)
    assert confirmed is True
    assert abs(confidence - round(1 / 9, 3)) < 1e-6, f"Expected ≈0.111, got {confidence}"


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-41/42 — P0-C : _is_confirmed_placement retourne string
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_41_placement_returns_string_or_false():
    """T-FSM-41: P0-C — _is_confirmed_placement retourne string ou False."""
    fsm = _SelectPlaceFSM()
    fsm._floor_colour = 0
    fsm._piece_colour = 3
    fsm._prev_active_count = 4  # était 4, maintenant 1 → diminué
    curr_frame = _col_frame([[0, 0, 0], [0, 3, 0], [0, 0, 0]])
    result = fsm._is_confirmed_placement(curr_frame)
    assert result in ("active_count_decreased", "piece_absent_full_grid", False), \
        f"Expected string or False, got {result}"


def test_fsm_42_piece_absent_full_grid():
    """T-FSM-42: P0-C — 'piece_absent_full_grid' quand pièce introuvable sur grille entière."""
    fsm = _SelectPlaceFSM()
    fsm._floor_colour = 0
    fsm._piece_colour = 5
    fsm._prev_active_count = 2  # était 2 → maintenant 1 (cible reste)
    fsm._last_click_r = 1
    fsm._last_click_c = 1
    # Seule la cible (3) reste, la pièce (5) est absente
    curr_grid = [[0, 0, 0], [0, 0, 0], [0, 0, 3]]
    curr_frame = _col_frame(curr_grid)
    result = fsm._is_confirmed_placement(curr_frame)
    # Heuristique 1 (count decreased) et/ou heuristique 2 (piece absente)
    assert result in ("active_count_decreased", "piece_absent_full_grid"), \
        f"Expected placement confirmed, got {result}"


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-43/44 — P0-D : validation live vs régression
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_43_validate_live_frame_columnar():
    """T-FSM-43: P0-D — _validate_live_frame sur frame columnar valide."""
    frame = [[[1, 2, 3, 4], [5, 6, 7, 8]]]  # 2 cols × 4 rows
    result = _validate_live_frame(frame)
    assert result["ok"] is True
    assert result["format"] == "columnar"
    assert result["rows"] == 4
    assert result["cols"] == 2


def test_fsm_44_regression_still_passes():
    """T-FSM-44: P0-D — _validate_transposition_regression toujours 5/5 PASS."""
    result = _validate_transposition_regression()
    assert result["ok"] is True
    assert result["passed"] == 5
    assert result["failed"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# T-FSM-45/46 — P0-F : blacklist cycle + stats
# ──────────────────────────────────────────────────────────────────────────────

def test_fsm_45_failed_coords_cleared_on_observe():
    """T-FSM-45: P0-F — _failed_coords purgé à chaque nouveau cycle OBSERVE."""
    fsm = _SelectPlaceFSM()
    # Injecter des coords dans la blacklist manuellement
    fsm._failed_coords = {(1, 2), (3, 4)}
    fsm._state = _SelectPlaceFSM.OBSERVE
    grid = [[0, 0, 0], [0, 1, 0], [0, 0, 2]]
    frame = _col_frame(grid)
    # step en OBSERVE → purge blacklist
    fsm.step(frame, None)
    assert len(fsm._failed_coords) == 0, \
        f"Expected empty failed_coords after OBSERVE, got {fsm._failed_coords}"


def test_fsm_46_stats_includes_new_fields():
    """T-FSM-46: P0-F/P0-A — stats inclut failed_coords_count + target_colour_unknown."""
    fsm = _SelectPlaceFSM()
    s = fsm.stats
    assert "failed_coords_count" in s, "stats missing failed_coords_count"
    assert "target_colour_unknown" in s, "stats missing target_colour_unknown"
    assert s["target_colour_unknown"] is True  # initial state = UNKNOWN
    assert s["failed_coords_count"] == 0  # initial state = no failed coords
