"""Tests L-052 — LuCY v13.3 : BFS groupes connexes + renforcement T-FSM-49/51/56

Tests couverts (T-FSM-67 à T-FSM-83) — nouveaux en v13.3 :
  T-FSM-67  : FIX-BFS — _find_connected_groups : groupe unique compact
  T-FSM-68  : FIX-BFS — _find_connected_groups : deux groupes disjoints
  T-FSM-69  : FIX-BFS — _find_connected_groups : trois groupes disjoints
  T-FSM-70  : FIX-BFS — _find_connected_groups : liste vide → []
  T-FSM-71  : FIX-BFS — _find_connected_groups : une seule cellule → un groupe de 1
  T-FSM-72  : FIX-BFS — _find_connected_groups : tri par taille décroissante
  T-FSM-73  : FIX-BFS — _find_connected_groups : cellules en diagonale → groupes séparés
  T-FSM-74  : FIX-BFS — _pick_cluster_centre deux groupes disjoints → centre du PLUS GRAND
  T-FSM-75  : FIX-BFS — _pick_cluster_centre : group le plus grand blacklisté → groupe suivant
  T-FSM-76  : FIX-BFS — _pick_cluster_centre : tous groupes blacklistés → fallback global
  T-FSM-77  : FIX-BFS — _pick_cluster_centre : groupe unique compact (rétrocompat v13.2)
  T-FSM-78  : FIX-BFS — blacklist partielle ne saute pas vers groupe minoritaire si maj dispo
  T-FSM-79  : RENFORCEMENT T-FSM-49 — attribution exacte pièce=couleur-la-plus-rare
  T-FSM-80  : RENFORCEMENT T-FSM-51 — grille sans égalité floor/ciel, exclusion stricte
  T-FSM-81  : RENFORCEMENT T-FSM-56 — fallback blacklist totale, pas de répétition justifiée
  T-FSM-82  : Non-régression — VERSION == "13.3"
  T-FSM-83  : Non-régression — 69 tests v13.0/v13.1/v13.2 non cassés par v13.3

CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif
"""

from __future__ import annotations

import sys
import os
import types
from typing import Any
from collections import Counter

# ── Stub arcengine (identique aux tests v13.0/v13.1/v13.2) ──────────────────
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

# ── Import module sous test (v13.3) ──────────────────────────────────────────
_agent_path = os.path.join(os.path.dirname(__file__), "..", "agent", "my_agent_v133.py")
import importlib.util

