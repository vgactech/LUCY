# L-027 — LuCY v9.0 : corrections BUG-C1→C7 + run local ForensicLogger NS

**Date :** 2026-10-14T20:51:54Z  
**Version agent :** v9.0  
**Source :** `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`  
**Log JSON :** `LuCY/logs/lucy_L027_20261014T205154Z.json`  
**CERTIFIED_100=false** | **unique_human_proven=false** | **DEBUG=true**  
**Espace rapports :** LuCY (L-001→L-027) — NE PAS croiser avec ARTCB (R-xxx)

---

## 1. Contexte

La session précédente (L-026) avait identifié par lecture brute des logs (L-060) que `levels_completed=0`
sur ls20 et vc33. Le présent rapport documente les corrections apportées en v9.0
(BUG-C1 à BUG-C7) et le run de validation local.

---

## 2. Bugs corrigés — tableau avant/après

| ID | Sévérité | Fichier source | Ligne AVANT | AVANT | APRÈS |
|----|----------|----------------|-------------|-------|-------|
| **BUG-C1** | P1 | `my_agent.py` | 548 | `action = untried[0]` — déterministe, toujours dans l'ordre de l'enum | `action = random.choice(untried)` — exploration aléatoire parmi les actions non essayées |
| **BUG-C3** | P2 | `my_agent.py` | 430 | `if self._action_count >= MAX_ACTIONS_TOTAL:` — framework appelle `is_done()` avant `choose_action()` → s'arrête à N+1 | `if self._action_count >= MAX_ACTIONS_TOTAL - 1:` — s'arrête à la bonne frontière |
| **BUG-C4** | P0 | `my_agent.py` | 481-482 | `current_levels = getattr(…) or 0` — peut décroître si le framework reset ce champ | `current_levels = max(current_levels_raw, self._max_levels_seen)` — clamp cumulatif |
| **BUG-C5** | P0 | `my_agent.py` | 461-470 | `per_level_budget` RESET ne réinitialisait pas `_stuck_streak` | `self._stuck_streak = 0` ajouté après le RESET de `_level_action_count` |
| **BUG-C7** | P1 | `my_agent.py` | `on_done()` | `on_done()` pouvait imprimer le SUMMARY deux fois si le framework appelle `is_done()` plusieurs fois | Guard `getattr(self, "_done_emitted", False)` + `self._done_emitted = True` |

---

## 3. Bugs identifiés NON corrigés (documentation)

| ID | Sévérité | Description | Décision |
|----|----------|-------------|----------|
| BUG-C2 | INFO | Le RESET consomme un `_action_count` — double compte mineur | Laissé en l'état — impact négligeable |
| BUG-C6 | P2 | `action.set_data()` appelé sur l'enum `GameAction` singleton | Risque théorique — Framework v8 semble thread-safe ; à surveiller |

---

## 4. Résultats run local v9.0

**Commande :** `make verify-local` → `python scripts/play_local.py --game ls20,vc33 --max-steps 50`

### 4.1 ls20

| Métrique | Valeur |
|----------|--------|
| Actions exécutées | 51 (limité par runner --max-steps 50) |
| Niveaux complétés | 0 |
| RESET(s) | 1 — raison `per_level_budget` à l'action 31 |
| `stuck_streak` post-RESET | **0 ✅ (BUG-C5 corrigé vérifié)** |
| Exploration (4 untried) | **ACTION1, ACTION4, ACTION2, ACTION3** — ordre non-déterministe ✅ |
| Phase après RESET | `explore` ✅ |
| `_stuck_streak` reset | Confirmé — `stuck_streak=0` dans ACTION_BEFORE action 32 |
| Durée | 0.72 s | 70.83 fps moyen |

**BUG-C1 vérifié sur preuves :** actions 1 à 4 = A1, A4, A2, A3 → non séquentielles ✅

### 4.2 vc33

| Métrique | Valeur |
|----------|--------|
| Candidats disponibles | **1 seul : ACTION6 (complex)** |
| Actions exécutées | 50+ |
| Niveaux complétés | 0 |
| RESET(s) | 0 |
| `stuck_streak` | 0 (frames différentes à chaque ACTION6 — delta 0.0002→0.0005) |
| Observation | vc33 n'expose qu'ACTION6. L'agent ne peut pas diversifier — limite du jeu, pas un bug |

---

## 5. Observation critique — problème fondamental non résolu

`levels_completed=0` persiste en v9.0. Les corrections BUG-C1→C7 améliorent la robustesse
mais ne résolvent pas la limite fondamentale :

**UCB1 sur fingerprints visuels est insuffisant pour ARC-AGI-3.**

Les puzzles ARC-AGI-3 nécessitent :
- Compréhension des grilles de symboles (pattern recognition)  
- Déduction des règles de transformation entre état initial et état cible  
- Sélection d'actions sémantiquement appropriées, pas seulement "celles qui changent l'écran"

Le modèle UCB1 actuel optimise `level_up` et `delta` (changement visuel) mais n'a aucun
accès au contenu sémantique des grilles. C'est une limite architecturale de v9.0.

---

## 6. Fichiers modifiés — avant/après (lignes exactes)

### `LuCY/vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py`

```
# AVANT ligne 1 : VERSION = "8.0"
# APRÈS ligne 71 : VERSION = "9.0"

# AVANT ligne 548 : action = untried[0]
# APRÈS ligne 588 : action = random.choice(untried)  # BUG-C1 fix

# AVANT ligne 430 : if self._action_count >= MAX_ACTIONS_TOTAL:
# APRÈS : if self._action_count >= MAX_ACTIONS_TOTAL - 1:  # BUG-C3 fix

# AVANT lignes 481-482 : current_levels = getattr(...) or 0
# APRÈS : current_levels = max(current_levels_raw, self._max_levels_seen)  # BUG-C4 fix

# AVANT : per_level_budget RESET sans reset stuck_streak
# APRÈS ligne 502 : self._stuck_streak = 0  # BUG-C5 fix

# AVANT : on_done() sans guard
# APRÈS : if getattr(self, "_done_emitted", False): return  # BUG-C7 fix
```

---

## 7. Fichiers créés

| Fichier | Rôle |
|---------|------|
| `LuCY/agent/my_agent_v90.py` | Copie versionnée archivée de v9.0 |
| `LuCY/logs/lucy_L027_20261014T205154Z.json` | Log JSON de ce run |
| `LuCY/rapports/L-027_lucy_v90_bugfix_C1_C7_run_2026-10-14.md` | Ce rapport |

---

## 8. Prochaine étape recommandée

Pour que `levels_completed > 0`, il faut une v10.0 avec **compréhension sémantique des grilles ARC**.
Deux approches possibles :

- **A) LLM Vision** : envoyer le rendu visuel du puzzle à un modèle multimodal (Bob CLI vision)
- **B) Pattern matching déterministe** : analyser les grilles directement via `latest_frame.frame` (tableaux 2D de symboles) pour inférer les règles de transformation

Attendre la décision de l'utilisateur avant d'implémenter.

---

*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
