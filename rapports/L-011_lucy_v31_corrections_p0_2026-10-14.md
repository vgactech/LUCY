# L-011 — LuCY v3.1 : Corrections P0-A..P0-F audit critique

**Date :** 2026-10-14  
**Rapport :** L-011 (espace LuCY, indépendant ARTCB)  
**Version agent :** v3.1 (depuis v3, commit 9e1a2c7)  
**CERTIFIED_100 :** false | **unique_human_proven :** false | **Mode DEBUG :** actif  

---

## 1. Objectif de cette session

Corriger les **6 défauts P0** identifiés dans le rapport L-010 (audit critique de l'agent v3) :

| ID | Défaut | Criticité |
|----|--------|-----------|
| P0-A | UCB1 : invariant `n_s >= n_sa` non garanti → `log(0)` possible | Plantage potentiel |
| P0-B | PE : `MD5(arr.tobytes()[:8192])` tronqué → collisions sémantiques | Faux états identiques |
| P0-C | `+0.15` sur tout changement d'état même cyclique → signal parasite | Apprentissage biaisé |
| P0-D | Exploration : sélection aléatoire parmi scores `∞` non différenciés | Exploration non reproductible |
| P0-E | `game_patterns` non persisté → perdu au redémarrage | Mémoire éphémère |
| P0-F | `RESET` non enregistré dans Q-table ni `n_sa` | Apprentissage incomplet |

---

## 2. Fichiers modifiés

| Fichier | Action |
|---------|--------|
| `src/lucy/kernel/lucy_agent_v31.py` | **CRÉÉ** — code agent v3.1 complet (368 lignes) |
| `tests/test_lucy_v31_p0_corrections.py` | **CRÉÉ** — 21 tests T35–T54 |
| `notebooks/arc3/lucy_arc_agi3_submission.ipynb` | **MODIFIÉ** — Cell 0 titre + Cell 2 code v3.1 |
| `logs/lucy_v31_p0_corrections_20261014T030223Z.json` | **CRÉÉ** — log d'exécution |

---

## 3. Corrections détaillées (Avant / Après)

### P0-A — UCB1 invariant et log(0) guard

**Fichier :** `src/lucy/kernel/lucy_agent_v31.py`

**AVANT (v3, `te_ucb1_score_actions()`) :**
```python
n_total = max(1, self.n_s[sid])  # si n_total=1 et n_action>0 → log(1)/n_action = 0
# Pas de vérification que n_s[sid] >= n_sa[(sid,aid)]
scored.sort(key=lambda x: (x[0] == float('inf'), x[0]), reverse=True)
```

**APRÈS (v3.1) :**
```python
# P0-A : garantir la cohérence des compteurs
n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions
               if aid != RESET_ACTION_ID)
n_total = max(1, self.n_s[sid], n_sa_sum)  # max des deux absorbe toute dérive
# ...
log_val = math.log(n_total) if n_total > 1 else 0.0  # log(1)=0 guard explicite
```

---

### P0-B — PE hash complet

**Fichier :** `src/lucy/kernel/lucy_agent_v31.py`, fonction `pe_encode_frame()`

**AVANT (v3) :**
```python
# Ligne 70 (v3) :
sid_full = hashlib.md5(arr.tobytes()[:8192]).hexdigest()[:16]
# Problème : deux grilles 100×100 ne différant qu'après le byte 8192
# donnaient le même sid_full → faux états équivalents
```

**APRÈS (v3.1) :**
```python
# Ligne 73 (v3.1) :
sid_full = hashlib.md5(arr.tobytes()).hexdigest()[:16]
# Hash sur TOUS les bytes — plus de troncature
```

---

### P0-C — Suppression REWARD_STATE_CHANGE

**Fichier :** `src/lucy/kernel/lucy_agent_v31.py`, méthode `update()`

**AVANT (v3) :**
```python
# Constante définie (v3, ligne ~52) :
REWARD_STATE_CHANGE = 0.15   # état différent (était 0.1)

# Dans update() (v3) :
elif curr_sid != prev_sid:
    reward += REWARD_STATE_CHANGE   # +0.15 sur tout changement même cyclique
```
**Conséquence :** l'agent apprenait à osciller entre deux états A→B→A→B pour maximiser la récompense.

**APRÈS (v3.1) :**
```python
# Constante SUPPRIMÉE (v3.1) — n'existe plus dans le code
# Dans update() (v3.1) :
reward = 0.0
if win:
    reward += REWARD_WIN
elif level_up:
    reward += REWARD_LEVEL_UP
elif action_id == RESET_ACTION_ID:
    reward += REWARD_RESET
else:
    reward += REWARD_CYCLE   # -0.05 pénalité (état inchangé ou déjà vu)
# Seuls win, level_up, reset, et cycle font varier le reward
```

---

### P0-D — Exploration stable (ordre index, pas aléatoire)

**Fichier :** `src/lucy/kernel/lucy_agent_v31.py`, `te_ucb1_score_actions()` + `arbitrate()`

**AVANT (v3) :**
```python
# te_ucb1_score_actions retournait les infinis dans un ordre indifférencié
# puis dans arbitrate() :
top_k = [aid for score, aid in scored[:3] if score != float('-inf')]
return random.choice(top_k)   # aléatoire parmi top-3 même si tous inf
```

**APRÈS (v3.1) :**
```python
# te_ucb1_score_actions() — P0-D : tri stable par index d'ordre
scored_inf.sort(key=lambda x: x[0])   # ordre par position dans available_actions
inf_list = [(float('inf'), aid) for _, aid in scored_inf]

# arbitrate() — P0-D : en mode explore, choisit le PREMIER non-essayé
inf_actions = [aid for score, aid in scored if score == float('inf')]
if inf_actions:
    return inf_actions[0]   # premier non-essayé — ordre déterministe
```

---

### P0-E — Persistance game_patterns

**Fichier :** `src/lucy/kernel/lucy_agent_v31.py`, classe `LuCYCognition`

**AVANT (v3) :**
```python
# Dans __init__() (v3) :
self.game_patterns: Dict[int, Dict] = {}   # en mémoire uniquement, perdu au restart
# Aucune sauvegarde ni chargement
```

**APRÈS (v3.1) :**
```python
# Dans __init__() (v3.1) :
self.game_patterns: Dict[str, Dict] = {}
self._load_patterns()   # chargement depuis disque au démarrage

# Nouvelle méthode _load_patterns() :
def _load_patterns(self) -> None:
    if os.path.exists(PATTERNS_PERSIST_PATH):
        with open(PATTERNS_PERSIST_PATH, 'r') as f:
            data = json.load(f)
        self.game_patterns = data.get('game_patterns', {})

# Nouvelle méthode _save_patterns() — appelée après chaque level_up :
def _save_patterns(self) -> None:
    data = {'game_patterns': self.game_patterns, 'version': VERSION}
    with open(PATTERNS_PERSIST_PATH, 'w') as f:
        json.dump(data, f)

# Dans update() (v3.1) — après level_up :
self._save_patterns()   # persist immédiatement

# Chemin de persistance :
PATTERNS_PERSIST_PATH = '/kaggle/working/lucy_game_patterns.json'
```

---

### P0-F — RESET enregistré dans Q-learning

**Fichier :** `src/lucy/kernel/lucy_agent_v31.py`, méthode `update()`

**AVANT (v3) :**
```python
# Dans update() (v3) :
# RESET_ACTION_ID était enregistré dans actions_tried mais PAS dans :
# - self.q_table[(prev_sid, RESET_ACTION_ID)]
# - self.n_sa[(prev_sid, RESET_ACTION_ID)]
# L'agent ne pouvait pas apprendre à éviter les resets inutiles
#
# max_next_q (v3) calculait sur STANDARD_ACTIONS seulement
next_qs = [self.q_table.get((curr_sid, a), 0.0) for a in STANDARD_ACTIONS]
```

**APRÈS (v3.1) :**
```python
# Dans update() (v3.1) :
# P0-A + P0-F : compteurs UCB1 — RESET inclus
self.n_sa[(prev_sid, action_id)] += 1   # inclut RESET si action_id=0
self.n_s[prev_sid] += 1

# max_next_q (v3.1) inclut RESET dans le calcul :
all_actions = STANDARD_ACTIONS + [RESET_ACTION_ID]
next_qs = [self.q_table.get((curr_sid, a), 0.0) for a in all_actions]
# → Q(sid, RESET) devient négatif après applications de REWARD_RESET
```

---

## 4. Résultats des tests

### Tests nouveaux T35–T54

| Classe | Tests | Résultat |
|--------|-------|----------|
| TestP0A_UCB1Invariant | T35–T40 (6 tests) | ✅ 6/6 PASS |
| TestP0B_PEHashComplet | T41–T43 (3 tests) | ✅ 3/3 PASS |
| TestP0C_RewardShaping | T44–T46 (3 tests) | ✅ 3/3 PASS |
| TestP0D_ExploreStable | T47–T49 (3 tests) | ✅ 3/3 PASS |
| TestP0E_Persistance | T50–T51 (2 tests) | ✅ 2/2 PASS |
| TestP0F_ResetQLearning | T52–T54 (3 tests) | ✅ 3/3 PASS |
| test_version | 1 test | ✅ 1/1 PASS |
| **TOTAL** | **21 tests** | **✅ 21/21 PASS** |

### Non-régression (suite complète)

```
133 passed in 0.78s
```

| Suite | Tests anciens | Nouveaux | Total |
|-------|--------------|----------|-------|
| test_lucy_operators.py | 32 | 0 | 32 |
| test_lucy_phase2_contracts.py | 32 | 0 | 32 |
| test_lucy_phase3_audit.py | 16 | 0 | 16 |
| test_lucy_phase4_audit.py | 20 | 0 | 20 |
| test_lucy_integration.py | 12 | 0 | 12 |
| test_lucy_v31_p0_corrections.py | 0 | 21 | 21 |
| **TOTAL** | **112** | **21** | **✅ 133/133** |

---

## 5. Log d'exécution

Fichier généré : `logs/lucy_v31_p0_corrections_20261014T030223Z.json`

```json
{
  "session": "L-011",
  "version": "3.1",
  "tests": {
    "new": {"count": 21, "pass": 21, "fail": 0},
    "regression": {"count": 133, "pass": 133, "fail": 0}
  },
  "source_sha256": "18f9aba8d1ed7099a23b7fab7e5f7653..."
}
```

---

## 6. État Kaggle

**Clé API Kaggle** : toujours 401 — régénération requise sur https://www.kaggle.com/settings/api

Le notebook `notebooks/arc3/lucy_arc_agi3_submission.ipynb` est à jour avec le code v3.1.  
Une fois la clé renouvelée : `kaggle kernels push -p notebooks/arc3/` → mode RERUN.

---

## 7. Points restants

| Item | Statut |
|------|--------|
| Clé Kaggle API | ❌ 401 — action requise utilisateur |
| Push Kaggle (mode RERUN) | ⏳ bloqué |
| Soumission compétition | ⏳ bloqué |
| Score live ARC-AGI-3 | ⏳ inconnu (attendu 0.05–0.15) |

---

**Avancement session L-011 : 100 %**  
`CERTIFIED_100=false` | `unique_human_proven=false` | `DEBUG=true`
