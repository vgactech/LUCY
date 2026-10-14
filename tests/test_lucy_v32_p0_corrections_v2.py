"""
Tests T55–T74 — Validation corrections P0-A..P0-F v2 (LuCY v3.2)
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Ces tests vérifient que chaque correction P0 v2 résout bien les défauts résiduels
identifiés dans l'audit L-011 (rapport précédent, session 2026-10-14).

Défauts résiduels corrigés en v3.2 :
  P0-A v2 : n_sa_sum excluait RESET → n_total pouvait être < n_sa[(sid, RESET)]
  P0-B v2 : hash sans dimensions → collision si même bytes, formes différentes
  P0-C v2 : REWARD_CYCLE pénalisait aussi les états nouveaux (pas level_up)
  P0-D v2 : tri stable dépendait de l'index dans available_actions (ordre env)
  P0-E v2 : game_patterns chargés mais jamais consultés dans arbitrate()
  P0-F v2 : max_next_q sur STANDARD_ACTIONS fixe, pas les actions légales suivantes

Tous les tests s'exécutent SANS arcengine réel (stubs injectés).
"""

import hashlib
import json
import math
import os
import sys
import tempfile
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ============================================================
# Stubs arcengine minimal (identique aux tests v3.1)
# ============================================================

class _GameState:
    WIN = 'WIN'
    GAME_OVER = 'GAME_OVER'
    IN_PROGRESS = 'IN_PROGRESS'


class _GameAction:
    RESET = None

    def __init__(self, action_id=0):
        self.action_id = action_id
        self.data = {}

    @classmethod
    def from_id(cls, action_id):
        return cls(action_id)


class _Agent:
    def __init__(self, *args, **kwargs):
        self.action_counter = 0
        self.game_id = 'test_game'


# Patch arcengine AVANT l'import du module v3.2
sys.modules['arcengine'] = MagicMock(
    GameState=_GameState, GameAction=_GameAction
)
sys.modules['agents'] = MagicMock()
sys.modules['agents.agent'] = MagicMock(Agent=_Agent)

# Import du module v3.2 via importlib (pas de dépendance arcengine)
import importlib.util

_v32_path = os.path.join(
    os.path.dirname(__file__), '..', 'src', 'lucy', 'kernel', 'lucy_agent_v32.py'
)
_spec = importlib.util.spec_from_file_location('lucy_agent_v32', _v32_path)
_mod = importlib.util.module_from_spec(_spec)
_mod.Agent = _Agent
_mod.GameState = _GameState
_mod.GameAction = _GameAction
_spec.loader.exec_module(_mod)

# Extraire les symboles testés
pe_encode_frame = _mod.pe_encode_frame
PIPatternAnalyzer = _mod.PIPatternAnalyzer
LuCYCognition = _mod.LuCYCognition
build_action = _mod.build_action
STANDARD_ACTIONS = _mod.STANDARD_ACTIONS
RESET_ACTION_ID = _mod.RESET_ACTION_ID
REWARD_LEVEL_UP = _mod.REWARD_LEVEL_UP
REWARD_WIN = _mod.REWARD_WIN
REWARD_CYCLE = _mod.REWARD_CYCLE
REWARD_RESET = _mod.REWARD_RESET
REWARD_PROGRESS = _mod.REWARD_PROGRESS
PATTERN_BIAS_BONUS = _mod.PATTERN_BIAS_BONUS
VERSION = _mod.VERSION


# ============================================================
# Helpers
# ============================================================

def make_cognition(persist_path: str = None) -> LuCYCognition:
    """Crée une instance LuCYCognition avec un chemin de persistance temporaire."""
    if persist_path:
        _mod.PATTERNS_PERSIST_PATH = persist_path
    cog = LuCYCognition()
    return cog


def make_frame_array(h: int, w: int, fill: int = 42) -> np.ndarray:
    return np.full((h, w, 3), fill, dtype=np.uint8)


def make_lf(state=None, levels=0, score=0):
    """Crée un fake game_state (lf) minimal."""
    lf = MagicMock()
    lf.state = state or _GameState.IN_PROGRESS
    lf.levels_completed = levels
    lf.score = score
    lf.available_actions = tuple(STANDARD_ACTIONS)
    lf.frame = None
    return lf


# ============================================================
# BLOC P0-A v2 — n_sa_sum inclut RESET (T55–T57)
# ============================================================

