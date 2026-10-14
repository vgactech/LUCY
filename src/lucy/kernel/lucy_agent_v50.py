# LuCY Cognitive Agent v5.0 for ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
#
# Architecture v5.0 — Nouvelle hiérarchie cognitive à 3 niveaux
# ─────────────────────────────────────────────────────────────
# Niveau 1 — 8 FONCTIONS COGNITIVES (unités opérationnelles)
#     SE (Sensation Externe)   : perception pixels actuels, couleurs saillantes, centroïde
#     SI (Sensation Interne)   : mémorisation patterns passés, Q-table, compteurs UCB1
#     NE (iNtuition Externe)   : exploration actions inconnues, epsilon-greedy, UCB1-inf
#     NI (iNtuition Interne)   : anticipation conséquences, Q(s,a) Bellman, valeur future
#     TE (Thinking Externe)    : scoring logique candidats, tri UCB1, sélection best action
#     TI (Thinking Interne)    : détection cycles, cohérence interne, analyse boucles
#     FE (Feeling Externe)     : adaptation contexte couleur (color_action_rewards), PI-bonus
#     FI (Feeling Interne)     : valeurs : bonus level_up, pénalité stuck, priorité escape
#
# Niveau 2 — 4 CONTRÔLEURS SPÉCIALISÉS
#     PI_ctrl = NI + SI  : perception introvertie — patterns accumulés + anticipation
#     PE_ctrl = NE + SE  : perception extravertie — exploration + perception actuelle
#     DI_ctrl = TI + FI  : décision introvertie  — analyse cycle + décision par valeurs
#     DE_ctrl = TE + FE  : décision extravertie  — scoring logique + adaptation couleur
#
# Niveau 3 — 1 MÉTA-CONTRÔLEUR
#     - Donne les AUTORISATIONS d'échange entre contrôleurs (pas de données qui transitent)
#     - Applique le profil cognitif (INTP : TI>NE>SI>FE → priorité DI_ctrl, PE_ctrl)
#     - Adaptatif : réévalue les priorités à chaque step (contexte → profil courant)
#     - Délègue les règles — ne relaie PAS les données
#
# Reward adaptatif (NOUVEAU v5.0) :
#     reward = base_reward × progression_factor × (1 - stagnation_penalty)
#     progression_factor : augmente si l'agent progresse, diminue si stagnation
#     stagnation_penalty : proportionnel au stuck_counter
#     win_reward : 10.0 (inchangé)
#     level_up_reward : 2.0 × min(2.0, 1 + progress_rate)  ← amplification selon vitesse
#     cycle_penalty : -0.05 × (1 + stuck_factor)            ← pénalité croissante avec blocage
#
# Héritage v4.1 (conservé) :
#   FIX-1 P0-G : pi.update() reçoit prev_sid_colors (attribution temporelle correcte)
#   FIX-2 P0-J : persistance cognitive COMPLÈTE (q_table + n_sa + n_s + color_action_rewards)
#   P0-A..P0-F (v3.2) + P0-G..P0-J (v4.0) + FIX-1/FIX-2 (v4.1)
#
# Différences v5.0 vs v4.1 :
#   1. Hiérarchie 3 niveaux : fonctions → contrôleurs → méta-contrôleur
#   2. Méta-contrôleur basé sur le profil cognitif dynamique (INTP par défaut)
#   3. Reward adaptatif (progression_factor, stagnation_penalty)
#   4. Flux non-linéaire : NE peut court-circuiter vers PI_ctrl si autorisation préalable
#   5. 4 contrôleurs comme objets Python indépendants (encapsulation claire)

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


# ===== LuCY v5.0 Constants =====
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False
DEBUG = True
VERSION = '5.0'

MAX_ACTIONS = 3000
MAX_ACTIONS_PER_LEVEL = 500
MIN_STATE_VISITS = 2

# UCB1
UCB1_C = 1.414

# Q-learning
ALPHA = 0.2
GAMMA = 0.9

# Epsilon
EPSILON_START = 0.4
EPSILON_MIN = 0.05
EPSILON_DECAY = 0.995

# Reward v5.0 adaptatif (NOUVEAU)
REWARD_WIN = 10.0
REWARD_LEVEL_UP_BASE = 2.0      # amplifié par progress_rate
REWARD_PROGRESS = 0.05
REWARD_CYCLE_BASE = -0.05       # aggravé par stuck_factor
REWARD_RESET = -0.3
REWARD_AMPLIFY_MAX = 2.0        # facteur max d'amplification
STAGNATION_DECAY = 0.98         # decay du facteur de progression par action nulle

# Bonus
PATTERN_BIAS_BONUS = 0.35
COLOR_MATCH_BONUS = 0.15
PATTERN_CHECKPOINT_INTERVAL = 50

