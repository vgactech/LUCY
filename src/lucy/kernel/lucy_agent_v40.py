# LuCY Cognitive Agent v4.0 for ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
# Phase 6.0 : Corrections P0-G..P0-J (audit critique L-014)
#
# Corrections v4.0 vs v3.2 :
# P0-G : sid_colors intégré dans le score UCB1 (3ème dimension perceptive — ANO-007)
# P0-H : click stratégique sur centroïde des pixels non-noirs (ANO-008)
# P0-I : stuck_counter remis à 0 complet après RESET productif (ANO-010)
# P0-J : checkpoint game_patterns toutes les PATTERN_CHECKPOINT_INTERVAL actions (ANO-009)
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


# ===== LuCY v4.0 Cognitive Constants =====
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False
DEBUG = True
VERSION = '4.0'

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

# P0-E v2 : fichier de persistance des patterns inter-niveaux
PATTERNS_PERSIST_PATH = '/kaggle/working/lucy_game_patterns.json'

# Bonus de biais quand un pattern connu couvre le sid_coarse courant
PATTERN_BIAS_BONUS = 0.35

# P0-G : poids du bonus couleur dans le score UCB1
# Une correspondance exacte de couleurs avec l'action la plus récompensée
# dans cet état de couleur reçoit ce bonus (valeur modeste — signal auxiliaire)
COLOR_MATCH_BONUS = 0.15

# P0-J : checkpoint des patterns tous les N actions (pas seulement sur level_up)
# AVANT (v3.2) : _save_patterns() uniquement lors d'un level_up
# APRÈS (v4.0) : _save_patterns() aussi tous les PATTERN_CHECKPOINT_INTERVAL actions
PATTERN_CHECKPOINT_INTERVAL = 50


# =========================================================
# PE — Perception Étendue v4.0
# Héritage P0-B v2 : hash inclut les dimensions de la grille
# =========================================================

def pe_encode_frame(frame_raw) -> Tuple[str, str, str]:
    """Encode le frame en identifiants multi-résolution.

    v3.2 — P0-B v2 : hash calculé sur shape_prefix + arr.tobytes().
    v4.0 — inchangé sur l'encodage ; sid_colors maintenant utilisé dans UCB1 (P0-G).

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
        coarse_prefix = (
            (h_blocks & 0xFF).to_bytes(1, 'little') +
            (w_blocks & 0xFF).to_bytes(1, 'little')
        )
        sid_coarse = hashlib.md5(coarse_prefix + coarse.tobytes()).hexdigest()[:8]
    except Exception:
        sid_coarse = sid_full[:8]

    # sid_colors : top-3 couleurs dominantes (buckets de 16)
    # P0-G v4.0 : ce champ est maintenant utilisé dans UCB1 (auparavant calculé mais ignoré)
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

    P0-H v4.0 : click stratégique sur le centroïde des pixels saillants.

    AVANT (v3.2) : x = w // 2, y = h // 2  (centre géométrique fixe — aveugle)
    APRÈS (v4.0) :
        - Trouver tous les pixels dont la valeur > BLACK_THRESHOLD
        - Calculer leur barycentre (y_mean, x_mean)
        - Si aucun pixel non-noir → fallback au centre géométrique

    Returns:
        (x, y) en coordonnées pixel (x=colonne, y=ligne)
    """
    BLACK_THRESHOLD = 16  # pixels dont val > 16 sont considérés "non-noirs"

    if arr is None:
        return 32, 32  # fallback absolu

    h = arr.shape[0] if arr.ndim >= 1 else 64
    w = arr.shape[1] if arr.ndim >= 2 else 64
    fallback_x, fallback_y = w // 2, h // 2

    try:
        # Créer un masque "non-noir"
        if arr.ndim == 3:
            # Image couleur : saillant si n'importe quel canal > seuil
            mask = np.any(arr > BLACK_THRESHOLD, axis=2)
        elif arr.ndim == 2:
            mask = arr > BLACK_THRESHOLD
        else:
            return fallback_x, fallback_y

        ys, xs = np.where(mask)
        if len(ys) == 0:
            # Aucun pixel non-noir → fallback centre
            return fallback_x, fallback_y

        centroid_x = int(np.mean(xs))
        centroid_y = int(np.mean(ys))
        return centroid_x, centroid_y

    except Exception:
        return fallback_x, fallback_y


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

        # P0-G v4.0 : historique (sid_colors, action, reward) pour le bonus couleur
        # Permet de savoir quelle action a été récompensée dans quel contexte couleur
        self.color_action_rewards: Dict[str, Dict[int, float]] = defaultdict(
            lambda: defaultdict(float)
        )

    def update(
        self, sid_coarse: str, sid_colors: str,
        action_id: int, reward: float, level_up: bool
    ) -> None:
        self.coarse_history.append(sid_coarse)
        self.color_history.append(sid_colors)

        if level_up:
            self.successful_actions.append(action_id)

        # P0-G v4.0 : mémoriser le reward par (sid_colors, action)
        # Accumulation exponentielle (somme directe suffisante pour le signal auxiliaire)
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

    # P0-G v4.0 : retourne l'action ayant le meilleur reward cumulé pour ce contexte couleur
    def suggest_action_for_colors(self, sid_colors: str) -> Optional[int]:
        """Retourne l'action la plus récompensée dans ce contexte de couleurs.

        v4.0 — P0-G :
        AVANT (v3.2) : sid_colors calculé dans pe_encode_frame() mais jamais utilisé ici.
        APRÈS (v4.0) : color_action_rewards[sid_colors] mémorise les rewards cumulés
        par action dans ce contexte couleur. L'action avec le meilleur cumul est retournée.

        Returns:
            action_id si des données couleur existent, None sinon.
        """
        rewards = self.color_action_rewards.get(sid_colors)
        if not rewards:
            return None
        best_action = max(rewards, key=lambda a: rewards[a])
        return best_action if rewards[best_action] > 0 else None


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
# LuCYCognition v4.0
# Héritage P0-A v2 à P0-F v2 (v3.2)
# Nouvelles corrections : P0-G / P0-H / P0-I / P0-J
# =========================================================

