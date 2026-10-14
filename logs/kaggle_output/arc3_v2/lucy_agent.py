# LuCY Cognitive Agent for ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
# Architecture: 8 operators (SE/SI/NE/NI/TE/TI/FE/FI) + Arbitrator

from __future__ import annotations

import hashlib
import math
import random
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agents.agent import Agent
from arcengine import GameAction, GameState


# ===== LuCY Cognitive Constants =====
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False
DEBUG = True
MAX_ACTIONS = 3000          # budget d'actions par jeu
MAX_ACTIONS_PER_LEVEL = 400 # budget par niveau
MIN_STATE_VISITS = 3        # seuil exploration → exploitation

# Actions disponibles dans arcengine (id 0-7)
# 0=RESET, 1=ACTION1, 2=ACTION2, 3=ACTION3, 4=ACTION4, 5=ACTION5,
# 6=CLICK(x,y), 7=ACTION7
STANDARD_ACTIONS = list(range(1, 6))  # actions non-risquées
RESET_ACTION_ID = 0
CLICK_ACTION_ID = 6


def state_id(frame_raw) -> str:
    """Fingerprint déterministe d'un état visuel."""
    if frame_raw is None:
        return "null_state"
    if hasattr(frame_raw, 'tobytes'):
        return hashlib.md5(frame_raw.tobytes()[:4096]).hexdigest()[:16]
    return hashlib.md5(str(frame_raw).encode()).hexdigest()[:16]


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


