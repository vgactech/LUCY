# LuCY Cognitive Agent v6.0 for ARC-AGI-3
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
#
# ============================================================
# ARCHITECTURE v6.0 — DIAGNOSTIC COMPLET ET CORRECTION RACINE
# ============================================================
#
# PROBLÈME FONDAMENTAL IDENTIFIÉ (L-019, L-020) :
#   Les versions v1→v5 implémentaient un agent RL tabular pour
#   jeux vidéo (score=0% sur tous les jeux ARC-AGI-3).
#   Cause racine : Q-table sur fingerprints MD5 de frames → jamais
#   de généralisation entre états visuellement proches.
#
# SOLUTION v6.0 — STRATÉGIE HYBRIDE EN 3 PHASES :
#
#   Phase 1 — EXPLORATION SYSTÉMATIQUE (niveaux 1 à N)
#     - Teste TOUTES les actions disponibles une fois chacune
#     - Mémorise les transitions utiles : action → delta_frame → reward
#     - Détecte les actions "progress" (changement de frame utile)
#     - Détecte les actions "level_up" (levels_completed augmente)
#
#   Phase 2 — EXPLOITATION GUIDÉE
#     - Répète les séquences d'actions qui ont déjà fait avancer
#     - Maintient un registre "game_model" par game_id :
#       {action_id: (success_count, fail_count, avg_delta)}
#     - Priorité aux actions avec meilleur taux de succès
#
#   Phase 3 — RÉCUPÉRATION INTELLIGENTE
#     - Si stuck (même état répété 5× sans progress) → RESET
#     - Après RESET → reprendre Phase 1 avec le knowledge accumulé
#     - Limite globale MAX_ACTIONS pour éviter timeout Kaggle
#
# SCORING ARC-AGI-3 (RHAE — Relative Human Action Efficiency) :
#   score = (human_baseline_actions / ai_actions)² par niveau
#   → Objectif : compléter au moins 1 niveau par jeu
#   → Secondaire : le faire efficacement (peu d'actions)
#
# CONFORMITÉ OFFICIELLE :
#   - Hérite de Agent (arcprize/ARC-AGI-3-Agents)
#   - Interface : choose_action(frames, latest_frame) → GameAction
#   - is_done(frames, latest_frame) → bool
#   - Compatible avec le framework Kaggle Starter (make submit)
#   - Soumission : submission.parquet généré par le framework
#
# ============================================================

from __future__ import annotations

import hashlib
import random
import time
from collections import Counter, defaultdict, deque
from typing import Any

from arcengine import FrameData, GameAction, GameState

from agents.agent import Agent

# ============================================================
# CONSTANTES
# ============================================================

VERSION = "6.0"
CERTIFIED_100 = False
UNIQUE_HUMAN_PROVEN = False
DEBUG = True

# Budget d'actions (conservateur pour respecter les limites Kaggle)
MAX_ACTIONS = 500        # budget total par jeu
MAX_ACTIONS_PER_LEVEL = 100  # budget par niveau avant RESET forcé

# Détection de stagnation
STUCK_THRESHOLD = 6      # même état N fois → changement de stratégie
RESET_AFTER_STUCK = 4    # N STUCK consécutifs → RESET complet

# Actions standard (sans RESET ni CLICK qui nécessite x,y)
SIMPLE_ACTIONS = [
    GameAction.ACTION1,
    GameAction.ACTION2,
    GameAction.ACTION3,
    GameAction.ACTION4,
    GameAction.ACTION5,
    GameAction.ACTION7,
]
CLICK_ACTION = GameAction.ACTION6


# ============================================================
# UTILITAIRES
# ============================================================

def frame_fingerprint(frame: Any) -> str:
    """Fingerprint déterministe d'un état visuel.

    Utilise les 512 premiers octets de la frame pour la vitesse.
    Plus robuste que MD5 complet : réduit les faux positifs sur
    frames visuellement identiques (même si quelques pixels diffèrent).
    """
    if frame is None:
        return "null"
    if isinstance(frame, list):
        # frame = liste de listes (grille 2D ou liste de grilles)
        try:
            flat = []
            for row_or_grid in frame:
                if isinstance(row_or_grid, list):
                    for cell_or_row in row_or_grid:
                        if isinstance(cell_or_row, list):
                            flat.extend(cell_or_row[:8])
                        else:
                            flat.append(cell_or_row)
                else:
                    flat.append(row_or_grid)
            key = str(flat[:64])
        except Exception:
            key = str(frame)[:200]
        return hashlib.md5(key.encode()).hexdigest()[:12]
    try:
        raw = bytes(frame) if hasattr(frame, '__iter__') else str(frame).encode()
        return hashlib.md5(raw[:512]).hexdigest()[:12]
    except Exception:
        return hashlib.md5(str(frame).encode()).hexdigest()[:12]


