# L-010 — ARC-AGI-3 Agent v3 : Phase 5 — UCB1 + PE/PI + Q-learning

**Date :** 2026-10-14T02:52:44Z  
**Référence :** L-010 (espace LUCY — `vgactech/LUCY`)  
**Fichier modifié :** `LuCY/notebooks/arc3/lucy_arc_agi3_submission.ipynb`  
**Version :** LuCY v3.0 (Phase 5)  
**Tests locaux :** **34/34 PASS**  
**Log :** `LuCY/logs/lucy_v3_phase5_20261014T025244Z.json`  
**CERTIFIED_100 :** false  
**unique_human_proven :** false  
**Mode DEBUG :** actif  

---

## 1. Contexte — Reprise depuis L-009

### État L-009 (v2)
- Notebook v2 soumis sur Kaggle : `ndarray2000/lucy-cognitive-kernel-arc-agi3`
- Mode INITIAL RUN correct : `submission.parquet` placeholder (2 648 bytes) ✅
- Architecture v2 : 8 opérateurs + arbitrateur basique
- Limites identifiées : scoring naïf, perception mono-résolution, reward binaire, pas de Q-learning

### Demande utilisateur
Améliorer l'agent LuCY pour la Phase 5 : opérateurs PE/PI + UCB1 + raisonnement visuel, en local (clé Kaggle 401 non disponible).

---

## 2. Améliorations v2 → v3

### AVANT (v2) — Faiblesses documentées

| Composant | v2 | Problème |
|-----------|-----|---------|
| TE scoring | `Q + 0.5` (bonus fixe si inconnu) + `0.3` (si change état) | Pas d'équilibre exploration/exploitation formalisé |
| SE perception | `MD5(frame[:4096])` = 1 seul niveau | Sensible au bruit ; pas de résolution grossière |
| NE stuck | `stuck_counter > 15` uniquement | Ignore les cycles visuels répétés |
| FI priorité | Seuil fixe `visits < 3` → explore | Pas d'adaptation à l'expérience accumulée |
| Reward | Binaire : `0 / 0.1 / 1.0` | Pas de Q-learning ; pas de pénalité cycle |
| Mémoire | `state_archive` par jeu uniquement | Pas de transfert inter-niveaux |
| Opérateurs | 8 (SE/SI/NE/NI/TE/TI/FE/FI) | PE et PI absents |

### APRÈS (v3) — Modifications

| Composant | v3 | Amélioration |
|-----------|-----|-------------|
| **TE — UCB1** | `Q(s,a) + C × sqrt(ln(N(s)) / N(s,a))` avec `C = sqrt(2) = 1.414` | Garantit l'exploration de chaque action au moins une fois (score infini) + exploitation des Q-values accumulées |
| **SE + PE multi-résolution** | `(sid_full, sid_coarse, sid_colors)` : MD5(8192), 4×4 average pool, top-3 couleurs | 3 niveaux : précis / invariant au bruit / couleurs dominantes |
| **NE + PI cycles visuels** | `stuck > 12 OR visual_cycle PI` | Détecte les boucles A→B→A→B sur sid_coarse |
| **FI epsilon adaptatif** | `epsilon_decay × (1 - success_factor)` via `PIPatternAnalyzer.get_epsilon()` | Moins d'exploration quand des patterns de succès existent |
| **Reward Q-learning** | `Q(s,a) ← Q(s,a) + α × [r + γ × maxQ(s') - Q(s,a)]` avec `α=0.2, γ=0.9` | Signal d'apprentissage continu avec pénalité cycle (`-0.05`) et reset (`-0.3`) |
| **Mémoire inter-niveaux** | `game_patterns[level_id] = {action, from_coarse, to_coarse}` | Transfère l'action ayant conduit au level_up |
| **PI PIPatternAnalyzer** | Nouveau opérateur : `failed_sequences`, `successful_actions`, `suggest_action_bias()` | Biais vers les actions qui ont fonctionné dans le passé |

---

## 3. Architecture v3 — Détail technique

### Constantes

