"""
Tests T35–T54 — Validation corrections P0-A..P0-F (LuCY v3.1)
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Ces tests vérifient que chaque correction P0 résout bien le bug décrit dans L-010.
Ils sont conçus pour être exécutés SANS arcengine (module local uniquement).
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

# Ajout du chemin source
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# ============================================================
# Import depuis le module v3.1
# On importe directement les fonctions/classes sans arcengine
# en patchant les imports au niveau module
# ============================================================

# Stub arcengine minimal pour les tests (identique aux tests précédents)
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

# Patch arcengine AVANT l'import du module
sys.modules['arcengine'] = MagicMock(
    GameState=_GameState, GameAction=_GameAction
)
sys.modules['agents'] = MagicMock()
sys.modules['agents.agent'] = MagicMock(Agent=_Agent)

# Maintenant importer les pièces testées depuis le fichier v3.1
import importlib.util
_v31_path = os.path.join(
    os.path.dirname(__file__), '..', 'src', 'lucy', 'kernel', 'lucy_agent_v31.py'
)
_spec = importlib.util.spec_from_file_location('lucy_agent_v31', _v31_path)
_mod = importlib.util.module_from_spec(_spec)
# Injecter les stubs dans le namespace du module
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
VERSION = _mod.VERSION


# ============================================================
# Helpers
# ============================================================

def make_cognition(persist_path=None) -> LuCYCognition:
    """Crée une instance LuCYCognition avec un chemin de persistance temporaire."""
    if persist_path:
        _mod.PATTERNS_PERSIST_PATH = persist_path
    cog = LuCYCognition()
    return cog


def make_frame_array(h: int, w: int, fill: int = 42) -> np.ndarray:
    return np.full((h, w), fill, dtype=np.uint8)


# ============================================================
# BLOC P0-A — UCB1 invariant n_s >= n_sa + log(0) guard (T35–T40)
# ============================================================

class TestP0A_UCB1Invariant:
    """T35–T40 — Invariant n_s >= n_sa et absence de log(0)/division par zéro."""

    def test_T35_n_s_incremented_with_n_sa(self):
        """T35 : Chaque update() incrémente n_s ET n_sa du même sid — invariant maintenu."""
        cog = make_cognition()
        cog.update('sA', 'cA', 'sB', 'cB', 'col', 1, False)
        assert cog.n_s['sA'] == 1
        assert cog.n_sa[('sA', 1)] == 1
        # Invariant : n_s[sid] >= n_sa[(sid, any_aid)]
        for (sid, aid), cnt in cog.n_sa.items():
            assert cog.n_s[sid] >= cnt, (
                f"Invariant violated: n_s[{sid}]={cog.n_s[sid]} < n_sa[({sid},{aid})]={cnt}"
            )

    def test_T36_invariant_after_multiple_updates(self):
        """T36 : Invariant tenu après 20 updates sur le même état."""
        cog = make_cognition()
        for _ in range(20):
            cog.update('sX', 'cX', 'sY', 'cY', 'col', 1, False)
            cog.update('sX', 'cX', 'sX', 'cX', 'col', 2, False)
        for (sid, aid), cnt in cog.n_sa.items():
            assert cog.n_s[sid] >= cnt, (
                f"Invariant violated: n_s[{sid}]={cog.n_s[sid]} < n_sa[({sid},{aid})]={cnt}"
            )

    def test_T37_ucb1_no_log_zero(self):
        """T37 : Pas de log(0) ni division par zéro quand n_total=1."""
        cog = make_cognition()
        # État avec 1 seule visite totale
        cog.n_s['sA'] = 1
        cog.n_sa[('sA', 1)] = 1
        cog.q_table[('sA', 1)] = 0.5
        # Ne doit pas lever d'exception
        scored = cog.te_ucb1_score_actions('sA', tuple(STANDARD_ACTIONS))
        assert len(scored) > 0

    def test_T38_ucb1_fresh_state_all_inf(self):
        """T38 : État frais → toutes les actions non essayées reçoivent score inf."""
        cog = make_cognition()
        scored = cog.te_ucb1_score_actions('sNew', tuple(STANDARD_ACTIONS))
        # Toutes les actions non essayées ont score infini
        inf_count = sum(1 for score, _ in scored if score == float('inf'))
        assert inf_count == len(STANDARD_ACTIONS), (
            f"Attendu {len(STANDARD_ACTIONS)} inf, obtenu {inf_count}"
        )

    def test_T39_ucb1_no_nan_no_inf_after_visits(self):
        """T39 : Aucun NaN ni inf (hors non-essayées) après visites réelles."""
        cog = make_cognition()
        for i, aid in enumerate(STANDARD_ACTIONS):
            cog.n_s['sA'] += 5
            cog.n_sa[('sA', aid)] = 5
            cog.q_table[('sA', aid)] = float(i) * 0.1
        scored = cog.te_ucb1_score_actions('sA', tuple(STANDARD_ACTIONS))
        for score, _ in scored:
            assert not math.isnan(score), f"NaN détecté dans UCB1 score: {scored}"
            assert math.isfinite(score), f"Infini inattendu dans UCB1 score: {scored}"

    def test_T40_ucb1_n_total_uses_max(self):
        """T40 : n_total = max(n_s[sid], sum n_sa) — aucune valeur négative."""
        cog = make_cognition()
        # Simuler un état potentiellement incohérent (n_sa > n_s suite à dérive)
        cog.n_s['sZ'] = 1
        cog.n_sa[('sZ', 1)] = 3  # artificiel pour tester le guard
        cog.n_sa[('sZ', 2)] = 0
        cog.q_table[('sZ', 1)] = 0.8
        # Doit calculer sans exception
        scored = cog.te_ucb1_score_actions('sZ', (1, 2))
        # action 2 est non essayée → inf
        inf_acts = [aid for s, aid in scored if s == float('inf')]
        assert 2 in inf_acts


# ============================================================
# BLOC P0-B — PE hash complet (T41–T43)
# ============================================================

class TestP0B_PEHashComplet:
    """T41–T43 — Hash PE sur TOUS les bytes (pas de troncature [:8192])."""

    def test_T41_large_array_different_frames_different_hashes(self):
        """T41 : Deux grandes grilles ne différant qu'au-delà du 8192ème byte → hashes distincts."""
        # Grille 100×100 = 10 000 bytes → > 8192
        arr1 = make_frame_array(100, 100, fill=0)
        arr2 = make_frame_array(100, 100, fill=0)
        # Ne différer QU'à la fin du tableau (au-delà du 8192ème byte)
        pos = 8200  # dépasse la limite v3
        arr2_flat = arr2.flatten()
        arr2_flat[pos] = 255
        arr2 = arr2_flat.reshape(100, 100)

        sid1, _, _ = pe_encode_frame(arr1)
        sid2, _, _ = pe_encode_frame(arr2)
        assert sid1 != sid2, (
            "P0-B FAIL : deux frames différentes après byte 8192 donnent le même hash"
        )

    def test_T42_small_array_hash_unchanged(self):
        """T42 : Pour un petit tableau (< 8192 bytes), le hash v3.1 est identique à v3."""
        # Grille 10×10 = 100 bytes — le comportement ne change pas
        arr = make_frame_array(10, 10, fill=7)
        sid, _, _ = pe_encode_frame(arr)
        # Vérifier que c'est bien le hash de arr.tobytes() complet
        expected = hashlib.md5(arr.tobytes()).hexdigest()[:16]
        assert sid == expected

    def test_T43_none_frame_returns_null(self):
        """T43 : Frame None retourne identifiants null_*."""
        sid_full, sid_coarse, sid_colors = pe_encode_frame(None)
        assert sid_full == 'null_full'
        assert sid_coarse == 'null_coarse'
        assert sid_colors == 'null_colors'


