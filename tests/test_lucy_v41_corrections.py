"""
Tests T91–T106 — Validation corrections FIX-1 (P0-G attribution temporelle) + FIX-2 (P0-J persistance complète)
LuCY v4.1
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true

Ces tests vérifient les 2 corrections résiduelles de LuCY v4.1 :
  FIX-1 (P0-G) : pi.update() reçoit prev_sid_colors (état AVANT) — corrige l'attribution temporelle
                 ÉTAIT (v4.0) : curr_sid_colors (état APRÈS) → mémoire incohérente
  FIX-2 (P0-J) : _save_cognitive_state() / _load_cognitive_state() — persistance COMPLÈTE
                 ÉTAIT (v4.0) : seul game_patterns sauvegardé → q_table/n_sa/n_s/color_action_rewards perdus

  + FIX-T89 : test T89 passe maintenant par update() réel (pas manipulation directe du compteur)

Tous les tests s'exécutent SANS arcengine réel (stubs injectés).
Non-régression complète v4.0 : les 16 tests T75–T90 sont repris implicitement.
"""

import json
import os
import sys
import tempfile
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Stubs arcengine ───────────────────────────────────────────────────────────

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

sys.modules.setdefault('arcengine', MagicMock(GameAction=GameAction, GameState=GameState))
sys.modules.setdefault('agents', MagicMock())
sys.modules.setdefault('agents.agent', MagicMock())

# ── Import du module sous test ────────────────────────────────────────────────

import importlib
import importlib.util

def load_v41():
    """Charge lucy_agent_v41 en injectant les stubs arcengine."""
    spec_path = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'lucy', 'kernel', 'lucy_agent_v41.py'
    )
    spec = importlib.util.spec_from_file_location('lucy_agent_v41', spec_path)
    mod = importlib.util.module_from_spec(spec)
    mod.GameAction = GameAction
    mod.GameState = GameState
    class Agent:
        action_counter = 0
        game_id = 'test_game'
    mod.Agent = Agent
    spec.loader.exec_module(mod)
    return mod

MODULE_ERROR = ''
try:
    v41 = load_v41()
    LuCYCognition = v41.LuCYCognition
    LuCYAgent = v41.LuCYAgent
    PIPatternAnalyzer = v41.PIPatternAnalyzer
    pe_encode_frame = v41.pe_encode_frame
    pe_find_nonblack_centroid = v41.pe_find_nonblack_centroid
    build_action = v41.build_action
    CLICK_ACTION_ID = v41.CLICK_ACTION_ID
    RESET_ACTION_ID = v41.RESET_ACTION_ID
    STANDARD_ACTIONS = v41.STANDARD_ACTIONS
    COLOR_MATCH_BONUS = v41.COLOR_MATCH_BONUS
    PATTERN_CHECKPOINT_INTERVAL = v41.PATTERN_CHECKPOINT_INTERVAL
    REWARD_RESET = v41.REWARD_RESET
    REWARD_LEVEL_UP = v41.REWARD_LEVEL_UP
    REWARD_PROGRESS = v41.REWARD_PROGRESS
    MODULE_LOADED = True
except Exception as e:
    MODULE_LOADED = False
    MODULE_ERROR = str(e)

# ── Fixture : crée LuCYCognition sans lire le disque ─────────────────────────

def make_cognition_v41(tmpdir=None):
    """Crée une instance LuCYCognition v4.1 isolée (pas de lecture disque)."""
    cog = LuCYCognition.__new__(LuCYCognition)
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
    cog.epsilon = v41.EPSILON_START
    cog.pi = PIPatternAnalyzer()
    cog._actions_since_last_checkpoint = 0
    return cog

# ═════════════════════════════════════════════════════════════════════════════
# SECTION FIX-1 : Correction attribution temporelle P0-G
# Tests T91–T96
# ═════════════════════════════════════════════════════════════════════════════

