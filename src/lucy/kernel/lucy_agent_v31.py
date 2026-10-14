# LuCY Cognitive Agent v3.1 for ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
# Phase 5.1 : Corrections P0-A..P0-F audit critique L-010
#
# Corrections v3.1 vs v3 :
# P0-A : UCB1 — invariant n_s[sid] >= sum(n_sa[(sid,aid)]) garanti + log(1)=0 guard
# P0-B : PE hash — hash sur TOUS les bytes (plus de troncature à 8192)
# P0-C : Reward shaping — REWARD_STATE_CHANGE supprimé (signal parasite)
# P0-D : UCB1 explore — tri stable parmi scores infinis (non-essayées d'abord)
# P0-E : Persistance — game_patterns sauvegardé/chargé sur disque JSON
# P0-F : RESET enregistré dans Q-table + n_sa pour apprentissage

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


# ===== LuCY v3.1 Cognitive Constants =====
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False
DEBUG = True
VERSION = '3.1'

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

# Récompenses v3.1 — P0-C : REWARD_STATE_CHANGE RETIRÉ (signal parasite)
# AVANT (v3) : REWARD_STATE_CHANGE = 0.15 → récompensait tout changement même cyclique
# APRÈS (v3.1) : seuls les vrais progrès (level_up, win) sont récompensés
REWARD_LEVEL_UP = 2.0        # niveau complété
REWARD_WIN = 10.0            # victoire finale
REWARD_CYCLE = -0.05         # pénalité cycle improductif
REWARD_RESET = -0.3          # pénalité reset

# Actions disponibles dans arcengine
STANDARD_ACTIONS = list(range(1, 6))
RESET_ACTION_ID = 0
CLICK_ACTION_ID = 6

# P0-E : fichier de persistance des patterns inter-niveaux
PATTERNS_PERSIST_PATH = '/kaggle/working/lucy_game_patterns.json'


# =========================================================
# PE — Perception Étendue v3.1
# P0-B : hash sur TOUS les bytes (suppression de la troncature [:8192])
# =========================================================

