# LuCY Cognitive Agent v3.2 for ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
# Phase 5.2 : Corrections P0-A..P0-F v2 (audit critique L-011)
#
# Corrections v3.2 vs v3.1 :
# P0-A v2 : n_sa_sum inclut RESET dans le calcul de l'invariant UCB1
# P0-B v2 : hash inclut les dimensions de la grille (préfixe shape) — évite collision même-bytes/formes-différentes
# P0-C v2 : 3 niveaux de reward : CYCLE (état ident.) / PROGRESS (+0.05 état nouveau) / LEVEL_UP
# P0-D v2 : tri des non-essayées par action_id canonique (pas l'index dans available_actions)
# P0-E v2 : arbitrate() consulte game_patterns pour biaiser si sid_coarse connu
# P0-F v2 : max_next_q calculé sur available_actions passées en param (pas liste fixe)

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


# ===== LuCY v3.2 Cognitive Constants =====
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False
DEBUG = True
VERSION = '3.2'

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

# Récompenses v3.2
# P0-C v2 : 3 niveaux distincts
# AVANT (v3.1) : REWARD_CYCLE = -0.05 pénalisait TOUT (y compris états nouveaux utiles)
# APRÈS (v3.2) :
#   - REWARD_CYCLE      = -0.05  si curr_sid == prev_sid   (vraie boucle stérile)
#   - REWARD_PROGRESS   = +0.05  si curr_sid != prev_sid   (état nouveau, pas level_up)
#   - REWARD_LEVEL_UP   = 2.0    (inchangé)
#   - REWARD_WIN        = 10.0   (inchangé)
#   - REWARD_RESET      = -0.3   (inchangé)
REWARD_LEVEL_UP = 2.0        # niveau complété
REWARD_WIN = 10.0            # victoire finale
REWARD_PROGRESS = 0.05       # état nouveau sans level_up (signal progrès réel)
REWARD_CYCLE = -0.05         # état identique = vraie boucle improductive
REWARD_RESET = -0.3          # pénalité reset

# Actions disponibles dans arcengine
STANDARD_ACTIONS = list(range(1, 6))
RESET_ACTION_ID = 0
CLICK_ACTION_ID = 6

# P0-E v2 : fichier de persistance des patterns inter-niveaux
PATTERNS_PERSIST_PATH = '/kaggle/working/lucy_game_patterns.json'

# Bonus de biais quand un pattern connu couvre le sid_coarse courant
PATTERN_BIAS_BONUS = 0.35


# =========================================================
# PE — Perception Étendue v3.2
# P0-B v2 : hash inclut les dimensions de la grille
# =========================================================