```python
UCB1_C = 1.414           # sqrt(2) — paramètre standard UCB1
ALPHA = 0.2              # learning rate Q-learning
GAMMA = 0.9              # discount factor
EPSILON_START = 0.4      # exploration initiale
EPSILON_MIN = 0.05       # plancher epsilon
EPSILON_DECAY = 0.995    # décroissance par action
REWARD_LEVEL_UP = 2.0    # (était 1.0)
REWARD_WIN = 10.0        # victoire
REWARD_STATE_CHANGE = 0.15  # (était 0.1)
REWARD_CYCLE = -0.05     # pénalité cycle
REWARD_RESET = -0.3      # pénalité reset
MAX_ACTIONS_PER_LEVEL = 500  # (était 400)
MIN_STATE_VISITS = 2         # (était 3)
```

### PE — Perception Étendue (nouveau)

```python
def pe_encode_frame(frame_raw) -> (sid_full, sid_coarse, sid_colors):
    sid_full   = MD5(arr.tobytes()[:8192])[:16]    # précis
    sid_coarse = MD5(arr_4x4_pooled.tobytes())[:8] # invariant au bruit
    sid_colors = top-3 couleurs dominantes (buckets 16)
```

### PI — Pattern Interne (nouveau)

```python
class PIPatternAnalyzer:
    coarse_history[]       # historique sid_coarse
    failed_sequences       # paires (A,B) alternantes → cycle
    successful_actions[]   # actions ayant mené à level_up
    
    detect_visual_cycle(sid_coarse) → bool  # NE amélioré
    suggest_action_bias()           → int   # TE amélioré
    get_epsilon(base, n)            → float # FI adaptatif
```

### TE — UCB1

```
Si N(s,a) == 0 → UCB1 = ∞  (exploration forcée)
Sinon         → UCB1 = Q(s,a) + 1.414 × sqrt(ln(N(s)) / N(s,a))
+ 0.2 si action suggérée par PI
```

---

## 4. AVANT / APRÈS — Lignes exactes

### Fichier : `LuCY/notebooks/arc3/lucy_arc_agi3_submission.ipynb` (Cell 2 — `lucy_agent.py`)

#### AVANT — `te_score_actions()` (v2, ~ligne 189-213)

```python
def te_score_actions(self, sid, available_actions):
    for aid in available_actions:
        reward = self.action_rewards.get((sid, aid), 0.0)
        if aid not in info['actions_tried']:
            reward += 0.5          # bonus fixe
        transition = self.transition_graph.get((sid, aid))
        if transition and transition != sid:
            reward += 0.3          # bonus fixe
        scored.append((reward, aid))
    scored.sort(reverse=True)
```

#### APRÈS — `te_ucb1_score_actions()` (v3)

```python
def te_ucb1_score_actions(self, sid, available_actions):
    n_total = max(1, self.n_s[sid])
    for aid in available_actions:
        n_action = self.n_sa.get((sid, aid), 0)
        q_val = self.q_table.get((sid, aid), 0.0)
        if n_action == 0:
            ucb_score = float('inf')   # exploration forcée
        else:
            ucb_score = q_val + UCB1_C * sqrt(log(n_total) / n_action)
        if self.pi.suggest_action_bias() == aid:
            ucb_score += 0.2           # biais PI
    scored.sort(key=lambda x: (x[0]==inf, x[0]), reverse=True)
```

#### AVANT — `se_perceive()` (v2)

```python
def se_perceive(self, frame_raw) -> (sid, arr):
    sid = hashlib.md5(arr.tobytes()[:4096]).hexdigest()[:16]
    return sid, arr
```

#### APRÈS — `se_perceive()` + PE (v3)

```python
def se_perceive(self, frame_raw) -> (sid_full, sid_coarse, sid_colors, arr):
    sid_full, sid_coarse, sid_colors = pe_encode_frame(frame_raw)
    return sid_full, sid_coarse, sid_colors, arr
```

#### AVANT — `update()` (v2)

```python
def update(self, prev_sid, curr_sid, action_id, level_up):
    reward = 0.0
    if curr_sid != prev_sid:
        reward += 0.1
    if level_up:
        reward += 1.0
    self.action_rewards[(prev_sid, action_id)] = reward
```

#### APRÈS — `update()` Q-learning (v3)