# Actions
STANDARD_ACTIONS = list(range(1, 6))
RESET_ACTION_ID = 0
CLICK_ACTION_ID = 6

# Persistance
PATTERNS_PERSIST_PATH = '/kaggle/working/lucy_game_patterns.json'
COGNITIVE_STATE_PATH = '/kaggle/working/lucy_cognitive_state.json'

# Profils cognitifs (ordre de priorité des contrôleurs)
# Format : (ctrl_name, priority_weight)
COGNITIVE_PROFILES = {
    'INTP': [('DI', 1.4), ('PE', 1.2), ('PI', 1.0), ('DE', 0.8)],   # TI>NE>SI>FE
    'INTJ': [('DI', 1.4), ('PI', 1.2), ('DE', 1.0), ('PE', 0.8)],   # TI>NI>TE>SE
    'ENTP': [('PE', 1.4), ('DI', 1.2), ('DE', 1.0), ('PI', 0.8)],   # NE>TI>TE>SI
    'ADAPTIVE': [('DI', 1.0), ('PE', 1.0), ('PI', 1.0), ('DE', 1.0)], # équilibré
}
DEFAULT_PROFILE = 'INTP'


# ============================================================
# NIVEAU 1 — 8 FONCTIONS COGNITIVES (implémentations)
# ============================================================