def pe_encode_frame(frame_raw) -> Tuple[str, str, str]:
    """Encode le frame en identifiants multi-résolution.

    v3.2 — P0-B v2 : hash calculé sur shape_prefix + arr.tobytes().
    Deux grilles avec les mêmes bytes bruts mais des formes différentes
    (ex: 4×8 vs 8×4) donnaient le même sid_full en v3.1.
    En v3.2, le préfixe de dimensions (4 bytes encodant rows et cols)
    est ajouté avant les bytes de contenu, éliminant ces collisions.

    Returns:
        (sid_full, sid_coarse, sid_colors)
    """
    if frame_raw is None:
        return 'null_full', 'null_coarse', 'null_colors'

    # Normaliser en numpy
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

    # sid_full : P0-B v2 — préfixe dimensions + tobytes()
    # AVANT (v3.1) : hashlib.md5(arr.tobytes()).hexdigest()[:16]
    #   → collision si même bytes, shapes différentes (ex: 4×8 vs 8×4)
    # APRÈS (v3.2) : dimensions encodées en 4 bytes + tobytes()
    #   rows, cols en uint16 little-endian (max 65535 chacun)
    if arr.ndim >= 2:
        rows, cols = arr.shape[0], arr.shape[1]
    else:
        rows, cols = arr.shape[0], 1
    shape_prefix = (
        (rows & 0xFFFF).to_bytes(2, 'little') +
        (cols & 0xFFFF).to_bytes(2, 'little')
    )
    sid_full = hashlib.md5(shape_prefix + arr.tobytes()).hexdigest()[:16]

    # sid_coarse : réduction 4×4 (invariant au bruit mineur)
    try:
        h_blocks = max(1, arr.shape[0] // 4) if arr.ndim >= 2 else 1
        w_blocks = max(1, arr.shape[1] // 4) if arr.ndim >= 2 else 1
        coarse = arr[:h_blocks*4, :w_blocks*4].reshape(
            h_blocks, 4, w_blocks, 4, -1
        ).mean(axis=(1, 3)).astype(np.uint8)
        # Inclure les dimensions dans sid_coarse aussi (cohérence)
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


# =========================================================
# PI — Pattern Interne
# =========================================================

class PIPatternAnalyzer:
    """Analyse les patterns internes pour guider l'exploration."""

    def __init__(self):
        self.coarse_history: List[str] = []
        self.color_history: List[str] = []
        self.successful_actions: List[int] = []
        self.failed_sequences: Set[Tuple] = set()

    def update(
        self, sid_coarse: str, sid_colors: str,
        action_id: int, reward: float, level_up: bool
    ) -> None:
        self.coarse_history.append(sid_coarse)
        self.color_history.append(sid_colors)

        if level_up:
            self.successful_actions.append(action_id)

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
# LuCYCognition v3.2
# P0-A v2 : n_sa_sum inclut RESET
# P0-C v2 : 3 niveaux reward
# P0-E v2 : arbitrate() consulte game_patterns
# P0-F v2 : max_next_q sur available_actions (pas liste fixe)
# =========================================================

class LuCYCognition:
    """
    Noyau cognitif LuCY v3.2 — 6 corrections P0 v2.

    Opérateurs actifs :
    - SE : Perception multi-résolution (via PE v3.2 — P0-B v2 hash + dimensions)
    - SI : Mémoire d'états avec Q-values
    - NE : Détection de blocage
    - NI : Compteur de cycles + PI
    - TE : UCB1 complet (P0-A v2 + P0-D v2)
    - TI : Budget check + cohérence
    - FE : Détection victoire + progress signal
    - FI : Epsilon adaptatif via PI
    + PE : Perception Étendue multi-résolution (P0-B v2)
    + PI : Pattern Interne (consulté dans arbitrate — P0-E v2)
    """

    def __init__(self):
        # SI : mémoire d'états
        self.state_archive: Dict[str, Dict] = {}

        # Graphe de transitions
        self.transition_graph: Dict[Tuple, str] = {}

        # Q-table
        self.q_table: Dict[Tuple, float] = {}

        # Compteurs UCB1
        # P0-A v2 : invariant n_s[sid] = sum des n_sa[(sid,aid)] pour TOUT aid
        # incluant RESET (correction vs v3.1 qui excluait RESET du n_sa_sum)
        self.n_sa: Dict[Tuple, int] = defaultdict(int)
        self.n_s: Dict[str, int] = defaultdict(int)

        # P0-E v2 : game_patterns persisté sur disque + utilisé dans arbitrate()
        self.game_patterns: Dict[str, Dict] = {}  # str(level_id) -> dict
        self._load_patterns()

        # État courant
        self.level_start_sid: Optional[str] = None
        self.actions_this_level = 0
        self.total_actions = 0
        self.level_count = 0
        self.prev_sid: Optional[str] = None
        self.prev_sid_coarse: Optional[str] = None
        self.prev_action_id: Optional[int] = None
        self.stuck_counter = 0
        self.epsilon = EPSILON_START

        # PE + PI
        self.pi = PIPatternAnalyzer()

    # ---- P0-E v2 : persistance game_patterns ----
    def _load_patterns(self) -> None:
        """Charge game_patterns depuis le disque si disponible."""
        try:
            if os.path.exists(PATTERNS_PERSIST_PATH):
                with open(PATTERNS_PERSIST_PATH, 'r') as f:
                    data = json.load(f)
                self.game_patterns = data.get('game_patterns', {})
                if DEBUG:
                    print(f'[LuCY v{VERSION}] Loaded {len(self.game_patterns)} game patterns from disk')
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] Could not load patterns: {e}')
            self.game_patterns = {}

    def _save_patterns(self) -> None:
        """Sauvegarde game_patterns sur le disque (append-safe)."""
        try:
            data = {'game_patterns': self.game_patterns, 'version': VERSION}
            with open(PATTERNS_PERSIST_PATH, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] Could not save patterns: {e}')

    # ---- P0-E v2 : lookup coarse → action connue ----
    def _lookup_pattern_action(self, sid_coarse: str) -> Optional[int]:
        """Retourne l'action conseillée si sid_coarse apparaît dans un pattern connu.

        v3.2 — P0-E v2 :
        En v3.1, game_patterns était sauvegardé mais JAMAIS consulté dans arbitrate().
        En v3.2, cette méthode est appelée depuis arbitrate() pour biaiser le score UCB1
        si l'état grossier courant correspond à un pattern réussi précédemment.

        Returns:
            action_id si un pattern correspondant est trouvé, None sinon.
        """
        if not self.game_patterns:
            return None
        for level_key, pattern in self.game_patterns.items():
            # Un pattern stocke from_sid_coarse + action qui a mené au level_up
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

    # ---- NI ----
    def ni_count_stuck(self, prev_sid: str, curr_sid: str, reward: float) -> None:
        if prev_sid == curr_sid:
            self.stuck_counter += 1
        elif reward <= 0:
            self.stuck_counter = max(0, self.stuck_counter - 1)
        else:
            self.stuck_counter = 0

    # ---- TE : UCB1 v3.2 — P0-A v2 + P0-D v2 ----
    def te_ucb1_score_actions(
        self, sid: str, available_actions: Tuple[int, ...],
        pattern_action: Optional[int] = None,
    ) -> List[Tuple[float, int]]:
        """Score les actions avec UCB1.

        v3.2 — P0-A v2 :
        - n_sa_sum inclut RESET dans le compte (était exclu en v3.1 avec
          la condition `if aid != RESET_ACTION_ID`).
        - Cela garantit que n_total >= n_sa[(sid, RESET)] quand RESET a été joué.

        AVANT (v3.1) :
            n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions
                           if aid != RESET_ACTION_ID)   ← RESET exclu
        APRÈS (v3.2) :
            n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in all_candidate_aids)
            where all_candidate_aids = available_actions (qui peut contenir RESET)

        v3.2 — P0-D v2 :
        - Tri des non-essayées par action_id canonique (pas par l'index dans
          available_actions, qui dépend de l'ordre reçu par l'env).

        AVANT (v3.1) :
            scored_inf.sort(key=lambda x: x[0])  # x[0] = idx dans available_actions
        APRÈS (v3.2) :
            scored_inf.sort(key=lambda x: x[1])  # x[1] = action_id canonique

        v3.2 — P0-E v2 (bonus pattern) :
        - Si pattern_action est fourni et présent dans available_actions,
          son score UCB1 reçoit un bonus PATTERN_BIAS_BONUS.
        """
        if not available_actions:
            available_actions = tuple(STANDARD_ACTIONS)

        # P0-A v2 : n_sa_sum inclut TOUTES les actions (y compris RESET)
        # AVANT (v3.1) : excluait RESET → n_total pouvait être < n_sa[(sid, RESET)]
        n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions)
        n_total = max(1, self.n_s[sid], n_sa_sum)

        scored_inf: List[Tuple[int, int]] = []   # (action_id, action_id) pour scores infinis
        scored_finite: List[Tuple[float, int]] = []  # (score, aid) pour scores finis

        for aid in available_actions:
            if aid == RESET_ACTION_ID:
                continue

            n_action = self.n_sa.get((sid, aid), 0)
            q_val = self.q_table.get((sid, aid), 0.0)

            if n_action == 0:
                # P0-D v2 : stocker (action_id, action_id) — tri par valeur canonique
                scored_inf.append((aid, aid))
            else:
                log_val = math.log(n_total) if n_total > 1 else 0.0
                exploration_bonus = UCB1_C * math.sqrt(log_val / n_action)
                ucb_score = q_val + exploration_bonus

                # Bonus PI : action souvent réussie
                if self.pi.suggest_action_bias() == aid:
                    ucb_score += 0.2

                # P0-E v2 : bonus pattern connu pour cet état
                if pattern_action is not None and pattern_action == aid:
                    ucb_score += PATTERN_BIAS_BONUS

                scored_finite.append((ucb_score, aid))

        # P0-D v2 : tri par action_id canonique (indépendant de l'ordre available_actions)
        # AVANT (v3.1) : scored_inf.sort(key=lambda x: x[0]) où x[0]=idx → dépendait de l'env
        # APRÈS (v3.2) : scored_inf.sort(key=lambda x: x[1]) où x[1]=aid → stable et canonique
        scored_inf.sort(key=lambda x: x[1])  # tri par action_id canonique
        inf_list = [(float('inf'), aid) for _, aid in scored_inf]

        # Trier les finis par score décroissant
        scored_finite.sort(key=lambda x: x[0], reverse=True)

        # Résultat : non-essayées en premier (ordre canonique), puis exploitation UCB1
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

    # ---- Arbitrateur v3.2 — P0-E v2 : consultation game_patterns ----
    def arbitrate(
        self, sid: str, sid_coarse: str,
        available_actions: Tuple[int, ...], lf
    ) -> int:
        """Synthèse des 10 opérateurs → choix d'action.

        v3.2 — P0-E v2 :
        En v3.1, game_patterns était sauvegardé sur disque mais JAMAIS consulté ici.
        En v3.2 :
        1. On cherche si sid_coarse correspond à un pattern connu via _lookup_pattern_action().
        2. Si oui, on passe pattern_action à te_ucb1_score_actions() qui applique PATTERN_BIAS_BONUS.
        3. En mode escape_cycle, si le pattern_action est non essayé → on le choisit en priorité.

        AVANT (v3.1) :
            scored = self.te_ucb1_score_actions(sid, available_actions)
            # game_patterns jamais consulté ici

        APRÈS (v3.2) :
            pattern_action = self._lookup_pattern_action(sid_coarse)
            scored = self.te_ucb1_score_actions(sid, available_actions, pattern_action)
        """
        win_prox = self.fe_detect_win_proximity(lf)
        if win_prox >= 1.0:
            return STANDARD_ACTIONS[0]

        if not self.ti_check_consistency():
            return RESET_ACTION_ID

        priority = self.fi_get_priority(sid, sid_coarse)

        # P0-E v2 : récupérer l'action conseillée par les patterns connus
        pattern_action = self._lookup_pattern_action(sid_coarse)
        if DEBUG and pattern_action is not None:
            print(f'[LuCY v{VERSION}] Pattern match: sid_coarse={sid_coarse[:6]} → action={pattern_action}')

        if priority == 'escape_cycle':
            info = self.si_get_state_info(sid)
            # P0-E v2 : en mode escape, tenter en priorité l'action du pattern si non essayée
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

        # TE (UCB1) : scorer les actions avec pattern_action comme hint
        scored = self.te_ucb1_score_actions(sid, available_actions, pattern_action)
        if not scored:
            return STANDARD_ACTIONS[0]

        if priority == 'explore':
            inf_actions = [aid for score, aid in scored if score == float('inf')]
            if inf_actions:
                return inf_actions[0]  # premier non-essayé (ordre canonique P0-D v2)
            finite_actions = [aid for score, aid in scored if score != float('inf')]
            top_k = finite_actions[:3]
            return random.choice(top_k) if top_k else STANDARD_ACTIONS[0]

        # Exploit : argmax UCB1 (tenant compte du bonus pattern_action)
        return scored[0][1]

    # ---- Mise à jour Q-learning v3.2 ----
    def update(
        self,
        prev_sid: str,
        prev_sid_coarse: str,
        curr_sid: str,
        curr_sid_coarse: str,
        curr_sid_colors: str,
        action_id: int,
        level_up: bool,
        win: bool = False,
        next_available_actions: Optional[Tuple[int, ...]] = None,
    ) -> float:
        """Met à jour Q-table + mémoire cognitive + PI.

        v3.2 corrections :
        P0-C v2 : 3 niveaux de reward
            AVANT (v3.1) : else: reward += REWARD_CYCLE  (pénalisait état nouveau aussi)
            APRÈS (v3.2) :
                si curr_sid == prev_sid → REWARD_CYCLE (-0.05)  [vraie boucle]
                si curr_sid != prev_sid → REWARD_PROGRESS (+0.05) [progrès réel sans level_up]

        P0-F v2 : max_next_q calculé sur next_available_actions si fourni
            AVANT (v3.1) : all_actions = STANDARD_ACTIONS + [RESET_ACTION_ID]  (liste fixe)
            APRÈS (v3.2) : all_next = next_available_actions si fourni, sinon fallback fixe

        Returns:
            reward obtenu
        """
        info = self.si_get_state_info(prev_sid)
        info['visits'] += 1
        info['actions_tried'].add(action_id)

        # P0-C v2 : 3 niveaux de récompense
        # AVANT (v3.1) :
        #   elif action_id == RESET_ACTION_ID: reward += REWARD_RESET
        #   else: reward += REWARD_CYCLE  # pénalise TOUT y compris état nouveau
        # APRÈS (v3.2) :
        #   distinction cycle (état ident.) vs progrès (état nouveau)
        reward = 0.0
        if win:
            reward += REWARD_WIN
        elif level_up:
            reward += REWARD_LEVEL_UP
            self.level_count += 1
            self.actions_this_level = 0
            # P0-E : mémoriser + sauvegarder les patterns du niveau
            level_key = str(self.level_count - 1)
            self.game_patterns[level_key] = {
                'action': action_id,
                'from_sid_coarse': prev_sid_coarse,
                'to_sid_coarse': curr_sid_coarse,
            }
            self._save_patterns()  # persist immédiatement
        elif action_id == RESET_ACTION_ID:
            reward += REWARD_RESET
        elif curr_sid == prev_sid:
            # P0-C v2 : vraie boucle stérile — pénalité
            reward += REWARD_CYCLE
        else:
            # P0-C v2 : état nouveau sans level_up — signal de progrès
            reward += REWARD_PROGRESS

        # Q-learning update
        old_q = self.q_table.get((prev_sid, action_id), 0.0)

        # P0-F v2 : max_next_q sur les actions réellement disponibles dans l'état suivant
        # AVANT (v3.1) : all_actions = STANDARD_ACTIONS + [RESET_ACTION_ID]  (fixe)
        # APRÈS (v3.2) : on utilise next_available_actions si fourni,
        #                sinon fallback vers STANDARD_ACTIONS + [RESET_ACTION_ID]
        if next_available_actions and len(next_available_actions) > 0:
            all_next = list(next_available_actions)
        else:
            all_next = STANDARD_ACTIONS + [RESET_ACTION_ID]

        next_qs = [self.q_table.get((curr_sid, a), 0.0) for a in all_next]
        max_next_q = max(next_qs) if next_qs else 0.0
        new_q = old_q + ALPHA * (reward + GAMMA * max_next_q - old_q)
        self.q_table[(prev_sid, action_id)] = new_q

        # P0-A v2 : compteurs UCB1 — inclut RESET (correction vs v3.1)
        # invariant : n_s[sid] >= n_sa[(sid, aid)] pour tout aid, y compris RESET
        self.n_sa[(prev_sid, action_id)] += 1
        self.n_s[prev_sid] += 1

        # Graphe de transitions
        self.transition_graph[(prev_sid, action_id)] = curr_sid

        # PI update
        self.pi.update(curr_sid_coarse, curr_sid_colors, action_id, reward, level_up)

        # NI
        self.ni_count_stuck(prev_sid, curr_sid, reward)

        self.prev_sid = curr_sid
        self.prev_sid_coarse = curr_sid_coarse
        self.total_actions += 1
        self.actions_this_level += 1

        info['reward_sum'] += reward
        return reward


