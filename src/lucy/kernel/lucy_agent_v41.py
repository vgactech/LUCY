# LuCY Cognitive Agent v4.1 for ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
# Phase 6.1 : Corrections résiduelles P0-G attribution temporelle + P0-J persistance complète
#
# Corrections v4.1 vs v4.0 :
# FIX-1 (P0-G) : pi.update() reçoit MAINTENANT prev_sid_coarse/prev_sid_colors (état AVANT l'action)
#                ÉTAIT (v4.0) : curr_sid_coarse/curr_sid_colors (état APRÈS — erreur attribution temporelle)
#                LIGNE CORRIGÉE : update() ligne ~764 → pi.update(prev_sid_coarse, prev_sid_colors, ...)
#
# FIX-2 (P0-J) : _save_cognitive_state() / _load_cognitive_state() — persistance COMPLÈTE
#                ÉTAIT (v4.0) : seul game_patterns sauvegardé → q_table, n_sa, n_s,
#                               color_action_rewards perdus à chaque redémarrage
#                MAINTENANT   : snapshot complet {q_table, n_sa, n_s, game_patterns,
#                               color_action_rewards, level_count, total_actions}
#                FICHIER      : /kaggle/working/lucy_cognitive_state.json (nouveau)
#                               /kaggle/working/lucy_game_patterns.json (conservé pour compat)
#
# FIX-3 (T89)  : test T89 désormais déclenche update() réel pour vérifier que
#                _actions_since_last_checkpoint est bien remis à 0 par le chemin code
#                (au lieu de le manipuler directement avant appel)
#
# Héritage v4.0 (conservé sans modification) :
# P0-G intégration : sid_colors dans UCB1 via PI.color_action_rewards (COLOR_MATCH_BONUS)
# P0-H : click sur centroïde des pixels non-noirs (pe_find_nonblack_centroid)
# P0-I : stuck_counter = 0 complet après RESET productif
# P0-J : checkpoint périodique + écriture atomique (maintenant persistance complète)
#
# Héritage v3.2 (conservé sans modification) :
# P0-A v2 : n_sa_sum inclut RESET
# P0-B v2 : hash inclut dimensions de la grille
# P0-C v2 : 3 niveaux de reward (CYCLE / PROGRESS / LEVEL_UP)
# P0-D v2 : tri des non-essayées par action_id canonique
# P0-E v2 : arbitrate() consulte game_patterns pour biaiser si sid_coarse connu
# P0-F v2 : max_next_q calculé sur available_actions de l'état suivant

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from agents.agent import Agent
from arcengine import GameAction, GameState


# ===== LuCY v4.1 Cognitive Constants =====
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False
DEBUG = True
VERSION = '4.1'

MAX_ACTIONS = 3000           # budget d'actions par jeu
MAX_ACTIONS_PER_LEVEL = 500  # budget par niveau
MIN_STATE_VISITS = 2         # seuil exploration → exploitation

# UCB1 paramètre d'exploration
UCB1_C = 1.414  # sqrt(2) — paramètre standard

# Q-learning
ALPHA = 0.2   # learning rate
GAMMA = 0.9   # discount factor

# Epsilon-greedy adaptatif
EPSILON_START = 0.4
EPSILON_MIN = 0.05
EPSILON_DECAY = 0.995  # par action

# Récompenses v3.2 (inchangées)
REWARD_LEVEL_UP = 2.0        # niveau complété
REWARD_WIN = 10.0            # victoire finale
REWARD_PROGRESS = 0.05       # état nouveau sans level_up (signal progrès réel)
REWARD_CYCLE = -0.05         # état identique = vraie boucle improductive
REWARD_RESET = -0.3          # pénalité reset

# Actions disponibles dans arcengine
STANDARD_ACTIONS = list(range(1, 6))
RESET_ACTION_ID = 0
CLICK_ACTION_ID = 6

# P0-E v2 : fichier de persistance des patterns inter-niveaux (CONSERVÉ pour compat)
PATTERNS_PERSIST_PATH = '/kaggle/working/lucy_game_patterns.json'

# FIX-2 (P0-J) : nouveau fichier de persistance de l'état cognitif COMPLET
# AVANT (v4.0) : seul lucy_game_patterns.json sauvegardé
# APRÈS (v4.1) : lucy_cognitive_state.json contient le snapshot complet
COGNITIVE_STATE_PATH = '/kaggle/working/lucy_cognitive_state.json'

# Bonus de biais quand un pattern connu couvre le sid_coarse courant
PATTERN_BIAS_BONUS = 0.35

# P0-G : poids du bonus couleur dans le score UCB1
COLOR_MATCH_BONUS = 0.15

# P0-J : checkpoint des patterns tous les N actions
PATTERN_CHECKPOINT_INTERVAL = 50


# =========================================================
# PE — Perception Étendue v4.1 (inchangée vs v4.0)
# =========================================================

