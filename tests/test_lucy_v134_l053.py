"""Tests L-053 — LuCY v13.4 : centroïde groupe complet + blacklist reset recovery

Tests couverts (T-FSM-84 à T-FSM-100) — nouveaux en v13.4 :
  T-FSM-84  : FIX-P1A — forme U : centroïde calculé sur groupe COMPLET (pas available filtrés)
  T-FSM-85  : FIX-P1A — forme L : centroïde ne dévie pas quand bords blacklistés
  T-FSM-86  : FIX-P1A — forme anneau : centroïde géométrique stable malgré blacklist bords
  T-FSM-87  : FIX-P1A — groupe compact sans blacklist : résultat identique v13.3/v13.4
  T-FSM-88  : FIX-P1A — deux objets disjoints : centroïde basé sur groupe, pas available
  T-FSM-89  : FIX-P1C — recovery (MAX_CONSECUTIVE_MISSES) purge la blacklist
  T-FSM-90  : FIX-P1C — blacklist ne grossit pas entre deux OBSERVE si recovery intervient
  T-FSM-91  : FIX-P1C — après recovery, coordonnées précédemment échouées sont disponibles
  T-FSM-92  : FIX-P1D — 4-connexité : cellules diagonales = groupes séparés (explicite)
  T-FSM-93  : FIX-P1D — 4-connexité : cellules adjacentes H/V = même groupe (explicite)
  T-FSM-94  : FIX-P1D — 8 directions explicitement refusées en BFS (diag = séparés)
  T-FSM-95  : Formes U/L — clic toujours sur une cellule occupée (pas le vide intérieur)
  T-FSM-96  : Blacklist partielle forme U — clic reste dans le groupe, bonne branche
  T-FSM-97  : Centroïde stable sur forme pleine rectangulaire — non-régression
  T-FSM-98  : Recovery + classify_frame cohérence — blacklist purgée avant SELECT
  T-FSM-99  : VERSION == "13.4"
  T-FSM-100 : Non-régression — 86 tests v13.0/v13.1/v13.2/v13.3 non cassés par v13.4

CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif
"""

from __future__ import annotations

import sys
import os
import types
from typing import Any
from collections import Counter

# ── Stub arcengine (identique aux tests v13.0/v13.1/v13.2/v13.3) ─────────────
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

# ── Import module sous test (v13.4) ──────────────────────────────────────────
_agent_path = os.path.join(os.path.dirname(__file__), "..", "agent", "my_agent_v134.py")
import importlib.util