# ============================================================
# BLOC P0-C — Reward shaping sans state_change (T44–T46)
# ============================================================

class TestP0C_RewardShaping:
    """T44–T46 — REWARD_STATE_CHANGE supprimé du reward."""

    def test_T44_state_change_no_reward(self):
        """T44 : Changement d'état sans level_up ni win → reward négatif ou nul."""
        cog = make_cognition()
        reward = cog.update('sA', 'cA', 'sB', 'cB', 'col', 1, False, win=False)
        # AVANT (v3) : reward = +0.15 (REWARD_STATE_CHANGE)
        # APRÈS (v3.1) : reward = REWARD_CYCLE (négatif) car pas de level_up/win
        assert reward == REWARD_CYCLE, (
            f"P0-C FAIL : state_change donne reward={reward}, attendu {REWARD_CYCLE}"
        )

    def test_T45_level_up_still_rewarded(self):
        """T45 : level_up donne toujours REWARD_LEVEL_UP."""
        cog = make_cognition()
        reward = cog.update('sA', 'cA', 'sB', 'cB', 'col', 1, True, win=False)
        assert reward == REWARD_LEVEL_UP

    def test_T46_win_gives_reward_win(self):
        """T46 : Victoire donne REWARD_WIN."""
        cog = make_cognition()
        reward = cog.update('sA', 'cA', 'sB', 'cB', 'col', 1, False, win=True)
        assert reward == REWARD_WIN