class LuCYCognition:
    """
    Noyau cognitif LuCY v4.0 — 10 corrections P0 cumulées.

    Opérateurs actifs (inchangés depuis v3.2) :
    - SE : Perception multi-résolution (via PE v4.0 — P0-B v2 hash + dimensions)
    - SI : Mémoire d'états avec Q-values
    - NE : Détection de blocage
    - NI : Compteur de cycles + PI
    - TE : UCB1 complet (P0-A v2 + P0-D v2 + P0-G nouveau)
    - TI : Budget check + cohérence
    - FE : Détection victoire + progress signal
    - FI : Epsilon adaptatif via PI
    + PE : Perception Étendue multi-résolution (P0-B v2 + P0-H centroïde)
    + PI : Pattern Interne (colors dans arbitrate — P0-G)

    Nouvelles corrections v4.0 :
    - P0-G : sid_colors → bonus COLOR_MATCH_BONUS dans UCB1
    - P0-H : click sur centroïde pixels non-noirs (dans LuCYAgent.choose_action)
    - P0-I : stuck_counter = 0 complet après RESET productif
    - P0-J : checkpoint game_patterns toutes les PATTERN_CHECKPOINT_INTERVAL actions
    """

    def __init__(self):
        # SI : mémoire d'états
        self.state_archive: Dict[str, Dict] = {}

        # Graphe de transitions
        self.transition_graph: Dict[Tuple, str] = {}

        # Q-table
        self.q_table: Dict[Tuple, float] = {}

        # Compteurs UCB1 (P0-A v2 inchangé)
        self.n_sa: Dict[Tuple, int] = defaultdict(int)
        self.n_s: Dict[str, int] = defaultdict(int)

        # P0-E v2 : game_patterns persisté sur disque + utilisé dans arbitrate()
        self.game_patterns: Dict[str, Dict] = {}
        self._load_patterns()

        # État courant
        self.level_start_sid: Optional[str] = None
        self.actions_this_level = 0
        self.total_actions = 0
        self.level_count = 0
        self.prev_sid: Optional[str] = None
        self.prev_sid_coarse: Optional[str] = None
        self.prev_sid_colors: Optional[str] = None  # v4.0 : tracker colors précédent
        self.prev_action_id: Optional[int] = None
        self.stuck_counter = 0
        self.epsilon = EPSILON_START

        # PE + PI
        self.pi = PIPatternAnalyzer()

        # P0-J v4.0 : compteur pour checkpoint périodique des patterns
        self._actions_since_last_checkpoint = 0

    # ---- P0-E v2 + P0-J v4.0 : persistance game_patterns ----
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
        """Sauvegarde game_patterns sur le disque (écriture atomique via fichier temporaire).

        P0-J v4.0 :
        AVANT (v3.2) : écriture directe open(path, 'w') + appelé UNIQUEMENT sur level_up.
        APRÈS (v4.0) :
            1. Écriture atomique via fichier temporaire (évite corruption si crash pendant write)
            2. Appelé aussi toutes les PATTERN_CHECKPOINT_INTERVAL actions (checkpoint périodique)
               pour ne pas perdre les patterns en cas d'interruption Kaggle avant level_up
        """
        try:
            data = {'game_patterns': self.game_patterns, 'version': VERSION}
            # P0-J v4.0 : écriture atomique via fichier temporaire
            # AVANT (v3.2) : with open(PATTERNS_PERSIST_PATH, 'w') as f: json.dump(data, f)
            # APRÈS (v4.0) : écriture dans .tmp, puis os.replace() (atomique sur même fs)
            tmp_path = PATTERNS_PERSIST_PATH + '.tmp'
            with open(tmp_path, 'w') as f:
                json.dump(data, f)
            os.replace(tmp_path, PATTERNS_PERSIST_PATH)
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] Could not save patterns: {e}')

    def _maybe_checkpoint_patterns(self) -> None:
        """Checkpoint périodique des patterns (P0-J v4.0).

        Appelé à chaque action. Déclenche _save_patterns() tous les
        PATTERN_CHECKPOINT_INTERVAL actions si game_patterns non vide.

        AVANT (v3.2) : pas de checkpoint périodique — perte si crash avant level_up.
        APRÈS (v4.0) : checkpoint toutes les PATTERN_CHECKPOINT_INTERVAL actions.
        """
        if not self.game_patterns:
            return
        self._actions_since_last_checkpoint += 1
        if self._actions_since_last_checkpoint >= PATTERN_CHECKPOINT_INTERVAL:
            self._save_patterns()
            self._actions_since_last_checkpoint = 0
            if DEBUG:
                print(f'[LuCY v{VERSION}] Periodic checkpoint: {len(self.game_patterns)} patterns saved')

    # ---- P0-E v2 : lookup coarse → action connue ----
    def _lookup_pattern_action(self, sid_coarse: str) -> Optional[int]:
        """Retourne l'action conseillée si sid_coarse apparaît dans un pattern connu."""
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

    # ---- NI — v4.0 P0-I : stuck_counter reset complet après RESET productif ----
    def ni_count_stuck(self, prev_sid: str, curr_sid: str, reward: float, action_id: int) -> None:
        """Met à jour stuck_counter.

        v4.0 — P0-I :
        AVANT (v3.2) :
            if prev_sid == curr_sid: stuck_counter += 1
            elif reward <= 0: stuck_counter = max(0, stuck_counter - 1)  ← décrémente seulement
            else: stuck_counter = 0

        APRÈS (v4.0) :
            Si RESET a été joué ET l'état a changé (curr_sid != prev_sid) :
                → stuck_counter = 0  (reset complet — le RESET a été productif)
            Sinon si état identique :
                → stuck_counter += 1
            Sinon si reward <= 0 :
                → stuck_counter = max(0, stuck_counter - 1)
            Sinon :
                → stuck_counter = 0

        Rationale : en v3.2, un RESET qui changeait l'état ne réinitialisait pas
        stuck_counter à 0 si reward était <= 0 — il le décrémentait seulement de 1.
        Après 3+ resets, l'agent entrait en "mode reset permanent" même si l'état
        changeait correctement après chaque reset.
        """
        if action_id == RESET_ACTION_ID and curr_sid != prev_sid:
            # P0-I v4.0 : RESET productif (état a changé) → reset complet
            # AVANT (v3.2) : elif reward <= 0: self.stuck_counter = max(0, stuck_counter - 1)
            # APRÈS (v4.0) : self.stuck_counter = 0
            self.stuck_counter = 0
            if DEBUG:
                print(f'[LuCY v{VERSION}] P0-I: RESET productif → stuck_counter reset à 0')
        elif prev_sid == curr_sid:
            self.stuck_counter += 1
        elif reward <= 0:
            self.stuck_counter = max(0, self.stuck_counter - 1)
        else:
            self.stuck_counter = 0

    # ---- TE : UCB1 v4.0 — P0-G : bonus couleur ----
    def te_ucb1_score_actions(
        self, sid: str, sid_colors: str, available_actions: Tuple[int, ...],
        pattern_action: Optional[int] = None,
    ) -> List[Tuple[float, int]]:
        """Score les actions avec UCB1.

        Héritage v3.2 : P0-A v2, P0-D v2, P0-E v2.

        v4.0 — P0-G :
        Ajout d'un bonus COLOR_MATCH_BONUS si l'action correspond à celle
        que PI.suggest_action_for_colors(sid_colors) recommande.

        AVANT (v3.2) :
            # sid_colors calculé mais jamais utilisé dans UCB1
            ucb_score = q_val + exploration_bonus
            if pi.suggest_action_bias() == aid: ucb_score += 0.2
            if pattern_action == aid: ucb_score += PATTERN_BIAS_BONUS

        APRÈS (v4.0) :
            color_action = pi.suggest_action_for_colors(sid_colors)
            if color_action == aid: ucb_score += COLOR_MATCH_BONUS  ← NOUVEAU

        Note : le bonus couleur est plus petit que le bias pattern (0.15 vs 0.35)
        car il est basé sur des corrélations statistiques moins précises que les
        transitions coarse qui ont mené à un level_up.
        """
        if not available_actions:
            available_actions = tuple(STANDARD_ACTIONS)

        # P0-A v2 : n_sa_sum inclut TOUTES les actions (y compris RESET)
        n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions)
        n_total = max(1, self.n_s[sid], n_sa_sum)

        # P0-G v4.0 : récupérer l'action conseillée par le contexte couleur
        # AVANT (v3.2) : color_action = None (non calculé ici)
        # APRÈS (v4.0) : color_action = pi.suggest_action_for_colors(sid_colors)
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

                # Bonus PI succès globaux
                if self.pi.suggest_action_bias() == aid:
                    ucb_score += 0.2

                # P0-E v2 : bonus pattern connu pour cet état coarse
                if pattern_action is not None and pattern_action == aid:
                    ucb_score += PATTERN_BIAS_BONUS

                # P0-G v4.0 : bonus couleur (signal auxiliaire perceptif)
                # AVANT (v3.2) : cette branche n'existait pas
                # APRÈS (v4.0) : COLOR_MATCH_BONUS si action recommandée par le contexte couleur
                if color_action is not None and color_action == aid:
                    ucb_score += COLOR_MATCH_BONUS

                scored_finite.append((ucb_score, aid))

        # P0-D v2 : tri par action_id canonique
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

    # ---- Arbitrateur v4.0 ----
    def arbitrate(
        self, sid: str, sid_coarse: str, sid_colors: str,
        available_actions: Tuple[int, ...], lf
    ) -> int:
        """Synthèse des 10 opérateurs → choix d'action.

        v4.0 : passe sid_colors à te_ucb1_score_actions() (P0-G).

        AVANT (v3.2) :
            scored = self.te_ucb1_score_actions(sid, available_actions, pattern_action)
            # sid_colors non passé — P0-G non actif

        APRÈS (v4.0) :
            scored = self.te_ucb1_score_actions(sid, sid_colors, available_actions, pattern_action)
            # sid_colors transmis → bonus COLOR_MATCH_BONUS si correspondance
        """
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

        # P0-G v4.0 : passe sid_colors (était absent dans l'appel v3.2)
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

    # ---- Mise à jour Q-learning v4.0 ----
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

        v4.0 : ajoute prev_sid_colors dans la signature pour P0-G.
        P0-I : ni_count_stuck() reçoit action_id pour détecter RESET productif.
        P0-J : appelle _maybe_checkpoint_patterns() à chaque update.
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
            self._save_patterns()  # persist immédiatement sur level_up
            self._actions_since_last_checkpoint = 0  # reset compteur checkpoint
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

        # PI update — P0-G v4.0 : prev_sid_colors passé pour mémoriser reward couleur
        self.pi.update(curr_sid_coarse, curr_sid_colors, action_id, reward, level_up)

        # NI — P0-I v4.0 : action_id passé pour détecter RESET productif
        # AVANT (v3.2) : self.ni_count_stuck(prev_sid, curr_sid, reward)
        # APRÈS (v4.0) : self.ni_count_stuck(prev_sid, curr_sid, reward, action_id)
        self.ni_count_stuck(prev_sid, curr_sid, reward, action_id)

        self.prev_sid = curr_sid
        self.prev_sid_coarse = curr_sid_coarse
        self.prev_sid_colors = curr_sid_colors  # v4.0 : tracker colors
        self.total_actions += 1
        self.actions_this_level += 1

        info['reward_sum'] += reward

        # P0-J v4.0 : checkpoint périodique (toutes les PATTERN_CHECKPOINT_INTERVAL actions)
        # AVANT (v3.2) : pas de checkpoint périodique — perte si crash Kaggle avant level_up
        # APRÈS (v4.0) : _maybe_checkpoint_patterns() appelé à chaque update
        self._maybe_checkpoint_patterns()

        return reward