def frame_delta(frame_a: Any, frame_b: Any) -> float:
    """Mesure de changement entre deux frames (0.0 = identiques, 1.0 = totalement différentes)."""
    if frame_a is None or frame_b is None:
        return 1.0
    try:
        def flatten(f: Any) -> list:
            result = []
            if isinstance(f, list):
                for item in f:
                    if isinstance(item, list):
                        result.extend(flatten(item))
                    else:
                        result.append(item)
            return result

        fa = flatten(frame_a)[:256]
        fb = flatten(frame_b)[:256]
        if not fa or not fb:
            return 1.0
        n = min(len(fa), len(fb))
        if n == 0:
            return 1.0
        diff = sum(1 for a, b in zip(fa[:n], fb[:n]) if a != b)
        return diff / n
    except Exception:
        return 1.0


# ============================================================
# MÉMOIRE DE JEU
# ============================================================

class GameMemory:
    """Modèle du jeu appris par l'agent au fil des actions.

    Maintient pour chaque action :
    - Le nombre de fois qu'elle a fait avancer le jeu (level_up)
    - Le nombre de fois qu'elle a changé la frame (frame_change)
    - Le nombre de fois qu'elle n'a rien fait (no_change)
    - La séquence de succès récente (pour détection de patterns)
    """

    def __init__(self) -> None:
        # action_id → {level_up, frame_change, no_change, total}
        self.action_stats: dict[str, dict[str, int]] = {}
        # Séquence des (action, result) récents
        self.history: deque = deque(maxlen=50)
        # Séquences gagnantes : liste d'action_ids qui ont résolu un niveau
        self.winning_sequences: list[list[str]] = []
        # États visités (fingerprint → count)
        self.visited_states: Counter = Counter()
        # Dernier fingerprint de frame
        self.last_fingerprint: str = ""

    def record(self, action_id: str, result: str, delta: float) -> None:
        """Enregistre le résultat d'une action."""
        if action_id not in self.action_stats:
            self.action_stats[action_id] = {
                "level_up": 0,
                "frame_change": 0,
                "no_change": 0,
                "total": 0,
            }
        stats = self.action_stats[action_id]
        stats["total"] += 1
        if result == "level_up":
            stats["level_up"] += 1
            stats["frame_change"] += 1
        elif result == "frame_change" and delta > 0.02:
            stats["frame_change"] += 1
        else:
            stats["no_change"] += 1
        self.history.append((action_id, result, delta))

    def best_actions(self, available: list[str]) -> list[str]:
        """Retourne les actions disponibles triées par utilité décroissante."""
        def score(aid: str) -> float:
            if aid not in self.action_stats:
                return 0.5  # inconnu → score médian (exploration)
            s = self.action_stats[aid]
            t = max(s["total"], 1)
            # Poids : level_up > frame_change > no_change
            return (s["level_up"] * 3 + s["frame_change"] * 1) / t

        return sorted(available, key=score, reverse=True)

    def unexplored(self, available: list[str]) -> list[str]:
        """Actions non encore essayées ou peu essayées (< 3 fois)."""
        return [
            aid for aid in available
            if self.action_stats.get(aid, {}).get("total", 0) < 3
        ]

    def is_stuck(self) -> bool:
        """Détecte si l'agent tourne en rond (même état STUCK_THRESHOLD fois)."""
        if self.last_fingerprint and self.visited_states.get(self.last_fingerprint, 0) >= STUCK_THRESHOLD:
            return True
        return False

    def record_state(self, fingerprint: str) -> None:
        self.last_fingerprint = fingerprint
        self.visited_states[fingerprint] += 1

    def reset_visit_counts(self) -> None:
        """Réinitialise les compteurs de visite (après RESET du jeu) sans perdre le modèle."""
        self.visited_states.clear()
        self.last_fingerprint = ""


# ============================================================
# AGENT PRINCIPAL
# ============================================================

