# L-055 — Soumission Kaggle LuCY v13.5 — arc-prize-2026

**Date :** 2026-10-16T14:44:40Z  
**Version agent :** 13.5  
**Rapport précédent :** L-054 (guards rareté + tests renforcés)  
**Action :** Première soumission réelle Kaggle v13.5  
**CERTIFIED_100=false | unique_human_proven=false | DEBUG=true**

---

## 1. Contexte

Suite à l'audit L-050 (analyse critique v13.2) et aux corrections successives v13.3→v13.5, LuCY dispose désormais d'une FSM SELECT→PLACE, de groupes connexes BFS, de guards de rareté et d'une blacklist de coordonnées.

L'audit L-050 recommandait explicitement (§6) :

> « Exécuter v13.2 sur Kaggle — c'est la prochaine étape pertinente. »

Cette session a été consacrée à déployer la version la plus avancée (v13.5) sur la compétition réelle `arc-prize-2026-arc-agi-3`.

---

## 2. Processus de soumission

### 2.1 Format Kaggle (découverte)

Le starter officiel (`vendor/ARC-AGI-3-Kaggle-Starter/`) suit exactement ce flux :

```
agent/my_agent.py  →  scripts/build_notebook.py  →  notebooks/submission.ipynb
                                                          ↓
                                              kaggle kernels push -p notebooks/
```

Le notebook contient 5 cellules :
1. `pip install arc-agi` (depuis les wheels offline Kaggle)
2. `%%writefile /tmp/my_agent.py` — le corps complet de l'agent
3. Exécution si `KAGGLE_IS_COMPETITION_RERUN` (gateway sidecar, `python main.py --agent myagent`)
4. Dummy `submission.parquet` si mode commit (pas competition rerun)

L'agent doit subclasser `agents.agent.Agent`, s'appeler `MyAgent`, et implémenter `is_done()` + `choose_action()`.

### 2.2 Étapes exécutées

| Étape | Action | Résultat |
|-------|--------|----------|
| 1 | Copier `LuCY/agent/my_agent_v135.py` → `vendor/.../agent/my_agent.py` | ✅ |
| 2 | Mettre à jour `kernel-metadata.json` : id `ndarray2000/lucy-v13-5-arc-agi-3-bfs-guards` | ✅ |
| 3 | Générer `notebooks/submission.ipynb` via `build_notebook.py` | ✅ 5 cellules |
| 4 | Vérifier VERSION dans notebook : `VERSION = "13.5"` présent | ✅ |
| 5 | `kaggle kernels push -p notebooks/` | ✅ Kernel version 1 |
| 6 | Commit sous-module + dépôt LuCY | ✅ `fda5b56` / `98eaecf` |

### 2.3 Résultat push Kaggle

```
Kernel version 1 successfully pushed.
URL: https://www.kaggle.com/code/ndarray2000/lucy-v13-5-arc-agi-3-bfs-guards-fsm-select-place
```

---

## 3. État de l'agent v13.5 soumis

### Fonctionnalités actives

| Module | Description | Version introduite |
|--------|-------------|-------------------|
| `_SelectPlaceFSM` | FSM SELECT→PLACE 3 états | v13.0 (L-048) |
| `_find_connected_groups()` | BFS 4-connexité groupes réels | v13.3 (L-052) |
| `_pick_cluster_centre()` | Centroïde du plus grand groupe | v13.4 (L-053) |
| `GUARD-DISTINCT` | `piece_colour != target_colour` garanti | v13.5 (L-054) |
| `GUARD-FLOOR-COVERAGE` | Alerte si floor < 20% des cellules | v13.5 (L-054) |
| Blacklist coords | Coordonnées échouées exclues | v13.4 (L-053) |
| Confirmation sélection | Confiance = changed_cells / 9 | v13.1 (L-049) |
| Placement grille entière | Vérification `piece_colour` sur tout le frame | v13.1 (L-049) |
| Logger forensic MAXIMAL | JSON Lines, nanoseconde | v12.0 |

### Tests — 123/123 PASS (commit `a068d18`)

---

## 4. Avant / Après soumission

### AVANT cette session