# ============================================================
# BLOC P0-D — Exploration UCB1 ordre stable (T47–T49)
# ============================================================

class TestP0D_ExploreStable:
    """T47–T49 — Exploration non-essayées en ordre stable (premier index)."""

    def test_T47_first_unexplored_action_chosen(self):
        """T47 : Mode explore choisit la première action non essayée (ordre STANDARD_ACTIONS)."""
        cog = make_cognition()
        # Marquer les actions 1 et 2 comme essayées
        cog.n_sa[('sA', 1)] = 2
        cog.n_s['sA'] = 2
        cog.n_sa[('sA', 2)] = 2
        # Action 3, 4, 5 non essayées → should return 3 (le premier)

        # Forcer priority='explore' via min_visits
        info = cog.si_get_state_info('sA')
        info['visits'] = 0  # déclenche 'explore' dans fi_get_priority

        # Tester te_ucb1_score_actions directement
        scored = cog.te_ucb1_score_actions('sA', tuple(STANDARD_ACTIONS))
        # Les non-essayées (3,4,5) doivent être en tête avec inf
        inf_actions = [aid for s, aid in scored if s == float('inf')]
        assert inf_actions[0] == 3, (
            f"P0-D FAIL : premier non-essayé attendu=3, obtenu={inf_actions[0]}"
        )

    def test_T48_explore_order_is_deterministic(self):
        """T48 : Deux appels successifs à te_ucb1_score_actions donnent le même ordre."""
        cog = make_cognition()
        scored_1 = cog.te_ucb1_score_actions('sNew', tuple(STANDARD_ACTIONS))
        scored_2 = cog.te_ucb1_score_actions('sNew', tuple(STANDARD_ACTIONS))
        # Même liste dans le même ordre
        assert scored_1 == scored_2, "P0-D FAIL : ordre non déterministe"

    def test_T49_all_explored_falls_to_ucb1(self):
        """T49 : Quand toutes les actions ont été essayées, on utilise UCB1 pur."""
        cog = make_cognition()
        for aid in STANDARD_ACTIONS:
            cog.n_sa[('sA', aid)] = 3
        cog.n_s['sA'] = 15  # 3 × 5 actions
        cog.q_table[('sA', 3)] = 5.0  # action 3 = meilleure Q-value

        scored = cog.te_ucb1_score_actions('sA', tuple(STANDARD_ACTIONS))
        # Aucun score infini
        assert all(s != float('inf') for s, _ in scored)
        # Action 3 (meilleure Q) doit être en tête
        assert scored[0][1] == 3