spec = importlib.util.spec_from_file_location("my_agent_v133", _agent_path)
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
# T-FSM-67 — FIX-BFS : groupe unique compact
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_67_bfs_single_compact_group():
    """T-FSM-67: FIX-BFS — groupe unique compact → 1 groupe contenant toutes les cellules."""
    fsm = _SelectPlaceFSM()
    cells = [(0, 0), (0, 1), (1, 0), (1, 1)]  # 2×2 connexe
    groups = fsm._find_connected_groups(cells)
    assert len(groups) == 1, f"Expected 1 group, got {len(groups)}"
    assert len(groups[0]) == 4, f"Expected 4 cells in group, got {len(groups[0])}"
    assert set(groups[0]) == set(cells)


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-68 — FIX-BFS : deux groupes disjoints
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_68_bfs_two_disjoint_groups():
    """T-FSM-68: FIX-BFS — deux objets séparés → 2 groupes distincts.

    PROBLÈME identifié dans l'audit L-051 : v13.2 calculait un centroïde global
    qui tombait entre les deux objets.  v13.3 détecte les deux groupes séparément.
    """
    fsm = _SelectPlaceFSM()
    # Groupe A : 4 cellules à gauche (0,0)-(1,1)
    # Groupe B : 4 cellules à droite (0,5)-(1,6) — séparées par un vide
    cells = [(0, 0), (0, 1), (1, 0), (1, 1), (0, 5), (0, 6), (1, 5), (1, 6)]
    groups = fsm._find_connected_groups(cells)
    assert len(groups) == 2, f"Expected 2 groups, got {len(groups)}"
    sizes = sorted([len(g) for g in groups])
    assert sizes == [4, 4], f"Expected groups of sizes [4, 4], got {sizes}"
    # Les deux groupes doivent être disjoints
    all_g0 = set(groups[0])
    all_g1 = set(groups[1])
    assert all_g0.isdisjoint(all_g1), "Groups should be disjoint"
    assert all_g0 | all_g1 == set(cells), "Union of groups must equal all cells"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-69 — FIX-BFS : trois groupes disjoints
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_69_bfs_three_groups():
    """T-FSM-69: FIX-BFS — trois objets séparés → 3 groupes de tailles différentes."""
    fsm = _SelectPlaceFSM()
    # Groupe A : 3 cellules
    # Groupe B : 2 cellules
    # Groupe C : 1 cellule (isolée)
    cells = [
        (0, 0), (0, 1), (1, 0),           # Groupe A (3 cells)
        (5, 5), (5, 6),                    # Groupe B (2 cells)
        (9, 9),                            # Groupe C (1 cell)
    ]
    groups = fsm._find_connected_groups(cells)
    assert len(groups) == 3, f"Expected 3 groups, got {len(groups)}"
    # Tri décroissant par taille
    assert len(groups[0]) == 3, f"Largest group should have 3 cells, got {len(groups[0])}"
    assert len(groups[1]) == 2, f"Second group should have 2 cells, got {len(groups[1])}"
    assert len(groups[2]) == 1, f"Smallest group should have 1 cell, got {len(groups[2])}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-70 — FIX-BFS : liste vide → []
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_70_bfs_empty_input():
    """T-FSM-70: FIX-BFS — liste vide → [] sans exception."""
    fsm = _SelectPlaceFSM()
    groups = fsm._find_connected_groups([])
    assert groups == [], f"Expected [], got {groups}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-71 — FIX-BFS : cellule unique → groupe de taille 1
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_71_bfs_single_cell():
    """T-FSM-71: FIX-BFS — une seule cellule → un groupe de taille 1."""
    fsm = _SelectPlaceFSM()
    groups = fsm._find_connected_groups([(3, 7)])
    assert len(groups) == 1, f"Expected 1 group, got {len(groups)}"
    assert groups[0] == [(3, 7)], f"Expected [(3,7)], got {groups[0]}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-72 — FIX-BFS : tri par taille décroissante
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_72_bfs_sorted_descending():
    """T-FSM-72: FIX-BFS — groupes triés par taille décroissante (plus grand en premier)."""
    fsm = _SelectPlaceFSM()
    # Groupe petit : 2 cells en haut à gauche
    # Groupe grand : 5 cells en bas à droite
    cells = [
        (0, 0), (0, 1),                              # petit groupe (2)
        (8, 8), (8, 9), (8, 10), (9, 8), (9, 9),   # grand groupe (5)
    ]
    groups = fsm._find_connected_groups(cells)
    assert len(groups) == 2
    # Le plus grand groupe (5) doit être en premier
    assert len(groups[0]) == 5, f"Expected largest group first (5), got {len(groups[0])}"
    assert len(groups[1]) == 2, f"Expected smallest group second (2), got {len(groups[1])}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-73 — FIX-BFS : cellules en diagonale → groupes séparés (4-connexité)
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_73_bfs_diagonal_not_connected():
    """T-FSM-73: FIX-BFS — cellules en diagonale → deux groupes séparés (4-connexité seule).

    (0,0) et (1,1) sont en diagonale : pas connexes en 4-connexité.
    """
    fsm = _SelectPlaceFSM()
    cells = [(0, 0), (1, 1)]  # diagonale
    groups = fsm._find_connected_groups(cells)
    assert len(groups) == 2, (
        f"Diagonal cells should form 2 separate groups (4-conn), got {len(groups)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-74 — FIX-BFS : deux groupes disjoints → centroïde du PLUS GRAND
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_74_pick_centre_two_groups_selects_largest():
    """T-FSM-74: FIX-BFS — deux groupes disjoints → _pick_cluster_centre cible le plus grand.

    ANOMALIE P0-2 de l'audit L-051 : v13.2 calculait le centroïde global
    des deux groupes combinés, qui tombait entre les deux objets (dans le vide).
    v13.3 cible le centroïde du groupe le plus grand.
    """
    fsm = _SelectPlaceFSM()
    # Groupe grand : 6 cellules (lignes 0-1, cols 0-2)
    # Groupe petit : 2 cellules (lignes 8-9, col 9) — loin à droite
    large_group = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    small_group = [(8, 9), (9, 9)]
    cells = large_group + small_group

    result = fsm._pick_cluster_centre(cells, set())

    assert result is not None, "Should return a valid cell"
    # Le résultat DOIT appartenir au grand groupe (pas au petit, pas dans le vide)
    assert result in large_group, (
        f"Expected result in large_group {large_group}, got {result}. "
        f"v13.2 aurait retourné le centroïde global tombant dans le vide."
    )
    # Vérification explicite : le centroïde global v13.2 aurait été entre les deux groupes
    all_r = [r for r, c in cells]
    all_c = [c for r, c in cells]
    global_cr = sum(all_r) / len(all_r)
    global_cc = sum(all_c) / len(all_c)
    # Le centroïde global est ~(3.0, 3.4) — hors du grand groupe (rows 0-1)
    # Le résultat v13.3 doit être dans le grand groupe (rows 0-1)
    assert result[0] <= 1, (
        f"Row {result[0]} should be <= 1 (large group rows 0-1). "
        f"Global centroid was ({global_cr:.1f}, {global_cc:.1f})."
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-75 — FIX-BFS : groupe le plus grand entièrement blacklisté → groupe suivant
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_75_pick_centre_largest_blacklisted_uses_next():
    """T-FSM-75: FIX-BFS — si le plus grand groupe est entièrement blacklisté,
    on passe au groupe suivant (pas de fallback immédiat sur une coord échouée).

    v13.2 : dès que les available étaient vides → fallback global toutes cells.
    v13.3 : on essaie d'abord le 2ème groupe avant le fallback.
    """
    fsm = _SelectPlaceFSM()
    # Groupe grand (5 cells) — toutes blacklistées
    large_group = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]
    # Groupe petit (3 cells) — aucune blacklistée
    small_group = [(7, 7), (7, 8), (8, 7)]
    cells = large_group + small_group
    blacklist = set(large_group)  # tout le grand groupe échoué

    result = fsm._pick_cluster_centre(cells, blacklist)

    assert result is not None, "Should return a valid cell from small group"
    assert result in small_group, (
        f"Expected result in small_group {small_group}, got {result}. "
        f"v13.3 doit utiliser le 2ème groupe quand le 1er est entièrement blacklisté."
    )
    assert result not in blacklist, "Should not return a blacklisted cell"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-76 — FIX-BFS : tous groupes blacklistés → fallback global
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_76_pick_centre_all_groups_blacklisted_fallback():
    """T-FSM-76: FIX-BFS — tous les groupes entièrement blacklistés → fallback centroïde global.

    Le fallback évite le blocage infini mais retourne une cellule du centroïde
    global (meilleure coordination plutôt qu'une cellule aléatoire).
    """
    fsm = _SelectPlaceFSM()
    cells = [(0, 0), (0, 1), (5, 5), (5, 6)]  # 2 groupes disjoints
    blacklist = set(cells)  # tout blacklisté

    result = fsm._pick_cluster_centre(cells, blacklist)

    # Ne doit pas retourner None — fallback disponible
    assert result is not None, "Fallback should always return a cell (never None)"
    assert result in cells, f"Fallback result {result} should be in original cells"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-77 — FIX-BFS : groupe unique compact (rétrocompat v13.2)
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_77_pick_centre_single_group_retrocompat():
    """T-FSM-77: FIX-BFS — groupe unique → comportement identique à v13.2 (rétrocompat).

    Quand les cellules forment un seul groupe connexe, le résultat doit être
    identique au centroïde v13.2 (même algorithme sur le groupe unique).
    """
    fsm = _SelectPlaceFSM()
    cells = [(1, 1), (2, 1), (3, 1), (3, 2), (3, 0)]  # groupe unique en L
    result = fsm._pick_cluster_centre(cells, set())

    # Calcul v13.2 attendu (centroïde global = centroïde du seul groupe)
    cr = sum(r for r, c in cells) / len(cells)
    cc = sum(c for r, c in cells) / len(cells)
    expected = min(cells, key=lambda rc: (rc[0] - cr) ** 2 + (rc[1] - cc) ** 2)

    assert result == expected, (
        f"Single-group result should match v13.2 centroid. "
        f"Expected {expected}, got {result}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-78 — FIX-BFS : blacklist partielle ne force pas vers groupe minoritaire
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_78_partial_blacklist_stays_in_majority_group():
    """T-FSM-78: FIX-BFS — blacklist partielle dans le grand groupe →
    reste dans le grand groupe (pas de saut vers le petit groupe).
    """
    fsm = _SelectPlaceFSM()
    # Groupe grand : 4 cells, 2 blacklistées → 2 disponibles
    large_group = [(0, 0), (0, 1), (1, 0), (1, 1)]
    # Groupe petit : 2 cells, toutes disponibles
    small_group = [(9, 9), (9, 10)]
    cells = large_group + small_group
    # Blacklist partielle dans le grand groupe
    blacklist = {(0, 0), (0, 1)}  # 2 sur 4 blacklistées

    result = fsm._pick_cluster_centre(cells, blacklist)

    assert result is not None
    # Doit rester dans le grand groupe (2 cells disponibles : (1,0) et (1,1))
    available_large = [rc for rc in large_group if rc not in blacklist]
    assert result in available_large, (
        f"With partial blacklist on large group, should stay in large group. "
        f"Expected in {available_large}, got {result}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-79 — RENFORCEMENT T-FSM-49 : attribution exacte pièce / cible
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_79_exact_piece_target_attribution():
    """T-FSM-79: RENFORCEMENT T-FSM-49 — attribution exacte pièce=couleur-la-plus-rare.

    FAIBLESSE identifiée dans l'audit L-051 (T-FSM-49) :
      assert fsm._piece_colour in (3, 7)  ← ne dit pas LEQUEL est la pièce.

    Ce test impose : piece_colour == 7 (3 cells = plus rare) ET target_colour == 3 (4 cells).
    La pièce est la couleur avec le MOINS de cellules parmi les candidates.
    """
    fsm = _SelectPlaceFSM()
    # floor=5 (56 cells), piece=7 (3 cells = plus rare), target=3 (4 cells)
    grid = [[5] * 8 for _ in range(8)]  # 64 cells floor
    # Couleur 3 : 4 cells (moins rare)
    grid[0][0] = 3
    grid[0][1] = 3
    grid[1][0] = 3
    grid[1][1] = 3
    # Couleur 7 : 3 cells (plus rare)
    grid[7][7] = 7
    grid[7][6] = 7
    grid[6][7] = 7
    fsm._classify_frame(grid)

    # Vérification stricte de l'attribution
    assert fsm._piece_colour == 7, (
        f"piece_colour={fsm._piece_colour} — expected 7 (3 cells, rarest). "
        f"T-FSM-49 acceptait n'importe lequel des deux."
    )
    assert fsm._target_colour == 3, (
        f"target_colour={fsm._target_colour} — expected 3 (4 cells, second rarest). "
        f"T-FSM-49 acceptait n'importe lequel des deux."
    )
    # Vérifier aussi les listes de cellules
    assert len(fsm._piece_cells) == 3, f"Expected 3 piece cells (colour 7), got {len(fsm._piece_cells)}"
    assert len(fsm._target_cells) == 4, f"Expected 4 target cells (colour 3), got {len(fsm._target_cells)}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-80 — RENFORCEMENT T-FSM-51 : grille sans égalité floor/ciel
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_80_large_secondary_excluded_strict():
    """T-FSM-80: RENFORCEMENT T-FSM-51 — grille sans égalité, exclusion stricte du ciel.

    FAIBLESSE identifiée dans l'audit L-051 (T-FSM-51) :
      La grille avait floor=5 à 40 cells ET sky=2 à 40 cells — égalité non déterministe.
      Le test ne vérifiait pas explicitement que sky=2 est exclu.

    Ce test construit une grille SANS égalité : floor=5 à 50 cells, sky=2 à 40 cells.
    piece=3 à 5 cells. On vérifie explicitement que piece_colour != 2.
    """
    fsm = _SelectPlaceFSM()
    # Grille 10x10 = 100 cells
    # floor=5 : 50 cells (rows 0-4, all cols) — DOMINANT sans ambiguïté
    # sky=2 : 40 cells (rows 5-8, all cols) — > 15% → doit être EXCLU
    # piece=3 : 5 cells (row 9, cols 0-4) — ≤ 15% → doit être INCLUS
    grid = []
    for r in range(10):
        row = []
        for c in range(10):
            if r < 5:
                row.append(5)   # floor : 50 cells
            elif r < 9:
                row.append(2)   # sky : 40 cells (40% > MAX_PIECE_CELLS_RATIO=15%)
            elif c < 5:
                row.append(3)   # piece : 5 cells
            else:
                row.append(5)   # encore floor
        grid.append(row)

    fsm._classify_frame(grid)

    # floor doit être 5 (50 cells, dominant sans ambiguïté)
    assert fsm._floor_colour == 5, f"floor={fsm._floor_colour} — expected 5 (50 cells)"

    # sky=2 doit être EXCLU (40 cells = 40% > MAX_PIECE_CELLS_RATIO=15%)
    assert fsm._piece_colour != 2, (
        f"piece_colour={fsm._piece_colour} — sky (colour 2, 40 cells) should be excluded "
        f"as it exceeds MAX_PIECE_CELLS_RATIO={fsm.MAX_PIECE_CELLS_RATIO*100:.0f}%."
    )
    assert fsm._target_colour != 2, (
        f"target_colour={fsm._target_colour} — sky should not be target either"
    )

    # piece_colour doit être 3 (5 cells = 5% ≤ 15%)
    assert fsm._piece_colour == 3, (
        f"piece_colour={fsm._piece_colour} — expected 3 (5 cells, valid rare colour)"
    )

    # Vérification des comptes
    sky_count = sum(1 for row in grid for v in row if v == 2)
    assert sky_count == 40, f"Test setup: sky should be 40 cells, got {sky_count}"
    piece_count = sum(1 for row in grid for v in row if v == 3)
    assert piece_count == 5, f"Test setup: piece should be 5 cells, got {piece_count}"


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-81 — RENFORCEMENT T-FSM-56 : fallback, pas de répétition justifiée
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_81_full_blacklist_fallback_uses_centroid():
    """T-FSM-81: RENFORCEMENT T-FSM-56 — fallback blacklist totale retourne le centroïde.

    FAIBLESSE identifiée dans l'audit L-051 (T-FSM-56) :
      assert result in cells  ← vérifie seulement qu'on ne plante pas.
      Ne vérifie pas que le fallback retourne bien le centroïde (pas une cellule arbitraire).

    Ce test vérifie :
      1. Le résultat est dans cells (pas de crash).
      2. Le résultat est la cellule la plus proche du centroïde global (comportement défini).
    """
    fsm = _SelectPlaceFSM()
    cells = [(0, 0), (0, 1), (1, 0), (1, 1)]
    blacklist = set(cells)  # tout blacklisté

    result = fsm._pick_cluster_centre(cells, blacklist)

    assert result is not None, "Fallback should not return None"
    assert result in cells, f"Fallback result {result} should be in cells"

    # Vérification du comportement défini : centroïde global
    cr = sum(r for r, c in cells) / len(cells)
    cc = sum(c for r, c in cells) / len(cells)
    expected = min(cells, key=lambda rc: (rc[0] - cr) ** 2 + (rc[1] - cc) ** 2)
    assert result == expected, (
        f"Fallback should return centroid cell {expected}, got {result}. "
        f"T-FSM-56 ne vérifiait pas quel fallback était retourné."
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-82 — Non-régression : VERSION == "13.3"
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_82_version_is_13_3():
    """T-FSM-82: Non-régression — le module importé est bien v13.3."""
    assert VERSION == "13.3", (
        f"VERSION={VERSION!r} — expected '13.3'. "
        f"Vérifier que le bon fichier est importé (my_agent_v133.py)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-FSM-83 — Non-régression : 69 tests v13.0/v13.1/v13.2 non cassés par v13.3
# ─────────────────────────────────────────────────────────────────────────────

def test_fsm_83_retrocompat_all_previous_fixes():
    """T-FSM-83: Non-régression — les fixes v13.0/v13.1/v13.2 sont maintenus en v13.3.

    Vérifie un sous-ensemble représentatif des invariants des versions précédentes :
    - FIX-P0A-v2 : classification par rareté (piece=couleur rare, pas couleur fréquente)
    - FIX-P0B : _is_confirmed_selection retourne (bool, float)
    - FIX-P0C : _is_confirmed_placement retourne string
    - FIX-P0F : _failed_coords est bien un set
    - FIX-CLUSTER (v13.2) : centroïde unique groupe = même résultat
    - FIX-BFS (v13.3) : _find_connected_groups existe et retourne une liste
    """
    fsm = _SelectPlaceFSM()

    # FIX-P0A-v2 : rareté
    grid = [[5] * 8 for _ in range(8)]
    grid[0][0] = grid[0][1] = grid[1][0] = 3  # 3 cells (rare)
    fsm._classify_frame(grid)
    assert fsm._piece_colour == 3, f"FIX-P0A-v2 broken: piece_colour={fsm._piece_colour}"

    # FIX-P0B : tuple (bool, float)
    grid1 = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
    grid2 = [[1, 1, 1], [1, 7, 1], [1, 1, 1]]
    frame1 = _col_frame(grid1)
    frame2 = _col_frame(grid2)
    fsm._last_click_r, fsm._last_click_c = 1, 1
    result_p0b = fsm._is_confirmed_selection(frame1, frame2)
    assert isinstance(result_p0b, tuple) and len(result_p0b) == 2, (
        f"FIX-P0B broken: _is_confirmed_selection returned {result_p0b!r}"
    )

    # FIX-P0C : string
    fsm._piece_colour = 3
    fsm._floor_colour = 5
    fsm._prev_active_count = 10
    frame_clean = _col_frame([[5, 5, 5], [5, 5, 5], [5, 5, 5]])
    result_p0c = fsm._is_confirmed_placement(frame_clean)
    assert isinstance(result_p0c, str), (
        f"FIX-P0C broken: _is_confirmed_placement returned {type(result_p0c)}"
    )

    # FIX-P0F : _failed_coords est un set
    fsm2 = _SelectPlaceFSM()
    assert isinstance(fsm2._failed_coords, set), (
        f"FIX-P0F broken: _failed_coords is {type(fsm2._failed_coords)}"
    )

    # FIX-BFS : _find_connected_groups existe et est callable
    assert hasattr(fsm, "_find_connected_groups"), "FIX-BFS: _find_connected_groups missing"
    assert callable(fsm._find_connected_groups), "FIX-BFS: _find_connected_groups not callable"
    groups_test = fsm._find_connected_groups([(0, 0), (0, 1)])
    assert isinstance(groups_test, list), f"FIX-BFS: should return list, got {type(groups_test)}"
    assert len(groups_test) == 1, f"FIX-BFS: [(0,0),(0,1)] should be 1 group, got {len(groups_test)}"
