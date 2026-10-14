# L-017 — LuCY v5.0 : Architecture 3 niveaux + Reward adaptatif + Comparaison modèles existants

**Date :** 2026-10-14  
**Rapport :** L-017 (espace LuCY, indépendant ARTCB)  
**Version agent :** v5.0  
**Précédent :** L-016 (v4.1 — FIX-1 attribution temporelle + FIX-2 persistance complète)  
**Log source :** `LuCY/logs/lucy_L017_20261014T150000Z.json`  
**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**

---

## 🔷 RÉSUMÉ EXÉCUTIF (à lire en premier)

| Livrable | Statut |
|----------|--------|
| `lucy_agent_v50.py` — architecture 3 niveaux | ✅ CRÉÉ (966 lignes) |
| `test_lucy_v50_architecture.py` — T107→T122 | ✅ **17/17 PASS** |
| Non-régression v4.0 + v4.1 (T75→T106) | ✅ **32/32 PASS** |
| `kernel-metadata.json` : `is_private=true`, `enable_gpu=true`, `accelerator="gpu"` | ✅ MODIFIÉ |
| `kaggle_push_api.py` : `isPrivate=True`, `enableGpu=True` FORCÉS | ✅ MODIFIÉ |
| **Total tests :** 49/49 PASS | ✅ 0 échec |

**Ce que v5.0 apporte par rapport à v4.1 :**
1. **Hiérarchie explicite** : 8 fonctions → 4 contrôleurs → 1 méta-contrôleur
2. **Méta-contrôleur par autorisations** (les données ne transitent pas par lui — pas de bottleneck)
3. **Flux non-linéaire** : court-circuits autorisés (PE→PI, DE→PE) sans passer par le méta
4. **Reward adaptatif** : `level_up_reward = 2.0 × min(2.0, 1 + progress_rate)` + pénalité cycle croissante avec `stuck_counter`
5. **Profil cognitif configurable** : INTP (défaut), INTJ, ENTP, ADAPTIVE

**Ce que v5.0 réussit vs ne réussit pas (identique à v4.1 sur ARC-AGI-3) :**
- ✅ Exploration UCB1, détection cycles, persistance complète, reward cohérent
- ❌ Généralisation inter-puzzles (limite fondamentale Q-table)
- ❌ Compréhension règles visuelles abstraites (besoin CNN/LLM)

---

## 1. Architecture v5.0 — 3 niveaux

```
┌─────────────────────────────────────────────────────────────────┐
│  NIVEAU 3 — MÉTA-CONTRÔLEUR                                     │
│  MetaController(profile=INTP)                                   │
│  · Profil INTP : DI(1.4) > PE(1.2) > PI(1.0) > DE(0.8)        │
│  · Donne les AUTORISATIONS uniquement (pas de données)          │
│  · Court-circuits : PE→PI, DE→PE (évite bottleneck)            │
│  · Adaptatif : boost DI si stuck↑, boost PE si non-exploré      │
└───────────────────┬─────────────────────────────────────────────┘
                    │ autorisations seulement
        ┌───────────┼───────────────────────┐
        ▼           ▼           ▼           ▼
┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  PI_ctrl   │ │ PE_ctrl  │ │ DI_ctrl  │ │ DE_ctrl  │
│  NI + SI   │ │ NE + SE  │ │ TI + FI  │ │ TE + FE  │
│ anticipation│ │exploration│ │cycle+val │ │scoring   │
│  + patterns │ │ + percept │ │detection │ │ + couleur│
└────────────┘ └──────────┘ └──────────┘ └──────────┘
        ▲           ▲           ▲           ▲
        └───────────┴───────────┴───────────┘
                    │ 8 fonctions cognitives
        SE  SI  NE  NI  TE  TI  FE  FI
```

### 1.1 — Différences v4.1 → v5.0