def pe_encode_frame(frame_raw) -> Tuple[str, str, str]:
    """Encode le frame en identifiants multi-résolution.

    v3.1 — P0-B : hash calculé sur arr.tobytes() complet (PLUS de [:8192]).
    La troncature à 8192 bytes provoquait des collisions sémantiques sur
    les grandes grilles où seule la fin du tableau différait.

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
        # P0-B fix : pas de [:8192] sur la chaîne non plus
        raw = str(frame_raw).encode()
        h = hashlib.md5(raw).hexdigest()[:16]
        return h, h[:8], h[:4]

    # sid_full : P0-B — hash sur TOUS les bytes (pas de troncature)
    # AVANT (v3) : hashlib.md5(arr.tobytes()[:8192]).hexdigest()[:16]
    # APRÈS (v3.1) : hashlib.md5(arr.tobytes()).hexdigest()[:16]
    sid_full = hashlib.md5(arr.tobytes()).hexdigest()[:16]

    # sid_coarse : réduction 4×4 (invariant au bruit mineur)
    try:
        h_blocks = max(1, arr.shape[0] // 4) if arr.ndim >= 2 else 1
        w_blocks = max(1, arr.shape[1] // 4) if arr.ndim >= 2 else 1
        coarse = arr[:h_blocks*4, :w_blocks*4].reshape(
            h_blocks, 4, w_blocks, 4, -1
        ).mean(axis=(1, 3)).astype(np.uint8)
        sid_coarse = hashlib.md5(coarse.tobytes()).hexdigest()[:8]
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
# LuCYCognition v3.1
# P0-A : UCB1 invariant garanti
# P0-E : persistance game_patterns
# P0-F : RESET enregistré dans Q-table
# =========================================================

class LuCYCognition:
    """
    Noyau cognitif LuCY v3.1 — 6 corrections P0.

    Opérateurs actifs :
    - SE : Perception multi-résolution (via PE v3.1 — P0-B hash complet)
    - SI : Mémoire d'états avec Q-values
    - NE : Détection de blocage
    - NI : Compteur de cycles + PI
    - TE : UCB1 garanti (P0-A + P0-D)
    - TI : Budget check + cohérence
    - FE : Détection victoire + progress signal
    - FI : Epsilon adaptatif via PI
    + PE : Perception Étendue multi-résolution (P0-B)
    + PI : Pattern Interne
    """

    def __init__(self):
        # SI : mémoire d'états
        self.state_archive: Dict[str, Dict] = {}

        # Graphe de transitions
        self.transition_graph: Dict[Tuple, str] = {}

        # Q-table — P0-F : inclut (sid, RESET_ACTION_ID)
        self.q_table: Dict[Tuple, float] = {}

        # Compteurs UCB1
        # P0-A : invariant n_s[sid] = sum des n_sa[(sid,aid)] pour tout aid
        # Géré en incrémentant les deux ensemble dans update()
        self.n_sa: Dict[Tuple, int] = defaultdict(int)
        self.n_s: Dict[str, int] = defaultdict(int)

        # P0-E : game_patterns persisté sur disque
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

    # ---- P0-E : persistance game_patterns ----
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

    # ---- TE : UCB1 v3.1 — P0-A + P0-D ----
    def te_ucb1_score_actions(
        self, sid: str, available_actions: Tuple[int, ...]
    ) -> List[Tuple[float, int]]:
        """Score les actions avec UCB1.

        v3.1 — P0-A :
        - n_total garanti >= 1 (déjà présent) mais aussi :
          n_total = max(n_s[sid], sum(n_sa[(sid,aid)] pour tous aid))
          Ceci empêche n_sa[(sid,aid)] > n_s[sid] (état incohérent)
        - Si n_total = 1 et n_action = 1 : log(1)/1 = 0 → score = q_val (pas de division par zéro)

        v3.1 — P0-D :
        - Les actions non essayées (score=inf) sont triées par leur index de priorité
          (action la moins récemment essayée en premier) plutôt qu'aléatoirement.
          Cela donne un ordre stable et reproductible.
        """
        if not available_actions:
            available_actions = tuple(STANDARD_ACTIONS)

        # P0-A : garantir la cohérence des compteurs
        n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions
                       if aid != RESET_ACTION_ID)
        # n_total = max des deux pour absorber toute dérive possible
        n_total = max(1, self.n_s[sid], n_sa_sum)

        scored_inf: List[Tuple[int, int]] = []   # (priority_idx, aid) pour scores infinis
        scored_finite: List[Tuple[float, int]] = []  # (score, aid) pour scores finis

        for idx, aid in enumerate(available_actions):
            if aid == RESET_ACTION_ID:
                continue

            n_action = self.n_sa.get((sid, aid), 0)
            q_val = self.q_table.get((sid, aid), 0.0)

            if n_action == 0:
                # P0-D : stocker avec index d'ordre pour tri stable
                scored_inf.append((idx, aid))
            else:
                # UCB1 standard — log(n_total) >= 0 garanti car n_total >= 1
                log_val = math.log(n_total) if n_total > 1 else 0.0
                exploration_bonus = UCB1_C * math.sqrt(log_val / n_action)
                ucb_score = q_val + exploration_bonus

                # Bonus PI : action souvent réussie
                if self.pi.suggest_action_bias() == aid:
                    ucb_score += 0.2

                scored_finite.append((ucb_score, aid))

        # P0-D : trier les infinis par ordre d'index (priorité stable, pas aléatoire)
        scored_inf.sort(key=lambda x: x[0])
        inf_list = [(float('inf'), aid) for _, aid in scored_inf]

        # Trier les finis par score décroissant
        scored_finite.sort(key=lambda x: x[0], reverse=True)

        # Résultat : non-essayées en premier (ordre stable), puis exploitation UCB1
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

    # ---- Arbitrateur v3.1 ----
    def arbitrate(
        self, sid: str, sid_coarse: str,
        available_actions: Tuple[int, ...], lf
    ) -> int:
        """Synthèse des 10 opérateurs → choix d'action."""
        win_prox = self.fe_detect_win_proximity(lf)
        if win_prox >= 1.0:
            return STANDARD_ACTIONS[0]

        if not self.ti_check_consistency():
            return RESET_ACTION_ID

        priority = self.fi_get_priority(sid, sid_coarse)

        if priority == 'escape_cycle':
            info = self.si_get_state_info(sid)
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

        # TE (UCB1) : scorer les actions (résultat déjà trié — P0-D stable)
        scored = self.te_ucb1_score_actions(sid, available_actions)
        if not scored:
            return STANDARD_ACTIONS[0]

        if priority == 'explore':
            # P0-D : parmi les non-essayées (score inf), prendre la première
            # (ordre stable par index), sinon parmi top-3 finis
            inf_actions = [aid for score, aid in scored if score == float('inf')]
            if inf_actions:
                return inf_actions[0]  # premier non-essayé (ordre stable)
            finite_actions = [aid for score, aid in scored if score != float('inf')]
            top_k = finite_actions[:3]
            return random.choice(top_k) if top_k else STANDARD_ACTIONS[0]

        # Exploit : argmax UCB1
        return scored[0][1]

    # ---- Mise à jour Q-learning v3.1 ----
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
    ) -> float:
        """Met à jour Q-table + mémoire cognitive + PI.

        v3.1 corrections :
        P0-C : REWARD_STATE_CHANGE supprimé — seuls win/level_up/cycle/reset comptent
        P0-F : action_id = RESET_ACTION_ID enregistré dans Q-table et n_sa

        Returns:
            reward obtenu
        """
        info = self.si_get_state_info(prev_sid)
        info['visits'] += 1
        info['actions_tried'].add(action_id)

        # P0-C : Récompense shapée v3.1
        # SUPPRIMÉ : elif curr_sid != prev_sid: reward += REWARD_STATE_CHANGE
        # Raison : récompenser tout changement d'état induisait des boucles
        # entre deux états (A→B→A→B...) où chaque transition rapportait +0.15
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
        else:
            reward += REWARD_CYCLE  # pénalité cycle (état inchangé ou déjà vu)

        # Q-learning update
        old_q = self.q_table.get((prev_sid, action_id), 0.0)
        # P0-F : max_next_q inclut toutes les actions possibles y compris RESET
        all_actions = STANDARD_ACTIONS + [RESET_ACTION_ID]
        next_qs = [self.q_table.get((curr_sid, a), 0.0) for a in all_actions]
        max_next_q = max(next_qs) if next_qs else 0.0
        new_q = old_q + ALPHA * (reward + GAMMA * max_next_q - old_q)
        self.q_table[(prev_sid, action_id)] = new_q

        # P0-A + P0-F : compteurs UCB1 — RESET inclus dans n_sa et n_s
        # n_s[sid] est incrémenté une fois par update() (pas par action_id)
        # Invariant maintenu : n_s[sid] >= n_sa[(sid, any_aid)] car chaque
        # update() incrémente n_s de 1 et n_sa[(sid, action_id)] de 1 seulement
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
# LuCYAgent v3.1
# =========================================================