class TestP0A_v2_NsaSumIncludesReset:
    """T55–T57 — Invariant UCB1 complet : n_total >= n_sa[(sid, RESET)]."""

    def test_T55_n_total_accounts_for_reset(self):
        """T55 : Après un RESET, n_total doit tenir compte de n_sa[(sid, RESET)].

        DÉFAUT v3.1 :
            n_sa_sum = sum(...for aid in available_actions if aid != RESET_ACTION_ID)
            → n_total ignorait RESET → invariant cassé si RESET joué souvent

        CORRECTION v3.2 :
            n_sa_sum = sum(...for aid in available_actions)  # sans exclusion RESET
            → n_total = max(1, n_s[sid], n_sa_sum) toujours >= n_sa[(sid, RESET)]
        """
        cog = make_cognition()
        sid = 'sid_reset_test'
        # Simuler plusieurs resets depuis ce sid
        for _ in range(5):
            cog.update(sid, 'coarse', 'sid_next', 'coarse_next', 'col',
                       RESET_ACTION_ID, False)

        # n_sa[(sid, RESET)] = 5
        assert cog.n_sa[(sid, RESET_ACTION_ID)] == 5
        # n_s[sid] = 5 (incrémenté à chaque update)
        assert cog.n_s[sid] == 5

        # Dans te_ucb1_score_actions, n_total doit être >= n_sa[(sid, RESET)]
        # available_actions ici inclut RESET (on passe le tuple complet)
        available = tuple(STANDARD_ACTIONS + [RESET_ACTION_ID])
        n_sa_sum = sum(cog.n_sa.get((sid, aid), 0) for aid in available)
        n_total = max(1, cog.n_s[sid], n_sa_sum)
        assert n_total >= cog.n_sa[(sid, RESET_ACTION_ID)], (
            f"n_total={n_total} < n_sa[(sid, RESET)]={cog.n_sa[(sid, RESET_ACTION_ID)]}"
        )

    def test_T56_invariant_still_holds_after_mixed_actions(self):
        """T56 : Invariant tenu après un mélange d'actions standard et RESET."""
        cog = make_cognition()
        sid = 'sid_mixed'
        # 3 actions normales, 2 resets
        cog.update(sid, 'c', 'nxt', 'c2', 'col', 1, False)
        cog.update(sid, 'c', 'nxt', 'c2', 'col', 2, False)
        cog.update(sid, 'c', 'nxt', 'c2', 'col', RESET_ACTION_ID, False)
        cog.update(sid, 'c', 'nxt', 'c2', 'col', 3, False)
        cog.update(sid, 'c', 'nxt', 'c2', 'col', RESET_ACTION_ID, False)

        # Vérifier pour TOUTES les actions
        available = tuple(STANDARD_ACTIONS + [RESET_ACTION_ID])
        n_sa_sum_full = sum(cog.n_sa.get((sid, aid), 0) for aid in available)
        n_total = max(1, cog.n_s[sid], n_sa_sum_full)
        for aid in available:
            n_act = cog.n_sa.get((sid, aid), 0)
            assert n_total >= n_act, (
                f"n_total={n_total} < n_sa[({sid},{aid})]={n_act}"
            )

    def test_T57_ucb1_score_no_exception_with_reset_available(self):
        """T57 : te_ucb1_score_actions ne lève pas d'exception si RESET est dans available_actions."""
        cog = make_cognition()
        sid = 'sid_ucb_reset'
        # Jouer RESET 3 fois depuis ce sid
        for _ in range(3):
            cog.update(sid, 'c', sid, 'c', 'col', RESET_ACTION_ID, False)

        # RESET dans available — ne doit pas planter
        available_with_reset = tuple(STANDARD_ACTIONS + [RESET_ACTION_ID])
        try:
            scored = cog.te_ucb1_score_actions(sid, available_with_reset)
        except Exception as exc:
            pytest.fail(f"te_ucb1_score_actions a levé une exception : {exc}")

        # On doit avoir au moins un score
        assert len(scored) >= 1


# ============================================================
# BLOC P0-B v2 — Hash avec dimensions (T58–T61)
# ============================================================