def pe_encode_frame(frame_raw) -> Tuple[str, str, str]:
    """Encode le frame en identifiants multi-résolution.

    v3.2 — P0-B v2 : hash calculé sur shape_prefix + arr.tobytes().
    v4.0 / v4.1 — inchangé.

    Returns:
        (sid_full, sid_coarse, sid_colors)
    """
    if frame_raw is None:
        return 'null_full', 'null_coarse', 'null_colors'

    if isinstance(frame_raw, list):
        try:
            arr = np.array(frame_raw[0], dtype=np.uint8) if frame_raw else None
        except Exception:
            arr = None
    elif isinstance(frame_raw, np.ndarray):
        arr = frame_raw.astype(np.uint8)
    else:
        arr = None

    if arr is None:
        raw = str(frame_raw).encode()
        h = hashlib.md5(raw).hexdigest()[:16]
        return h, h[:8], h[:4]

    # sid_full : P0-B v2
    if arr.ndim >= 2:
        rows, cols = arr.shape[0], arr.shape[1]
    else:
        rows, cols = arr.shape[0], 1
    shape_prefix = (
        (rows & 0xFFFF).to_bytes(2, 'little') +
        (cols & 0xFFFF).to_bytes(2, 'little')
    )
    sid_full = hashlib.md5(shape_prefix + arr.tobytes()).hexdigest()[:16]

    # sid_coarse : réduction 4×4
    try:
        h_blocks = max(1, arr.shape[0] // 4) if arr.ndim >= 2 else 1
        w_blocks = max(1, arr.shape[1] // 4) if arr.ndim >= 2 else 1
        coarse = arr[:h_blocks*4, :w_blocks*4].reshape(
            h_blocks, 4, w_blocks, 4, -1
        ).mean(axis=(1, 3)).astype(np.uint8)
        coarse_prefix = (
            (h_blocks & 0xFF).to_bytes(1, 'little') +
            (w_blocks & 0xFF).to_bytes(1, 'little')
        )
        sid_coarse = hashlib.md5(coarse_prefix + coarse.tobytes()).hexdigest()[:8]
    except Exception:
        sid_coarse = sid_full[:8]

    # sid_colors : top-3 couleurs dominantes (buckets de 16)
    try:
        pixels = arr.reshape(-1, arr.shape[-1] if arr.ndim == 3 else 1)
        buckets = (pixels // 16).tobytes()[:512]
        cnt = Counter(buckets)
        top3 = ''.join(f'{k:02x}' for k, _ in cnt.most_common(3))
        sid_colors = top3 if top3 else 'nocolor'
    except Exception:
        sid_colors = 'nocolor'

    return sid_full, sid_coarse, sid_colors


def pe_find_nonblack_centroid(arr: Optional[np.ndarray]) -> Tuple[int, int]:
    """Calcule le centroïde des pixels non-noirs dans le frame.

    P0-H v4.0 (inchangé en v4.1) : click stratégique sur le centroïde des pixels saillants.

    Returns:
        (x, y) en coordonnées pixel (x=colonne, y=ligne)
    """
    BLACK_THRESHOLD = 16

    if arr is None:
        return 32, 32

    h = arr.shape[0] if arr.ndim >= 1 else 64
    w = arr.shape[1] if arr.ndim >= 2 else 64
    fallback_x, fallback_y = w // 2, h // 2

    try:
        if arr.ndim == 3:
            mask = np.any(arr > BLACK_THRESHOLD, axis=2)
        elif arr.ndim == 2:
            mask = arr > BLACK_THRESHOLD
        else:
            return fallback_x, fallback_y

        ys, xs = np.where(mask)
        if len(ys) == 0:
            return fallback_x, fallback_y

        centroid_x = int(np.mean(xs))
        centroid_y = int(np.mean(ys))
        return centroid_x, centroid_y

    except Exception:
        return fallback_x, fallback_y


# =========================================================
# PI — Pattern Interne v4.1
# =========================================================

class PIPatternAnalyzer:
    """Analyse les patterns internes pour guider l'exploration."""

    def __init__(self):
        self.coarse_history: List[str] = []
        self.color_history: List[str] = []
        self.successful_actions: List[int] = []
        self.failed_sequences: Set[Tuple] = set()

        # P0-G v4.0 : historique (sid_colors, action, reward) pour le bonus couleur
        self.color_action_rewards: Dict[str, Dict[int, float]] = defaultdict(
            lambda: defaultdict(float)
        )

    def update(
        self, sid_coarse: str, sid_colors: str,
        action_id: int, reward: float, level_up: bool
    ) -> None:
        """Met à jour l'état interne du pattern analyzer.

        FIX-1 (P0-G) v4.1 — CORRECTION ATTRIBUTION TEMPORELLE :
        Ce paramètre sid_coarse/sid_colors doit représenter l'état AVANT l'action.

        ÉTAIT (v4.0) : pi.update(curr_sid_coarse, curr_sid_colors, ...)
            → mémorisait "quelle action fonctionne dans l'état RÉSULTANT"
            → incohérent : l'agent n'est plus dans cet état au moment de l'apprentissage

        MAINTENANT (v4.1) : pi.update(prev_sid_coarse, prev_sid_colors, ...)
            → mémorise "quelle action fonctionne quand on VOIT cet état"
            → cohérent avec le principe RL : récompense associée à (état_avant, action)

        La correction est dans LuCYCognition.update() qui passe prev_sid_coarse
        et prev_sid_colors au lieu de curr_sid_coarse et curr_sid_colors.
        """
        self.coarse_history.append(sid_coarse)
        self.color_history.append(sid_colors)

        if level_up:
            self.successful_actions.append(action_id)

        # P0-G v4.0 (conservé) : mémoriser le reward par (sid_colors, action)
        if reward > 0:
            self.color_action_rewards[sid_colors][action_id] += reward

        if len(self.coarse_history) >= 4:
            last4 = tuple(self.coarse_history[-4:])
            if last4[:2] == last4[2:]:
                self.failed_sequences.add(last4[:2])

        if len(self.coarse_history) > 200:
            self.coarse_history = self.coarse_history[-100:]
            self.color_history = self.color_history[-100:]

    def detect_visual_cycle(self, sid_coarse: str) -> bool:
        if len(self.coarse_history) < 4:
            return False
        recent_pair = tuple(self.coarse_history[-2:])
        return recent_pair in self.failed_sequences

    def suggest_action_bias(self) -> Optional[int]:
        if not self.successful_actions:
            return None
        cnt = Counter(self.successful_actions)
        return cnt.most_common(1)[0][0]

    def get_epsilon(self, base_epsilon: float, total_actions: int) -> float:
        success_factor = min(1.0, len(self.successful_actions) * 0.1)
        decayed = max(EPSILON_MIN, base_epsilon * (EPSILON_DECAY ** total_actions))
        return decayed * (1.0 - success_factor * 0.5)

    def suggest_action_for_colors(self, sid_colors: str) -> Optional[int]:
        """Retourne l'action la plus récompensée dans ce contexte de couleurs.

        P0-G v4.0 (inchangé en v4.1) — maintenant alimenté avec les données correctes
        grâce à FIX-1 qui corrige l'attribution temporelle en amont.
        """
        rewards = self.color_action_rewards.get(sid_colors)
        if not rewards:
            return None
        best_action = max(rewards, key=lambda a: rewards[a])
        return best_action if rewards[best_action] > 0 else None

    def to_dict(self) -> Dict:
        """Sérialise l'état PI pour la persistance.

        FIX-2 (P0-J) v4.1 : NOUVEAU — permet de sauvegarder l'état PI complet.
        ÉTAIT (v4.0) : color_action_rewards non sauvegardé → réapprentissage couleur à zéro.
        MAINTENANT   : sérialisé dans _save_cognitive_state().
        """
        return {
            'coarse_history': self.coarse_history[-100:],
            'color_history': self.color_history[-100:],
            'successful_actions': self.successful_actions[-500:],
            # failed_sequences : set de tuples → liste de listes pour JSON
            'failed_sequences': [list(seq) for seq in self.failed_sequences],
            # color_action_rewards : defaultdict imbriqué → dict JSON sérialisable
            'color_action_rewards': {
                colors: dict(actions)
                for colors, actions in self.color_action_rewards.items()
            },
        }

    def from_dict(self, data: Dict) -> None:
        """Restaure l'état PI depuis un snapshot.

        FIX-2 (P0-J) v4.1 : NOUVEAU.
        """
        self.coarse_history = data.get('coarse_history', [])
        self.color_history = data.get('color_history', [])
        self.successful_actions = data.get('successful_actions', [])
        self.failed_sequences = {
            tuple(seq) for seq in data.get('failed_sequences', [])
        }
        raw_car = data.get('color_action_rewards', {})
        self.color_action_rewards = defaultdict(lambda: defaultdict(float))
        for colors, actions in raw_car.items():
            for action_str, reward in actions.items():
                self.color_action_rewards[colors][int(action_str)] += reward


# =========================================================
# Utilitaires
# =========================================================

def build_action(action_id: int, x: int = 32, y: int = 32) -> GameAction:
    """Construit un GameAction robustement."""
    try:
        if action_id == RESET_ACTION_ID and hasattr(GameAction, 'RESET'):
            return GameAction.RESET
        elif hasattr(GameAction, 'from_id'):
            action = GameAction.from_id(action_id)
        else:
            action = GameAction(action_id)
    except Exception:
        action = GameAction.RESET

    if action_id == CLICK_ACTION_ID:
        for method in ('set_data', 'set_action_data'):
            if hasattr(action, method):
                try:
                    getattr(action, method)({'x': x, 'y': y})
                    break
                except Exception:
                    pass
        try:
            action.data = {'x': x, 'y': y}
        except Exception:
            pass
    return action


# =========================================================
# LuCYCognition v4.1
# =========================================================

class LuCYCognition:
    """
    Noyau cognitif LuCY v4.1 — corrections résiduelles P0-G + P0-J.

    FIX-1 (P0-G) : pi.update() reçoit prev_sid_coarse/prev_sid_colors (état AVANT l'action)
        ÉTAIT (v4.0) : curr_sid_coarse/curr_sid_colors → erreur attribution temporelle
        MAINTENANT   : prev_sid_coarse/prev_sid_colors → apprentissage cohérent (S,A)→R

    FIX-2 (P0-J) : _save_cognitive_state() / _load_cognitive_state() — snapshot COMPLET
        ÉTAIT (v4.0) : seul game_patterns persisté → q_table/n_sa/n_s/color_action_rewards perdus
        MAINTENANT   : snapshot complet {q_table, n_sa, n_s, game_patterns,
                       pi.color_action_rewards, level_count, total_actions}

    Opérateurs actifs (inchangés) :
    SE/SI/NE/NI/TE/TI/FE/FI/PE/PI
    """

    def __init__(self):
        # SI : mémoire d'états
        self.state_archive: Dict[str, Dict] = {}

        # Graphe de transitions
        self.transition_graph: Dict[Tuple, str] = {}

        # Q-table — FIX-2 : maintenant persisté
        self.q_table: Dict[Tuple, float] = {}

        # Compteurs UCB1 — FIX-2 : maintenant persistés
        self.n_sa: Dict[Tuple, int] = defaultdict(int)
        self.n_s: Dict[str, int] = defaultdict(int)

        # game_patterns — conservé + persisté comme avant
        self.game_patterns: Dict[str, Dict] = {}

        # État courant
        self.level_start_sid: Optional[str] = None
        self.actions_this_level = 0
        self.total_actions = 0
        self.level_count = 0
        self.prev_sid: Optional[str] = None
        self.prev_sid_coarse: Optional[str] = None
        self.prev_sid_colors: Optional[str] = None
        self.prev_action_id: Optional[int] = None
        self.stuck_counter = 0
        self.epsilon = EPSILON_START

        # PE + PI
        self.pi = PIPatternAnalyzer()

        # Compteur checkpoint périodique
        self._actions_since_last_checkpoint = 0

        # FIX-2 : tenter de charger l'état cognitif COMPLET en priorité
        # puis fallback sur l'ancien game_patterns seul (compat v4.0)
        loaded_full = self._load_cognitive_state()
        if not loaded_full:
            self._load_patterns()  # compat v4.0

    # ----------------------------------------------------------------
    # FIX-2 (P0-J) : persistance COMPLÈTE de l'état cognitif
    # ----------------------------------------------------------------

    def _save_cognitive_state(self) -> None:
        """Sauvegarde l'état cognitif COMPLET sur le disque (écriture atomique).

        FIX-2 (P0-J) v4.1 :
        ÉTAIT (v4.0) : seul game_patterns sauvegardé dans lucy_game_patterns.json
            → q_table, n_sa, n_s, color_action_rewards perdus à chaque redémarrage
            → l'agent recommençait son apprentissage Q-learning à zéro entre les runs

        MAINTENANT (v4.1) : snapshot COMPLET dans lucy_cognitive_state.json
            → q_table : toutes les Q-values apprises
            → n_sa    : compteurs UCB1 (state, action) — calibre l'exploration
            → n_s     : compteurs par état — détermine MIN_STATE_VISITS
            → game_patterns : patterns inter-niveaux (inchangé)
            → pi.color_action_rewards : association (couleur→action) du bonus P0-G
            → level_count, total_actions : reprise du budget correct

        Écriture atomique via fichier temporaire (inchangée — P0-J v4.0).
        """
        try:
            # Sérialiser q_table : clés = tuples (str, int) → str JSON
            q_table_serializable = {
                f'{sid}|{aid}': val
                for (sid, aid), val in self.q_table.items()
            }
            # n_sa : même sérialisation
            n_sa_serializable = {
                f'{sid}|{aid}': cnt
                for (sid, aid), cnt in self.n_sa.items()
            }
            # n_s : dict str → int (déjà JSON-compatible via defaultdict)
            n_s_serializable = dict(self.n_s)

            data = {
                'version': VERSION,
                'timestamp': time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()),
                # FIX-2 : nouvelles clés
                'q_table': q_table_serializable,
                'n_sa': n_sa_serializable,
                'n_s': n_s_serializable,
                # Inchangé depuis v4.0
                'game_patterns': self.game_patterns,
                # FIX-2 : état PI sérialisé (color_action_rewards inclus)
                'pi_state': self.pi.to_dict(),
                # Compteurs de reprise
                'level_count': self.level_count,
                'total_actions': self.total_actions,
            }
            tmp_path = COGNITIVE_STATE_PATH + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(data, f)
            os.replace(tmp_path, COGNITIVE_STATE_PATH)

            # FIX-2 : aussi sauvegarder game_patterns seul pour compat v4.0
            self._save_patterns()

            if DEBUG:
                print(
                    f'[LuCY v{VERSION}] _save_cognitive_state: '
                    f'q_table={len(q_table_serializable)} '
                    f'n_sa={len(n_sa_serializable)} '
                    f'n_s={len(n_s_serializable)} '
                    f'patterns={len(self.game_patterns)} '
                    f'color_rewards={sum(len(v) for v in self.pi.color_action_rewards.values())}'
                )
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] _save_cognitive_state ERREUR: {e}')

    def _load_cognitive_state(self) -> bool:
        """Charge l'état cognitif COMPLET depuis le disque.

        FIX-2 (P0-J) v4.1 : NOUVEAU.
        Retourne True si le chargement a réussi, False sinon (fallback v4.0).
        """
        try:
            if not os.path.exists(COGNITIVE_STATE_PATH):
                return False
            with open(COGNITIVE_STATE_PATH, 'r') as f:
                data = json.load(f)

            # Restaurer q_table
            q_raw = data.get('q_table', {})
            self.q_table = {}
            for key_str, val in q_raw.items():
                parts = key_str.split('|', 1)
                if len(parts) == 2:
                    sid, aid_str = parts
                    try:
                        self.q_table[(sid, int(aid_str))] = float(val)
                    except ValueError:
                        pass

            # Restaurer n_sa
            n_sa_raw = data.get('n_sa', {})
            self.n_sa = defaultdict(int)
            for key_str, cnt in n_sa_raw.items():
                parts = key_str.split('|', 1)
                if len(parts) == 2:
                    sid, aid_str = parts
                    try:
                        self.n_sa[(sid, int(aid_str))] = int(cnt)
                    except ValueError:
                        pass

            # Restaurer n_s
            self.n_s = defaultdict(int, {k: int(v) for k, v in data.get('n_s', {}).items()})

            # Restaurer game_patterns
            self.game_patterns = data.get('game_patterns', {})

            # Restaurer état PI
            pi_data = data.get('pi_state', {})
            if pi_data:
                self.pi.from_dict(pi_data)

            # Restaurer compteurs de reprise
            self.level_count = int(data.get('level_count', 0))
            self.total_actions = int(data.get('total_actions', 0))

            if DEBUG:
                print(
                    f'[LuCY v{VERSION}] _load_cognitive_state: '
                    f'q_table={len(self.q_table)} '
                    f'n_sa={len(self.n_sa)} '
                    f'patterns={len(self.game_patterns)}'
                )
            return True

        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] _load_cognitive_state ERREUR: {e}')
            return False

    # ----------------------------------------------------------------
    # P0-E v2 + P0-J v4.0 : persistance game_patterns (compat)
    # ----------------------------------------------------------------

    def _load_patterns(self) -> None:
        """Charge game_patterns (compat v4.0 — utilisé si cognitive_state absent)."""
        try:
            if os.path.exists(PATTERNS_PERSIST_PATH):
                with open(PATTERNS_PERSIST_PATH, 'r') as f:
                    data = json.load(f)
                self.game_patterns = data.get('game_patterns', {})
                if DEBUG:
                    print(f'[LuCY v{VERSION}] Loaded {len(self.game_patterns)} game patterns (compat v4.0)')
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] Could not load patterns: {e}')
            self.game_patterns = {}

    def _save_patterns(self) -> None:
        """Sauvegarde game_patterns seul (compat v4.0 — appelé par _save_cognitive_state)."""
        try:
            data = {'game_patterns': self.game_patterns, 'version': VERSION}
            tmp_path = PATTERNS_PERSIST_PATH + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(data, f)
            os.replace(tmp_path, PATTERNS_PERSIST_PATH)
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] Could not save patterns: {e}')

    def _maybe_checkpoint_patterns(self) -> None:
        """Checkpoint périodique (P0-J v4.0 inchangé).

        FIX-2 (v4.1) : appelle maintenant _save_cognitive_state() au lieu de _save_patterns()
        pour persister l'état COMPLET à chaque checkpoint périodique.

        AVANT (v4.0) : self._save_patterns() → seul game_patterns sauvegardé
        APRÈS (v4.1) : self._save_cognitive_state() → snapshot complet
        """
        if not self.game_patterns and not self.q_table:
            # Rien à sauvegarder (début de run, aucune donnée utile)
            return
        self._actions_since_last_checkpoint += 1
        if self._actions_since_last_checkpoint >= PATTERN_CHECKPOINT_INTERVAL:
            self._save_cognitive_state()
            self._actions_since_last_checkpoint = 0
            if DEBUG:
                print(f'[LuCY v{VERSION}] Periodic checkpoint: full cognitive state saved')

    # ---- P0-E v2 : lookup coarse → action connue ----
    def _lookup_pattern_action(self, sid_coarse: str) -> Optional[int]:
        if not self.game_patterns:
            return None
        for level_key, pattern in self.game_patterns.items():
            if pattern.get('from_sid_coarse') == sid_coarse:
                action = pattern.get('action')
                if action is not None and isinstance(action, int):
                    return action
        return None

    # ---- SE + PE ----
    def se_perceive(self, frame_raw) -> Tuple[str, str, str, Optional[np.ndarray]]:
        if frame_raw is None:
            return 'null', 'null', 'null', None

        if isinstance(frame_raw, list):
            try:
                arr = np.array(frame_raw[0], dtype=np.uint8) if frame_raw else None
            except Exception:
                arr = None
        elif isinstance(frame_raw, np.ndarray):
            arr = frame_raw.astype(np.uint8)
        else:
            arr = None

        sid_full, sid_coarse, sid_colors = pe_encode_frame(frame_raw)
        return sid_full, sid_coarse, sid_colors, arr

    # ---- SI ----
    def si_get_state_info(self, sid: str) -> Dict:
        if sid not in self.state_archive:
            self.state_archive[sid] = {
                'visits': 0,
                'actions_tried': set(),
                'reward_sum': 0.0,
            }
        return self.state_archive[sid]

    # ---- NE ----
    def ne_detect_stuck(self, sid: str, sid_coarse: str) -> bool:
        info = self.si_get_state_info(sid)
        all_tried = all(a in info['actions_tried'] for a in STANDARD_ACTIONS)
        visual_cycle = self.pi.detect_visual_cycle(sid_coarse)
        return all_tried or self.stuck_counter > 12 or visual_cycle

    # ---- NI — P0-I v4.0 (inchangé) ----
    def ni_count_stuck(self, prev_sid: str, curr_sid: str, reward: float, action_id: int) -> None:
        if action_id == RESET_ACTION_ID and curr_sid != prev_sid:
            self.stuck_counter = 0
            if DEBUG:
                print(f'[LuCY v{VERSION}] P0-I: RESET productif → stuck_counter reset à 0')
        elif prev_sid == curr_sid:
            self.stuck_counter += 1
        elif reward <= 0:
            self.stuck_counter = max(0, self.stuck_counter - 1)
        else:
            self.stuck_counter = 0

    # ---- TE : UCB1 v4.0 (inchangé) ----
    def te_ucb1_score_actions(
        self, sid: str, sid_colors: str, available_actions: Tuple[int, ...],
        pattern_action: Optional[int] = None,
    ) -> List[Tuple[float, int]]:
        if not available_actions:
            available_actions = tuple(STANDARD_ACTIONS)

        n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions)
        n_total = max(1, self.n_s[sid], n_sa_sum)

        color_action = self.pi.suggest_action_for_colors(sid_colors)

        scored_inf: List[Tuple[int, int]] = []
        scored_finite: List[Tuple[float, int]] = []

        for aid in available_actions:
            if aid == RESET_ACTION_ID:
                continue

            n_action = self.n_sa.get((sid, aid), 0)
            q_val = self.q_table.get((sid, aid), 0.0)

            if n_action == 0:
                scored_inf.append((aid, aid))
            else:
                log_val = math.log(n_total) if n_total > 1 else 0.0
                exploration_bonus = UCB1_C * math.sqrt(log_val / n_action)
                ucb_score = q_val + exploration_bonus

                if self.pi.suggest_action_bias() == aid:
                    ucb_score += 0.2

                if pattern_action is not None and pattern_action == aid:
                    ucb_score += PATTERN_BIAS_BONUS

                if color_action is not None and color_action == aid:
                    ucb_score += COLOR_MATCH_BONUS

                scored_finite.append((ucb_score, aid))

        scored_inf.sort(key=lambda x: x[1])
        inf_list = [(float('inf'), aid) for _, aid in scored_inf]
        scored_finite.sort(key=lambda x: x[0], reverse=True)

        return inf_list + scored_finite

    # ---- TI ----
    def ti_check_consistency(self) -> bool:
        return (
            self.total_actions < MAX_ACTIONS
            and self.actions_this_level < MAX_ACTIONS_PER_LEVEL
        )

    # ---- FE ----
    def fe_detect_win_proximity(self, lf) -> float:
        if lf is None:
            return 0.0
        state = getattr(lf, 'state', None)
        if state == GameState.WIN:
            return 1.0
        levels = getattr(lf, 'levels_completed', 0)
        if levels > self.level_count:
            return 0.8
        score = getattr(lf, 'score', None)
        if score is not None and score > 0:
            return min(0.6, float(score) * 0.1)
        return 0.0

    # ---- FI ----
    def fi_get_priority(self, sid: str, sid_coarse: str) -> str:
        if self.ne_detect_stuck(sid, sid_coarse):
            return 'escape_cycle'
        self.epsilon = self.pi.get_epsilon(self.epsilon, self.total_actions)
        info = self.si_get_state_info(sid)
        if info['visits'] < MIN_STATE_VISITS:
            return 'explore'
        if random.random() < self.epsilon:
            return 'explore'
        return 'exploit'

    # ---- Arbitrateur v4.0 (inchangé) ----
    def arbitrate(
        self, sid: str, sid_coarse: str, sid_colors: str,
        available_actions: Tuple[int, ...], lf
    ) -> int:
        win_prox = self.fe_detect_win_proximity(lf)
        if win_prox >= 1.0:
            return STANDARD_ACTIONS[0]

        if not self.ti_check_consistency():
            return RESET_ACTION_ID

        priority = self.fi_get_priority(sid, sid_coarse)
        pattern_action = self._lookup_pattern_action(sid_coarse)
        if DEBUG and pattern_action is not None:
            print(f'[LuCY v{VERSION}] Pattern match: sid_coarse={sid_coarse[:6]} → action={pattern_action}')

        if priority == 'escape_cycle':
            info = self.si_get_state_info(sid)
            if (pattern_action is not None
                    and pattern_action in available_actions
                    and pattern_action not in info['actions_tried']):
                self.stuck_counter = max(0, self.stuck_counter - 5)
                return pattern_action
            for aid in STANDARD_ACTIONS:
                if aid not in info['actions_tried']:
                    self.stuck_counter = max(0, self.stuck_counter - 5)
                    return aid
            bias = self.pi.suggest_action_bias()
            if bias is not None and bias in STANDARD_ACTIONS:
                self.stuck_counter = 0
                return bias
            self.stuck_counter = 0
            return RESET_ACTION_ID

        scored = self.te_ucb1_score_actions(sid, sid_colors, available_actions, pattern_action)
        if not scored:
            return STANDARD_ACTIONS[0]

        if priority == 'explore':
            inf_actions = [aid for score, aid in scored if score == float('inf')]
            if inf_actions:
                return inf_actions[0]
            finite_actions = [aid for score, aid in scored if score != float('inf')]
            top_k = finite_actions[:3]
            return random.choice(top_k) if top_k else STANDARD_ACTIONS[0]

        return scored[0][1]

    # ---- Mise à jour Q-learning v4.1 ----
    def update(
        self,
        prev_sid: str,
        prev_sid_coarse: str,
        prev_sid_colors: str,
        curr_sid: str,
        curr_sid_coarse: str,
        curr_sid_colors: str,
        action_id: int,
        level_up: bool,
        win: bool = False,
        next_available_actions: Optional[Tuple[int, ...]] = None,
    ) -> float:
        """Met à jour Q-table + mémoire cognitive + PI.

        FIX-1 (P0-G) v4.1 — CORRECTION ATTRIBUTION TEMPORELLE :
        ÉTAIT (v4.0) ligne 764 :
            self.pi.update(curr_sid_coarse, curr_sid_colors, action_id, reward, level_up)
            #              ^^^^^^^^^^^^^ état APRÈS l'action → erreur temporelle

        MAINTENANT (v4.1) :
            self.pi.update(prev_sid_coarse, prev_sid_colors, action_id, reward, level_up)
            #              ^^^^^^^^^^^^^ état AVANT l'action → apprentissage cohérent (S,A)→R

        Explication de l'impact :
        - En v4.0, color_action_rewards[colors_après][action] += reward
          → L'agent mémorisait "dans l'état couleur résultant, cette action a fonctionné"
          → Ce qui est inutilisable : quand l'agent est DANS cet état, il ne sait plus
            qu'il vient d'y arriver via cette action depuis un autre état couleur.
        - En v4.1, color_action_rewards[colors_avant][action] += reward
          → L'agent mémorise "quand je vois ces couleurs, l'action X rapporte"
          → Cohérent avec suggest_action_for_colors(sid_colors_courant) dans te_ucb1_score_actions

        FIX-2 (P0-J) v4.1 : _maybe_checkpoint_patterns() déclenche maintenant
        _save_cognitive_state() (complet) au lieu de _save_patterns() (partiel).
        """
        info = self.si_get_state_info(prev_sid)
        info['visits'] += 1
        info['actions_tried'].add(action_id)

        # P0-C v2 (hérité v3.2) : 3 niveaux de récompense
        reward = 0.0
        if win:
            reward += REWARD_WIN
        elif level_up:
            reward += REWARD_LEVEL_UP
            self.level_count += 1
            self.actions_this_level = 0
            level_key = str(self.level_count - 1)
            self.game_patterns[level_key] = {
                'action': action_id,
                'from_sid_coarse': prev_sid_coarse,
                'to_sid_coarse': curr_sid_coarse,
            }
            # FIX-2 : sauvegarder l'état COMPLET sur level_up (pas seulement patterns)
            # AVANT (v4.0) : self._save_patterns()
            # APRÈS (v4.1) : self._save_cognitive_state() (inclut _save_patterns() en interne)
            self._save_cognitive_state()
            self._actions_since_last_checkpoint = 0
        elif action_id == RESET_ACTION_ID:
            reward += REWARD_RESET
        elif curr_sid == prev_sid:
            reward += REWARD_CYCLE
        else:
            reward += REWARD_PROGRESS

        # Q-learning update (P0-F v2 hérité)
        old_q = self.q_table.get((prev_sid, action_id), 0.0)
        if next_available_actions and len(next_available_actions) > 0:
            all_next = list(next_available_actions)
        else:
            all_next = STANDARD_ACTIONS + [RESET_ACTION_ID]
        next_qs = [self.q_table.get((curr_sid, a), 0.0) for a in all_next]
        max_next_q = max(next_qs) if next_qs else 0.0
        new_q = old_q + ALPHA * (reward + GAMMA * max_next_q - old_q)
        self.q_table[(prev_sid, action_id)] = new_q

        # P0-A v2 (hérité) : compteurs UCB1
        self.n_sa[(prev_sid, action_id)] += 1
        self.n_s[prev_sid] += 1

        # Graphe de transitions
        self.transition_graph[(prev_sid, action_id)] = curr_sid

        # FIX-1 (P0-G) v4.1 : CORRECTION ATTRIBUTION TEMPORELLE
        # AVANT (v4.0) : self.pi.update(curr_sid_coarse, curr_sid_colors, ...)
        # APRÈS (v4.1) : self.pi.update(prev_sid_coarse, prev_sid_colors, ...)
        self.pi.update(prev_sid_coarse, prev_sid_colors, action_id, reward, level_up)

        # NI — P0-I v4.0 (inchangé)
        self.ni_count_stuck(prev_sid, curr_sid, reward, action_id)

        self.prev_sid = curr_sid
        self.prev_sid_coarse = curr_sid_coarse
        self.prev_sid_colors = curr_sid_colors
        self.total_actions += 1
        self.actions_this_level += 1

        info['reward_sum'] += reward

        # FIX-2 (P0-J) : checkpoint périodique → maintenant sauvegarde l'état complet
        self._maybe_checkpoint_patterns()

        return reward