| Aspect | v4.1 | v5.0 |
|--------|-------|-------|
| Organisation | 10 opérateurs plats (PE+PI redondants avec SE/SI/NE/NI) | 3 niveaux hiérarchiques |
| PE/PI statut | Opérateurs cognitifs au même niveau que SE/NE | **Contrôleurs** orchestrant 2 fonctions chacun |
| Méta-contrôleur | Absent — `arbitrate()` monolithique | Présent — `MetaController` séparé |
| Données via méta | N/A | ❌ Jamais — autorisations uniquement |
| Flux | Linéaire (`arbitrate()` → 1 chemin) | Non-linéaire (court-circuits autorisés) |
| Reward | Fixe (2.0 level_up, -0.05 cycle) | **Adaptatif** (amplifié par `progress_rate`) |
| Profils cognitifs | Un seul comportement | INTP/INTJ/ENTP/ADAPTIVE configurables |

---

## 2. AVANT / APRÈS — kernel-metadata.json

**Fichier :** `LuCY/notebooks/arc3/kernel-metadata.json`

### AVANT (v4.1)
```json
{
  "is_private": false,
  "enable_gpu": false
}
```

### APRÈS (v5.0)
```json
{
  "is_private": true,
  "enable_gpu": true,
  "accelerator": "gpu",
  "title": "LuCY Cognitive Kernel Arc Agi3 v5.0"
}
```

---

## 3. AVANT / APRÈS — kaggle_push_api.py

**Fichier :** `LuCY/scripts/kaggle_push_api.py`

### AVANT (lisait les valeurs du metadata)
```python
"isPrivate": meta["is_private"],   # pouvait être False
"enableGpu": meta["enable_gpu"],   # pouvait être False
```

### APRÈS (valeurs FORCÉES — règle permanente)
```python
"isPrivate": True,           # FORCÉ — jamais public
"enableGpu": True,           # FORCÉ — GPU toujours activé
"accelerator": "gpu",        # FORCÉ — accélérateur explicite
```

**Pourquoi forcer dans le script ET dans le metadata ?** Double protection : si le metadata est accidentellement réinitialisé, le script garantit les bonnes valeurs.

---

## 4. Reward adaptatif (FI v5.0)

```python
def fi_compute_adaptive_reward(base_reward, stuck_counter, progress_rate, win, level_up, is_cycle):
```

### Tableau des rewards

| Événement | v4.1 (fixe) | v5.0 (adaptatif) | Condition d'amplification |
|-----------|-------------|-------------------|--------------------------|
| Victoire  | 10.0 | 10.0 | Invariant |
| Level up  | 2.0 | `2.0 × min(2.0, 1 + progress_rate)` | progress_rate = 0.8 → reward = 3.6 |
| Cycle     | -0.05 | `-0.05 × (1 + stuck_factor)` | stuck=12 → reward = -0.10 |
| Progrès   | 0.05 | 0.05 | Inchangé |
| Reset     | -0.3 | -0.3 | Inchangé |

### Logique progress_rate

```
reward > 0  →  progress_rate += 0.05 (plafonné à 1.0)
reward ≤ 0  →  progress_rate *= 0.98 (décroissance exponentielle)
```

**Effet pratique :** Un agent qui enchaîne les level_up rapidement voit sa récompense augmenter jusqu'à 4.0 (×2). Un agent bloqué depuis 12 actions voit sa pénalité de cycle doubler.

---

## 5. Comparaison LuCY v5.0 vs modèles existants

### 5.1 — Tableau général