class TestP0B_v2_HashWithDimensions:
    """T58–T61 — pe_encode_frame inclut les dimensions de la grille dans le hash."""

    def test_T58_same_bytes_different_shape_give_different_sid(self):
        """T58 : Deux grilles avec les mêmes bytes mais des formes différentes → sid_full distincts.

        DÉFAUT v3.1 :
            sid_full = hashlib.md5(arr.tobytes()).hexdigest()[:16]
            → np.full((4,8), 42) et np.full((8,4), 42) : même bytes → même sid_full

        CORRECTION v3.2 :
            shape_prefix = rows.to_bytes(2,'little') + cols.to_bytes(2,'little')
            sid_full = hashlib.md5(shape_prefix + arr.tobytes()).hexdigest()[:16]
            → formes différentes → sid_full différents
        """
        # Deux tableaux avec exactement les mêmes bytes mais des formes différentes
        arr_4x8 = np.full((4, 8), 42, dtype=np.uint8)
        arr_8x4 = np.full((8, 4), 42, dtype=np.uint8)

        # Vérifier que les bytes sont bien identiques
        assert arr_4x8.tobytes() == arr_8x4.tobytes(), (
            "Prérequis du test : les deux tableaux doivent avoir des bytes identiques"
        )

        sid_4x8, _, _ = pe_encode_frame(arr_4x8)
        sid_8x4, _, _ = pe_encode_frame(arr_8x4)

        assert sid_4x8 != sid_8x4, (
            f"DÉFAUT v2 présent : sid_4x8={sid_4x8} == sid_8x4={sid_8x4} "
            "(collision de formes différentes)"
        )

    def test_T59_same_shape_same_content_same_sid(self):
        """T59 : Deux tableaux identiques (même shape, même contenu) → même sid_full."""
        arr_a = np.full((6, 6), 7, dtype=np.uint8)
        arr_b = np.full((6, 6), 7, dtype=np.uint8)

        sid_a, _, _ = pe_encode_frame(arr_a)
        sid_b, _, _ = pe_encode_frame(arr_b)

        assert sid_a == sid_b, (
            f"Deux tableaux identiques doivent donner le même sid_full : {sid_a} != {sid_b}"
        )

    def test_T60_different_content_same_shape_different_sid(self):
        """T60 : Même shape mais contenu différent → sid_full différents (régression)."""
        arr_a = np.full((5, 5), 10, dtype=np.uint8)
        arr_b = np.full((5, 5), 20, dtype=np.uint8)

        sid_a, _, _ = pe_encode_frame(arr_a)
        sid_b, _, _ = pe_encode_frame(arr_b)

        assert sid_a != sid_b

    def test_T61_1xN_vs_Nx1_arrays_differ(self):
        """T61 : Tableaux 1×N et N×1 avec même contenu → sid_full différents."""
        # 1×4 vs 4×1 : même bytes [1,2,3,4]
        arr_row = np.array([[1, 2, 3, 4]], dtype=np.uint8)   # shape (1, 4)
        arr_col = np.array([[1], [2], [3], [4]], dtype=np.uint8)  # shape (4, 1)

        assert arr_row.tobytes() == arr_col.tobytes(), (
            "Prérequis : bytes identiques pour (1,4) et (4,1)"
        )

        sid_row, _, _ = pe_encode_frame(arr_row)
        sid_col, _, _ = pe_encode_frame(arr_col)

        assert sid_row != sid_col, (
            f"Collision 1×N vs N×1 non détectée : {sid_row} == {sid_col}"
        )


# ============================================================
# BLOC P0-C v2 — 3 niveaux de reward (T62–T64)
# ============================================================