| Fichier | État |
|---------|------|
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | VERSION = "13.0" (L-048) |
| `vendor/ARC-AGI-3-Kaggle-Starter/notebooks/kernel-metadata.json` | id = `ndarray2000/lucy-v8-0-arc-agi-3-forensic-ns` |
| Soumission Kaggle | **AUCUNE** — aucun push depuis plusieurs sessions |

### APRÈS cette session

| Fichier | État |
|---------|------|
| `vendor/ARC-AGI-3-Kaggle-Starter/agent/my_agent.py` | VERSION = "13.5" — BFS + guards + FSM complet |
| `vendor/ARC-AGI-3-Kaggle-Starter/notebooks/kernel-metadata.json` | id = `ndarray2000/lucy-v13-5-arc-agi-3-bfs-guards` |
| Soumission Kaggle | **VERSION 1 poussée** — kernel `lucy-v13-5-arc-agi-3-bfs-guards-fsm-select-place` |

---

## 5. Anomalies encore ouvertes (de l'audit L-050)

Les points suivants de l'audit L-050 restent à traiter en v14.x :

| Anomalie | Niveau | État v13.5 |
|----------|--------|-----------|
| Généralisation rareté : objet décoratif plus rare que la pièce | P0 | PARTIEL — guards ajoutés mais rareté reste heuristique principale |
| Détection structurelle : groupes connexes, forme, position | P0 | BFS fait (v13.3), forme/position non encore utilisés |
| Tests T-FSM-49/51/56 insuffisants | P1 | CORRIGÉ — IDs explicites vérifiés en v13.5 |

### Point critique non résolu

La classification par rareté (`_classify_frame`) reste une heuristique, non une perception structurelle. Si un jeu présente un objet décoratif plus rare que la pièce, v13.5 peut encore se tromper. La solution complète (v14.x) nécessite :
1. Détection des groupes connexes par couleur (BFS — déjà fait)
2. Calcul de propriétés structurelles : taille, forme, compacité, position relative
3. Vérification par interaction : si un clic provoque le changement attendu → confirmer l'identité de l'objet

---

## 6. Protocole de validation post-Kaggle

Conformément à l'audit L-050 §6, après exécution competition rerun, vérifier :

| Vérification | Critère | Source |
|--------------|---------|--------|
| Version exécutée | `VERSION = "13.5"` dans logs GAME_INIT | Logs forensic Kaggle |
| Perception r11l | `piece_colour=3`, `target_colour=15` dans FSM_CLASSIFY | Logs forensic Kaggle |
| Sélections confirmées | `confirmed_selection=true` et `selection_confidence > 0` | Logs FSM_TRANSITION |
| Placements réussis | `placement_confirmed=true`, `piece_absent_whole_grid=true` | Logs FSM_TRANSITION |
| Progression | `levels_completed > 0` dans GAME_DONE | Logs GAME_DONE |
| Victoire | `LEVEL_UP` émis, `levels_completed >= 1` | Logs LEVEL_UP |

---

## 7. Commits

| Dépôt | Commit | Description |
|-------|--------|-------------|
| `vendor/ARC-AGI-3-Kaggle-Starter` | `fda5b56` | Deploy v13.5 — my_agent.py + kernel-metadata.json |
| `vgactech/LUCY` | `98eaecf` | L-055 : deploy LuCY v13.5 Kaggle arc-prize-2026 |

---

## 8. Prochaine action

1. **Surveiller** l'exécution Kaggle sur [https://www.kaggle.com/code/ndarray2000/lucy-v13-5-arc-agi-3-bfs-guards-fsm-select-place](https://www.kaggle.com/code/ndarray2000/lucy-v13-5-arc-agi-3-bfs-guards-fsm-select-place)
2. **Analyser** les logs forensics JSON Lines après competition rerun
3. **Produire** L-056 avec les résultats réels mesurés (protocole §6)
4. **Implémenter** v14.x si la perception par rareté produit encore des erreurs de ciblage

---

*Log JSON : `LuCY/logs/lucy_L055_v135_kaggle_deploy_20261016T144440Z.json`*  
*CERTIFIED_100=false | unique_human_proven=false | DEBUG=true*