# =========================================================
# LuCYAgent v3.2
# =========================================================

class LuCYAgent(Agent):
    """
    Agent LuCY v3.2 pour ARC-AGI-3.

    Corrections v3.2 vs v3.1 :
    - P0-A v2 : n_sa_sum inclut RESET pour l'invariant UCB1
    - P0-B v2 : hash inclut dimensions de la grille (préfixe shape)
    - P0-C v2 : 3 niveaux de reward (CYCLE / PROGRESS / LEVEL_UP)
    - P0-D v2 : tri des non-essayées par action_id canonique
    - P0-E v2 : arbitrate() consulte game_patterns pour biaiser si sid_coarse connu
    - P0-F v2 : max_next_q calculé sur available_actions de l'état suivant
    """

    MAX_ACTIONS = MAX_ACTIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cognition = LuCYCognition()
        self._prev_levels = 0
        self._started = False
        self._t_start = time.time()
        # Stocker les available_actions précédentes pour P0-F v2
        self._prev_available: Optional[Tuple[int, ...]] = None
        print(f'[LuCY v{VERSION}] Agent initialized | game_id={getattr(self, "game_id", "unknown")}')
        print(f'  CERTIFIED_100={CERTIFIED_100} | DEBUG={DEBUG}')
        print(f'  UCB1_C={UCB1_C} | ALPHA={ALPHA} | GAMMA={GAMMA} | EPS0={EPSILON_START}')
        print(f'  Corrections v3.2: P0-A(UCB1+RESET) P0-B(hash+shape) P0-C(3-levels-reward) '
              f'P0-D(canonical-sort) P0-E(patterns-in-arbitrate) P0-F(next-available-q)')

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
        """Sélectionne une action via le noyau cognitif LuCY v3.2."""
        frame_raw = getattr(lf, 'frame', None)
        sid_full, sid_coarse, sid_colors, arr = self.cognition.se_perceive(frame_raw)

        curr_levels = getattr(lf, 'levels_completed', 0)
        level_up = curr_levels > self._prev_levels
        self._prev_levels = curr_levels

        state = getattr(lf, 'state', None)
        win = (state == GameState.WIN)

        # Récupérer available_actions AVANT l'update (pour P0-F v2 du tour PRÉCÉDENT)
        available = getattr(lf, 'available_actions', ())
        if not available:
            available = tuple(STANDARD_ACTIONS)
        available = tuple(available)

        if not self._started:
            self._started = True
            if DEBUG:
                print(f'[LuCY v{VERSION}] First action | sid_full={sid_full[:8]} | '
                      f'sid_coarse={sid_coarse} | available={available}')

        if (self.cognition.prev_sid is not None
                and self.cognition.prev_action_id is not None):
            # P0-F v2 : passer les available_actions du state courant comme "next"
            # pour le calcul de max_next_q dans update()
            reward = self.cognition.update(
                self.cognition.prev_sid,
                self.cognition.prev_sid_coarse or sid_coarse,
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
            info = self.cognition.si_get_state_info(sid_full)
            info['visits'] += 1
            self.cognition.n_s[sid_full] += 1

        action_id = self.cognition.arbitrate(sid_full, sid_coarse, available, lf)
        self.cognition.prev_action_id = action_id
        self.cognition.prev_sid = sid_full
        self.cognition.prev_sid_coarse = sid_coarse

        if action_id == CLICK_ACTION_ID and arr is not None:
            h, w = arr.shape[:2] if arr.ndim >= 2 else (64, 64)
            action = build_action(CLICK_ACTION_ID, x=w // 2, y=h // 2)
        else:
            action = build_action(action_id)

        return action
# ============================================================
# END lucy_agent_v32.py — LuCY v3.2 (P0-A v2..P0-F v2 corrigés)
# ============================================================