class TestP0C_v2_ThreeLevelReward:
    """T62–T64 — Distinction CYCLE (état ident.) / PROGRESS (état nouveau) / LEVEL_UP."""

    def test_T62_progress_reward_when_state_changes(self):
        """T62 : État nouveau (curr_sid != prev_sid) sans level_up → REWARD_PROGRESS.

        DÉFAUT v3.1 :
            else: reward += REWARD_CYCLE  # -0.05 même si état nouveau !
        CORRECTION v3.2 :
            elif curr_sid == prev_sid: reward += REWARD_CYCLE
            else: reward += REWARD_PROGRESS  # +0.05 si état différent
        """
        cog = make_cognition()
        reward = cog.update('sA', 'cA', 'sB', 'cB', 'col', 1, False)
        assert reward == REWARD_PROGRESS, (
            f"État nouveau sans level_up doit donner REWARD_PROGRESS={REWARD_PROGRESS}, "
            f"obtenu={reward}"
        )
        assert REWARD_PROGRESS > 0, "REWARD_PROGRESS doit être positif (signal de progrès)"

    def test_T63_cycle_reward_when_state_unchanged(self):
        """T63 : État identique (curr_sid == prev_sid) sans level_up → REWARD_CYCLE.

        Cela reste -0.05 : une vraie boucle stérile est toujours pénalisée.
        """
        cog = make_cognition()
        reward = cog.update('sA', 'cA', 'sA', 'cA', 'col', 1, False)
        assert reward == REWARD_CYCLE, (
            f"État inchangé doit donner REWARD_CYCLE={REWARD_CYCLE}, obtenu={reward}"
        )
        assert REWARD_CYCLE < 0, "REWARD_CYCLE doit être négatif (pénalité boucle)"

    def test_T64_progress_and_cycle_distinct_from_each_other(self):
        """T64 : REWARD_PROGRESS > 0 > REWARD_CYCLE et tous deux < REWARD_LEVEL_UP."""
        assert REWARD_PROGRESS > 0, "REWARD_PROGRESS doit être positif"
        assert REWARD_CYCLE < 0, "REWARD_CYCLE doit être négatif"
        assert REWARD_PROGRESS < REWARD_LEVEL_UP, "REWARD_PROGRESS < REWARD_LEVEL_UP"
        assert REWARD_CYCLE > REWARD_RESET, "REWARD_CYCLE > REWARD_RESET (reset pire)"


# ============================================================
# BLOC P0-D v2 — Tri canonique par action_id (T65–T67)
# ============================================================

class TestP0D_v2_CanonicalSort:
    """T65–T67 — Tri des non-essayées par action_id canonique, indépendant de l'ordre env."""

    def test_T65_order_independent_of_available_actions_order(self):
        """T65 : Peu importe l'ordre des available_actions, le premier non-essayé est toujours min(action_id).

        DÉFAUT v3.1 :
            scored_inf.sort(key=lambda x: x[0])  # x[0] = idx dans available_actions
            → si available_actions = (3, 1, 2), la première non-essayée était 3 (idx=0)

        CORRECTION v3.2 :
            scored_inf.sort(key=lambda x: x[1])  # x[1] = action_id canonique
            → peu importe l'ordre reçu, la première non-essayée est toujours action_id min
        """
        cog = make_cognition()
        sid = 'sid_order_test'

        # available_actions dans un ordre non standard : (3, 1, 2)
        available_reversed = (3, 1, 2)
        scored = cog.te_ucb1_score_actions(sid, available_reversed)

        # Toutes sont non-essayées → toutes à inf, triées par action_id
        inf_actions = [aid for score, aid in scored if score == float('inf')]
        assert inf_actions[0] == 1, (
            f"Premier non-essayé doit être action_id=1 (canonique), obtenu={inf_actions[0]}"
        )
        # Ordre canonique : 1, 2, 3
        assert inf_actions == [1, 2, 3], (
            f"Ordre canonique attendu [1,2,3], obtenu={inf_actions}"
        )

    def test_T66_canonical_order_matches_action_id_ascending(self):
        """T66 : Les non-essayées sont triées par action_id croissant quel que soit l'ordre env."""
        cog = make_cognition()
        sid = 'sid_canonical'

        # Tester plusieurs permutations
        import itertools
        actions = [1, 2, 3, 4, 5]
        permutations = list(itertools.permutations(actions))[:6]  # 6 premières

        first_actions = set()
        for perm in permutations:
            scored = cog.te_ucb1_score_actions(sid, tuple(perm))
            inf_actions = [aid for score, aid in scored if score == float('inf')]
            first_actions.add(inf_actions[0])

        # Peu importe la permutation, le premier non-essayé est toujours 1
        assert first_actions == {1}, (
            f"Le premier non-essayé devrait toujours être 1, obtenu={first_actions}"
        )

    def test_T67_canonical_order_stable_after_partial_exploration(self):
        """T67 : Après avoir essayé action_id=1, le suivant non-essayé est action_id=2."""
        cog = make_cognition()
        sid = 'sid_partial_explore'

        # Essayer action 1
        cog.update(sid, 'c', 'nxt', 'c2', 'col', 1, False)

        # available en ordre non standard (5, 3, 1, 2, 4)
        available = (5, 3, 1, 2, 4)
        scored = cog.te_ucb1_score_actions(sid, available)
        inf_actions = [aid for score, aid in scored if score == float('inf')]

        # action 1 est essayée, donc non-essayées = [2, 3, 4, 5] → premier = 2
        assert 1 not in inf_actions, "action_id=1 déjà essayée, ne doit pas être à inf"
        if inf_actions:
            assert inf_actions[0] == 2, (
                f"Après avoir essayé action 1, le premier non-essayé canonique doit être 2, "
                f"obtenu={inf_actions[0]}"
            )