| Dimension | Neurone DNN | DQN | LLM (GPT-4/Claude) | ARC-AGI-2 winner (42%) | LuCY v5.0 |
|-----------|-------------|-----|---------------------|------------------------|-----------|
| **Architecture** | `y=σ(Wx+b)` | Réseau + Q-table | Transformer 175B+ | CNN + symbolic | 3 niveaux cognitifs |
| **Apprentissage** | Backprop (gradient global) | Backprop + replay | Préentraînement | Supervisé + règles | Q-learning + UCB1 (incrémental) |
| **Mémoire** | Aucune entre inférences | Replay buffer | Contexte (fenêtre) | Modèle entraîné | Q-table + game_patterns persistants |
| **Exploration** | Aucune | Epsilon-greedy | Sampling temperatura | N/A (inférence) | UCB1 + PE_ctrl (non-linéaire) |
| **Blocage** | N/A | Pas de détection | N/A | N/A | DI_ctrl (TI) → escape_cycle |
| **Budget ARC** | Nécessite GPU | GPU + mémoire | ~30 s/puzzle | Optimisé | CPU-only, 3000 actions |
| **Compréhension règles** | ❌ | ❌ faible | ✅ forte | ✅ forte | ❌ (A-003 limite ouverte) |
| **Généralisation** | ✅ forte | ✅ avec entraînement | ✅ très forte | ✅ forte | ⚠️ partielle (sid_coarse) |
| **Explicabilité** | ❌ boîte noire | ❌ | ❌ | Partielle | ✅ chaque décision tracée |
| **Reward adaptatif** | N/A | Fixe | N/A | N/A | ✅ amplifié par progress_rate |

### 5.2 — Ce que LuCY fait que les DNN/DQN ne font pas

1. **Persistance inter-runs** : la Q-table survit entre deux exécutions Kaggle. Un DNN oublie tout si non sauvegardé explicitement (fine-tuning requis).

2. **Détection de cycles garantie** : `DI_ctrl (TI)` analyse l'historique `coarse_history`. Un DQN n'a pas de mécanisme explicite de détection de boucle — il peut tourner indéfiniment.

3. **Exploration systématique** : UCB1 garantit que chaque action est essayée au moins une fois avant d'exploiter. Un DNN ne sait pas quelles actions il n'a pas encore explorées.

4. **Métacognition** : le méta-contrôleur évalue le contexte (stuck_counter, has_unexplored) et adapte les priorités dynamiquement. Un DQN a une politique fixe post-entraînement.

### 5.3 — Ce que LuCY ne fait pas (limites honnêtes)

| Limite | Identifiant | Impact ARC-AGI-3 | Amélioration possible |
|--------|-------------|------------------|----------------------|
| Pas de compréhension des règles visuelles | A-003 | 🔴 Critique — la plupart des puzzles ARC nécessitent de comprendre une règle abstraite | Ajouter un composant LLM ou CNN |
| Q-table non généralisante | A-001 | 🔴 — 1 pixel différent = nouvel état | Encoder par features abstraites |
| Bruit visuel = nouvel état | A-002 | 🟡 | Utiliser sid_coarse uniquement |
| Budget 3000 actions limité | — | 🟡 — puzzles complexes l'épuisent | N-step Q-learning ou MCTS |

### 5.4 — Comparaison avec ARC-AGI-2 winner (42.6% accuracy)

L'approche gagnante ARC-AGI-2 (ARC-AGI-2 2026) combinait :
- Un CNN entraîné sur les exemples d'entraînement du puzzle
- Un moteur de règles symboliques qui extrait la transformation
- Un LLM pour lever les ambiguïtés

LuCY v5.0 n'a **aucun de ces trois composants** pour ARC-AGI-3 (qui est séquentiel/interactif, pas statique). La nature différente d'ARC-AGI-3 (jeu interactif vs prédiction de grille) justifie l'approche RL — mais sans compréhension des règles visuelles (A-003), les performances resteront basses.

**Architecture hybride recommandée (piste future) :**
```
LLM/CNN ──► comprend la règle visuelle → produit un "plan d'actions"
LuCY v5.0 ──► exécute le plan via DI_ctrl + PE_ctrl (UCB1 guidé)
MetaController ──► arbitre entre plan LLM et exploration UCB1
```

### 5.5 — Bugs cachés identifiés (analyse croisée)

| ID | Description | Sévérité | Statut |
|----|-------------|----------|--------|
| BUG-H1 | `_maybe_checkpoint()` ne sauvegarde pas si `q_table` vide mais `coarse_history` non-vide | 🟡 Mineur | ⚠️ OUVERT |
| BUG-H2 | `MetaController._granted_shortcuts` n'est pas persisté entre runs → autorisations court-circuit recalculées à zéro | 🟡 Mineur | ⚠️ OUVERT |
| BUG-H3 | `progress_rate` sauvegardé mais `_actions_no_progress` non sauvegardé → reprise légèrement incohérente | 🟡 Mineur | ⚠️ OUVERT |
| BUG-H4 | `level_count` incrémenté dans `step()` AVANT d'être sauvegardé dans `game_patterns` (ligne 562 vs 557) → `game_patterns` utilise `level_count` non-incrémenté | 🟢 Sans impact pratique (la clé change d'une exécution à l'autre mais reste unique) | ℹ️ NOTÉ |