class LuCYAgent(Agent):
    """
    Agent LuCY v3.1 pour ARC-AGI-3.

    Corrections v3.1 vs v3 :
    - P0-A : UCB1 invariant n_s >= n_sa garanti + log(1)=0 guard
    - P0-B : PE hash sur tous les bytes (suppression troncature [:8192])
    - P0-C : REWARD_STATE_CHANGE supprimé (signal parasite boucles A→B→A)
    - P0-D : Exploration non-essayées en ordre stable (plus de random parmi inf)
    - P0-E : game_patterns persisté sur disque JSON entre parties
    - P0-F : RESET enregistré dans Q-table + n_sa pour apprentissage réel
    """

    MAX_ACTIONS = MAX_ACTIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cognition = LuCYCognition()
        self._prev_levels = 0
        self._started = False
        self._t_start = time.time()
        print(f'[LuCY v{VERSION}] Agent initialized | game_id={getattr(self, "game_id", "unknown")}')
        print(f'  CERTIFIED_100={CERTIFIED_100} | DEBUG={DEBUG}')
        print(f'  UCB1_C={UCB1_C} | ALPHA={ALPHA} | GAMMA={GAMMA} | EPS0={EPSILON_START}')
        print(f'  Corrections: P0-A(UCB1 invariant) P0-B(hash complet) P0-C(reward) '
              f'P0-D(explore stable) P0-E(persist) P0-F(RESET Q-learning)')

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
        """Sélectionne une action via le noyau cognitif LuCY v3.1."""
        frame_raw = getattr(lf, 'frame', None)
        sid_full, sid_coarse, sid_colors, arr = self.cognition.se_perceive(frame_raw)

        curr_levels = getattr(lf, 'levels_completed', 0)
        level_up = curr_levels > self._prev_levels
        self._prev_levels = curr_levels

        state = getattr(lf, 'state', None)
        win = (state == GameState.WIN)

        if not self._started:
            self._started = True
            if DEBUG:
                avail = getattr(lf, 'available_actions', ())
                print(f'[LuCY v{VERSION}] First action | sid_full={sid_full[:8]} | '
                      f'sid_coarse={sid_coarse} | available={avail}')

        if (self.cognition.prev_sid is not None
                and self.cognition.prev_action_id is not None):
            reward = self.cognition.update(
                self.cognition.prev_sid,
                self.cognition.prev_sid_coarse or sid_coarse,
                sid_full,
                sid_coarse,
                sid_colors,
                self.cognition.prev_action_id,
                level_up,
                win=win,
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

        available = getattr(lf, 'available_actions', ())
        if not available:
            available = tuple(STANDARD_ACTIONS)

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
# END lucy_agent_v31.py — LuCY v3.1 (P0-A..P0-F corrigés)
# ============================================================