class LuCYCognition:
    """
    Noyau cognitif LuCY simplifié pour l'interaction en temps réel.

    Les 8 opérateurs sont intégrés dans une boucle d'exploration cognitive :
    - SE (Sens External) : perception du frame courant
    - SI (Sens Internal) : état interne de la mémoire d'états
    - NE (Négatif External) : hypothèses sur ce qui ne fonctionne pas
    - NI (Négatif Internal) : identification des cycles improductifs
    - TE (Test External) : évaluation des actions disponibles
    - TI (Test Internal) : vérification de cohérence interne
    - FE (Finalité External) : but observable dans l'environnement
    - FI (Finalité Internal) : but interne de progression
    """

    def __init__(self):
        self.state_archive: Dict[str, Dict] = {}  # sid -> {visits, actions_tried, reward_sum}
        self.transition_graph: Dict[Tuple, str] = {}  # (sid, action_id) -> next_sid
        self.action_rewards: Dict[Tuple, float] = {}  # (sid, action_id) -> reward
        self.level_start_sid: Optional[str] = None
        self.actions_this_level = 0
        self.total_actions = 0
        self.level_count = 0
        self.prev_sid: Optional[str] = None
        self.prev_action_id: Optional[int] = None
        self.best_reward_this_level = 0.0
        self.stuck_counter = 0
        self.last_frame_hash: Optional[str] = None

    # ---- SE : Perception du frame ----
    def se_perceive(self, frame_raw) -> Tuple[str, Optional[np.ndarray]]:
        """Encode le frame en identifiant d'état."""
        if frame_raw is None:
            return 'null', None
        if isinstance(frame_raw, list):
            arr = np.array(frame_raw[0], dtype=np.uint8) if frame_raw else None
        elif isinstance(frame_raw, np.ndarray):
            arr = frame_raw.astype(np.uint8)
        else:
            arr = None
        sid = state_id(arr)
        return sid, arr

    # ---- SI : État interne ----
    def si_get_state_info(self, sid: str) -> Dict:
        """Récupère les infos mémorisées pour cet état."""
        if sid not in self.state_archive:
            self.state_archive[sid] = {
                'visits': 0,
                'actions_tried': set(),
                'reward_sum': 0.0,
            }
        return self.state_archive[sid]

    # ---- NE : Hypothèses négatives ----
    def ne_detect_stuck(self, sid: str) -> bool:
        """Détecte si on est bloqué dans un cycle."""
        info = self.si_get_state_info(sid)
        # Bloqué si on a essayé toutes les actions standard
        all_tried = all(a in info['actions_tried'] for a in STANDARD_ACTIONS)
        return all_tried or self.stuck_counter > 15

    # ---- NI : Identification des cycles improductifs ----
    def ni_count_stuck(self, prev_sid: str, curr_sid: str) -> None:
        """Incrémente le compteur de blocage si l'état n'a pas changé."""
        if prev_sid == curr_sid:
            self.stuck_counter += 1
        else:
            self.stuck_counter = 0

    # ---- TE : Évaluation des actions disponibles ----
    def te_score_actions(
        self, sid: str, available_actions: Tuple[int, ...]
    ) -> List[Tuple[float, int]]:
        """Score les actions disponibles selon les récompenses passées."""
        info = self.si_get_state_info(sid)
        scored = []
        if not available_actions:
            available_actions = tuple(STANDARD_ACTIONS)

        for aid in available_actions:
            if aid == RESET_ACTION_ID:
                continue  # éviter reset sauf si bloqué
            reward = self.action_rewards.get((sid, aid), 0.0)
            # Bonus exploration pour actions non essayées
            if aid not in info['actions_tried']:
                reward += 0.5
            # Bonus pour actions connues comme efficaces
            transition = self.transition_graph.get((sid, aid))
            if transition and transition != sid:
                reward += 0.3  # cette action change l'état
            scored.append((reward, aid))

        scored.sort(reverse=True)
        return scored

    # ---- TI : Vérification cohérence interne ----
    def ti_check_consistency(self) -> bool:
        """Vérifie la cohérence de l'état interne."""
        return (
            self.total_actions < MAX_ACTIONS
            and self.actions_this_level < MAX_ACTIONS_PER_LEVEL
        )

    # ---- FE : But observable ----
    def fe_detect_win_proximity(self, lf) -> float:
        """Estime la proximité d'une victoire depuis le frame."""
        if lf is None:
            return 0.0
        state = getattr(lf, 'state', None)
        if state == GameState.WIN:
            return 1.0
        levels = getattr(lf, 'levels_completed', 0)
        if levels > self.level_count:
            return 0.8  # niveau complété
        return 0.0

    # ---- FI : But interne ----
    def fi_get_priority(self) -> str:
        """Retourne la priorité cognitife courante."""
        if self.stuck_counter > 10:
            return 'escape_cycle'
        info = self.si_get_state_info(self.prev_sid or 'start')
        if info['visits'] < MIN_STATE_VISITS:
            return 'explore'
        return 'exploit'

    # ---- Arbitrateur ----
    def arbitrate(
        self, sid: str, available_actions: Tuple[int, ...], lf
    ) -> int:
        """
        Synthèse des 8 opérateurs → choix d'action.
        Retourne l'action_id sélectionné.
        """
        # FE : Victoire proche ?
        win_prox = self.fe_detect_win_proximity(lf)
        if win_prox >= 1.0:
            return STANDARD_ACTIONS[0]  # déjà gagné, continuer

        # TI : Cohérence interne
        if not self.ti_check_consistency():
            return RESET_ACTION_ID

        # NE + NI : Détection de blocage
        priority = self.fi_get_priority()
        if priority == 'escape_cycle':
            # Choisir une action non encore essayée depuis cet état
            info = self.si_get_state_info(sid)
            for aid in STANDARD_ACTIONS:
                if aid not in info['actions_tried']:
                    return aid
            # Toutes essayées → choisir la meilleure connue
            self.stuck_counter = 0
            scored = self.te_score_actions(sid, available_actions)
            if scored:
                return scored[0][1]
            return STANDARD_ACTIONS[0]

        # TE : Score les actions
        scored = self.te_score_actions(sid, available_actions)
        if not scored:
            return STANDARD_ACTIONS[0]

        # FI : explore vs exploit
        if priority == 'explore' and len(scored) > 1:
            # Exploration : choisir parmi les meilleures avec bruit
            top_k = scored[:3]
            return random.choice(top_k)[1]

        return scored[0][1]

    def update(
        self,
        prev_sid: str,
        curr_sid: str,
        action_id: int,
        level_up: bool,
    ) -> None:
        """Met à jour la mémoire cognitive après une action."""
        info = self.si_get_state_info(prev_sid)
        info['visits'] += 1
        info['actions_tried'].add(action_id)

        # Récompense
        reward = 0.0
        if curr_sid != prev_sid:
            reward += 0.1  # état différent = bon
        if level_up:
            reward += 1.0
            self.level_count += 1
            self.actions_this_level = 0

        info['reward_sum'] += reward
        self.action_rewards[(prev_sid, action_id)] = reward
        self.transition_graph[(prev_sid, action_id)] = curr_sid

        # NI update
        self.ni_count_stuck(prev_sid, curr_sid)
        self.prev_sid = curr_sid
        self.total_actions += 1
        self.actions_this_level += 1

        if self.best_reward_this_level < reward:
            self.best_reward_this_level = reward