```python
def update(self, prev_sid, prev_sid_coarse, curr_sid, ..., win=False) -> float:
    reward = REWARD_WIN if win else (REWARD_LEVEL_UP if level_up else
             REWARD_STATE_CHANGE if curr_sid!=prev_sid else
             REWARD_RESET if action_id==0 else REWARD_CYCLE)
    old_q = self.q_table.get((prev_sid, action_id), 0.0)
    max_next_q = max([self.q_table.get((curr_sid, a), 0.0) for a in STANDARD_ACTIONS])
    self.q_table[(prev_sid, action_id)] = old_q + ALPHA * (reward + GAMMA*max_next_q - old_q)
    return reward
```

---

## 5. Résultats des tests locaux

```
LuCY v3.0 — Tests unitaires locaux
============================================================
[PASS] T01 PE None → null_full/coarse/colors
[PASS] T02 PE numpy → 3 hashes distincts
[PASS] T03 PE déterministe
[PASS] T04 PE frames différents → sid_full différents
[PASS] T05 PI init vide
[PASS] T06 PI pas de cycle au début
[PASS] T07 PI cycle détecté après alternance
[PASS] T08 PI bias None sans succès
[PASS] T09 PI bias → action la plus réussie
[PASS] T10 PI epsilon décroît avec total_actions
[PASS] T11 Cognition init
[PASS] T12 se_perceive retourne 4 valeurs
[PASS] T13 si_get_state_info init
[PASS] T14 ne_detect_stuck False début
[PASS] T15 ne_detect_stuck True si > 12
[PASS] T16 UCB1 actions inconnues → inf
[PASS] T17 UCB1 sépare connus/inconnus
[PASS] T18 fi priority explore sur état neuf
[PASS] T19 arbitrate retourne action valide
[PASS] T20 update state_change → reward > 0
[PASS] T20b update Q-table mise à jour
[PASS] T21 update level_up → reward 2.0
[PASS] T21b level_count incrémenté
[PASS] T22 update win → reward 10.0
[PASS] T23 update cycle → reward négatif
[PASS] T24 NI stuck_counter incrémenté
[PASS] T24b NI stuck_counter reset sur changement
[PASS] T25 game_patterns mémorisé level 0
[PASS] T25b game_patterns contient action
[PASS] T26 PI cycles visuels dans Cognition
[PASS] T27 epsilon réduit avec succès PI
[PASS] T28 simulation 50 cycles sans crash
[PASS] T29 UCB1 exploitation choisit action avec Q max
[PASS] T30 escape_cycle choisit action inexploitée

Résultat : 34/34 PASS
```

---

## 6. Log généré

**Fichier :** `LuCY/logs/lucy_v3_phase5_20261014T025244Z.json`

```json
{
  "ts_iso": "20261014T025244Z",
  "version": "3.0",
  "phase": "Phase5_UCB1_PE_PI",
  "certified_100": false,
  "tests": {"total": 34, "pass": 34, "fail": 0},
  "expected_score_range": {
    "v2_estimate": "0.02-0.10",
    "v3_estimate": "0.05-0.15",
    "note": "amélioration honnête, non certifiée sans rerun Kaggle"
  }
}
```

---

## 7. Situation clé Kaggle

La clé Kaggle actuelle dans `~/.kaggle/kaggle.json` retourne **401 Unauthorized**.  
Le notebook v3 est prêt localement mais ne peut pas être poussé sur Kaggle sans clé valide.

**Action requise par l'utilisateur :**
1. Aller sur https://www.kaggle.com/settings/api
2. "Generate New Token" → télécharge `kaggle.json` (username + key)
3. Remplacer `~/.kaggle/kaggle.json`
4. Me dire "push kaggle" → je pousserai le notebook v3

---

## 8. Prochaines étapes

| Priorité | Action | Blocage |
|----------|--------|---------|
| P0 | Push Kaggle v3 | Clé API 401 — besoin nouvelle clé |
| P0 | TASK-001-BIOMETRIE-SUITE | FHE véritable (PaillierHammingBackend) |
| P1 | LuCY Phase 6 | Click stratégique PE (centroïde objet coloré) |

---

## 9. Invariants vérifiés

- ✅ `CERTIFIED_100=false` dans tout le code v3
- ✅ `unique_human_proven=false` dans tout le code v3
- ✅ Mode DEBUG actif
- ✅ Log forensic produit après exécution
- ✅ Rapport L-009 non écrasé — nouveau fichier L-010
- ✅ 34/34 tests PASS locaux

---

*Rapport L-010 — espace LUCY (`vgactech/LUCY`) — jamais écraser les anciens rapports*  
*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