class LuCYAgent(Agent):
    """Agent LuCY v6.0 pour ARC-AGI-3.

    Architecture v6.0 : Exploration → Modélisation → Exploitation.

    Stratégie fondamentalement révisée (correction BUG-A3) :
    - Explore toutes les actions disponibles pour chaque état
    - Construit un modèle du jeu (action → conséquence)
    - Exploite les actions qui font avancer le jeu
    - Se remet à zéro intelligemment en cas de blocage
    - Compatible avec le framework officiel ARC-AGI-3 Kaggle Starter

    CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
    """

    MAX_ACTIONS = MAX_ACTIONS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Mémoire de jeu
        self.memory = GameMemory()

        # État interne
        self._prev_levels: int = 0
        self._levels_this_episode: int = 0
        self._actions_this_level: int = 0
        self._consecutive_stuck: int = 0
        self._started: bool = False
        self._t_start: float = time.time()

        # Stratégie courante : 'explore' | 'exploit' | 'recover'
        self._strategy: str = "explore"

        # File d'exploration systématique des actions non essayées
        self._explore_queue: list[str] = []

        # Dernière frame pour calcul de delta
        self._last_frame: Any = None
        self._last_action_id: str = ""

        if DEBUG:
            print(f"[LuCY v{VERSION}] Agent initialisé | game_id={self.game_id}")
            print(f"  CERTIFIED_100={CERTIFIED_100} | DEBUG={DEBUG}")
            print(f"  MAX_ACTIONS={MAX_ACTIONS} | Stratégie initiale: explore")
            print(f"  Correction BUG-A3: exploration active + modélisation du jeu")

    # --------------------------------------------------------
    # INTERFACE OBLIGATOIRE : is_done
    # --------------------------------------------------------

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        """Fin de jeu si WIN, si budget épuisé, ou si budget par niveau épuisé."""
        if latest_frame.state is GameState.WIN:
            elapsed = time.time() - self._t_start
            if DEBUG:
                print(
                    f"[LuCY v{VERSION}] WIN! "
                    f"actions={self.action_counter} "
                    f"levels={latest_frame.levels_completed} "
                    f"t={elapsed:.1f}s"
                )
            return True
        if self.action_counter >= MAX_ACTIONS:
            if DEBUG:
                print(f"[LuCY v{VERSION}] Budget global épuisé: {self.action_counter}")
            return True
        return False

    # --------------------------------------------------------
    # INTERFACE OBLIGATOIRE : choose_action
    # --------------------------------------------------------

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        """Sélectionne la prochaine action selon la stratégie courante.

        Flux décisionnel :
        1. Mise à jour de l'état interne depuis latest_frame
        2. Calcul du delta de frame (pour évaluer la dernière action)
        3. Sélection de la stratégie : explore / exploit / recover
        4. Choix de l'action et retour
        """
        # ── Mise à jour état interne ──
        curr_levels = latest_frame.levels_completed or 0
        game_state = latest_frame.state

        # Calcul du fingerprint de l'état courant
        frame_data = latest_frame.frame
        curr_fp = frame_fingerprint(frame_data)
        self.memory.record_state(curr_fp)

        # Calcul du delta avec la frame précédente
        delta = 0.0
        if self._last_frame is not None:
            delta = frame_delta(self._last_frame, frame_data)

        # Enregistrement du résultat de la dernière action
        if self._last_action_id and not self._started:
            level_up = curr_levels > self._prev_levels
            if level_up:
                self.memory.record(self._last_action_id, "level_up", delta)
            elif delta > 0.02:
                self.memory.record(self._last_action_id, "frame_change", delta)
            else:
                self.memory.record(self._last_action_id, "no_change", delta)

        # Mise à jour des compteurs de niveau
        if curr_levels > self._prev_levels:
            level_up_count = curr_levels - self._prev_levels
            self._levels_this_episode += level_up_count
            self._actions_this_level = 0
            self._consecutive_stuck = 0
            self.memory.reset_visit_counts()
            if DEBUG:
                print(
                    f"[LuCY v{VERSION}] LEVEL UP! levels={curr_levels} "
                    f"actions_used={self.action_counter}"
                )
        self._prev_levels = curr_levels

        # ── Gestion du démarrage ──
        if not self._started:
            self._started = True
            if game_state in (GameState.NOT_PLAYED, None):
                return self._emit(GameAction.RESET, "reset_init", curr_fp, frame_data)

        # ── Gestion GAME_OVER : RESET systématique ──
        if game_state is GameState.GAME_OVER:
            self._consecutive_stuck = 0
            self.memory.reset_visit_counts()
            self._actions_this_level = 0
            if DEBUG:
                print(f"[LuCY v{VERSION}] GAME_OVER → RESET")
            return self._emit(GameAction.RESET, "reset_game_over", curr_fp, frame_data)

        # ── Détection de stagnation ──
        self._actions_this_level += 1
        if self.memory.is_stuck():
            self._consecutive_stuck += 1
            if DEBUG:
                print(
                    f"[LuCY v{VERSION}] STUCK x{self._consecutive_stuck} "
                    f"state={curr_fp} → stratégie: recover"
                )
            if self._consecutive_stuck >= RESET_AFTER_STUCK:
                self.memory.reset_visit_counts()
                self._consecutive_stuck = 0
                self._actions_this_level = 0
                return self._emit(GameAction.RESET, "reset_stuck", curr_fp, frame_data)
            self._strategy = "recover"
        elif self._actions_this_level > MAX_ACTIONS_PER_LEVEL:
            # Trop d'actions sur ce niveau → RESET pour recommencer
            self.memory.reset_visit_counts()
            self._actions_this_level = 0
            if DEBUG:
                print(f"[LuCY v{VERSION}] Budget niveau épuisé → RESET")
            return self._emit(GameAction.RESET, "reset_level_budget", curr_fp, frame_data)

        # ── Sélection de l'action ──
        available = self._available_action_ids(latest_frame)

        action = self._select_action(available, curr_fp, game_state)
        return self._emit(action, self._strategy, curr_fp, frame_data)

    # --------------------------------------------------------
    # SÉLECTION DE L'ACTION
    # --------------------------------------------------------

    def _select_action(
        self,
        available: list[str],
        curr_fp: str,
        game_state: Any,
    ) -> GameAction:
        """Sélectionne l'action selon la stratégie courante.

        explore  → essayer les actions non encore testées
        exploit  → répéter les actions qui ont déjà bien marché
        recover  → actions aléatoires pour sortir d'un cycle
        """
        if not available:
            # Fallback : toutes les actions simples
            available = [str(a.value) for a in SIMPLE_ACTIONS]

        unexplored = self.memory.unexplored(available)

        # ── Sélection de stratégie ──
        if self._strategy != "recover":
            if unexplored:
                self._strategy = "explore"
            elif self.memory.best_actions(available):
                self._strategy = "exploit"

        if self._strategy == "explore" and unexplored:
            # Explorer d'abord les actions non essayées
            aid = unexplored[0]
            self._last_action_id = aid
            return self._action_from_id(aid)

        if self._strategy == "exploit":
            # Meilleure action connue + légère exploration (10%)
            ranked = self.memory.best_actions(available)
            if random.random() < 0.10 and len(ranked) > 1:
                aid = random.choice(ranked[1:3])
            else:
                aid = ranked[0]
            self._last_action_id = aid
            return self._action_from_id(aid)

        # recover → action aléatoire (évite les boucles)
        self._strategy = "explore"  # reset strategy after recover
        aid = random.choice(available)
        self._last_action_id = aid
        return self._action_from_id(aid)

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------

    def _available_action_ids(self, latest_frame: FrameData) -> list[str]:
        """Retourne les IDs d'actions disponibles sous forme de strings."""
        available = getattr(latest_frame, "available_actions", None) or []
        if available:
            try:
                return [str(a) if not hasattr(a, "value") else str(a.value) for a in available]
            except Exception:
                pass
        # Fallback : actions standard sans RESET
        return [str(a.value) for a in SIMPLE_ACTIONS]

    def _action_from_id(self, action_id: str) -> GameAction:
        """Construit un GameAction depuis son ID string."""
        try:
            aid_int = int(action_id)
            if aid_int == 0:
                return GameAction.RESET
            action = GameAction.from_id(aid_int) if hasattr(GameAction, "from_id") else GameAction(aid_int)
        except (ValueError, TypeError, AttributeError):
            # Fallback : ACTION1
            action = GameAction.ACTION1

        # Pour ACTION6 (CLICK), définir des coordonnées centrales par défaut
        if hasattr(action, "is_complex") and action.is_complex():
            try:
                action.set_data({"x": 32, "y": 32})
            except Exception:
                try:
                    action.data = {"x": 32, "y": 32}
                except Exception:
                    pass

        action.reasoning = f"LuCY v{VERSION} strategy={self._strategy} action={action_id}"
        return action

    def _emit(
        self,
        action: GameAction,
        reason: str,
        fingerprint: str,
        frame: Any,
    ) -> GameAction:
        """Enregistre l'état de sortie et retourne l'action."""
        self._last_frame = frame
        if not hasattr(action, "reasoning") or not action.reasoning:
            action.reasoning = (
                f"LuCY v{VERSION} | {reason} | state={fingerprint} "
                f"| actions={self.action_counter} | strategy={self._strategy}"
            )
        return action


# ============================================================
# ALIAS pour compatibilité avec le registre des agents
# ============================================================

LuCYAgentV6 = LuCYAgent


# ============================================================
# END lucy_agent_v60.py
# CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
# ============================================================
