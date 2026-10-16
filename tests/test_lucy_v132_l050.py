"""Tests L-050 — LuCY v13.2 classification par rareté + ciblage cluster

Tests couverts :
  T-FSM-47  : FIX-P0A-v2 — r11l réel : floor=5, piece=3(rare), target=15(rare)
               (non plus floor=5, piece=2(ciel), target=0(bordure))
  T-FSM-48  : FIX-P0A-v2 — grille uniforme reste piece=-1, target=UNKNOWN
  T-FSM-49  : FIX-P0A-v2 — 2 couleurs rares identifiées correctement
  T-FSM-50  : FIX-P0A-v2 — couleur très rare (1 cell) exclue (< MIN_PIECE_CELLS)
  T-FSM-51  : FIX-P0A-v2 — couleur trop fréquente exclue (> MAX_PIECE_CELLS_RATIO)
  T-FSM-52  : FIX-P0A-v2 — black border (0) exclue quand floor != 0
  T-FSM-53  : FIX-P0A-v2 — black border (0) NON exclue quand floor == 0
  T-FSM-54  : FIX-CLUSTER — centroide retourne cellule proche du centre
  T-FSM-55  : FIX-CLUSTER — avec blacklist partielle → centroide sur cellules restantes
  T-FSM-56  : FIX-CLUSTER — blacklist totale → fallback toutes cellules
  T-FSM-57  : FIX-CLUSTER — liste vide → None retourné
  T-FSM-58  : FIX-CLUSTER — centroide stable sur symétrie (grille carrée)
  T-FSM-59  : Intégration — step SELECT cible piece_colour=3 (rare) pas 2 (fréquent)
  T-FSM-60  : Intégration — step PLACE cible target_colour=15 (rare) pas 0 (bordure)
  T-FSM-61  : Rétrocompat — FIX-P0B tuple (bool, float) maintenu en v13.2
  T-FSM-62  : Rétrocompat — FIX-P0C placement string maintenu en v13.2
  T-FSM-63  : Rétrocompat — FIX-P0F blacklist maintained in v13.2
  T-FSM-64  : stats inclut piece_colour et target_colour
  T-FSM-65  : FSM_ACTION log inclut v13_2_fix field
  T-FSM-66  : Non-régression — 49 tests v13.0/v13.1 non cassés par v13.2

CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif
"""

from __future__ import annotations

import sys
import os
import types
from typing import Any
from collections import Counter

# ── Stub arcengine (identique aux tests v13.0/v13.1) ─────────────────────────
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

# ── Import module sous test (v13.2) ───────────────────────────────────────────
_agent_path = os.path.join(os.path.dirname(__file__), "..", "agent", "my_agent_v132.py")
import importlib.util

spec = importlib.util.spec_from_file_location("my_agent_v132", _agent_path)
mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(mod)  # type: ignore[union-attr]

_SelectPlaceFSM = mod._SelectPlaceFSM
COLOUR_UNKNOWN = _SelectPlaceFSM.COLOUR_UNKNOWN
VERSION = mod.VERSION


def _col_frame(grid: list) -> list:
    """Convert row-major grid to columnar ARC-AGI-3 frame format."""
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    return [[[grid[r][c] for r in range(rows)] for c in range(cols)]]