# =========================================================
# LuCYAgent v4.1
# =========================================================

class LuCYAgent(Agent):
    """
    Agent LuCY v4.1 pour ARC-AGI-3.

    FIX-1 (P0-G) : attribution temporelle corrigée — pi.update() reçoit prev_sid_colors
    FIX-2 (P0-J) : persistance cognitive COMPLÈTE — q_table + n_sa + n_s + color_action_rewards
    """

    MAX_ACTIONS = MAX_ACTIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cognition = LuCYCognition()
        self._prev_levels = 0
        self._started = False
        self._t_start = time.time()
        self._prev_available: Optional[Tuple[int, ...]] = None
        print(f'[LuCY v{VERSION}] Agent initialized | game_id={getattr(self, "game_id", "unknown")}')
        print(f'  CERTIFIED_100={CERTIFIED_100} | DEBUG={DEBUG}')
        print(f'  UCB1_C={UCB1_C} | ALPHA={ALPHA} | GAMMA={GAMMA} | EPS0={EPSILON_START}')
        print(f'  FIX-1: P0-G attribution temporelle (prev_sid_colors dans pi.update)')
        print(f'  FIX-2: P0-J persistance complete (q_table+n_sa+n_s+color_action_rewards)')
        print(f'  Héritage v4.0: P0-H(click-nonblack) P0-I(stuck-reset-full) + v3.2 P0-A..P0-F')

    def is_done(self, frames: List[Any], lf: Any) -> bool:
        state = getattr(lf, 'state', None)
        if state in (GameState.WIN, GameState.GAME_OVER):
            elapsed = time.time() - self._t_start
            cog = self.cognition
            print(f'[LuCY v{VERSION}] Game ended: state={state} | '
                  f'actions={cog.total_actions} | levels={cog.level_count} | '
                  f'states={len(cog.state_archive)} | t={elapsed:.1f}s')
            return True
        if self.action_counter >= self.MAX_ACTIONS:
            print(f'[LuCY v{VERSION}] Budget épuisé: {self.action_counter} actions')
            return True
        return False

    def choose_action(self, frames: List[Any], lf: Any) -> GameAction:
        """Sélectionne une action via le noyau cognitif LuCY v4.1.

        Inchangé par rapport à v4.0 — les corrections FIX-1/FIX-2 sont dans
        LuCYCognition.update() et la persistance, pas dans choose_action().
        """
        frame_raw = getattr(lf, 'frame', None)
        sid_full, sid_coarse, sid_colors, arr = self.cognition.se_perceive(frame_raw)

        curr_levels = getattr(lf, 'levels_completed', 0)
        level_up = curr_levels > self._prev_levels
        self._prev_levels = curr_levels

        state = getattr(lf, 'state', None)
        win = (state == GameState.WIN)

        available = getattr(lf, 'available_actions', ())
        if not available:
            available = tuple(STANDARD_ACTIONS)
        available = tuple(available)

        if not self._started:
            self._started = True
            if DEBUG:
                print(f'[LuCY v{VERSION}] First action | sid_full={sid_full[:8]} | '
                      f'sid_coarse={sid_coarse} | sid_colors={sid_colors} | available={available}')

        if (self.cognition.prev_sid is not None
                and self.cognition.prev_action_id is not None):
            prev_colors = self.cognition.prev_sid_colors or 'nocolor'
            reward = self.cognition.update(
                self.cognition.prev_sid,
                self.cognition.prev_sid_coarse or sid_coarse,
                prev_colors,
                sid_full,
                sid_coarse,
                sid_colors,
                self.cognition.prev_action_id,
                level_up,
                win=win,
                next_available_actions=available,
            )
            if DEBUG and (level_up or win):
                print(f'[LuCY v{VERSION}] Event: level_up={level_up} win={win} '
                      f'reward={reward:.2f} | total_actions={self.cognition.total_actions}')
        else:
            self.cognition.prev_sid = sid_full
            self.cognition.prev_sid_coarse = sid_coarse
            self.cognition.prev_sid_colors = sid_colors
            info = self.cognition.si_get_state_info(sid_full)
            info['visits'] += 1
            self.cognition.n_s[sid_full] += 1

        action_id = self.cognition.arbitrate(sid_full, sid_coarse, sid_colors, available, lf)
        self.cognition.prev_action_id = action_id
        self.cognition.prev_sid = sid_full
        self.cognition.prev_sid_coarse = sid_coarse
        self.cognition.prev_sid_colors = sid_colors

        if action_id == CLICK_ACTION_ID and arr is not None:
            # P0-H v4.0 (inchangé) : centroïde pixels non-noirs
            cx, cy = pe_find_nonblack_centroid(arr)
            if DEBUG:
                h = arr.shape[0] if arr.ndim >= 1 else 64
                w = arr.shape[1] if arr.ndim >= 2 else 64
                print(f'[LuCY v{VERSION}] P0-H: click centroïde non-noir ({cx},{cy}) '
                      f'vs centre géo ({w//2},{h//2})')
            action = build_action(CLICK_ACTION_ID, x=cx, y=cy)
        else:
            action = build_action(action_id)

        return action

# ============================================================
# END lucy_agent_v41.py — LuCY v4.1 (FIX-1: P0-G temporal, FIX-2: P0-J full persist)
# ============================================================