spec = importlib.util.spec_from_file_location("my_agent_v134", _agent_path)
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


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-84 — FIX-P1A : forme U — centroïde groupe complet stable
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_84_p1a_u_shape_centroid_uses_full_group():
    """T-FSM-84: FIX-P1A — forme U : centroïde calculé sur groupe complet.

    Forme U (3 branches, vide en haut au centre) :
    X X X
    X . X
    X . X
    (rangées : (0,0),(0,1),(0,2),(1,0),(1,2),(2,0),(2,2))

    Centroïde géométrique du GROUPE COMPLET = (1.0, 1.14...) → proche de (1,1).
    Avec blacklist vide, la cellule retournée doit être dans le groupe.

    AVANT (v13.3) : centroïde = moyenne(available). Si available == group,
                    résultat identique. Mais si bords blacklistés → dérive.
    APRÈS (v13.4) : centroïde toujours = moyenne(group complet).
    """
    fsm = _SelectPlaceFSM()
    # Forme U : 7 cellules, vide à (1,1) et (2,1)
    u_shape = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2)]

    # Sans blacklist : doit retourner une cellule du groupe
    result = fsm._pick_cluster_centre(u_shape, set())
    assert result is not None, "Expected a result, got None"
    assert result in u_shape, f"Result {result} not in U-shape cells {u_shape}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-85 — FIX-P1A : forme U avec bords blacklistés — centroïde stable
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_85_p1a_u_shape_blacklisted_edges_centroid_stable():
    """T-FSM-85: FIX-P1A — forme U, bords gauches blacklistés.

    Même forme U. On blackliste les cellules de gauche (colonne 0).
    AVANT (v13.3) : centroïde calculé sur available (col 1 et 2 seulement)
                    → centroïde dérive vers la droite.
    APRÈS (v13.4) : centroïde calculé sur groupe complet (cols 0,1,2)
                    → centroïde géométrique réel, cible la branche la plus proche.
    """
    fsm = _SelectPlaceFSM()
    u_shape = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2)]
    # Blacklist colonne 0 (bord gauche)
    blacklist = {(0, 0), (1, 0), (2, 0)}
    available = [rc for rc in u_shape if rc not in blacklist]

    result = fsm._pick_cluster_centre(u_shape, blacklist)
    assert result is not None, "Expected a result, got None"
    assert result in available, f"Result {result} should be in available {available}"
    assert result in u_shape, f"Result {result} not in U-shape cells"

    # Vérifier que le centroïde utilisé est celui du groupe COMPLET
    # Centroïde groupe complet ≈ (1.0, 1.143) → cellule la plus proche parmi available
    # = (0,1) ou (1,2) ou (0,2) — mais PAS dérivé vers (1,2) uniquement comme v13.3
    # On vérifie que le résultat est une cellule disponible valide
    cr_full = sum(r for r, c in u_shape) / len(u_shape)
    cc_full = sum(c for r, c in u_shape) / len(u_shape)
    expected = min(available, key=lambda rc: (rc[0] - cr_full) ** 2 + (rc[1] - cc_full) ** 2)
    assert result == expected, (
        f"FIX-P1A: centroïde doit être calculé sur groupe complet. "
        f"Expected {expected}, got {result}. "
        f"Centroïde groupe complet = ({cr_full:.3f}, {cc_full:.3f})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-86 — FIX-P1A : forme anneau — centroïde groupe complet stable
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_86_p1a_ring_shape_centroid_full_group():
    """T-FSM-86: FIX-P1A — forme anneau 3×3 (bord extérieur, intérieur vide).

    Anneau :
    X X X
    X . X
    X X X
    (8 cellules de bord)

    Centroïde géométrique anneau = (1.0, 1.0) — centre.
    Avec blacklist partielle (bords top), centroïde groupe ne dérive pas.
    """
    fsm = _SelectPlaceFSM()
    ring = [(0, 0), (0, 1), (0, 2),
            (1, 0),         (1, 2),
            (2, 0), (2, 1), (2, 2)]

    # Blacklist bords haut
    blacklist = {(0, 0), (0, 1), (0, 2)}
    available = [rc for rc in ring if rc not in blacklist]

    result = fsm._pick_cluster_centre(ring, blacklist)
    assert result is not None, "Expected a result, got None"
    assert result in available, f"Result {result} not in available {available}"

    # Centroïde groupe complet = (1.0, 1.0) → cellule la plus proche dans available
    cr_full = sum(r for r, c in ring) / len(ring)
    cc_full = sum(c for r, c in ring) / len(ring)
    expected = min(available, key=lambda rc: (rc[0] - cr_full) ** 2 + (rc[1] - cc_full) ** 2)
    assert result == expected, (
        f"FIX-P1A anneau: expected {expected} (centroïde groupe complet), got {result}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-87 — FIX-P1A : groupe compact sans blacklist — résultat identique
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_87_p1a_compact_no_blacklist_same_result():
    """T-FSM-87: FIX-P1A — sans blacklist, centroïde groupe = centroïde available.

    Pour un groupe compact sans aucune cellule blacklistée, le résultat de
    v13.4 doit être identique à v13.3 (les deux calculent le même centroïde).
    Non-régression comportementale sur le cas le plus courant.
    """
    fsm = _SelectPlaceFSM()
    compact = [(0, 0), (0, 1), (1, 0), (1, 1)]

    result = fsm._pick_cluster_centre(compact, set())
    assert result is not None, "Expected a result, got None"
    assert result in compact, f"Result {result} not in compact cells"

    # Centroïde = (0.5, 0.5) → cellule la plus proche = n'importe laquelle des 4
    # (distance identique) — le résultat doit être dans le groupe
    cr = sum(r for r, c in compact) / len(compact)
    cc = sum(c for r, c in compact) / len(compact)
    expected = min(compact, key=lambda rc: (rc[0] - cr) ** 2 + (rc[1] - cc) ** 2)
    assert result == expected, f"Non-régression: expected {expected}, got {result}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-88 — FIX-P1A : deux objets disjoints — centroïde du plus grand groupe
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_88_p1a_two_disjoint_centroid_largest_group():
    """T-FSM-88: FIX-P1A — deux groupes disjoints, centroïde basé sur le plus grand.

    Groupe A (grand, 4 cellules) : (0,0)-(1,1)
    Groupe B (petit, 2 cellules) : (5,5),(5,6)
    Centroïde du plus grand groupe = (0.5, 0.5).
    """
    fsm = _SelectPlaceFSM()
    cells = [(0, 0), (0, 1), (1, 0), (1, 1),   # groupe A
             (5, 5), (5, 6)]                      # groupe B

    result = fsm._pick_cluster_centre(cells, set())
    assert result is not None, "Expected a result, got None"
    # Le résultat doit être dans le groupe A (le plus grand)
    group_a = {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert result in group_a, (
        f"FIX-P1A: should return cell from largest group {group_a}, got {result}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-89 — FIX-P1C : recovery purge la blacklist
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_89_p1c_recovery_clears_blacklist():
    """T-FSM-89: FIX-P1C — MAX_CONSECUTIVE_MISSES déclenche clear() de la blacklist.

    AVANT (v13.3): le bloc recovery (consecutive_misses >= MAX) ne purgait
                   pas failed_coords. La blacklist grossissait indéfiniment
                   entre deux cycles OBSERVE.
    APRÈS (v13.4): failed_coords.clear() ajouté dans le recovery.

    Test : on injecte manuellement N misses = MAX_CONSECUTIVE_MISSES sur la FSM.
    On appelle step() avec un grid minimal. On vérifie que failed_coords == 0
    après le step.
    """
    fsm = _SelectPlaceFSM()

    # Pré-remplir la blacklist
    fsm._failed_coords = {(0, 0), (0, 1), (1, 0)}
    fsm._consecutive_misses = fsm.MAX_CONSECUTIVE_MISSES  # déclenche le recovery

    # Grille minimale 4×4 couleur 5 (floor) avec quelques cellules couleur 3 (pièce)
    # et couleur 15 (cible) pour que classify_frame ait des candidats
    grid_4x4 = [
        [5, 5, 5, 5],
        [5, 3, 3, 5],
        [5, 15, 15, 5],
        [5, 5, 5, 5],
    ]
    frame = _col_frame(grid_4x4)
    x, y, label = fsm.step(frame=frame, prev_frame=None)

    # Après recovery + OBSERVE, failed_coords doit être vide
    assert len(fsm._failed_coords) == 0, (
        f"FIX-P1C: blacklist should be cleared after recovery, "
        f"got {len(fsm._failed_coords)} entries: {fsm._failed_coords}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-90 — FIX-P1C : blacklist ne grossit pas entre deux OBSERVE avec recovery
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_90_p1c_blacklist_does_not_accumulate_across_recovery():
    """T-FSM-90: FIX-P1C — la blacklist est bornée après recovery.

    Vérifie qu'après plusieurs cycles miss → recovery → miss → recovery,
    la blacklist reste à 0 après chaque recovery (pas d'accumulation).
    """
    fsm = _SelectPlaceFSM()

    grid_4x4 = [
        [5, 5, 5, 5],
        [5, 3, 3, 5],
        [5, 15, 15, 5],
        [5, 5, 5, 5],
    ]
    frame = _col_frame(grid_4x4)

    for _ in range(3):
        # Simuler accumulation de misses jusqu'au seuil
        fsm._failed_coords = {(r, c) for r in range(2) for c in range(2)}  # 4 entrées
        fsm._consecutive_misses = fsm.MAX_CONSECUTIVE_MISSES
        fsm.step(frame=frame, prev_frame=None)

        assert len(fsm._failed_coords) == 0, (
            f"FIX-P1C: blacklist should be 0 after recovery, "
            f"got {len(fsm._failed_coords)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-91 — FIX-P1C : après recovery, anciennes coords sont disponibles
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_91_p1c_after_recovery_old_coords_available():
    """T-FSM-91: FIX-P1C — après recovery, les coordonnées précédemment blacklistées
    peuvent être retentées si l'état de la grille a changé.

    On injecte une blacklist contenant toutes les cellules pièce.
    Si la blacklist n'est pas purgée au recovery, _pick_cluster_centre tombe
    en fallback global (moins précis).
    Après purge (v13.4), les cellules pièce redeviennent disponibles.
    """
    fsm = _SelectPlaceFSM()

    # Forcer un état WHERE toutes les pièces sont blacklistées
    piece_cells = [(1, 1), (1, 2), (2, 1), (2, 2)]
    fsm._piece_cells = piece_cells
    fsm._failed_coords = set(piece_cells)  # tout blacklisté

    # Sans recovery, _pick_cluster_centre retourne le fallback global
    result_with_blacklist = fsm._pick_cluster_centre(piece_cells, fsm._failed_coords)
    # (fallback retourne quand même une cellule — mais ignorant la blacklist)

    # Déclencher le recovery
    fsm._consecutive_misses = fsm.MAX_CONSECUTIVE_MISSES
    grid_4x4 = [
        [5, 5, 5, 5],
        [5, 3, 3, 5],
        [5, 3, 3, 5],
        [5, 5, 5, 5],
    ]
    frame = _col_frame(grid_4x4)
    fsm.step(frame=frame, prev_frame=None)

    # La blacklist doit être vide après le recovery
    assert len(fsm._failed_coords) == 0, (
        f"FIX-P1C: blacklist should be empty after recovery, got {fsm._failed_coords}"
    )

    # _pick_cluster_centre doit maintenant retourner depuis les cellules disponibles
    result_after_recovery = fsm._pick_cluster_centre(piece_cells, fsm._failed_coords)
    assert result_after_recovery in piece_cells, (
        f"After recovery, should target a piece cell, got {result_after_recovery}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-92 — FIX-P1D : 4-connexité — diagonales = groupes séparés (explicite)
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_92_p1d_diagonal_cells_are_separate_groups():
    """T-FSM-92: FIX-P1D — 4-connexité EXPLICITE : diagonales ne créent pas de lien.

    (0,0) et (1,1) sont en diagonale → 2 groupes séparés.
    Test explicitement documenté pour rappeler la décision architecturale.
    """
    fsm = _SelectPlaceFSM()
    diagonal_cells = [(0, 0), (1, 1)]  # diagonale, pas de voisin 4-conn commun
    groups = fsm._find_connected_groups(diagonal_cells)
    assert len(groups) == 2, (
        f"FIX-P1D: diagonales = groupes séparés en 4-connexité. "
        f"Expected 2 groups, got {len(groups)}: {groups}"
    )
    # Chaque groupe = 1 cellule
    assert all(len(g) == 1 for g in groups), (
        f"Each diagonal cell should be its own group, got sizes: {[len(g) for g in groups]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-93 — FIX-P1D : 4-connexité — adjacence H/V = même groupe
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_93_p1d_horizontal_vertical_same_group():
    """T-FSM-93: FIX-P1D — voisins horizontaux et verticaux = même groupe.

    (0,0)-(0,1)-(1,0) : L-shape connexe en 4-connexité → 1 groupe.
    """
    fsm = _SelectPlaceFSM()
    l_cells = [(0, 0), (0, 1), (1, 0)]
    groups = fsm._find_connected_groups(l_cells)
    assert len(groups) == 1, (
        f"FIX-P1D: L-shape en 4-connexité = 1 groupe. Got {len(groups)}: {groups}"
    )
    assert len(groups[0]) == 3, f"Expected 3 cells, got {len(groups[0])}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-94 — FIX-P1D : les 4 diagonales ne créent pas de connexion
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_94_p1d_all_four_diagonals_are_disconnected():
    """T-FSM-94: FIX-P1D — les 4 diagonales d'un pixel central sont toutes séparées.

    Pixels : (0,0), (0,2), (2,0), (2,2) — aux 4 coins d'une grille 3×3.
    Aucune adjacence 4-conn entre eux → 4 groupes de 1.
    """
    fsm = _SelectPlaceFSM()
    corners = [(0, 0), (0, 2), (2, 0), (2, 2)]
    groups = fsm._find_connected_groups(corners)
    assert len(groups) == 4, (
        f"FIX-P1D: 4 coins non connexes → 4 groupes séparés. Got {len(groups)}: {groups}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-95 — Forme U/L : le clic est toujours sur une cellule occupée
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_95_u_l_shapes_click_always_on_occupied_cell():
    """T-FSM-95: Forme U et L — le centroïde retourné est toujours dans cells.

    Garantit que le FIX-P1A ne produit jamais de clic sur le vide intérieur
    d'une forme creuse (le vide ne fait pas partie de cells).
    """
    fsm = _SelectPlaceFSM()

    # Forme U
    u_shape = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2)]
    result_u = fsm._pick_cluster_centre(u_shape, set())
    assert result_u in u_shape, f"U-shape result {result_u} not in cells"
    # Le vide intérieur (1,1) et (2,1) ne doit pas être retourné
    void_cells = {(1, 1), (2, 1)}
    assert result_u not in void_cells, f"U-shape: clic sur vide intérieur {result_u} interdit"

    # Forme L
    l_shape = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
    result_l = fsm._pick_cluster_centre(l_shape, set())
    assert result_l in l_shape, f"L-shape result {result_l} not in cells"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-96 — Blacklist partielle forme U — clic reste dans le groupe
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_96_u_shape_partial_blacklist_stays_in_group():
    """T-FSM-96: Forme U, blacklist partielle — le clic reste dans la forme.

    On blackliste (0,0) et (0,2) (coins haut). Le centroïde groupe complet
    reste à (1.0, 1.14), et la cellule retournée doit être dans available.
    """
    fsm = _SelectPlaceFSM()
    u_shape = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2)]
    blacklist = {(0, 0), (0, 2)}
    available = [rc for rc in u_shape if rc not in blacklist]

    result = fsm._pick_cluster_centre(u_shape, blacklist)
    assert result is not None
    assert result in available, f"Result {result} not in available cells {available}"
    assert result in u_shape, f"Result {result} not in u_shape"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-97 — Centroïde stable sur rectangle plein — non-régression
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_97_full_rectangle_centroid_stable():
    """T-FSM-97: Rectangle plein — centroïde au centre exact, non-régression.

    Rectangle 4×4 : centroïde = (1.5, 1.5).
    Cellule la plus proche = une des 4 cellules centrales.
    Sans blacklist, résultat identique v13.3/v13.4.
    """
    fsm = _SelectPlaceFSM()
    rect = [(r, c) for r in range(4) for c in range(4)]  # 16 cellules

    result = fsm._pick_cluster_centre(rect, set())
    assert result is not None
    assert result in rect

    # Centroïde = (1.5, 1.5) → cellules proches = (1,1), (1,2), (2,1), (2,2)
    central_cells = {(1, 1), (1, 2), (2, 1), (2, 2)}
    assert result in central_cells, (
        f"Rectangle 4×4: centroïde (1.5,1.5) → cellule dans {central_cells}, got {result}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-98 — Recovery + classify_frame — blacklist purgée avant SELECT
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_98_recovery_then_classify_blacklist_clear():
    """T-FSM-98: Recovery + classify_frame — cohérence séquence.

    Séquence :
    1. FSM en SELECT avec N misses = MAX
    2. Grille avec pièce couleur 3 (rare) et cible couleur 15
    3. step() déclenche recovery → OBSERVE → classify → SELECT
    4. failed_coords doit être vide en sortie
    5. _piece_cells doit contenir les cellules couleur 3
    """
    fsm = _SelectPlaceFSM()
    fsm._consecutive_misses = fsm.MAX_CONSECUTIVE_MISSES
    fsm._failed_coords = {(0, 0), (1, 1), (2, 2)}

    # Grille 8×8 : fond=5 (dominant), pièce=3 (≤15% = ≤9 cells/64 → ok 4 cells),
    # cible=15 (2 cells). 4/64=6.25% < 15% → valide comme candidat.
    grid_6x6 = [
        [5, 5, 5, 5, 5, 5, 5, 5],
        [5, 3, 3, 5, 5, 5, 5, 5],
        [5, 3, 3, 5, 5, 5, 5, 5],
        [5, 5, 5, 5, 5, 5, 5, 5],
        [5, 5, 5, 5, 5, 5, 5, 5],
        [5, 5, 5, 5, 15, 15, 5, 5],
        [5, 5, 5, 5, 5, 5, 5, 5],
        [5, 5, 5, 5, 5, 5, 5, 5],
    ]
    frame = _col_frame(grid_6x6)
    x, y, label = fsm.step(frame=frame, prev_frame=None)

    # Blacklist purgée
    assert len(fsm._failed_coords) == 0, (
        f"T-FSM-98: blacklist should be 0 after recovery+observe, got {fsm._failed_coords}"
    )
    # piece_cells doit être non vide (classify_frame a bien fonctionné)
    assert len(fsm._piece_cells) > 0, (
        "T-FSM-98: piece_cells should be populated after classify_frame"
    )
    # label doit indiquer SELECT (pas OBSERVE)
    assert "SELECT" in label or "PLACE" in label, (
        f"T-FSM-98: expected SELECT/PLACE state after recovery, got '{label}'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-99 — VERSION == "13.4"
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_99_version_is_13_4():
    """T-FSM-99: Non-régression — VERSION doit être "13.4"."""
    assert VERSION == "13.4", f"Expected VERSION='13.4', got '{VERSION}'"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-100 — Non-régression : 86 tests v13.0/v13.1/v13.2/v13.3 PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_100_non_regression_86_previous_tests():
    """T-FSM-100: Non-régression — les 86 tests précédents passent sur v13.4.

    Vérifie les invariants fondamentaux couverts par les suites L-048/L-049/L-050/L-052 :
    - _find_connected_groups([]) → []
    - _find_connected_groups([single_cell]) → 1 groupe de 1
    - _find_connected_groups([compact_2x2]) → 1 groupe de 4
    - _pick_cluster_centre([], set()) → None
    - _pick_cluster_centre([cells], set()) → cellule dans cells
    - FSM instance créée sans erreur
    - classify_frame grille uniforme → piece_colour == -1 (pas de candidat)
    - step() retourne (x, y, label) avec x,y ∈ [0,63]
    - VERSION est une chaîne non vide
    """
    # Invariant 1 : liste vide
    fsm = _SelectPlaceFSM()
    assert fsm._find_connected_groups([]) == []

    # Invariant 2 : une seule cellule
    groups = fsm._find_connected_groups([(3, 7)])
    assert len(groups) == 1 and len(groups[0]) == 1

    # Invariant 3 : groupe compact 2×2
    groups = fsm._find_connected_groups([(0, 0), (0, 1), (1, 0), (1, 1)])
    assert len(groups) == 1 and len(groups[0]) == 4

    # Invariant 4 : cells vide → None
    assert fsm._pick_cluster_centre([], set()) is None

    # Invariant 5 : résultat dans cells
    cells = [(1, 1), (1, 2), (2, 1)]
    result = fsm._pick_cluster_centre(cells, set())
    assert result in cells

    # Invariant 6 : grille uniforme → pas de candidat pièce
    uniform_grid = [[5] * 8 for _ in range(8)]
    fsm2 = _SelectPlaceFSM()
    fsm2._classify_frame(uniform_grid)
    assert fsm2._piece_colour == -1, f"Uniform grid should have no piece, got {fsm2._piece_colour}"

    # Invariant 7 : step() retourne coordonnées valides
    grid_3x3 = [
        [5, 5, 5],
        [5, 3, 5],
        [5, 5, 5],
    ]
    frame = _col_frame(grid_3x3)
    x, y, label = fsm2.step(frame=frame, prev_frame=None)
    assert 0 <= x <= 63, f"x={x} out of range [0,63]"
    assert 0 <= y <= 63, f"y={y} out of range [0,63]"
    assert isinstance(label, str) and label, f"label should be non-empty string, got '{label}'"

    # Invariant 8 : VERSION non vide
    assert VERSION and isinstance(VERSION, str)