def se_encode_frame(frame_raw) -> Tuple[str, str, str, Optional[np.ndarray]]:
    """SE : perception des détails concrets actuels — encode frame en identifiants."""
    if frame_raw is None:
        return 'null_full', 'null_coarse', 'null_colors', None

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
        return h, h[:8], h[:4], None

    if arr.ndim >= 2:
        rows, cols = arr.shape[0], arr.shape[1]
    else:
        rows, cols = arr.shape[0], 1
    shape_prefix = (rows & 0xFFFF).to_bytes(2, 'little') + (cols & 0xFFFF).to_bytes(2, 'little')
    sid_full = hashlib.md5(shape_prefix + arr.tobytes()).hexdigest()[:16]

    try:
        h_b = max(1, arr.shape[0] // 4) if arr.ndim >= 2 else 1
        w_b = max(1, arr.shape[1] // 4) if arr.ndim >= 2 else 1
        coarse = arr[:h_b*4, :w_b*4].reshape(h_b, 4, w_b, 4, -1).mean(axis=(1, 3)).astype(np.uint8)
        cp = (h_b & 0xFF).to_bytes(1, 'little') + (w_b & 0xFF).to_bytes(1, 'little')
        sid_coarse = hashlib.md5(cp + coarse.tobytes()).hexdigest()[:8]
    except Exception:
        sid_coarse = sid_full[:8]

    try:
        pixels = arr.reshape(-1, arr.shape[-1] if arr.ndim == 3 else 1)
        buckets = (pixels // 16).tobytes()[:512]
        cnt = Counter(buckets)
        top3 = ''.join(f'{k:02x}' for k, _ in cnt.most_common(3))
        sid_colors = top3 if top3 else 'nocolor'
    except Exception:
        sid_colors = 'nocolor'

    return sid_full, sid_coarse, sid_colors, arr


def se_find_nonblack_centroid(arr: Optional[np.ndarray]) -> Tuple[int, int]:
    """SE : calcule le centroïde des pixels non-noirs (click stratégique P0-H)."""
    BLACK_THRESHOLD = 16
    if arr is None:
        return 32, 32
    h = arr.shape[0] if arr.ndim >= 1 else 64
    w = arr.shape[1] if arr.ndim >= 2 else 64
    fx, fy = w // 2, h // 2
    try:
        if arr.ndim == 3:
            mask = np.any(arr > BLACK_THRESHOLD, axis=2)
        elif arr.ndim == 2:
            mask = arr > BLACK_THRESHOLD
        else:
            return fx, fy
        ys, xs = np.where(mask)
        if len(ys) == 0:
            return fx, fy
        return int(np.mean(xs)), int(np.mean(ys))
    except Exception:
        return fx, fy


def ne_detect_stuck(n_sa: Dict, n_s: Dict, state_archive: Dict,
                    stuck_counter: int, sid: str, sid_coarse: str,
                    pi_coarse_history: List[str]) -> bool:
    """NE : détecte les blocages — toutes actions essayées ou cycle visuel."""
    info = state_archive.get(sid, {})
    actions_tried = info.get('actions_tried', set())
    all_tried = all(a in actions_tried for a in STANDARD_ACTIONS)

    visual_cycle = False
    if len(pi_coarse_history) >= 4:
        recent_pair = tuple(pi_coarse_history[-2:])
        prev_pair = tuple(pi_coarse_history[-4:-2])
        visual_cycle = (recent_pair == prev_pair)

    return all_tried or stuck_counter > 12 or visual_cycle


def ni_compute_target(q_table: Dict, curr_sid: str,
                      next_available: Tuple[int, ...]) -> float:
    """NI : valeur cible Q Bellman pour l'état suivant."""
    if not next_available:
        next_available = tuple(STANDARD_ACTIONS)
    next_qs = [q_table.get((curr_sid, a), 0.0) for a in next_available]
    return max(next_qs) if next_qs else 0.0


def te_ucb1_score(q_table: Dict, n_sa: Dict, n_s: Dict,
                  sid: str, sid_colors: str,
                  available_actions: Tuple[int, ...],
                  pattern_action: Optional[int],
                  color_action: Optional[int],
                  bias_action: Optional[int]) -> List[Tuple[float, int]]:
    """TE : scoring UCB1 logique des actions candidates."""
    if not available_actions:
        available_actions = tuple(STANDARD_ACTIONS)

    n_sa_sum = sum(n_sa.get((sid, aid), 0) for aid in available_actions)
    n_total = max(1, n_s.get(sid, 0), n_sa_sum)

    scored_inf: List[Tuple[int, int]] = []
    scored_finite: List[Tuple[float, int]] = []

    for aid in available_actions:
        if aid == RESET_ACTION_ID:
            continue
        n_action = n_sa.get((sid, aid), 0)
        q_val = q_table.get((sid, aid), 0.0)
        if n_action == 0:
            scored_inf.append((aid, aid))
        else:
            log_val = math.log(n_total) if n_total > 1 else 0.0
            score = q_val + UCB1_C * math.sqrt(log_val / n_action)
            if bias_action == aid:
                score += 0.2
            if pattern_action == aid:
                score += PATTERN_BIAS_BONUS
            if color_action == aid:
                score += COLOR_MATCH_BONUS
            scored_finite.append((score, aid))

    scored_inf.sort(key=lambda x: x[1])
    scored_finite.sort(key=lambda x: x[0], reverse=True)
    return [(float('inf'), aid) for _, aid in scored_inf] + scored_finite


def ti_detect_cycle(coarse_history: List[str], stuck_counter: int) -> bool:
    """TI : analyse interne de cohérence — cycle détecté."""
    if len(coarse_history) < 4:
        return False
    recent = tuple(coarse_history[-2:])
    prev = tuple(coarse_history[-4:-2])
    return recent == prev or stuck_counter > 12


def fe_suggest_action_for_colors(color_action_rewards: Dict, sid_colors: str) -> Optional[int]:
    """FE : suggestion action basée sur le contexte couleur courant."""
    rewards = color_action_rewards.get(sid_colors)
    if not rewards:
        return None
    best = max(rewards, key=lambda a: rewards[a])
    return best if rewards[best] > 0 else None


def fe_update_color_rewards(color_action_rewards: Dict, sid_colors: str,
                            action_id: int, reward: float) -> None:
    """FE : mise à jour de l'association couleur→action."""
    if reward > 0:
        color_action_rewards[sid_colors][action_id] += reward


def fi_compute_adaptive_reward(
    base_reward: float,
    stuck_counter: int,
    progress_rate: float,
    win: bool,
    level_up: bool,
    is_cycle: bool,
) -> float:
    """FI : calcul du reward adaptatif (NOUVEAU v5.0).

    Logique :
    - Si victoire  : 10.0 (invariant)
    - Si level_up  : 2.0 × min(AMPLIFY_MAX, 1 + progress_rate) — récompense la vitesse
    - Si cycle     : -0.05 × (1 + stuck_factor)                — pénalise l'enlisement
    - Si progrès   : 0.05 (inchangé)
    - Si reset     : -0.3 (inchangé)

    progression_factor = max(0.1, 1.0 + progress_rate × 0.5)
    stuck_factor = min(1.0, stuck_counter / 12.0)
    """
    stuck_factor = min(1.0, stuck_counter / 12.0)

    if win:
        return REWARD_WIN

    if level_up:
        amplify = min(REWARD_AMPLIFY_MAX, 1.0 + progress_rate)
        return REWARD_LEVEL_UP_BASE * amplify

    if base_reward == REWARD_CYCLE_BASE or is_cycle:
        return REWARD_CYCLE_BASE * (1.0 + stuck_factor)

    return base_reward


# ============================================================
# NIVEAU 2 — 4 CONTRÔLEURS SPÉCIALISÉS
# ============================================================

class PI_Controller:
    """Contrôleur PI : NI + SI — Perception Introvertie.

    Orchestre :
    - NI (iNtuition Interne) : anticipation Q Bellman, valeur future
    - SI (Sensation Interne) : patterns accumulés, Q-table, game_patterns

    Responsabilité : évaluer ce qu'on sait déjà + anticiper les conséquences.
    """

    def suggest(self, q_table: Dict, n_sa: Dict, game_patterns: Dict,
                sid_coarse: str, curr_sid: str,
                next_available: Tuple[int, ...]) -> Tuple[Optional[int], float]:
        """Retourne (action_suggérée_depuis_patterns, valeur_future_anticipée)."""
        # SI : lookup pattern
        pattern_action: Optional[int] = None
        for _, pattern in game_patterns.items():
            if pattern.get('from_sid_coarse') == sid_coarse:
                a = pattern.get('action')
                if isinstance(a, int):
                    pattern_action = a
                    break

        # NI : max Q futur
        future_value = ni_compute_target(q_table, curr_sid, next_available)

        return pattern_action, future_value


class PE_Controller:
    """Contrôleur PE : NE + SE — Perception Extravertie.

    Orchestre :
    - NE (iNtuition Externe) : exploration actions inconnues, UCB1-infini
    - SE (Sensation Externe) : perception pixels, centroïde non-noir

    Responsabilité : explorer l'inconnu + percevoir l'environnement actuel.
    """

    def suggest_explore(self, state_archive: Dict, sid: str,
                        available: Tuple[int, ...]) -> Optional[int]:
        """NE : retourne la première action non-essayée (UCB1-infini)."""
        actions_tried = state_archive.get(sid, {}).get('actions_tried', set())
        for aid in sorted(STANDARD_ACTIONS):
            if aid not in actions_tried and aid in available:
                return aid
        return None


class DI_Controller:
    """Contrôleur DI : TI + FI — Décision Introvertie.

    Orchestre :
    - TI (Thinking Interne) : détection cycles, analyse cohérence
    - FI (Feeling Interne)  : valeurs prioritaires (escape, niveau, stuck)

    Responsabilité : détecter les blocages + décider des actions de valeur.
    """

    def evaluate(self, coarse_history: List[str], stuck_counter: int,
                 state_archive: Dict, sid: str,
                 sid_coarse: str) -> Tuple[bool, str]:
        """TI+FI : retourne (is_stuck, priority)."""
        is_cycle = ti_detect_cycle(coarse_history, stuck_counter)
        info = state_archive.get(sid, {})
        visits = info.get('visits', 0)

        if is_cycle:
            priority = 'escape_cycle'
        elif visits < MIN_STATE_VISITS:
            priority = 'explore'
        else:
            priority = 'exploit'

        return is_cycle, priority


class DE_Controller:
    """Contrôleur DE : TE + FE — Décision Extravertie.

    Orchestre :
    - TE (Thinking Externe) : scoring UCB1 logique, tri des candidats
    - FE (Feeling Externe)  : adaptation couleur, suggestion context-aware

    Responsabilité : sélectionner la meilleure action selon scoring + couleur.
    """

    def score(self, q_table: Dict, n_sa: Dict, n_s: Dict,
              color_action_rewards: Dict,
              sid: str, sid_colors: str,
              available: Tuple[int, ...],
              pattern_action: Optional[int],
              bias_action: Optional[int]) -> List[Tuple[float, int]]:
        """TE+FE : scoring complet UCB1 + bonus couleur."""
        color_action = fe_suggest_action_for_colors(color_action_rewards, sid_colors)
        return te_ucb1_score(
            q_table, n_sa, n_s, sid, sid_colors, available,
            pattern_action, color_action, bias_action,
        )


# ============================================================
# NIVEAU 3 — MÉTA-CONTRÔLEUR
# ============================================================

class MetaController:
    """Méta-contrôleur LuCY v5.0 — autorisations et profil cognitif.

    RÈGLE FONDAMENTALE :
    - Les DONNÉES ne passent PAS par le méta-contrôleur.
    - Seules les AUTORISATIONS d'échange entre contrôleurs transitent ici.
    - Les contrôleurs communiquent directement entre eux si l'autorisation est donnée.

    Profil cognitif (INTP par défaut) : TI>NE>SI>FE
        → DI_ctrl prioritaire (TI fort)
        → PE_ctrl secondaire (NE fort)
        → PI_ctrl tertiaire (SI moyen)
        → DE_ctrl quaternaire (FE faible)

    Autorisation court-circuit : si NE a une action non-essayée ET DI dit 'explore',
    autoriser NE→PE_ctrl direct (pas de passage par DE_ctrl).
    """

    def __init__(self, profile: str = DEFAULT_PROFILE):
        self.profile = profile
        self._weights = {name: w for name, w in COGNITIVE_PROFILES.get(profile, COGNITIVE_PROFILES['ADAPTIVE'])}
        # Mémoire d'autorisations préalables (court-circuit)
        self._granted_shortcuts: Set[Tuple[str, str]] = set()

    def get_priority_order(self, context: Dict) -> List[str]:
        """Retourne les contrôleurs dans l'ordre de priorité selon le profil + contexte.

        ADAPTATIF : si stuck_counter élevé → booster DI (TI détection cycles)
                    si nouvelles actions disponibles → booster PE (NE exploration)
        """
        stuck = context.get('stuck_counter', 0)
        has_unexplored = context.get('has_unexplored_actions', False)

        weights = dict(self._weights)
        if stuck > 6:
            weights['DI'] = weights.get('DI', 1.0) * 1.5
        if has_unexplored:
            weights['PE'] = weights.get('PE', 1.0) * 1.3

        return sorted(weights.keys(), key=lambda k: weights[k], reverse=True)

    def authorize_shortcut(self, src_ctrl: str, dst_ctrl: str) -> bool:
        """Donne l'autorisation d'un échange direct entre deux contrôleurs.

        Un échange direct évite le passage par le méta-contrôleur pour les données.
        Ex: NE (dans PE_ctrl) → PI_ctrl direct si l'autorisation a déjà été accordée.
        """
        key = (src_ctrl, dst_ctrl)
        if key in self._granted_shortcuts:
            return True
        # Règle : NE peut court-circuiter vers PI si DI dit 'explore'
        if src_ctrl == 'PE' and dst_ctrl == 'PI':
            self._granted_shortcuts.add(key)
            return True
        # Règle : DE peut court-circuiter vers PE si patterns couleur connus
        if src_ctrl == 'DE' and dst_ctrl == 'PE':
            self._granted_shortcuts.add(key)
            return True
        return False

    def select_action(
        self,
        priority_order: List[str],
        di_result: Tuple[bool, str],
        pe_explore: Optional[int],
        de_scored: List[Tuple[float, int]],
        pi_pattern: Optional[int],
        available: Tuple[int, ...],
        state_archive: Dict,
        sid: str,
        stuck_counter: int,
    ) -> int:
        """Décision finale — délègue aux contrôleurs sans faire transiter les données.

        Logique de résolution (NOUVEAU v5.0) :
        1. DI_ctrl (TI+FI) évalue priority ('escape_cycle' / 'explore' / 'exploit')
        2. Si 'escape_cycle' → PE_ctrl cherche action non-essayée, sinon PI pattern, sinon RESET
        3. Si 'explore' → PE_ctrl fournit l'action UCB1-infinie non-essayée
                       → ou court-circuit PE→PI si PI a un pattern (autorisation méta)
        4. Si 'exploit' → DE_ctrl donne le top UCB1+couleur
        """
        is_cycle, priority = di_result

        if priority == 'escape_cycle':
            if pi_pattern is not None and pi_pattern in available:
                info = state_archive.get(sid, {})
                if pi_pattern not in info.get('actions_tried', set()):
                    return pi_pattern
            if pe_explore is not None:
                return pe_explore
            # Court-circuit accordé par méta : PE peut demander à PI
            if self.authorize_shortcut('PE', 'PI') and pi_pattern is not None:
                return pi_pattern
            return RESET_ACTION_ID

        if priority == 'explore':
            if pe_explore is not None:
                return pe_explore
            # Court-circuit DE→PE accordé si couleurs connues
            if self.authorize_shortcut('DE', 'PE') and de_scored:
                inf_actions = [aid for s, aid in de_scored if s == float('inf')]
                if inf_actions:
                    return inf_actions[0]
            if de_scored:
                return de_scored[0][1]
            return STANDARD_ACTIONS[0]

        # 'exploit'
        if de_scored:
            return de_scored[0][1]
        return STANDARD_ACTIONS[0]


# ============================================================
# LuCYCognition v5.0 — intègre les 3 niveaux
# ============================================================

class LuCYCognition:
    """Noyau cognitif LuCY v5.0.

    Orchestre les 3 niveaux :
    1. Fonctions cognitives (8) via leurs implémentations fonctionnelles
    2. Contrôleurs spécialisés (4) : PI_ctrl, PE_ctrl, DI_ctrl, DE_ctrl
    3. Méta-contrôleur : sélection finale par profil cognitif
    """

    def __init__(self, profile: str = DEFAULT_PROFILE):
        # Mémoire SI
        self.state_archive: Dict[str, Dict] = {}
        self.q_table: Dict[Tuple, float] = {}
        self.n_sa: Dict[Tuple, int] = defaultdict(int)
        self.n_s: Dict[str, int] = defaultdict(int)
        self.game_patterns: Dict[str, Dict] = {}
        self.transition_graph: Dict[Tuple, str] = {}

        # Mémoire FE
        self.color_action_rewards: Dict[str, Dict[int, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        # Historique pour TI (cycles)
        self.coarse_history: List[str] = []

        # État temporel
        self.total_actions = 0
        self.level_count = 0
        self.actions_this_level = 0
        self.stuck_counter = 0
        self.epsilon = EPSILON_START
        self.prev_sid: Optional[str] = None
        self.prev_sid_coarse: Optional[str] = None
        self.prev_sid_colors: Optional[str] = None
        self.prev_action_id: Optional[int] = None

        # Reward adaptatif — tracking progression
        self._progress_rate: float = 0.0    # taux de progression récent
        self._actions_no_progress: int = 0  # actions sans progrès consécutives

        # Contrôleurs niveau 2
        self.pi_ctrl = PI_Controller()
        self.pe_ctrl = PE_Controller()
        self.di_ctrl = DI_Controller()
        self.de_ctrl = DE_Controller()

        # Méta-contrôleur niveau 3
        self.meta = MetaController(profile=profile)

        # Checkpoint
        self._actions_since_checkpoint = 0

        # Chargement état cognitif persisté
        loaded = self._load_cognitive_state()
        if not loaded:
            self._load_patterns()

    # ----------------------------------------------------------------
    # Persistance (héritage v4.1 FIX-2 — inchangé)
    # ----------------------------------------------------------------

    def _save_cognitive_state(self) -> None:
        try:
            q_ser = {f'{sid}|{aid}': v for (sid, aid), v in self.q_table.items()}
            nsa_ser = {f'{sid}|{aid}': c for (sid, aid), c in self.n_sa.items()}
            ns_ser = dict(self.n_s)
            car_ser = {colors: dict(actions)
                       for colors, actions in self.color_action_rewards.items()}
            data = {
                'version': VERSION,
                'timestamp': time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()),
                'q_table': q_ser,
                'n_sa': nsa_ser,
                'n_s': ns_ser,
                'game_patterns': self.game_patterns,
                'color_action_rewards': car_ser,
                'coarse_history': self.coarse_history[-100:],
                'level_count': self.level_count,
                'total_actions': self.total_actions,
                'progress_rate': self._progress_rate,
            }
            tmp = COGNITIVE_STATE_PATH + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(data, f)
            os.replace(tmp, COGNITIVE_STATE_PATH)
            self._save_patterns()
            if DEBUG:
                print(f'[LuCY v{VERSION}] _save_cognitive_state: '
                      f'q={len(q_ser)} n_sa={len(nsa_ser)} patterns={len(self.game_patterns)}')
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] _save_cognitive_state ERROR: {e}')

    def _load_cognitive_state(self) -> bool:
        try:
            if not os.path.exists(COGNITIVE_STATE_PATH):
                return False
            with open(COGNITIVE_STATE_PATH, 'r') as f:
                data = json.load(f)
            self.q_table = {}
            for k, v in data.get('q_table', {}).items():
                parts = k.split('|', 1)
                if len(parts) == 2:
                    try:
                        self.q_table[(parts[0], int(parts[1]))] = float(v)
                    except ValueError:
                        pass
            self.n_sa = defaultdict(int)
            for k, c in data.get('n_sa', {}).items():
                parts = k.split('|', 1)
                if len(parts) == 2:
                    try:
                        self.n_sa[(parts[0], int(parts[1]))] = int(c)
                    except ValueError:
                        pass
            self.n_s = defaultdict(int, {k: int(v) for k, v in data.get('n_s', {}).items()})
            self.game_patterns = data.get('game_patterns', {})
            raw_car = data.get('color_action_rewards', {})
            self.color_action_rewards = defaultdict(lambda: defaultdict(float))
            for colors, actions in raw_car.items():
                for a_str, r in actions.items():
                    try:
                        self.color_action_rewards[colors][int(a_str)] += r
                    except ValueError:
                        pass
            self.coarse_history = data.get('coarse_history', [])
            self.level_count = int(data.get('level_count', 0))
            self.total_actions = int(data.get('total_actions', 0))
            self._progress_rate = float(data.get('progress_rate', 0.0))
            if DEBUG:
                print(f'[LuCY v{VERSION}] _load_cognitive_state: '
                      f'q={len(self.q_table)} patterns={len(self.game_patterns)}')
            return True
        except Exception as e:
            if DEBUG:
                print(f'[LuCY v{VERSION}] _load_cognitive_state ERROR: {e}')
            return False

    def _load_patterns(self) -> None:
        try:
            if os.path.exists(PATTERNS_PERSIST_PATH):
                with open(PATTERNS_PERSIST_PATH, 'r') as f:
                    d = json.load(f)
                self.game_patterns = d.get('game_patterns', {})
        except Exception:
            self.game_patterns = {}

    def _save_patterns(self) -> None:
        try:
            tmp = PATTERNS_PERSIST_PATH + '.tmp'
            with open(tmp, 'w') as f:
                json.dump({'game_patterns': self.game_patterns, 'version': VERSION}, f)
            os.replace(tmp, PATTERNS_PERSIST_PATH)
        except Exception:
            pass

    def _maybe_checkpoint(self) -> None:
        if not self.game_patterns and not self.q_table:
            return
        self._actions_since_checkpoint += 1
        if self._actions_since_checkpoint >= PATTERN_CHECKPOINT_INTERVAL:
            self._save_cognitive_state()
            self._actions_since_checkpoint = 0

    def _get_state_info(self, sid: str) -> Dict:
        if sid not in self.state_archive:
            self.state_archive[sid] = {'visits': 0, 'actions_tried': set(), 'reward_sum': 0.0}
        return self.state_archive[sid]

    # ----------------------------------------------------------------
    # Boucle principale v5.0 — 3 niveaux
    # ----------------------------------------------------------------

    def step(
        self,
        frame_raw,
        lf: Any,
        level_up: bool,
        win: bool,
        available: Tuple[int, ...],
    ) -> GameAction:
        """Étape cognitive complète v5.0 — 3 niveaux en séquence."""

        # ── NIVEAU 1 : Fonctions cognitives ──────────────────────────
        # SE : perception
        sid_full, sid_coarse, sid_colors, arr = se_encode_frame(frame_raw)

        # Mise à jour historique TI
        self.coarse_history.append(sid_coarse)
        if len(self.coarse_history) > 200:
            self.coarse_history = self.coarse_history[-100:]

        # SI : archive état courant
        info = self._get_state_info(sid_full)
        info['visits'] += 1
        self.n_s[sid_full] += 1

        # ── NIVEAU 2 : Contrôleurs ───────────────────────────────────
        # PI_ctrl (NI+SI) : pattern + valeur future
        pi_pattern, future_value = self.pi_ctrl.suggest(
            self.q_table, self.n_sa, self.game_patterns,
            sid_coarse, sid_full, available,
        )

        # PE_ctrl (NE+SE) : action exploratoire
        pe_explore = self.pe_ctrl.suggest_explore(self.state_archive, sid_full, available)

        # DI_ctrl (TI+FI) : détection cycle + priorité
        di_result = self.di_ctrl.evaluate(
            self.coarse_history, self.stuck_counter,
            self.state_archive, sid_full, sid_coarse,
        )

        # Biais successfull actions (FI héritage)
        bias_action: Optional[int] = None
        if self.game_patterns:
            cnt = Counter(p.get('action') for p in self.game_patterns.values()
                          if isinstance(p.get('action'), int))
            if cnt:
                bias_action = cnt.most_common(1)[0][0]

        # DE_ctrl (TE+FE) : scoring UCB1 + couleur
        de_scored = self.de_ctrl.score(
            self.q_table, self.n_sa, self.n_s, self.color_action_rewards,
            sid_full, sid_colors, available, pi_pattern, bias_action,
        )

        # ── NIVEAU 3 : Méta-contrôleur ──────────────────────────────
        has_unexplored = pe_explore is not None
        ctx = {'stuck_counter': self.stuck_counter, 'has_unexplored_actions': has_unexplored}
        priority_order = self.meta.get_priority_order(ctx)

        action_id = self.meta.select_action(
            priority_order, di_result, pe_explore, de_scored,
            pi_pattern, available, self.state_archive, sid_full, self.stuck_counter,
        )

        # ── Q-LEARNING update (si pas premier pas) ──────────────────
        if self.prev_sid is not None and self.prev_action_id is not None:
            prev_sid = self.prev_sid
            prev_coarse = self.prev_sid_coarse or sid_coarse
            prev_colors = self.prev_sid_colors or 'nocolor'
            prev_action = self.prev_action_id

            # FI reward adaptatif (NOUVEAU v5.0)
            is_same_state = (prev_sid == sid_full)
            base = REWARD_CYCLE_BASE if is_same_state else (
                REWARD_RESET if prev_action == RESET_ACTION_ID else REWARD_PROGRESS
            )
            reward = fi_compute_adaptive_reward(
                base, self.stuck_counter, self._progress_rate,
                win, level_up, is_same_state,
            )

            # Mise à jour progress_rate (FI tracking)
            if reward > 0:
                self._progress_rate = min(1.0, self._progress_rate + 0.05)
                self._actions_no_progress = 0
            else:
                self._actions_no_progress += 1
                self._progress_rate *= STAGNATION_DECAY

            # Q update Bellman
            old_q = self.q_table.get((prev_sid, prev_action), 0.0)
            max_next = ni_compute_target(self.q_table, sid_full, available)
            new_q = old_q + ALPHA * (reward + GAMMA * max_next - old_q)
            self.q_table[(prev_sid, prev_action)] = new_q

            # Compteurs UCB1
            self.n_sa[(prev_sid, prev_action)] += 1

            # Graphe transitions
            self.transition_graph[(prev_sid, prev_action)] = sid_full

            # FE : update color rewards (héritage FIX-1 : prev_colors)
            fe_update_color_rewards(self.color_action_rewards, prev_colors, prev_action, reward)

            # NI stuck counter (héritage P0-I)
            if prev_action == RESET_ACTION_ID and sid_full != prev_sid:
                self.stuck_counter = 0
            elif is_same_state:
                self.stuck_counter += 1
            elif reward <= 0:
                self.stuck_counter = max(0, self.stuck_counter - 1)
            else:
                self.stuck_counter = 0

            # Persistance sur level_up
            if level_up:
                info['actions_tried'].add(prev_action)
                level_key = str(self.level_count)
                self.game_patterns[level_key] = {
                    'action': prev_action,
                    'from_sid_coarse': prev_coarse,
                    'to_sid_coarse': sid_coarse,
                }
                self.level_count += 1
                self.actions_this_level = 0
                self._save_cognitive_state()
                self._actions_since_checkpoint = 0

            info['reward_sum'] += reward
            info['actions_tried'].add(prev_action)

            if DEBUG and (level_up or win or reward <= -0.25):
                print(f'[LuCY v{VERSION}] Q-update: ({prev_sid[:6]},{prev_action})'
                      f' reward={reward:.3f} (base={base:.3f} progress={self._progress_rate:.2f}'
                      f' stuck={self.stuck_counter})')

        # Mémoriser l'état courant pour le prochain step
        self.prev_sid = sid_full
        self.prev_sid_coarse = sid_coarse
        self.prev_sid_colors = sid_colors
        self.prev_action_id = action_id
        self.total_actions += 1
        self.actions_this_level += 1

        # Checkpoint périodique
        self._maybe_checkpoint()

        # Construction GameAction
        if action_id == CLICK_ACTION_ID and arr is not None:
            cx, cy = se_find_nonblack_centroid(arr)
            if DEBUG:
                print(f'[LuCY v{VERSION}] click centroid ({cx},{cy}) | meta_priority={di_result[1]}')
            return _build_action(CLICK_ACTION_ID, x=cx, y=cy)
        return _build_action(action_id)


def _build_action(action_id: int, x: int = 32, y: int = 32) -> GameAction:
    """Construit un GameAction de façon robuste."""
    try:
        if action_id == RESET_ACTION_ID and hasattr(GameAction, 'RESET'):
            return GameAction.RESET
        action = (GameAction.from_id(action_id) if hasattr(GameAction, 'from_id')
                  else GameAction(action_id))
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


# ============================================================
# LuCYAgent v5.0
# ============================================================

class LuCYAgent(Agent):
    """Agent LuCY v5.0 pour ARC-AGI-3.

    Architecture 3 niveaux :
    - 8 fonctions cognitives (SE/SI/NE/NI/TE/TI/FE/FI)
    - 4 contrôleurs (PI_ctrl/PE_ctrl/DI_ctrl/DE_ctrl)
    - 1 méta-contrôleur (profil cognitif INTP par défaut, flux non-linéaire)

    Reward adaptatif : amplification selon progress_rate, pénalité selon stuck_counter.
    """

    MAX_ACTIONS = MAX_ACTIONS

    def __init__(self, *args, profile: str = DEFAULT_PROFILE, **kwargs):
        super().__init__(*args, **kwargs)
        self.cognition = LuCYCognition(profile=profile)
        self._prev_levels = 0
        self._started = False
        self._t_start = time.time()
        print(f'[LuCY v{VERSION}] Agent initialisé | profile={profile}')
        print(f'  CERTIFIED_100={CERTIFIED_100} | DEBUG={DEBUG}')
        print(f'  Architecture: 8 fonctions → 4 contrôleurs → 1 méta-contrôleur')
        print(f'  Reward adaptatif: level_up_base={REWARD_LEVEL_UP_BASE} × progress_rate')
        print(f'  Profil: {COGNITIVE_PROFILES.get(profile)}')

    def is_done(self, frames: List[Any], lf: Any) -> bool:
        state = getattr(lf, 'state', None)
        if state in (GameState.WIN, GameState.GAME_OVER):
            cog = self.cognition
            elapsed = time.time() - self._t_start
            print(f'[LuCY v{VERSION}] Fin: state={state} actions={cog.total_actions} '
                  f'levels={cog.level_count} t={elapsed:.1f}s '
                  f'progress_rate={cog._progress_rate:.3f}')
            return True
        if self.action_counter >= self.MAX_ACTIONS:
            print(f'[LuCY v{VERSION}] Budget épuisé: {self.action_counter}')
            return True
        return False

    def choose_action(self, frames: List[Any], lf: Any) -> GameAction:
        """Délègue entièrement au noyau cognitif v5.0 à 3 niveaux."""
        frame_raw = getattr(lf, 'frame', None)
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
                print(f'[LuCY v{VERSION}] Premier step | budget={MAX_ACTIONS} available={available}')

        return self.cognition.step(frame_raw, lf, level_up, win, available)


# ============================================================
# END lucy_agent_v50.py — LuCY v5.0 (3 niveaux + reward adaptatif)
# ============================================================