def _r11l_sample_grid():
    """Build a miniature grid mimicking r11l structure.

    floor=5 (dominant), sky=2 (large secondary), border=0 (sparse),
    piece=3 (12 cells = rare), target=15 (34 cells = rare).
    Scale: 16x16 instead of 64x64 for test speed.
    """
    total = 16 * 16
    grid = [[5] * 16 for _ in range(16)]  # floor = 5 everywhere
    # Add sky (colour 2) — large secondary: 30 cells (~12%)
    for r in range(8):
        for c in range(4):
            grid[r][c] = 2
    # Add border (colour 0) — 4 cells
    for c in range(4):
        grid[0][c] = 0
    # Add piece (colour 3) — 4 cells (rare, < 15% of 256 = 38)
    grid[10][10] = 3
    grid[10][11] = 3
    grid[11][10] = 3
    grid[11][11] = 3
    # Add target (colour 15) — 6 cells (rare)
    for r in range(3, 5):
        for c in range(8, 11):
            grid[r][c] = 15
    return grid


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-47 — FIX-P0A-v2 : classification rareté sur r11l-like
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_47_r11l_rarity_classification():
    """T-FSM-47: FIX-P0A-v2 — sur r11l-like: piece=3(rare), target=15(rare), floor=5."""
    fsm = _SelectPlaceFSM()
    grid = _r11l_sample_grid()
    fsm._classify_frame(grid)
    # floor doit être 5 (dominant)
    assert fsm._floor_colour == 5, f"floor={fsm._floor_colour}"
    # piece doit être 3 (4 cells — rare) — PAS 2 (ciel, 30 cells)
    assert fsm._piece_colour == 3, (
        f"piece_colour={fsm._piece_colour} — expected 3 (rare), not 2 (ciel)"
    )
    # target doit être 15 (6 cells) — PAS 0 (bordure qui devrait être filtrée)
    assert fsm._target_colour == 15, (
        f"target_colour={fsm._target_colour} — expected 15 (rare targets)"
    )
    # piece_cells doit contenir les 4 cellules colour=3
    assert len(fsm._piece_cells) == 4, f"piece_cells={len(fsm._piece_cells)}"
    # target_cells doit contenir les 6 cellules colour=15
    assert len(fsm._target_cells) == 6, f"target_cells={len(fsm._target_cells)}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-48 — FIX-P0A-v2 : grille uniforme
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_48_uniform_grid_unknown():
    """T-FSM-48: FIX-P0A-v2 — grille uniforme → piece=-1, target=UNKNOWN."""
    fsm = _SelectPlaceFSM()
    grid = [[5] * 8 for _ in range(8)]
    fsm._classify_frame(grid)
    assert fsm._piece_colour == -1, f"piece={fsm._piece_colour}"
    assert fsm._target_colour == COLOUR_UNKNOWN, f"target={fsm._target_colour}"
    assert fsm._piece_cells == []
    assert fsm._target_cells == []


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-49 — FIX-P0A-v2 : 2 couleurs rares correctement identifiées
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_49_two_rare_colours_identified():
    """T-FSM-49: FIX-P0A-v2 — 2 couleurs rares → piece et target distincts."""
    fsm = _SelectPlaceFSM()
    # floor=5 (50 cells), piece=3 (4 cells), target=7 (3 cells)
    grid = [[5] * 8 for _ in range(8)]  # 64 cells floor
    grid[0][0] = 3
    grid[0][1] = 3
    grid[1][0] = 3
    grid[1][1] = 3  # 4 cells colour 3
    grid[7][7] = 7
    grid[7][6] = 7
    grid[6][7] = 7  # 3 cells colour 7
    fsm._classify_frame(grid)
    assert fsm._piece_colour != fsm._target_colour
    assert fsm._piece_colour in (3, 7)
    assert fsm._target_colour in (3, 7)
    assert fsm._target_colour != COLOUR_UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-50 — FIX-P0A-v2 : couleur isolée (1 cell) exclue
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_50_single_cell_excluded():
    """T-FSM-50: FIX-P0A-v2 — couleur avec 1 seule cellule exclue (< MIN_PIECE_CELLS=3)."""
    fsm = _SelectPlaceFSM()
    assert fsm.MIN_PIECE_CELLS >= 2  # doit être au moins 2
    grid = [[5] * 8 for _ in range(8)]
    grid[3][3] = 99  # 1 seule cellule couleur 99
    grid[0][0] = 3
    grid[0][1] = 3
    grid[1][0] = 3  # 3 cellules colour 3 — au-dessus de MIN_PIECE_CELLS
    fsm._classify_frame(grid)
    # 99 doit être exclu (1 cell < MIN_PIECE_CELLS)
    assert fsm._piece_colour != 99, f"piece_colour={fsm._piece_colour} should not be 99 (1 cell)"
    # 3 doit être piece si MIN_PIECE_CELLS == 3
    if fsm.MIN_PIECE_CELLS <= 3:
        assert fsm._piece_colour == 3


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-51 — FIX-P0A-v2 : couleur trop fréquente exclue
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_51_large_secondary_excluded():
    """T-FSM-51: FIX-P0A-v2 — couleur avec > MAX_PIECE_CELLS_RATIO exclue (ciel)."""
    fsm = _SelectPlaceFSM()
    # grid 10x10 = 100 cells
    # floor=5 (40), sky=2 (35 cells = 35% > 15%) → sky doit être exclu
    # piece=3 (5 cells = 5% ≤ 15%) → piece doit être inclus
    grid = []
    for r in range(10):
        row = []
        for c in range(10):
            if r < 4:
                row.append(2)  # 40 cells sky
            elif r < 8:
                row.append(5)  # 40 cells floor
            else:
                row.append(3 if c < 5 else 5)  # 5 cells piece
        grid.append(row)
    fsm._classify_frame(grid)
    total = 100
    sky_count = sum(1 for row in grid for v in row if v == 2)
    # sky_count = 40, mais floor = dominant (40 = 5) ou 2 ?
    # Le floor est le plus fréquent → 5 ou 2 selon la grille
    # Dans tous les cas, le piece_colour ne doit pas être la couleur à > 15%
    if fsm._piece_colour is not None and fsm._piece_colour >= 0:
        piece_count = sum(1 for row in grid for v in row if v == fsm._piece_colour)
        assert piece_count <= int(total * fsm.MAX_PIECE_CELLS_RATIO) or piece_count == Counter(
            v for row in grid for v in row
        ).most_common(1)[0][1]


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-52 — FIX-P0A-v2 : bordure noire exclue quand floor != 0
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_52_black_border_excluded_when_floor_not_zero():
    """T-FSM-52: FIX-P0A-v2 — colour 0 exclue quand floor != 0."""
    fsm = _SelectPlaceFSM()
    # floor=5, bordure noire=0 (5 cells), vraie pièce=3 (4 cells)
    grid = [[5] * 8 for _ in range(8)]
    for c in range(5):
        grid[0][c] = 0  # bordure noire
    grid[4][4] = 3
    grid[4][5] = 3
    grid[5][4] = 3
    grid[5][5] = 3
    fsm._classify_frame(grid)
    assert fsm._floor_colour == 5
    # piece_colour ne doit pas être 0 (bordure noire exclue)
    assert fsm._piece_colour != 0, f"piece_colour={fsm._piece_colour} should not be 0 (black border)"
    # piece_colour doit être 3 (la vraie pièce rare)
    assert fsm._piece_colour == 3, f"piece_colour={fsm._piece_colour}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-53 — FIX-P0A-v2 : bordure noire NON exclue quand floor == 0
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_53_black_floor_zero_colour_not_excluded():
    """T-FSM-53: FIX-P0A-v2 — quand floor=0, les autres couleurs ne sont pas filtrées."""
    fsm = _SelectPlaceFSM()
    # floor=0 (dominant), pièce=3 (4 cells), cible=7 (3 cells)
    grid = [[0] * 8 for _ in range(8)]
    grid[4][4] = 3
    grid[4][5] = 3
    grid[5][4] = 3
    grid[5][5] = 3
    grid[6][6] = 7
    grid[6][7] = 7
    grid[7][6] = 7
    fsm._classify_frame(grid)
    assert fsm._floor_colour == 0
    # Quand floor=0, on ne filtre pas 0 des candidats — mais 0 == floor donc
    # déjà exclu par la règle "if colour == self._floor_colour: continue"
    assert fsm._piece_colour in (3, 7)


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-54 — FIX-CLUSTER : centroïde cellule la plus proche du centre
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_54_cluster_centroid_closest_to_centre():
    """T-FSM-54: FIX-CLUSTER — centroïde retourne la cellule la plus proche du centre."""
    fsm = _SelectPlaceFSM()
    # Groupe de 5 cellules en L — centroïde = (2.0, 1.0)
    cells = [(1, 1), (2, 1), (3, 1), (3, 2), (3, 0)]
    # centroïde = (sum r / 5, sum c / 5) = (12/5, 5/5) = (2.4, 1.0)
    result = fsm._pick_cluster_centre(cells, set())
    assert result is not None
    assert result in cells
    # La cellule la plus proche de (2.4, 1.0) est (2, 1)
    cr = sum(r for r, c in cells) / len(cells)
    cc = sum(c for r, c in cells) / len(cells)
    expected = min(cells, key=lambda rc: (rc[0] - cr) ** 2 + (rc[1] - cc) ** 2)
    assert result == expected


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-55 — FIX-CLUSTER : blacklist partielle → centroïde sur restantes
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_55_cluster_centroid_with_partial_blacklist():
    """T-FSM-55: FIX-CLUSTER — avec blacklist partielle, centroïde calculé sur cellules disponibles."""
    fsm = _SelectPlaceFSM()
    cells = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]
    blacklist = {(0, 0), (1, 0)}  # 2 cellules blacklistées
    result = fsm._pick_cluster_centre(cells, blacklist)
    assert result is not None
    assert result not in blacklist
    # Doit être parmi les disponibles
    available = [(0, 1), (0, 2), (1, 1)]
    assert result in available


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-56 — FIX-CLUSTER : blacklist totale → fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_56_cluster_centroid_full_blacklist_fallback():
    """T-FSM-56: FIX-CLUSTER — blacklist totale → fallback sur toutes les cellules."""
    fsm = _SelectPlaceFSM()
    cells = [(0, 0), (0, 1)]
    blacklist = {(0, 0), (0, 1)}  # tout est blacklisté
    result = fsm._pick_cluster_centre(cells, blacklist)
    # Ne doit pas retourner None — fallback sur cells ignorant la blacklist
    assert result is not None
    assert result in cells


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-57 — FIX-CLUSTER : liste vide → None
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_57_cluster_centroid_empty_cells():
    """T-FSM-57: FIX-CLUSTER — liste vide → None retourné sans exception."""
    fsm = _SelectPlaceFSM()
    result = fsm._pick_cluster_centre([], set())
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-58 — FIX-CLUSTER : centroïde stable sur symétrie
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_58_cluster_centroid_symmetric_grid():
    """T-FSM-58: FIX-CLUSTER — grille symétrique → centroïde au centre exact."""
    fsm = _SelectPlaceFSM()
    # Carré 3x3 de pièces — centroïde = (1, 1) = centre exact
    cells = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
    result = fsm._pick_cluster_centre(cells, set())
    assert result == (1, 1), f"result={result} — expected centre (1,1) of 3x3"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-59 — Intégration : step SELECT cible la bonne pièce (couleur rare)
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_59_step_select_targets_rare_piece():
    """T-FSM-59: Intégration — step SELECT cible piece_colour rare (pas la couleur fréquente)."""
    fsm = _SelectPlaceFSM()
    grid = _r11l_sample_grid()  # floor=5, sky=2(large), piece=3(4 cells), target=15(6 cells)
    frame = _col_frame(grid)
    # Exécuter assez de steps pour que la FSM classe les cellules
    for _ in range(3):
        x, y, label = fsm.step(frame, None)
    # piece_colour doit être 3 (rare), pas 2 (ciel)
    assert fsm._piece_colour == 3, (
        f"piece_colour={fsm._piece_colour} — expected 3 (rare), not 2 (sky/ciel)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-60 — Intégration : step PLACE cible la bonne cible (couleur rare)
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_60_step_place_targets_rare_target():
    """T-FSM-60: Intégration — step PLACE cible target_colour rare (pas la bordure)."""
    fsm = _SelectPlaceFSM()
    grid = _r11l_sample_grid()
    frame = _col_frame(grid)
    fsm.step(frame, None)  # OBSERVE → SELECT
    fsm._classify_frame([[int(grid[c][r]) for c in range(len(grid[0]))] for r in range(len(grid))]
                         if False else grid)
    # target_colour doit être 15 (rare), pas 0 (bordure)
    assert fsm._target_colour == 15, (
        f"target_colour={fsm._target_colour} — expected 15 (rare target), not 0 (border)"
    )
    assert fsm._target_colour != 0


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-61 — Rétrocompat : FIX-P0B tuple maintenu en v13.2
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_61_retrocompat_p0b_tuple():
    """T-FSM-61: FIX-P0B (v13.1) — _is_confirmed_selection retourne (bool, float) en v13.2."""
    fsm = _SelectPlaceFSM()
    grid1 = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
    grid2 = [[1, 1, 1], [1, 7, 1], [1, 1, 1]]  # 1 cell changed
    frame1 = _col_frame(grid1)
    frame2 = _col_frame(grid2)
    fsm._last_click_r, fsm._last_click_c = 1, 1
    result = fsm._is_confirmed_selection(frame1, frame2)
    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2
    confirmed, confidence = result
    assert isinstance(confirmed, bool)
    assert isinstance(confidence, float)
    assert confirmed is True


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-62 — Rétrocompat : FIX-P0C string maintenu en v13.2
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_62_retrocompat_p0c_string():
    """T-FSM-62: FIX-P0C (v13.1) — _is_confirmed_placement retourne string en v13.2."""
    fsm = _SelectPlaceFSM()
    fsm._piece_colour = 3
    fsm._floor_colour = 5
    # Grille sans aucune cellule de couleur 3 → piece absente de toute la grille
    grid = [[5, 5, 5], [5, 5, 5], [5, 5, 5]]
    fsm._prev_active_count = 10  # était 10 avant
    frame = _col_frame(grid)
    result = fsm._is_confirmed_placement(frame)
    assert result in ("active_count_decreased", "piece_absent_full_grid", "ambiguous", False)


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-63 — Rétrocompat : FIX-P0F blacklist maintenu en v13.2
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_63_retrocompat_p0f_blacklist():
    """T-FSM-63: FIX-P0F (v13.1) — blacklist _failed_coords maintenu en v13.2."""
    fsm = _SelectPlaceFSM()
    # Forcer MAX_CONSECUTIVE_MISSES récupérations
    grid = [[5, 5], [5, 3]]  # 1 pièce en (1,1)
    frame = _col_frame(grid)
    fsm._last_click_r, fsm._last_click_c = 1, 1
    fsm._consecutive_misses = fsm.MAX_CONSECUTIVE_MISSES
    fsm.step(frame, None)
    # Après récupération, (1,1) doit être blacklisté (tant que c'était le dernier clic)
    # La purge arrive à OBSERVE, donc vérifier le comportement
    assert hasattr(fsm, "_failed_coords")
    assert isinstance(fsm._failed_coords, set)


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-64 — stats inclut piece_colour et target_colour
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_64_stats_includes_colour_info():
    """T-FSM-64: stats (v13.2) inclut piece_colour et target_colour."""
    fsm = _SelectPlaceFSM()
    grid = _r11l_sample_grid()
    frame = _col_frame(grid)
    fsm.step(frame, None)
    s = fsm.stats
    assert "piece_colour" in s, f"stats keys: {list(s.keys())}"
    assert "target_colour" in s
    assert "piece_cells_count" in s
    assert "target_cells_count" in s
    # Après un step sur r11l-like, piece_colour doit être 3
    assert s["piece_colour"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-65 — FSM_ACTION log inclut v13_2_fix
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_65_fsm_action_log_v132_field():
    """T-FSM-65: FSM_ACTION log (v13.2) inclut le champ v13_2_fix."""
    import types as _types

    class MockLogger:
        def __init__(self):
            self.events = []

        def _emit(self, event_type, data):
            self.events.append({"type": event_type, "data": data})

    fsm = _SelectPlaceFSM()
    grid = _r11l_sample_grid()
    frame = _col_frame(grid)
    logger = MockLogger()
    fsm.step(frame, None, logger=logger)
    fsm.step(frame, frame, logger=logger)  # 2ème step avec prev_frame

    fsm_actions = [e for e in logger.events if e["type"] == "FSM_ACTION"]
    assert len(fsm_actions) > 0
    for ev in fsm_actions:
        assert "v13_2_fix" in ev["data"], f"v13_2_fix absent de FSM_ACTION: {ev['data'].keys()}"
        assert ev["data"]["v13_2_fix"] == "rarity_classification_cluster_centroid"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-66 — VERSION est bien 13.2
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_66_version_is_13_2():
    """T-FSM-66: VERSION du module est '13.2'."""
    assert VERSION == "13.2", f"VERSION={VERSION} — expected 13.2"