# =========================================================
# LuCYAgent v4.0
# =========================================================

class LuCYAgent(Agent):
    """
    Agent LuCY v4.0 pour ARC-AGI-3.

    Héritage v3.2 :
    - P0-A v2 : n_sa_sum inclut RESET
    - P0-B v2 : hash inclut dimensions de la grille
    - P0-C v2 : 3 niveaux de reward
    - P0-D v2 : tri canonique UCB1
    - P0-E v2 : game_patterns dans arbitrate
    - P0-F v2 : max_next_q sur available_actions

    Nouvelles corrections v4.0 :
    - P0-G : sid_colors branché dans UCB1 via PI.color_action_rewards
    - P0-H : click stratégique sur centroïde pixels non-noirs (pe_find_nonblack_centroid)
    - P0-I : stuck_counter = 0 complet après RESET productif
    - P0-J : checkpoint game_patterns périodique (écriture atomique)
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
        print(f'  Corrections v4.0: P0-G(colors-UCB1) P0-H(click-nonblack) '
              f'P0-I(stuck-reset-full) P0-J(periodic-checkpoint)')
        print(f'  Héritage v3.2: P0-A(UCB1+RESET) P0-B(hash+shape) P0-C(3-levels-reward) '
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
        """Sélectionne une action via le noyau cognitif LuCY v4.0.

        P0-H v4.0 :
        AVANT (v3.2) :
            if action_id == CLICK_ACTION_ID and arr is not None:
                h, w = arr.shape[:2] if arr.ndim >= 2 else (64, 64)
                action = build_action(CLICK_ACTION_ID, x=w // 2, y=h // 2)  ← centre géométrique

        APRÈS (v4.0) :
            if action_id == CLICK_ACTION_ID and arr is not None:
                cx, cy = pe_find_nonblack_centroid(arr)  ← centroïde pixels non-noirs
                action = build_action(CLICK_ACTION_ID, x=cx, y=cy)
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
            # v4.0 : passe prev_sid_colors dans l'update (P0-G)
            prev_colors = self.cognition.prev_sid_colors or 'nocolor'
            reward = self.cognition.update(
                self.cognition.prev_sid,
                self.cognition.prev_sid_coarse or sid_coarse,
                prev_colors,         # v4.0 : NOUVEAU — prev_sid_colors
                sid_full,
                sid_coarse,
                sid_colors,          # v4.0 : NOUVEAU — curr_sid_colors
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
            self.cognition.prev_sid_colors = sid_colors  # v4.0
            info = self.cognition.si_get_state_info(sid_full)
            info['visits'] += 1
            self.cognition.n_s[sid_full] += 1

        # v4.0 : passe sid_colors à arbitrate() (P0-G)
        action_id = self.cognition.arbitrate(sid_full, sid_coarse, sid_colors, available, lf)
        self.cognition.prev_action_id = action_id
        self.cognition.prev_sid = sid_full
        self.cognition.prev_sid_coarse = sid_coarse
        self.cognition.prev_sid_colors = sid_colors  # v4.0

        if action_id == CLICK_ACTION_ID and arr is not None:
            # P0-H v4.0 : centroïde pixels non-noirs
            # AVANT (v3.2) :
            #   h, w = arr.shape[:2] if arr.ndim >= 2 else (64, 64)
            #   action = build_action(CLICK_ACTION_ID, x=w // 2, y=h // 2)
            # APRÈS (v4.0) :
            #   cx, cy = pe_find_nonblack_centroid(arr)
            #   action = build_action(CLICK_ACTION_ID, x=cx, y=cy)
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
# END lucy_agent_v40.py — LuCY v4.0 (P0-A v2..P0-J v4.0)
# ============================================================