# ============================================================
# BLOC P0-E — Persistance game_patterns (T50–T51)
# ============================================================

class TestP0E_Persistance:
    """T50–T51 — game_patterns sauvegardé et rechargé correctement."""

    def test_T50_patterns_saved_on_level_up(self):
        """T50 : Après un level_up, game_patterns est sauvegardé sur disque."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name

        try:
            _mod.PATTERNS_PERSIST_PATH = path
            cog = LuCYCognition()
            # Simuler un level_up
            cog.update('sA', 'cA', 'sB', 'cB', 'col', 2, True, win=False)

            # Vérifier que le fichier existe et contient les données
            assert os.path.exists(path), "P0-E FAIL : fichier patterns non créé"
            with open(path) as fp:
                data = json.load(fp)
            assert 'game_patterns' in data
            assert '0' in data['game_patterns']  # level_id 0
        finally:
            os.unlink(path)

    def test_T51_patterns_loaded_on_init(self):
        """T51 : Une nouvelle instance charge les patterns existants depuis le disque."""
        with tempfile.NamedTemporaryFile(
            suffix='.json', delete=False, mode='w'
        ) as f:
            json.dump({
                'game_patterns': {'0': {'action': 3, 'from_sid_coarse': 'abc', 'to_sid_coarse': 'def'}},
                'version': '3.1'
            }, f)
            path = f.name

        try:
            _mod.PATTERNS_PERSIST_PATH = path
            cog = LuCYCognition()
            assert '0' in cog.game_patterns, "P0-E FAIL : patterns non chargés depuis disque"
            assert cog.game_patterns['0']['action'] == 3
        finally:
            os.unlink(path)


# ============================================================
# BLOC P0-F — RESET enregistré dans Q-table (T52–T54)
# ============================================================

class TestP0F_ResetQLearning:
    """T52–T54 — RESET (action_id=0) enregistré dans n_sa et Q-table."""

    def test_T52_reset_updates_q_table(self):
        """T52 : update() avec action_id=RESET met à jour q_table[(sid, 0)]."""
        cog = make_cognition()
        cog.update('sA', 'cA', 'sA', 'cA', 'col', RESET_ACTION_ID, False, win=False)
        assert ('sA', RESET_ACTION_ID) in cog.q_table, (
            "P0-F FAIL : RESET non enregistré dans Q-table"
        )

    def test_T53_reset_updates_n_sa(self):
        """T53 : update() avec action_id=RESET incrémente n_sa[(sid, 0)]."""
        cog = make_cognition()
        cog.update('sA', 'cA', 'sB', 'cB', 'col', RESET_ACTION_ID, False, win=False)
        assert cog.n_sa[('sA', RESET_ACTION_ID)] == 1, (
            "P0-F FAIL : n_sa[(sid, RESET)] non incrémenté"
        )
        assert cog.n_s['sA'] == 1

    def test_T54_reset_q_decreases_after_penalization(self):
        """T54 : Q(sid, RESET) est négatif après application de REWARD_RESET."""
        cog = make_cognition()
        reward = cog.update(
            'sA', 'cA', 'sA', 'cA', 'col', RESET_ACTION_ID, False, win=False
        )
        assert reward == REWARD_RESET, (
            f"P0-F FAIL : reward RESET attendu={REWARD_RESET}, obtenu={reward}"
        )
        q_reset = cog.q_table.get(('sA', RESET_ACTION_ID), 0.0)
        # Q-learning : Q(s,RESET) = 0 + α*(REWARD_RESET + γ*max_next_q - 0) < 0
        assert q_reset < 0.0, (
            f"P0-F FAIL : Q(sid, RESET)={q_reset} devrait être négatif"
        )


# ============================================================
# Version check
# ============================================================

def test_version():
    """Vérifie que la version chargée est bien 3.1."""
    assert VERSION == '3.1', f"Version attendue 3.1, obtenu {VERSION}"
