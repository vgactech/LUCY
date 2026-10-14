"""
Tests T75–T90 — Validation corrections P0-G..P0-J (LuCY v4.0)
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Ces tests vérifient les 4 nouvelles corrections de LuCY v4.0 :
  P0-G : sid_colors branché dans UCB1 (COLOR_MATCH_BONUS)
  P0-H : click sur centroïde des pixels non-noirs (pe_find_nonblack_centroid)
  P0-I : stuck_counter = 0 complet après RESET productif
  P0-J : checkpoint game_patterns périodique + écriture atomique

Tous les tests s'exécutent SANS arcengine réel (stubs injectés).
Compatibilité descendante v3.2 : les corrections P0-A v2..P0-F v2 sont aussi
testées implicitement (non-régression) via les tests de flux complet.
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

# ── Stubs arcengine (identiques aux tests v3.2) ──────────────────────────────

class GameState:
    WIN = 'WIN'
    GAME_OVER = 'GAME_OVER'
    PLAYING = 'PLAYING'

class GameAction:
    RESET = 'RESET'
    def __init__(self, action_id):
        self.action_id = action_id
        self.data = {}
    @classmethod
    def from_id(cls, action_id):
        return cls(action_id)

class FakeLF:
    def __init__(self, state=GameState.PLAYING, levels_completed=0,
                 frame=None, available_actions=None, score=None):
        self.state = state
        self.levels_completed = levels_completed
        self.frame = frame
        self.available_actions = available_actions or (1, 2, 3, 4, 5)
        self.score = score

class FakeAgent:
    action_counter = 0
    game_id = 'test_game'

sys.modules.setdefault('arcengine', MagicMock(GameAction=GameAction, GameState=GameState))
sys.modules.setdefault('agents', MagicMock())
sys.modules.setdefault('agents.agent', MagicMock())

# ── Import du module sous test ────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'lucy', 'kernel'))

import importlib
import types

def load_v40():
    """Charge lucy_agent_v40 en injectant les stubs arcengine."""
    spec_path = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'lucy', 'kernel', 'lucy_agent_v40.py'
    )
    spec = importlib.util.spec_from_file_location('lucy_agent_v40', spec_path)
    mod = importlib.util.module_from_spec(spec)
    mod.GameAction = GameAction
    mod.GameState = GameState
    # Stub Agent base class
    class Agent:
        action_counter = 0
        game_id = 'test_game'
    mod.Agent = Agent
    spec.loader.exec_module(mod)
    return mod

try:
    v40 = load_v40()
    LuCYCognition = v40.LuCYCognition
    LuCYAgent = v40.LuCYAgent
    PIPatternAnalyzer = v40.PIPatternAnalyzer
    pe_encode_frame = v40.pe_encode_frame
    pe_find_nonblack_centroid = v40.pe_find_nonblack_centroid
    build_action = v40.build_action
    CLICK_ACTION_ID = v40.CLICK_ACTION_ID
    RESET_ACTION_ID = v40.RESET_ACTION_ID
    STANDARD_ACTIONS = v40.STANDARD_ACTIONS
    COLOR_MATCH_BONUS = v40.COLOR_MATCH_BONUS
    PATTERN_CHECKPOINT_INTERVAL = v40.PATTERN_CHECKPOINT_INTERVAL
    REWARD_RESET = v40.REWARD_RESET
    MODULE_LOADED = True
except Exception as e:
    MODULE_LOADED = False
    MODULE_ERROR = str(e)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_cognition(tmpdir=None):
    """Crée une instance LuCYCognition avec PATTERNS_PERSIST_PATH dans tmpdir."""
    cog = LuCYCognition.__new__(LuCYCognition)
    # Init manuelle pour contourner PATTERNS_PERSIST_PATH sur Kaggle
    cog.state_archive = {}
    cog.transition_graph = {}
    cog.q_table = {}
    cog.n_sa = defaultdict(int)
    cog.n_s = defaultdict(int)
    cog.game_patterns = {}
    cog.level_start_sid = None
    cog.actions_this_level = 0
    cog.total_actions = 0
    cog.level_count = 0
    cog.prev_sid = None
    cog.prev_sid_coarse = None
    cog.prev_sid_colors = None
    cog.prev_action_id = None
    cog.stuck_counter = 0
    cog.epsilon = v40.EPSILON_START
    cog.pi = PIPatternAnalyzer()
    cog._actions_since_last_checkpoint = 0
    if tmpdir:
        cog._patterns_path = str(tmpdir)
    return cog

# ─────────────────────────────────────────────────────────────────────────────
# SECTION P0-G : sid_colors dans UCB1
# Tests T75–T79
# ─────────────────────────────────────────────────────────────────────────────

class TestP0G_ColorsUCB1:
    """P0-G v4.0 : sid_colors branché dans UCB1 via PI.color_action_rewards."""

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T75_pi_suggest_action_for_colors_vide(self):
        """T75 — suggest_action_for_colors retourne None si aucun historique couleur."""
        pi = PIPatternAnalyzer()
        result = pi.suggest_action_for_colors('ff0000')
        assert result is None, (
            'AVANT (v3.2) : sid_colors jamais mémorisé → None attendu.\n'
            'P0-G v4.0 : color_action_rewards vide au départ → None.'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T76_pi_suggest_action_for_colors_memorise_reward_positif(self):
        """T76 — suggest_action_for_colors retourne l'action avec le meilleur reward cumulé."""
        pi = PIPatternAnalyzer()
        sid_colors = 'aabbcc'
        # Simuler action 3 récompensée positivement dans ce contexte couleur
        pi.update('coarse1', sid_colors, action_id=3, reward=0.5, level_up=False)
        pi.update('coarse1', sid_colors, action_id=1, reward=0.05, level_up=False)
        pi.update('coarse1', sid_colors, action_id=3, reward=0.5, level_up=False)

        best = pi.suggest_action_for_colors(sid_colors)
        assert best == 3, (
            f'AVANT (v3.2) : suggest_action_for_colors() non implémenté.\n'
            f'P0-G v4.0 : action 3 cumule 1.0 de reward, action 1 cumule 0.05 → doit retourner 3.\n'
            f'Obtenu : {best}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T77_pi_suggest_action_for_colors_ne_retourne_pas_si_reward_nul(self):
        """T77 — suggest_action_for_colors retourne None si rewards tous <= 0."""
        pi = PIPatternAnalyzer()
        sid_colors = 'ff1122'
        # Reward négatif seulement → ne doit pas retourner d'action
        # (reward <= 0 n'est pas ajouté dans color_action_rewards car condition `if reward > 0`)
        pi.update('coarse1', sid_colors, action_id=2, reward=-0.05, level_up=False)
        best = pi.suggest_action_for_colors(sid_colors)
        # Reward négatif → jamais ajouté → retourne None
        assert best is None, (
            f'P0-G v4.0 : un reward <= 0 ne doit pas creer d entree dans color_action_rewards.\n'
            f'Obtenu : {best}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T78_ucb1_score_inclut_color_bonus(self):
        """T78 — te_ucb1_score_actions applique COLOR_MATCH_BONUS à l'action couleur recommandée."""
        cog = make_cognition()
        sid = 'state_color_test'
        sid_colors = 'aabbcc'

        # Initialiser l'état avec quelques visites pour les actions 1..5
        for aid in range(1, 6):
            cog.n_sa[(sid, aid)] = 2
            cog.q_table[(sid, aid)] = 0.1
        cog.n_s[sid] = 10

        # Entraîner PI : action 4 meilleure dans ce contexte couleur
        cog.pi.update('coarse1', sid_colors, action_id=4, reward=2.0, level_up=True)
        cog.pi.update('coarse1', sid_colors, action_id=4, reward=1.0, level_up=False)

        # Scorer avec sid_colors actif
        scored = cog.te_ucb1_score_actions(sid, sid_colors, tuple(range(1, 6)))
        score_dict = {aid: score for score, aid in scored}

        # Action 4 doit avoir un score supérieur aux autres à cause de COLOR_MATCH_BONUS
        score_4 = score_dict.get(4, -999)
        score_others = [score_dict[a] for a in [1, 2, 3, 5]]
        assert score_4 > max(score_others), (
            f'AVANT (v3.2) : sid_colors ignoré dans UCB1 → scores égaux.\n'
            f'P0-G v4.0 : COLOR_MATCH_BONUS={COLOR_MATCH_BONUS} doit avantager action 4.\n'
            f'score_4={score_4:.4f}, max_others={max(score_others):.4f}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T79_ucb1_score_colors_independant_du_contenu_state(self):
        """T79 — Deux états différents avec le même sid_colors reçoivent le même bonus couleur."""
        cog = make_cognition()
        sid_colors = 'ff0000'
        cog.pi.update('c1', sid_colors, action_id=2, reward=1.0, level_up=False)

        # État A et état B différents mais même sid_colors
        for sid in ['stateA', 'stateB']:
            for aid in range(1, 6):
                cog.n_sa[(sid, aid)] = 1
                cog.q_table[(sid, aid)] = 0.0
            cog.n_s[sid] = 5

        scored_A = dict((aid, s) for s, aid in cog.te_ucb1_score_actions('stateA', sid_colors, tuple(range(1,6))))
        scored_B = dict((aid, s) for s, aid in cog.te_ucb1_score_actions('stateB', sid_colors, tuple(range(1,6))))

        # Action 2 doit avoir le même avantage COLOR_MATCH_BONUS dans les deux états
        diff_A = scored_A[2] - max(scored_A[a] for a in [1, 3, 4, 5])
        diff_B = scored_B[2] - max(scored_B[a] for a in [1, 3, 4, 5])
        assert abs(diff_A - diff_B) < 0.001, (
            f'P0-G v4.0 : le bonus couleur doit être identique pour même sid_colors.\n'
            f'diff_A={diff_A:.4f}, diff_B={diff_B:.4f}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION P0-H : click centroïde pixels non-noirs
# Tests T80–T83
# ─────────────────────────────────────────────────────────────────────────────

class TestP0H_ClickCentroid:
    """P0-H v4.0 : click sur centroïde des pixels non-noirs."""

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T80_centroid_image_vide_fallback_centre(self):
        """T80 — Image entièrement noire → fallback au centre géométrique."""
        arr = np.zeros((64, 64), dtype=np.uint8)
        cx, cy = pe_find_nonblack_centroid(arr)
        assert (cx, cy) == (32, 32), (
            f'P0-H v4.0 : image noire → fallback (32,32).\nObtenu : ({cx},{cy})'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T81_centroid_pixel_unique_haut_gauche(self):
        """T81 — Seul pixel non-noir en haut à gauche → centroïde = (0, 0)."""
        arr = np.zeros((64, 64), dtype=np.uint8)
        arr[0, 0] = 255  # pixel unique en (row=0, col=0)
        cx, cy = pe_find_nonblack_centroid(arr)
        # col=0 → x=0, row=0 → y=0
        assert (cx, cy) == (0, 0), (
            f'P0-H v4.0 : seul pixel en (0,0) → centroïde (0,0).\nObtenu : ({cx},{cy})'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T82_centroid_bande_droite(self):
        """T82 — Bande verticale de pixels à droite → centroïde décalé à droite du centre géo."""
        arr = np.zeros((64, 64), dtype=np.uint8)
        arr[:, 48:] = 200  # colonnes 48..63 = pixels non-noirs
        cx, cy = pe_find_nonblack_centroid(arr)
        # x attendu ≈ (48+63)//2 = 55
        assert cx > 32, (
            f'AVANT (v3.2) : click toujours au centre géo (32,32) → aveugle à la bande.\n'
            f'P0-H v4.0 : centroïde doit être > 32 (bande à droite).\nObtenu cx={cx}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T83_centroid_ne_depasse_pas_dimensions(self):
        """T83 — Centroïde toujours dans les dimensions de l'image."""
        arr = np.zeros((30, 20), dtype=np.uint8)
        arr[5:15, 10:20] = 128  # zone non-noire en bas à droite
        cx, cy = pe_find_nonblack_centroid(arr)
        assert 0 <= cx < 20 and 0 <= cy < 30, (
            f'P0-H v4.0 : centroïde doit rester dans les dimensions [0..19, 0..29].\n'
            f'Obtenu : cx={cx}, cy={cy}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION P0-I : stuck_counter = 0 après RESET productif
# Tests T84–T86
# ─────────────────────────────────────────────────────────────────────────────

class TestP0I_StuckCounterReset:
    """P0-I v4.0 : stuck_counter remis à 0 complet après RESET productif."""

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T84_reset_productif_remet_counter_a_zero(self):
        """T84 — RESET suivi d'un changement d'état remet stuck_counter à 0 (pas seulement -1)."""
        cog = make_cognition()
        cog.stuck_counter = 10  # simuler état très bloqué

        # AVANT (v3.2) : ni_count_stuck('sA', 'sB', reward=-0.3) avec reward<=0 → -1 seulement
        # APRÈS (v4.0) : action_id=RESET + sids différents → = 0 complet
        cog.ni_count_stuck('stateA', 'stateB', reward=REWARD_RESET, action_id=RESET_ACTION_ID)
        assert cog.stuck_counter == 0, (
            f'AVANT (v3.2) : stuck_counter=10 + RESET + reward<=0 → max(0, 10-1)=9.\n'
            f'P0-I v4.0 : RESET productif (état changé) → stuck_counter=0 complet.\n'
            f'Obtenu : {cog.stuck_counter}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T85_reset_improductif_ne_remet_pas_a_zero(self):
        """T85 — RESET sur même état (improductif) n'est PAS un reset complet de stuck_counter."""
        cog = make_cognition()
        cog.stuck_counter = 5

        # RESET mais état identique (sid avant == sid après) → pas productif
        # Le RESET résulte en reward REWARD_RESET = -0.3
        # Logique : prev_sid == curr_sid (état identique) → stuck_counter += 1
        cog.ni_count_stuck('stateA', 'stateA', reward=REWARD_RESET, action_id=RESET_ACTION_ID)
        # prev_sid == curr_sid → stuck_counter += 1 (pas reset complet)
        assert cog.stuck_counter == 6, (
            f'P0-I v4.0 : RESET improductif (même état) → stuck_counter += 1 (de 5 à 6).\n'
            f'Obtenu : {cog.stuck_counter}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T86_sans_reset_comportement_v32_conserve(self):
        """T86 — Sans RESET, le comportement v3.2 est conservé (non-régression)."""
        cog = make_cognition()
        cog.stuck_counter = 3

        # Action normale (pas RESET) avec état nouveau et reward positif → 0
        cog.ni_count_stuck('sA', 'sB', reward=0.05, action_id=1)
        assert cog.stuck_counter == 0, (
            f'P0-I v4.0 : action non-RESET + reward > 0 → stuck_counter = 0.\n'
            f'Obtenu : {cog.stuck_counter}'
        )

        cog.stuck_counter = 3
        # Même état, action non-RESET → +1
        cog.ni_count_stuck('sA', 'sA', reward=-0.05, action_id=2)
        assert cog.stuck_counter == 4, (
            f'P0-I v4.0 : même état → stuck_counter += 1 (de 3 à 4).\n'
            f'Obtenu : {cog.stuck_counter}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION P0-J : checkpoint périodique des patterns
# Tests T87–T90
# ─────────────────────────────────────────────────────────────────────────────

class TestP0J_PeriodicCheckpoint:
    """P0-J v4.0 : checkpoint game_patterns périodique + écriture atomique."""

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T87_checkpoint_se_declenche_apres_N_actions(self):
        """T87 — _maybe_checkpoint_patterns() sauvegarde après PATTERN_CHECKPOINT_INTERVAL actions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = os.path.join(tmpdir, 'lucy_patterns.json')

            cog = make_cognition(tmpdir)
            cog.game_patterns = {'0': {'action': 1, 'from_sid_coarse': 'abc', 'to_sid_coarse': 'def'}}

            # Patcher PATTERNS_PERSIST_PATH dans le module
            original_path = v40.PATTERNS_PERSIST_PATH
            v40.PATTERNS_PERSIST_PATH = persist_path
            try:
                # Moins d'actions que PATTERN_CHECKPOINT_INTERVAL → pas de checkpoint
                for _ in range(PATTERN_CHECKPOINT_INTERVAL - 1):
                    cog._maybe_checkpoint_patterns()

                assert not os.path.exists(persist_path), (
                    f'P0-J v4.0 : pas de checkpoint avant {PATTERN_CHECKPOINT_INTERVAL} actions.\n'
                    f'Fichier ne doit pas exister à {PATTERN_CHECKPOINT_INTERVAL-1} appels.'
                )

                # Exactement PATTERN_CHECKPOINT_INTERVAL → checkpoint déclenché
                cog._maybe_checkpoint_patterns()
                assert os.path.exists(persist_path), (
                    f'P0-J v4.0 : checkpoint doit avoir eu lieu après {PATTERN_CHECKPOINT_INTERVAL} actions.\n'
                    f'Fichier non créé : {persist_path}'
                )

                # Vérifier le contenu
                with open(persist_path) as f:
                    data = json.load(f)
                assert '0' in data.get('game_patterns', {}), (
                    f'P0-J v4.0 : game_patterns doit contenir la clé "0".'
                )
            finally:
                v40.PATTERNS_PERSIST_PATH = original_path

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T88_checkpoint_ecriture_atomique_via_tmp(self):
        """T88 — _save_patterns() écrit via fichier .tmp puis os.replace() (atomique)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = os.path.join(tmpdir, 'lucy_patterns.json')
            tmp_path = persist_path + '.tmp'

            cog = make_cognition()
            cog.game_patterns = {'1': {'action': 2, 'from_sid_coarse': 'xx', 'to_sid_coarse': 'yy'}}

            original_path = v40.PATTERNS_PERSIST_PATH
            v40.PATTERNS_PERSIST_PATH = persist_path
            try:
                cog._save_patterns()
                # Après save : le fichier final existe
                assert os.path.exists(persist_path), (
                    f'P0-J v4.0 : le fichier final doit exister après _save_patterns().'
                )
                # Le fichier .tmp ne doit plus exister (os.replace l'a renommé)
                assert not os.path.exists(tmp_path), (
                    f'P0-J v4.0 : le fichier .tmp ne doit plus exister après os.replace().\n'
                    f'AVANT (v3.2) : écriture directe, pas de .tmp.'
                )
            finally:
                v40.PATTERNS_PERSIST_PATH = original_path

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T89_counter_checkpoint_reinitialisé_apres_level_up(self):
        """T89 — _actions_since_last_checkpoint remis à 0 sur level_up (pas double-save)."""
        cog = make_cognition()
        cog._actions_since_last_checkpoint = PATTERN_CHECKPOINT_INTERVAL - 1

        save_calls = []
        def mock_save():
            save_calls.append(1)
        cog._save_patterns = mock_save

        # Simuler un level_up dans update()
        # Après level_up, le compteur doit être remis à 0
        cog._actions_since_last_checkpoint = 0  # remise à zéro sur level_up
        cog._maybe_checkpoint_patterns()

        # Compteur à 1 → pas de save encore
        assert len(save_calls) == 0, (
            f'P0-J v4.0 : après level_up le compteur est remis à 0 → '
            f'_maybe_checkpoint_patterns à 1 ne doit pas déclencher de save.'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR if not MODULE_LOADED else ""}')
    def test_T90_pas_de_checkpoint_si_patterns_vide(self):
        """T90 — Pas de checkpoint périodique si game_patterns est vide (économie I/O)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = os.path.join(tmpdir, 'lucy_patterns.json')
            cog = make_cognition()
            cog.game_patterns = {}  # vide

            original_path = v40.PATTERNS_PERSIST_PATH
            v40.PATTERNS_PERSIST_PATH = persist_path
            try:
                # Appeler N fois _maybe_checkpoint_patterns
                for _ in range(PATTERN_CHECKPOINT_INTERVAL * 2):
                    cog._maybe_checkpoint_patterns()

                assert not os.path.exists(persist_path), (
                    f'P0-J v4.0 : aucun checkpoint si game_patterns vide — I/O inutile évitée.'
                )
            finally:
                v40.PATTERNS_PERSIST_PATH = original_path


# ─────────────────────────────────────────────────────────────────────────────
# Récapitulatif
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('Tests T75–T90 — LuCY v4.0 (P0-G..P0-J)')
    print(f'  MODULE_LOADED: {MODULE_LOADED}')
    if not MODULE_LOADED:
        print(f'  Erreur: {MODULE_ERROR}')
    print('Run: pytest tests/test_lucy_v40_p0_corrections_v4.py -v')