### 5.6 — Anomalies structurelles héritées encore ouvertes

| ID | Description | Priorité |
|----|-------------|----------|
| A-001 | Explosion Q-table (`sid_full` unique par frame) | 🟡 P1 |
| A-002 | Invariance perceptive absente | 🟡 P1 |
| A-003 | Compréhension règles abstraites absente | 🔴 P0 (limite fondamentale) |

---

## 6. Tests — résultats

### Nouveaux T107→T122 (v5.0)

| Classe | Tests | Résultat | Ce que ça vérifie |
|--------|-------|----------|-------------------|
| `TestControllers` | T107→T110 | ✅ 4/4 | PI_ctrl, PE_ctrl, DI_ctrl, DE_ctrl séparément |
| `TestMetaController` | T111→T113b | ✅ 4/4 | Profil INTP, boost DI/PE, autorisations court-circuit |
| `TestAdaptiveReward` | T114→T117 | ✅ 4/4 | FI: victoire, amplification, pénalité, priorité win |
| `TestLuCYCognitionV50Integration` | T118→T120 | ✅ 3/3 | step() complet, Q-update, persistance level_up |
| `TestNonRegressionV41` | T121→T122 | ✅ 2/2 | FIX-1 conservation, FIX-2 champs complets |
| **Total** | **17** | **✅ 17/17** | |

### Non-régression totale

| Suite | Tests | Résultat |
|-------|-------|----------|
| T75→T90 (v4.0) | 16 | ✅ 16/16 |
| T91→T106 (v4.1) | 16 | ✅ 16/16 |
| T107→T122 (v5.0) | 17 | ✅ 17/17 |
| **TOTAL** | **49** | **✅ 49/49 PASS — 0 régression** |

---

## 7. Fichiers créés/modifiés

| Fichier | Action | Taille |
|---------|--------|--------|
| `LuCY/src/lucy/kernel/lucy_agent_v50.py` | CRÉÉ | 966 lignes |
| `LuCY/tests/test_lucy_v50_architecture.py` | CRÉÉ | ~290 lignes |
| `LuCY/notebooks/arc3/kernel-metadata.json` | MODIFIÉ | `is_private=true`, `enable_gpu=true`, `accelerator="gpu"` |
| `LuCY/scripts/kaggle_push_api.py` | MODIFIÉ | `isPrivate=True`, `enableGpu=True`, `accelerator="gpu"` FORCÉS |
| `LuCY/logs/lucy_L017_20261014T150000Z.json` | CRÉÉ | log complet |

---

## 8. Prochaines actions

| Priorité | Action | Statut |
|----------|--------|--------|
| P0 | Push Kaggle v5 (kernel-metadata.json + `kaggle_push_api.py` prêts) | ⏳ Exécuter `python3 scripts/kaggle_push_api.py` |
| P0 | Commit + push `vgactech/LUCY.git` | ⏳ |
| P1 | BUG-H1 : checkpoint si coarse_history non-vide | 🔲 |
| P1 | BUG-H2 : persister `_granted_shortcuts` méta-contrôleur | 🔲 |
| P1 | BUG-H3 : persister `_actions_no_progress` | 🔲 |
| P2 | A-003 : ajouter LLM/CNN pour comprendre les règles ARC | 🔲 |
| P2 | A-001 : LRU cache sur Q-table pour borner la mémoire | 🔲 |

---

*Rapport généré le 2026-10-14 | LuCY espace L-001→L-017 (indépendant ARTCB)*  
*Source log : `LuCY/logs/lucy_L017_20261014T150000Z.json`*  
*CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif*
