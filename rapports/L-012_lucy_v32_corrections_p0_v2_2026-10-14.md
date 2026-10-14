# L-012 — LuCY v3.2 : Corrections P0-A..P0-F v2 (défauts résiduels audit L-011)

**Date :** 2026-10-14  
**Rapport :** L-012 (espace LuCY, indépendant ARTCB)  
**Version agent :** v3.2 (depuis v3.1, commit 72f4a30)  
**CERTIFIED_100 :** false | **unique_human_proven :** false | **Mode DEBUG :** actif  

---

## 1. Objectif de cette session

Corriger les **6 défauts résiduels P0 v2** identifiés dans le rapport L-011 (audit critique de l'agent v3.1) :

| ID | Défaut résiduel v3.1 | Criticité |
|----|---------------------|-----------|
| P0-A v2 | `n_sa_sum` excluait RESET → `n_total` pouvait être < `n_sa[(sid, RESET)]` | Invariant UCB1 incomplet |
| P0-B v2 | Hash sans dimensions → collision si même bytes, formes différentes (4×8 vs 8×4) | Faux états équivalents |
| P0-C v2 | `REWARD_CYCLE=-0.05` pénalisait aussi les états nouveaux utiles (pas de level_up) | Signal d'apprentissage biaisé |
| P0-D v2 | Tri stable par `idx` dans `available_actions` (ordre reçu env) — non canonique | Exploration non reproductible |
| P0-E v2 | `game_patterns` chargés sur disque mais **jamais consultés** dans `arbitrate()` | Persistance sans effet comportemental |
| P0-F v2 | `max_next_q` calculé sur `STANDARD_ACTIONS + [RESET]` fixe | Q-learning sur état légal incorrect |

---

## 2. Fichiers créés

| Fichier | Action |
|---------|--------|
| `src/lucy/kernel/lucy_agent_v32.py` | **CRÉÉ** — code agent v3.2 complet (~488 lignes) |
| `tests/test_lucy_v32_p0_corrections_v2.py` | **CRÉÉ** — 20 tests T55–T74 |
| `logs/lucy_v32_p0_corrections_v2_20261014T080009Z.json` | **CRÉÉ** — log d'exécution |

---

## 3. Corrections détaillées (Avant / Après)

### P0-A v2 — n_sa_sum inclut RESET dans l'invariant UCB1

**Fichier :** `src/lucy/kernel/lucy_agent_v32.py`, méthode `te_ucb1_score_actions()`

**AVANT (v3.1, ligne ~362) :**
```python
n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions
               if aid != RESET_ACTION_ID)   # ← RESET exclu
# Problème : si RESET joué 10 fois → n_sa[(sid, RESET)]=10
# mais n_sa_sum ne l'inclut pas → n_total peut être < 10 → invariant cassé
```

**APRÈS (v3.2) :**
```python
# P0-A v2 : n_sa_sum inclut TOUTES les actions (y compris RESET)
n_sa_sum = sum(self.n_sa.get((sid, aid), 0) for aid in available_actions)
n_total = max(1, self.n_s[sid], n_sa_sum)
# Garantit : n_total >= n_sa[(sid, RESET)] quand RESET est dans available_actions
```

---

### P0-B v2 — Hash avec dimensions de la grille

**Fichier :** `src/lucy/kernel/lucy_agent_v32.py`, fonction `pe_encode_frame()`

**AVANT (v3.1) :**
```python
# np.full((4,8), 42).tobytes() == np.full((8,4), 42).tobytes()  → VRAI
# Les deux donnaient le même sid_full !
sid_full = hashlib.md5(arr.tobytes()).hexdigest()[:16]
```

**APRÈS (v3.2) :**
```python
# Préfixe de 4 bytes encodant rows et cols (uint16 little-endian)
if arr.ndim >= 2:
    rows, cols = arr.shape[0], arr.shape[1]
else:
    rows, cols = arr.shape[0], 1
shape_prefix = (
    (rows & 0xFFFF).to_bytes(2, 'little') +
    (cols & 0xFFFF).to_bytes(2, 'little')
)
sid_full = hashlib.md5(shape_prefix + arr.tobytes()).hexdigest()[:16]
# → (4,8) et (8,4) ont maintenant des sid_full distincts
```

---

### P0-C v2 — 3 niveaux de récompense

**Fichier :** `src/lucy/kernel/lucy_agent_v32.py`, méthode `update()`

**AVANT (v3.1) :**
```python
REWARD_CYCLE = -0.05   # pénalisait TOUT y compris états nouveaux utiles

# Dans update() :
elif action_id == RESET_ACTION_ID:
    reward += REWARD_RESET
else:
    reward += REWARD_CYCLE   # ← -0.05 même si l'état a changé (progrès réel)
```

**APRÈS (v3.2) :**
```python
REWARD_PROGRESS = 0.05   # état nouveau sans level_up — signal de progrès réel
REWARD_CYCLE = -0.05     # état IDENTIQUE = vraie boucle improductive

# Dans update() :
elif action_id == RESET_ACTION_ID:
    reward += REWARD_RESET
elif curr_sid == prev_sid:
    reward += REWARD_CYCLE      # -0.05 : vraie boucle stérile
else:
    reward += REWARD_PROGRESS   # +0.05 : état nouveau, signal positif
```

---

### P0-D v2 — Tri canonique par action_id

**Fichier :** `src/lucy/kernel/lucy_agent_v32.py`, méthode `te_ucb1_score_actions()`

**AVANT (v3.1) :**
```python
# scored_inf stockait (idx, aid) où idx = position dans available_actions
scored_inf.append((idx, aid))
scored_inf.sort(key=lambda x: x[0])   # x[0] = idx → dépend de l'ordre env
# Ex: available = (3, 1, 2) → premier non-essayé était action_id=3 (idx=0)
```

**APRÈS (v3.2) :**
```python
# scored_inf stocke (aid, aid) — tri par valeur canonique
scored_inf.append((aid, aid))
scored_inf.sort(key=lambda x: x[1])   # x[1] = action_id → stable et canonique
# Ex: available = (3, 1, 2) → premier non-essayé est toujours action_id=1
```

---

### P0-E v2 — game_patterns consultés dans arbitrate()

**Fichier :** `src/lucy/kernel/lucy_agent_v32.py`, nouvelle méthode `_lookup_pattern_action()` + `arbitrate()`

**AVANT (v3.1) :**
```python
def arbitrate(self, sid, sid_coarse, available_actions, lf) -> int:
    # game_patterns existait mais JAMAIS consulté ici
    scored = self.te_ucb1_score_actions(sid, available_actions)
    # ...
```

**APRÈS (v3.2) :**
```python
def _lookup_pattern_action(self, sid_coarse: str) -> Optional[int]:
    """Retourne l'action conseillée si sid_coarse apparaît dans un pattern connu."""
    for level_key, pattern in self.game_patterns.items():
        if pattern.get('from_sid_coarse') == sid_coarse:
            return pattern.get('action')
    return None

def arbitrate(self, sid, sid_coarse, available_actions, lf) -> int:
    # P0-E v2 : récupérer l'action conseillée par les patterns
    pattern_action = self._lookup_pattern_action(sid_coarse)
    # Passé à te_ucb1_score_actions → bonus PATTERN_BIAS_BONUS=0.35 si match
    scored = self.te_ucb1_score_actions(sid, available_actions, pattern_action)
    # En mode escape_cycle : pattern_action prioritaire si non essayé
    if (pattern_action is not None and pattern_action in available_actions
            and pattern_action not in info['actions_tried']):
        return pattern_action
```

---

### P0-F v2 — max_next_q sur les actions légales de l'état suivant

**Fichier :** `src/lucy/kernel/lucy_agent_v32.py`, méthode `update()`

**AVANT (v3.1) :**
```python
# Liste fixe — ignorait les contraintes légales de l'état suivant
all_actions = STANDARD_ACTIONS + [RESET_ACTION_ID]
next_qs = [self.q_table.get((curr_sid, a), 0.0) for a in all_actions]
max_next_q = max(next_qs)
```

**APRÈS (v3.2) :**
```python
def update(self, ..., next_available_actions: Optional[Tuple[int, ...]] = None) -> float:
    # P0-F v2 : utiliser les actions légales de l'état suivant si fournies
    if next_available_actions and len(next_available_actions) > 0:
        all_next = list(next_available_actions)
    else:
        all_next = STANDARD_ACTIONS + [RESET_ACTION_ID]   # fallback
    next_qs = [self.q_table.get((curr_sid, a), 0.0) for a in all_next]
    max_next_q = max(next_qs) if next_qs else 0.0
```

---

## 4. Résultats des tests

### Tests nouveaux T55–T74

| Classe | Tests | Résultat |
|--------|-------|----------|
| TestP0A_v2_NsaSumIncludesReset | T55–T57 (3 tests) | ✅ 3/3 PASS |
| TestP0B_v2_HashWithDimensions | T58–T61 (4 tests) | ✅ 4/4 PASS |
| TestP0C_v2_ThreeLevelReward | T62–T64 (3 tests) | ✅ 3/3 PASS |
| TestP0D_v2_CanonicalSort | T65–T67 (3 tests) | ✅ 3/3 PASS |
| TestP0E_v2_PatternUsedInArbitrate | T68–T70 (3 tests) | ✅ 3/3 PASS |
| TestP0F_v2_MaxNextQOnAvailableActions | T71–T73 (3 tests) | ✅ 3/3 PASS |
| TestVersionV32 | T74 (1 test) | ✅ 1/1 PASS |
| **TOTAL** | **20 tests** | **✅ 20/20 PASS** |

### Non-régression (suite complète)

```
153 passed in 1.68s
```

| Suite | Tests anciens | Nouveaux | Total |
|-------|--------------|----------|-------|
| test_lucy_integration.py | 12 | 0 | 12 |
| test_lucy_operators.py | 32 | 0 | 32 |
| test_lucy_phase2_contracts.py | 32 | 0 | 32 |
| test_lucy_phase3_audit.py | 16 | 0 | 16 |
| test_lucy_phase4_audit.py | 20 | 0 | 20 |
| test_lucy_v31_p0_corrections.py | 21 | 0 | 21 |
| test_lucy_v32_p0_corrections_v2.py | 0 | 20 | 20 |
| **TOTAL** | **133** | **20** | **✅ 153/153** |

---

## 5. Log d'exécution

Fichier généré : `logs/lucy_v32_p0_corrections_v2_20261014T080009Z.json`

Extrait :
```json
{
  "session": "L-012",
  "timestamp": "20261014T080009Z",
  "version": "3.2",
  "tests": {
    "nouveaux_T55_T74": 20,
    "nouveaux_resultat": "20/20 PASS",
    "regression_anciens": 133,
    "total": 153,
    "total_resultat": "153/153 PASS",
    "duree_secondes": 1.68
  }
}
```

---

## 6. Prochaines étapes

1. **Mettre à jour le notebook Kaggle** (`lucy_arc_agi3_submission.ipynb`) avec le code v3.2
2. **Push Kaggle kernel** : `kaggle kernels push -p LuCY/notebooks/arc3/`
3. **Commit + push** sur `git@github.com:vgactech/LUCY.git`

---

*Rapport généré le 2026-10-14. Espace numérotation LuCY (L-001 → L-012). Indépendant de l'espace ARTCB (R-xxx).*