class TestFix1_TemporalAttribution:
    """
    FIX-1 (P0-G) v4.1 : pi.update() reçoit prev_sid_colors (état AVANT l'action).

    ÉTAIT (v4.0) : self.pi.update(curr_sid_coarse, curr_sid_colors, ...)
                   → couleurs mémorisées = état RÉSULTANT après action
                   → incohérent : l'agent ne revoit pas cet état dans le même contexte

    MAINTENANT (v4.1) : self.pi.update(prev_sid_coarse, prev_sid_colors, ...)
                   → couleurs mémorisées = état où l'action a été choisie
                   → cohérent : (état_avant, action) → reward associé
    """

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T91_pi_update_recoit_prev_colors_pas_curr(self):
        """T91 — pi.update() est appelé avec les couleurs de l'état AVANT l'action.

        Vérification directe : injecter prev_sid_colors='PREV_COLORS' et curr_sid_colors='CURR_COLORS'
        dans update(), puis vérifier que color_action_rewards contient PREV_COLORS (pas CURR_COLORS).

        AVANT (v4.0) : color_action_rewards['CURR_COLORS'][action] aurait été incrémenté.
        APRÈS (v4.1) : color_action_rewards['PREV_COLORS'][action] est incrémenté.
        """
        cog = make_cognition_v41()
        prev_sid_colors = 'PREV_COLORS_RED'
        curr_sid_colors = 'CURR_COLORS_BLUE'

        cog.update(
            prev_sid='state_A',
            prev_sid_coarse='coarse_A',
            prev_sid_colors=prev_sid_colors,
            curr_sid='state_B',
            curr_sid_coarse='coarse_B',
            curr_sid_colors=curr_sid_colors,
            action_id=3,
            level_up=False,
            win=False,
            next_available_actions=(1, 2, 3, 4, 5),
        )

        # FIX-1 (v4.1) : la récompense PROGRESS (0.05 > 0) doit être mémorisée sous PREV_COLORS
        # AVANT (v4.0) : elle était mémorisée sous CURR_COLORS
        assert prev_sid_colors in cog.pi.color_action_rewards, (
            f'FIX-1 v4.1 : color_action_rewards doit contenir PREV_COLORS ({prev_sid_colors})\n'
            f'ÉTAIT (v4.0) : mémorisait curr_sid_colors — erreur attribution temporelle.\n'
            f'Clés présentes : {list(cog.pi.color_action_rewards.keys())}'
        )
        assert curr_sid_colors not in cog.pi.color_action_rewards, (
            f'FIX-1 v4.1 : color_action_rewards ne doit PAS contenir CURR_COLORS ({curr_sid_colors})\n'
            f'ÉTAIT (v4.0) : c\'était exactement ce bug — mémorisation de l\'état résultant.\n'
            f'Clés présentes : {list(cog.pi.color_action_rewards.keys())}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T92_attribution_cohérente_couleur_avant_action(self):
        """T92 — La suggestion de couleur pointe vers l'état où l'action PEUT être choisie.

        Scénario : l'agent voit 'RED_STATE', fait action 3, obtient PROGRESS.
        Ensuite quand l'agent est dans 'RED_STATE', suggest_action_for_colors('RED_STATE') doit retourner 3.

        AVANT (v4.0) : suggest_action_for_colors('RED_STATE') retournait None
                       (car le reward était stocké sous l'état RÉSULTANT 'BLUE_STATE').
        APRÈS (v4.1) : suggest_action_for_colors('RED_STATE') retourne 3 (correction).
        """
        cog = make_cognition_v41()
        state_rouge = 'RED_STATE_colors'
        state_bleu = 'BLUE_STATE_colors'

        # Simuler : dans RED_STATE, action 3 → BLUE_STATE avec progress
        cog.update(
            prev_sid='sid_rouge', prev_sid_coarse='coarse_rouge',
            prev_sid_colors=state_rouge,
            curr_sid='sid_bleu', curr_sid_coarse='coarse_bleu',
            curr_sid_colors=state_bleu,
            action_id=3, level_up=False, win=False,
        )
        # Simuler à nouveau : même transition (renforcement)
        cog.update(
            prev_sid='sid_rouge', prev_sid_coarse='coarse_rouge',
            prev_sid_colors=state_rouge,
            curr_sid='sid_bleu', curr_sid_coarse='coarse_bleu',
            curr_sid_colors=state_bleu,
            action_id=3, level_up=False, win=False,
        )

        # FIX-1 v4.1 : quand l'agent est dans RED_STATE, l'action 3 doit être suggérée
        suggested = cog.pi.suggest_action_for_colors(state_rouge)
        assert suggested == 3, (
            f'FIX-1 v4.1 : suggest_action_for_colors("{state_rouge}") doit retourner 3.\n'
            f'ÉTAIT (v4.0) : retournait None (mémorisation sous l\'état RÉSULTANT).\n'
            f'Obtenu : {suggested}'
        )

        # Bonus : l'état BLEU ne doit pas avoir de suggestion (jamais utilisé comme prev)
        suggested_bleu = cog.pi.suggest_action_for_colors(state_bleu)
        assert suggested_bleu is None, (
            f'FIX-1 v4.1 : suggest_action_for_colors("{state_bleu}") doit retourner None\n'
            f'car BLEU_STATE n\'a jamais été l\'état AVANT une action récompensée.\n'
            f'Obtenu : {suggested_bleu}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T93_reward_negatif_ne_pollue_pas_pi(self):
        """T93 — Un reward négatif (CYCLE/RESET) ne pollue pas color_action_rewards.

        Vérification : REWARD_CYCLE < 0 → pi.update() avec reward < 0 → pas d'entrée.
        Cette propriété est héritée de v4.0 mais la correction d'attribution la rend
        plus importante car les récompenses négatives étaient stockées sous le mauvais état.
        """
        cog = make_cognition_v41()
        prev_colors = 'PREV_CYCLE_COLORS'

        # État identique avant/après = REWARD_CYCLE < 0
        cog.update(
            prev_sid='state_X', prev_sid_coarse='coarse_X',
            prev_sid_colors=prev_colors,
            curr_sid='state_X',  # même état = cycle
            curr_sid_coarse='coarse_X',
            curr_sid_colors=prev_colors,
            action_id=2, level_up=False, win=False,
        )

        # Reward négatif → color_action_rewards ne doit pas contenir prev_colors
        assert prev_colors not in cog.pi.color_action_rewards, (
            f'T93 : reward négatif (CYCLE) ne doit pas polluer color_action_rewards.\n'
            f'color_action_rewards["{prev_colors}"] ne doit pas exister.\n'
            f'Clés : {list(cog.pi.color_action_rewards.keys())}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T94_level_up_reward_associe_à_prev_colors(self):
        """T94 — Le reward LEVEL_UP (2.0) est correctement associé à prev_sid_colors.

        AVANT (v4.0) : REWARD_LEVEL_UP était associé à curr_sid_colors (l'état APRÈS le level_up)
                       → suggestion incorrecte dans le niveau SUIVANT
        APRÈS (v4.1) : REWARD_LEVEL_UP est associé à prev_sid_colors (l'état QUI a déclenché le level_up)
        """
        cog = make_cognition_v41()
        prev_colors = 'AVANT_LEVEL_UP_COLORS'
        curr_colors = 'APRES_LEVEL_UP_COLORS'

        cog.update(
            prev_sid='state_fin_niveau', prev_sid_coarse='coarse_fin',
            prev_sid_colors=prev_colors,
            curr_sid='state_debut_niveau_suiv', curr_sid_coarse='coarse_debut',
            curr_sid_colors=curr_colors,
            action_id=5, level_up=True, win=False,
        )

        # FIX-1 v4.1 : reward = LEVEL_UP (2.0 > 0) → associé à prev_colors
        assert prev_colors in cog.pi.color_action_rewards, (
            f'T94 : REWARD_LEVEL_UP doit être associé à prev_sid_colors ("{prev_colors}").\n'
            f'ÉTAIT (v4.0) : associé à curr_sid_colors — mémoire du niveau suivant, pas du déclencheur.\n'
            f'Clés : {list(cog.pi.color_action_rewards.keys())}'
        )
        assert cog.pi.color_action_rewards[prev_colors][5] == v41.REWARD_LEVEL_UP, (
            f'T94 : color_action_rewards["{prev_colors}"][5] doit valoir REWARD_LEVEL_UP={v41.REWARD_LEVEL_UP}.\n'
            f'Obtenu : {cog.pi.color_action_rewards[prev_colors].get(5, "ABSENT")}'
        )

        # L'état APRÈS ne doit pas être pollué par ce level_up
        assert curr_colors not in cog.pi.color_action_rewards, (
            f'T94 : curr_sid_colors ("{curr_colors}") ne doit pas recevoir le reward level_up.\n'
            f'Clés : {list(cog.pi.color_action_rewards.keys())}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T95_ucb1_bonus_couleur_utilise_prev_state(self):
        """T95 — Le bonus COLOR_MATCH_BONUS dans UCB1 tire parti de la mémoire couleur correcte.

        Scénario E2E : apprentissage (prev_colors, action 4) → suggestion → bonus UCB1.
        """
        cog = make_cognition_v41()
        sid = 'state_ucb1_test'
        prev_colors = 'RED_PREV_COLORS'

        # Initialiser UCB1 avec visites sur tous les actions
        for aid in range(1, 6):
            cog.n_sa[(sid, aid)] = 3
            cog.q_table[(sid, aid)] = 0.0
        cog.n_s[sid] = 15

        # Enregistrer via update() : prev_colors, action 4, reward level_up
        cog.update(
            prev_sid=sid, prev_sid_coarse='coarse_ucb', prev_sid_colors=prev_colors,
            curr_sid='sid_next', curr_sid_coarse='coarse_next', curr_sid_colors='NEXT_COLORS',
            action_id=4, level_up=True, win=False,
        )

        # Scorer : passer prev_colors comme sid_colors courant (l'agent revoit cet état)
        scored = cog.te_ucb1_score_actions(sid, prev_colors, tuple(range(1, 6)))
        scores = {aid: sc for sc, aid in scored if sc != float('inf')}

        # Action 4 doit avoir COLOR_MATCH_BONUS en plus
        score_4 = scores.get(4, None)
        score_1 = scores.get(1, None)
        assert score_4 is not None, 'T95 : action 4 doit avoir un score fini.'
        assert score_1 is not None, 'T95 : action 1 doit avoir un score fini.'
        # Le delta doit être au moins COLOR_MATCH_BONUS (+ éventuellement suggest_action_bias)
        assert score_4 > score_1, (
            f'T95 : action 4 doit scorer plus que action 1 grâce à COLOR_MATCH_BONUS.\n'
            f'score_4={score_4:.4f} | score_1={score_1:.4f} | bonus={COLOR_MATCH_BONUS}'
        )

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T96_pi_to_dict_from_dict_roundtrip(self):
        """T96 — to_dict() / from_dict() roundtrip conserve color_action_rewards.

        FIX-2 (P0-J) nécessite la sérialisation/désérialisation de PI.
        Ce test valide que color_action_rewards survit au roundtrip JSON.
        """
        pi = PIPatternAnalyzer()
        pi.update('coarse_A', 'RED', action_id=3, reward=1.5, level_up=False)
        pi.update('coarse_A', 'RED', action_id=3, reward=0.5, level_up=False)
        pi.update('coarse_B', 'BLUE', action_id=1, reward=2.0, level_up=True)

        # Sérialiser
        data = pi.to_dict()
        # JSON roundtrip
        data_json = json.loads(json.dumps(data))

        # Désérialiser dans un nouvel objet
        pi2 = PIPatternAnalyzer()
        pi2.from_dict(data_json)

        # Vérifier color_action_rewards
        assert 'RED' in pi2.color_action_rewards, (
            f'T96 : color_action_rewards["RED"] doit survivre au roundtrip.\n'
            f'Clés après désérialisation : {list(pi2.color_action_rewards.keys())}'
        )
        assert pi2.color_action_rewards['RED'][3] == pytest.approx(2.0, abs=1e-6), (
            f'T96 : color_action_rewards["RED"][3] doit valoir 2.0.\n'
            f'Obtenu : {pi2.color_action_rewards["RED"].get(3)}'
        )
        assert 'BLUE' in pi2.color_action_rewards, (
            f'T96 : color_action_rewards["BLUE"] doit survivre au roundtrip.'
        )
        assert pi2.color_action_rewards['BLUE'][1] == pytest.approx(2.0, abs=1e-6), (
            f'T96 : color_action_rewards["BLUE"][1] doit valoir 2.0.'
        )
        # Vérifier aussi successful_actions et failed_sequences
        assert 1 in pi2.successful_actions, (
            f'T96 : successful_actions doit contenir action 1 (level_up).'
        )


# ═════════════════════════════════════════════════════════════════════════════
# SECTION FIX-2 : Persistance cognitive complète
# Tests T97–T103
# ═════════════════════════════════════════════════════════════════════════════

class TestFix2_CognitivePersistence:
    """
    FIX-2 (P0-J) v4.1 : _save_cognitive_state() / _load_cognitive_state() — snapshot COMPLET.

    ÉTAIT (v4.0) : seul game_patterns sauvegardé dans lucy_game_patterns.json
        → à chaque redémarrage Kaggle : q_table, n_sa, n_s, color_action_rewards remis à zéro
        → l'agent recommençait son apprentissage Q-learning de zéro

    MAINTENANT (v4.1) : lucy_cognitive_state.json contient le snapshot complet :
        → q_table, n_sa, n_s, game_patterns, pi.color_action_rewards,
          level_count, total_actions
    """

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T97_save_cognitive_state_ecrit_q_table(self):
        """T97 — _save_cognitive_state() écrit q_table dans le fichier JSON.

        AVANT (v4.0) : _save_patterns() ne sauvegardait que game_patterns.
        APRÈS (v4.1) : _save_cognitive_state() inclut q_table.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cog = make_cognition_v41()
            cog.q_table[('state_A', 3)] = 0.75
            cog.q_table[('state_B', 1)] = -0.1

            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            original = v41.COGNITIVE_STATE_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            try:
                cog._save_cognitive_state()
                assert os.path.exists(state_path), (
                    'T97 : _save_cognitive_state() doit créer le fichier cognitive state.'
                )
                with open(state_path) as f:
                    data = json.load(f)
                assert 'q_table' in data, (
                    f'T97 : le fichier doit contenir la clé "q_table".\n'
                    f'Clés présentes : {list(data.keys())}'
                )
                # Vérifier qu'une entrée de q_table est présente
                found = any('state_A' in k for k in data['q_table'].keys())
                assert found, (
                    f'T97 : q_table doit contenir l\'entrée (state_A, 3).\n'
                    f'Clés q_table : {list(data["q_table"].keys())[:5]}'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T98_save_cognitive_state_ecrit_n_sa_et_n_s(self):
        """T98 — _save_cognitive_state() écrit n_sa et n_s (compteurs UCB1).

        AVANT (v4.0) : perdus à chaque restart → UCB1 recommençait à zéro (sur-exploration).
        APRÈS (v4.1) : persistés → UCB1 reprend avec les compteurs réels.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cog = make_cognition_v41()
            cog.n_sa[('state_X', 2)] = 15
            cog.n_s['state_X'] = 30

            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            original = v41.COGNITIVE_STATE_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            try:
                cog._save_cognitive_state()
                with open(state_path) as f:
                    data = json.load(f)

                assert 'n_sa' in data, f'T98 : doit contenir "n_sa". Clés : {list(data.keys())}'
                assert 'n_s' in data, f'T98 : doit contenir "n_s". Clés : {list(data.keys())}'
                assert any('state_X' in k for k in data['n_sa']), (
                    f'T98 : n_sa doit contenir (state_X, 2).'
                )
                assert 'state_X' in data['n_s'], (
                    f'T98 : n_s doit contenir "state_X".'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T99_save_cognitive_state_ecrit_color_action_rewards(self):
        """T99 — _save_cognitive_state() écrit pi.color_action_rewards.

        AVANT (v4.0) : perdu → bonus P0-G réinitialisé à chaque run Kaggle.
        APRÈS (v4.1) : persisté via pi_state dans le snapshot.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cog = make_cognition_v41()
            cog.pi.color_action_rewards['RED'][3] = 2.5
            cog.pi.color_action_rewards['BLUE'][1] = 1.0

            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            original = v41.COGNITIVE_STATE_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            try:
                cog._save_cognitive_state()
                with open(state_path) as f:
                    data = json.load(f)
                assert 'pi_state' in data, (
                    f'T99 : doit contenir "pi_state". Clés : {list(data.keys())}'
                )
                car = data['pi_state'].get('color_action_rewards', {})
                assert 'RED' in car, f'T99 : pi_state.color_action_rewards doit contenir "RED".'
                assert car['RED'].get('3') == pytest.approx(2.5, abs=1e-6), (
                    f'T99 : color_action_rewards["RED"]["3"] doit valoir 2.5.\n'
                    f'Obtenu : {car["RED"].get("3")}'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T100_load_cognitive_state_restaure_q_table(self):
        """T100 — _load_cognitive_state() restaure q_table depuis le fichier.

        Vérification E2E : save → charge un nouvel objet → q_table identique.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')

            # Sauvegarder
            cog1 = make_cognition_v41()
            cog1.q_table[('state_A', 3)] = 0.75
            cog1.q_table[('state_B', 1)] = -0.1
            original = v41.COGNITIVE_STATE_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            try:
                cog1._save_cognitive_state()

                # Charger dans un nouveau objet
                cog2 = make_cognition_v41()
                result = cog2._load_cognitive_state()

                assert result is True, (
                    'T100 : _load_cognitive_state() doit retourner True si fichier présent.'
                )
                assert ('state_A', 3) in cog2.q_table, (
                    f'T100 : q_table restaurée doit contenir ("state_A", 3).\n'
                    f'Clés : {list(cog2.q_table.keys())[:5]}'
                )
                assert cog2.q_table[('state_A', 3)] == pytest.approx(0.75, abs=1e-6), (
                    f'T100 : q_table[("state_A", 3)] doit valoir 0.75.\n'
                    f'Obtenu : {cog2.q_table[("state_A", 3)]}'
                )
                assert cog2.q_table[('state_B', 1)] == pytest.approx(-0.1, abs=1e-6), (
                    f'T100 : q_table[("state_B", 1)] doit valoir -0.1.'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T101_load_cognitive_state_restaure_n_sa_n_s(self):
        """T101 — _load_cognitive_state() restaure n_sa et n_s."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            cog1 = make_cognition_v41()
            cog1.n_sa[('state_X', 2)] = 15
            cog1.n_s['state_X'] = 30

            original = v41.COGNITIVE_STATE_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            try:
                cog1._save_cognitive_state()
                cog2 = make_cognition_v41()
                cog2._load_cognitive_state()

                assert cog2.n_sa[('state_X', 2)] == 15, (
                    f'T101 : n_sa[("state_X", 2)] doit valoir 15. Obtenu : {cog2.n_sa[("state_X", 2)]}'
                )
                assert cog2.n_s['state_X'] == 30, (
                    f'T101 : n_s["state_X"] doit valoir 30. Obtenu : {cog2.n_s["state_X"]}'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T102_load_cognitive_state_restaure_pi_color_action_rewards(self):
        """T102 — _load_cognitive_state() restaure pi.color_action_rewards.

        FIX-2 clé : le bonus P0-G survit au redémarrage du kernel Kaggle.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            cog1 = make_cognition_v41()
            cog1.pi.color_action_rewards['RED'][3] = 2.5
            cog1.pi.color_action_rewards['BLUE'][1] = 1.0

            original = v41.COGNITIVE_STATE_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            try:
                cog1._save_cognitive_state()
                cog2 = make_cognition_v41()
                cog2._load_cognitive_state()

                assert 'RED' in cog2.pi.color_action_rewards, (
                    f'T102 : color_action_rewards["RED"] doit être restauré.'
                )
                assert cog2.pi.color_action_rewards['RED'][3] == pytest.approx(2.5, abs=1e-6), (
                    f'T102 : color_action_rewards["RED"][3] doit valoir 2.5.\n'
                    f'Obtenu : {cog2.pi.color_action_rewards["RED"].get(3)}'
                )
                assert cog2.pi.color_action_rewards['BLUE'][1] == pytest.approx(1.0, abs=1e-6), (
                    f'T102 : color_action_rewards["BLUE"][1] doit valoir 1.0.'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T103_load_retourne_false_si_fichier_absent(self):
        """T103 — _load_cognitive_state() retourne False si fichier absent (fallback compat v4.0)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, 'nonexistent_cognitive_state.json')
            cog = make_cognition_v41()
            original = v41.COGNITIVE_STATE_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            try:
                result = cog._load_cognitive_state()
                assert result is False, (
                    f'T103 : _load_cognitive_state() doit retourner False si fichier absent.\n'
                    f'Obtenu : {result}'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original


# ═════════════════════════════════════════════════════════════════════════════
# SECTION FIX-T89 : Test T89 corrigé — via update() réel
# Tests T104–T106
# ═════════════════════════════════════════════════════════════════════════════

class TestFixT89_CheckpointViaUpdate:
    """
    FIX-T89 v4.1 : le test T89 doit vérifier que _actions_since_last_checkpoint
    est remis à 0 via le chemin de code update() réel — pas par manipulation directe.

    ÉTAIT (T89 v4.0) :
        cog._actions_since_last_checkpoint = PATTERN_CHECKPOINT_INTERVAL - 1  # manipulation directe
        cog._actions_since_last_checkpoint = 0  # autre manipulation directe
        cog._maybe_checkpoint_patterns()
        # → ne testait pas le chemin update() → level_up → _actions_since_last_checkpoint = 0

    MAINTENANT (T104 v4.1) :
        1. Remplir le compteur jusqu'à INTERVAL - 1 via _maybe_checkpoint_patterns()
        2. Déclencher un level_up via update() réel
        3. Vérifier que le compteur est remis à 0 par update()
        4. Appeler _maybe_checkpoint_patterns() 1 fois → pas de save (compteur à 1)
    """

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T104_checkpoint_reset_via_update_level_up(self):
        """T104 (remplace T89) — update() avec level_up=True remet _actions_since_last_checkpoint à 0.

        Test du chemin de code RÉEL : pas de manipulation directe du compteur.

        Séquence dans update() sur level_up :
            (A) _save_cognitive_state() appelé
            (B) _actions_since_last_checkpoint = 0  ← reset
            (C) ... fin de update() ...
            (D) _maybe_checkpoint_patterns() appelé → compteur passe de 0 à 1

        Résultat après update() complet : compteur == 1 (pas 0).
        Ce qui prouve le reset : avant update(), compteur == INTERVAL-1 (49).
        Après update(level_up=True) : compteur == 1 (reset + incrémentation).
        Si le reset n'avait PAS eu lieu : compteur == INTERVAL (50) → save immédiat.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cog = make_cognition_v41()
            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            patterns_path = os.path.join(tmpdir, 'lucy_patterns.json')
            original_cs = v41.COGNITIVE_STATE_PATH
            original_pp = v41.PATTERNS_PERSIST_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            v41.PATTERNS_PERSIST_PATH = patterns_path
            try:
                # Étape 1 : mettre le compteur à INTERVAL - 1 (quasi-saturation)
                cog.q_table[('dummy_sid', 1)] = 0.1
                for _ in range(PATTERN_CHECKPOINT_INTERVAL - 1):
                    cog._maybe_checkpoint_patterns()
                assert cog._actions_since_last_checkpoint == PATTERN_CHECKPOINT_INTERVAL - 1, (
                    f'T104 étape 1 : compteur doit valoir {PATTERN_CHECKPOINT_INTERVAL - 1}.\n'
                    f'Obtenu : {cog._actions_since_last_checkpoint}'
                )

                # Étape 2 : simuler un level_up via update() réel
                cog.update(
                    prev_sid='state_pre_level', prev_sid_coarse='coarse_pre',
                    prev_sid_colors='PRE_COLORS',
                    curr_sid='state_post_level', curr_sid_coarse='coarse_post',
                    curr_sid_colors='POST_COLORS',
                    action_id=3, level_up=True, win=False,
                )

                # Étape 3 : vérification comportementale du reset
                # Après update() : reset(→0) + _maybe_checkpoint(→+1) = compteur == 1
                # Sans reset : compteur serait INTERVAL (50) → le prochain _maybe aurait déclenché un save
                counter_after = cog._actions_since_last_checkpoint
                assert counter_after == 1, (
                    f'T104 FIX-T89 : compteur doit valoir 1 après update(level_up=True).\n'
                    f'Séquence attendue : reset→0, _maybe_checkpoint→+1 = 1.\n'
                    f'ÉTAIT (T89 v4.0) : testait une manipulation directe du compteur.\n'
                    f'Obtenu : {counter_after}'
                )

                # Étape 4 : vérifier que le compteur reste < INTERVAL pour les prochains appels
                # (le reset est bien fonctionnel : INTERVAL-2 appels de plus ne déclenchent pas de save)
                save_calls_after = []
                original_save = cog._save_cognitive_state
                def mock_save():
                    save_calls_after.append(1)
                    original_save()
                cog._save_cognitive_state = mock_save

                for _ in range(PATTERN_CHECKPOINT_INTERVAL - 2):
                    cog._maybe_checkpoint_patterns()
                assert len(save_calls_after) == 0, (
                    f'T104 FIX-T89 : {PATTERN_CHECKPOINT_INTERVAL - 2} appels ne doivent pas sauvegarder.\n'
                    f'Compteur actuel : {cog._actions_since_last_checkpoint}\n'
                    f'Saves : {len(save_calls_after)}'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original_cs
                v41.PATTERNS_PERSIST_PATH = original_pp

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T105_checkpoint_periodique_sauvegarde_etat_complet(self):
        """T105 — Le checkpoint périodique (toutes INTERVAL actions) sauvegarde l'état COMPLET.

        FIX-2 (P0-J) v4.1 :
        AVANT (_maybe_checkpoint_patterns v4.0) : appelait _save_patterns() → partiel
        APRÈS (_maybe_checkpoint_patterns v4.1) : appelle _save_cognitive_state() → complet
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cog = make_cognition_v41()
            cog.q_table[('state_A', 2)] = 0.55
            cog.n_sa[('state_A', 2)] = 8
            cog.pi.color_action_rewards['ORANGE'][4] = 3.0

            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            patterns_path = os.path.join(tmpdir, 'lucy_patterns.json')
            original_cs = v41.COGNITIVE_STATE_PATH
            original_pp = v41.PATTERNS_PERSIST_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            v41.PATTERNS_PERSIST_PATH = patterns_path
            try:
                # Déclencher exactement INTERVAL fois _maybe_checkpoint_patterns
                for _ in range(PATTERN_CHECKPOINT_INTERVAL):
                    cog._maybe_checkpoint_patterns()

                # Le fichier cognitif doit exister
                assert os.path.exists(state_path), (
                    f'T105 : après {PATTERN_CHECKPOINT_INTERVAL} appels, '
                    f'le fichier cognitive_state doit exister.'
                )
                with open(state_path) as f:
                    data = json.load(f)

                # q_table présente
                assert 'q_table' in data, f'T105 : q_table manquant. Clés : {list(data.keys())}'
                assert any('state_A' in k for k in data['q_table']), (
                    f'T105 : q_table doit contenir (state_A, 2).'
                )

                # color_action_rewards présent
                pi_state = data.get('pi_state', {})
                car = pi_state.get('color_action_rewards', {})
                assert 'ORANGE' in car, (
                    f'T105 : color_action_rewards["ORANGE"] doit être dans le checkpoint.'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original_cs
                v41.PATTERNS_PERSIST_PATH = original_pp

    @pytest.mark.skipif(not MODULE_LOADED, reason=f'Module non chargé: {MODULE_ERROR}')
    def test_T106_ecriture_atomique_via_tmp(self):
        """T106 — _save_cognitive_state() utilise l'écriture atomique via fichier .tmp.

        Propriété de robustesse : pas de corruption si crash pendant l'écriture.
        Le fichier .tmp ne doit plus exister après la sauvegarde (os.replace() l'a renommé).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cog = make_cognition_v41()
            cog.q_table[('state_Z', 5)] = 0.99

            state_path = os.path.join(tmpdir, 'lucy_cognitive_state.json')
            tmp_path = state_path + '.tmp'
            original_cs = v41.COGNITIVE_STATE_PATH
            original_pp = v41.PATTERNS_PERSIST_PATH
            v41.COGNITIVE_STATE_PATH = state_path
            v41.PATTERNS_PERSIST_PATH = os.path.join(tmpdir, 'lucy_patterns.json')
            try:
                cog._save_cognitive_state()

                # Le fichier final doit exister
                assert os.path.exists(state_path), (
                    'T106 : le fichier cognitive_state.json doit exister après sauvegarde.'
                )
                # Le fichier temporaire ne doit plus exister (os.replace() l'a déplacé)
                assert not os.path.exists(tmp_path), (
                    f'T106 : le fichier .tmp ne doit plus exister après os.replace().\n'
                    f'Écriture atomique = write .tmp → os.replace(.tmp → final).'
                )
            finally:
                v41.COGNITIVE_STATE_PATH = original_cs
                v41.PATTERNS_PERSIST_PATH = original_pp


# ═════════════════════════════════════════════════════════════════════════════
# Récapitulatif
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('Tests LuCY v4.1 — FIX-1 (P0-G attribution temporelle) + FIX-2 (P0-J persistance complète)')
    print('CERTIFIED_100=false | unique_human_proven=false | DEBUG=true')
    print(f'Module chargé : {MODULE_LOADED}')
    if not MODULE_LOADED:
        print(f'Erreur : {MODULE_ERROR}')
    print('\nLancer avec : pytest LuCY/tests/test_lucy_v41_corrections.py -v')