class LuCYAgent(Agent):
    """
    Agent LuCY pour ARC-AGI-3.

    Implémente l'interface Agent du framework ARC-AGI-3-Agents.
    Utilise le noyau cognitif LuCYCognition (8 opérateurs + Arbitrateur)
    pour naviguer dans chaque environnement de façon adaptative.
    """

    MAX_ACTIONS = MAX_ACTIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cognition = LuCYCognition()
        self._prev_levels = 0
        self._started = False
        print(f'[LuCY] Agent initialized | game_id={getattr(self, "game_id", "unknown")}')
        print(f'       CERTIFIED_100={CERTIFIED_100} | DEBUG={DEBUG}')

    def is_done(self, frames: List[Any], lf: Any) -> bool:
        """Fin de jeu si victoire, game-over, ou budget épuisé."""
        state = getattr(lf, 'state', None)
        if state in (GameState.WIN, GameState.GAME_OVER):
            if DEBUG:
                print(f'[LuCY] Game ended: state={state}')
            return True
        if self.action_counter >= self.MAX_ACTIONS:
            if DEBUG:
                print(f'[LuCY] Budget épuisé: {self.action_counter} actions')
            return True
        return False

    def choose_action(self, frames: List[Any], lf: Any) -> GameAction:
        """Sélectionne une action via le noyau cognitif LuCY."""
        # SE : Perception
        frame_raw = getattr(lf, 'frame', None)
        sid, arr = self.cognition.se_perceive(frame_raw)

        # Détection level-up
        curr_levels = getattr(lf, 'levels_completed', 0)
        level_up = curr_levels > self._prev_levels
        self._prev_levels = curr_levels

        # Log de démarrage
        if not self._started:
            self._started = True
            if DEBUG:
                avail = getattr(lf, 'available_actions', ())
                print(f'[LuCY] First action | sid={sid} | available={avail}')

        # Mise à jour de la mémoire (si pas le premier pas)
        if self.cognition.prev_sid is not None and self.cognition.prev_action_id is not None:
            self.cognition.update(
                self.cognition.prev_sid,
                sid,
                self.cognition.prev_action_id,
                level_up,
            )
        else:
            # Premier pas : initialiser
            self.cognition.prev_sid = sid
            info = self.cognition.si_get_state_info(sid)
            info['visits'] += 1

        # Available actions
        available = getattr(lf, 'available_actions', ())
        if not available:
            available = tuple(STANDARD_ACTIONS)

        # Arbitrage cognitif
        action_id = self.cognition.arbitrate(sid, available, lf)
        self.cognition.prev_action_id = action_id
        self.cognition.prev_sid = sid

        # Construire l'action
        if action_id == CLICK_ACTION_ID and arr is not None:
            # Click au centre du frame
            h, w = arr.shape[:2] if arr.ndim >= 2 else (64, 64)
            action = build_action(CLICK_ACTION_ID, x=w // 2, y=h // 2)
        else:
            action = build_action(action_id)

        return action
# ============================================================
# CELL 2 — Agent LuCY (écrit dans un fichier pour main.py)
# Architecture : 8 opérateurs cognitifs + heuristiques ARC
# ============================================================