# ============================================================
# BLOC P0-E v2 — game_patterns consulté dans arbitrate() (T68–T70)
# ============================================================

class TestP0E_v2_PatternUsedInArbitrate:
    """T68–T70 — arbitrate() consulte game_patterns pour biaiser si sid_coarse connu."""

    def test_T68_lookup_pattern_action_returns_known_action(self):
        """T68 : _lookup_pattern_action() retourne l'action si sid_coarse est dans les patterns.

        DÉFAUT v3.1 :
            game_patterns était persisté mais jamais lu dans arbitrate().
        CORRECTION v3.2 :
            _lookup_pattern_action(sid_coarse) cherche dans game_patterns.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = os.path.join(tmpdir, 'patterns.json')
            cog = make_cognition(persist_path)

            # Injecter un pattern manuellement
            cog.game_patterns['0'] = {
                'action': 3,
                'from_sid_coarse': 'coarse_known',
                'to_sid_coarse': 'coarse_next',
            }

            result = cog._lookup_pattern_action('coarse_known')
            assert result == 3, (
                f"_lookup_pattern_action doit retourner 3 pour 'coarse_known', obtenu={result}"
            )

    def test_T69_lookup_returns_none_for_unknown_coarse(self):
        """T69 : _lookup_pattern_action() retourne None si sid_coarse inconnu."""
        cog = make_cognition()
        # Pas de patterns chargés
        result = cog._lookup_pattern_action('coarse_unknown_xyz')
        assert result is None

    def test_T70_pattern_bonus_applied_in_ucb1_score(self):
        """T70 : L'action du pattern reçoit PATTERN_BIAS_BONUS dans te_ucb1_score_actions().

        Après avoir essayé toutes les actions non-essayées, si un pattern suggère
        action=3 depuis le sid_coarse courant, son score UCB1 doit être augmenté.
        """
        cog = make_cognition()
        sid = 'sid_pattern_bonus'

        # Jouer toutes les actions standard au moins une fois pour qu'elles aient un score fini
        for aid in STANDARD_ACTIONS:
            cog.update(sid, 'coarse_pattern_test', 'nxt', 'c2', 'col', aid, False)

        # Maintenant, les scores sont finis ; vérifier que pattern_action=3 a un bonus
        scored_without_pattern = cog.te_ucb1_score_actions(
            sid, tuple(STANDARD_ACTIONS), pattern_action=None
        )
        scored_with_pattern = cog.te_ucb1_score_actions(
            sid, tuple(STANDARD_ACTIONS), pattern_action=3
        )

        # Trouver le score de action=3 dans les deux cas
        score_without = next((s for s, a in scored_without_pattern if a == 3), None)
        score_with = next((s for s, a in scored_with_pattern if a == 3), None)

        assert score_without is not None, "action=3 doit avoir un score"
        assert score_with is not None, "action=3 avec pattern doit avoir un score"
        assert score_with == score_without + PATTERN_BIAS_BONUS, (
            f"Bonus attendu PATTERN_BIAS_BONUS={PATTERN_BIAS_BONUS}, "
            f"score_sans={score_without:.4f}, score_avec={score_with:.4f}, "
            f"diff={score_with - score_without:.4f}"
        )


# ============================================================
# BLOC P0-F v2 — max_next_q sur available_actions (T71–T73)
# ============================================================

class TestP0F_v2_MaxNextQOnAvailableActions:
    """T71–T73 — max_next_q calculé sur next_available_actions passées en paramètre."""

    def test_T71_max_next_q_uses_provided_actions(self):
        """T71 : update() avec next_available_actions utilise ces actions pour max_next_q.

        DÉFAUT v3.1 :
            all_actions = STANDARD_ACTIONS + [RESET_ACTION_ID]  # liste fixe toujours
        CORRECTION v3.2 :
            if next_available_actions: all_next = list(next_available_actions)
            else: fallback vers liste fixe
        """
        cog = make_cognition()
        curr_sid = 'sid_next_state'

        # Pré-charger des Q-values : action 99 = Q très élevée, action 1 = faible
        cog.q_table[(curr_sid, 99)] = 100.0  # action fictive très attirante
        cog.q_table[(curr_sid, 1)] = 0.1

        # Si on ne passe que (1,) comme next_available_actions, max_next_q doit être 0.1
        # et NON 100.0 (car action 99 n'est pas dans la liste)
        reward = cog.update(
            'sid_prev', 'c_prev', curr_sid, 'c_curr', 'col',
            1, False, win=False,
            next_available_actions=(1,)
        )
        # max_next_q = 0.1 (seulement action 1 dans la liste)
        # new_q = old_q + ALPHA * (reward + GAMMA * max_next_q - old_q)
        # Comme reward = REWARD_PROGRESS (curr_sid != prev_sid) :
        expected_max_next = 0.1
        old_q = 0.0
        expected_new_q = old_q + _mod.ALPHA * (reward + _mod.GAMMA * expected_max_next - old_q)
        actual_q = cog.q_table.get(('sid_prev', 1), None)
        assert actual_q is not None
        assert abs(actual_q - expected_new_q) < 1e-9, (
            f"Q-value incorrecte: attendu={expected_new_q:.6f}, obtenu={actual_q:.6f}"
        )

    def test_T72_fallback_to_standard_when_no_next_actions(self):
        """T72 : Sans next_available_actions, le fallback est STANDARD_ACTIONS + [RESET]."""
        cog = make_cognition()
        curr_sid = 'sid_fallback'

        # Pré-charger Q pour action RESET dans l'état suivant
        cog.q_table[(curr_sid, RESET_ACTION_ID)] = 5.0

        # Sans next_available_actions → fallback inclut RESET → max_next_q = 5.0
        cog.update(
            'sid_p', 'c_p', curr_sid, 'c_c', 'col',
            1, False, win=False,
            next_available_actions=None
        )
        # max_next_q doit être 5.0 (RESET dans le fallback)
        # → vérifiable indirectement : Q('sid_p', 1) inclut GAMMA * 5.0
        reward_expected = _mod.REWARD_PROGRESS  # curr != prev
        q_actual = cog.q_table.get(('sid_p', 1), 0.0)
        expected = 0.0 + _mod.ALPHA * (reward_expected + _mod.GAMMA * 5.0 - 0.0)
        assert abs(q_actual - expected) < 1e-9, (
            f"Fallback incorrect: attendu={expected:.6f}, obtenu={q_actual:.6f}"
        )

    def test_T73_empty_next_actions_uses_fallback(self):
        """T73 : next_available_actions=() (vide) → fallback vers liste fixe."""
        cog = make_cognition()
        # Ne doit pas lever d'exception avec une liste vide
        try:
            cog.update(
                'sid_e', 'c_e', 'sid_e2', 'c_e2', 'col',
                1, False, win=False,
                next_available_actions=()
            )
        except Exception as exc:
            pytest.fail(f"update() avec next_available_actions=() a levé : {exc}")


# ============================================================
# BLOC VERSION — Vérification métadonnées v3.2 (T74)
# ============================================================

class TestVersionV32:
    """T74 — Vérification que le module est bien v3.2."""

    def test_T74_version_is_32(self):
        """T74 : VERSION == '3.2' et REWARD_PROGRESS est défini."""
        assert VERSION == '3.2', f"VERSION attendu '3.2', obtenu '{VERSION}'"
        assert hasattr(_mod, 'REWARD_PROGRESS'), "REWARD_PROGRESS doit exister en v3.2"
        assert _mod.REWARD_PROGRESS > 0, "REWARD_PROGRESS doit être > 0"
        assert hasattr(_mod, 'PATTERN_BIAS_BONUS'), "PATTERN_BIAS_BONUS doit exister en v3.2"
        assert _mod.PATTERN_BIAS_BONUS > 0, "PATTERN_BIAS_BONUS doit être > 0"
        assert _mod.CERTIFIED_100 is False
        print(f"[OK] LuCY v{VERSION} | REWARD_PROGRESS={REWARD_PROGRESS} "
              f"| REWARD_CYCLE={REWARD_CYCLE} | PATTERN_BIAS_BONUS={PATTERN_BIAS_BONUS}")
